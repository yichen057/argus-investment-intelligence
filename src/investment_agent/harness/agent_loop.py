from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from time import perf_counter
from uuid import uuid4

from sqlalchemy.orm import Session

from investment_agent.harness.budget import Budget, BudgetExceeded
from investment_agent.harness.tools import ToolRegistry
from investment_agent.harness.types import ToolResult
from investment_agent.providers.types import (
    Deployment,
    ModelProfile,
    ModelProvider,
    ModelRequest,
    ModelResponse,
)
from investment_agent.repositories import (
    AgentRunCreate,
    AgentRunRepository,
    ModelCallCreate,
    ToolCallRecordCreate,
)
from investment_agent.routing import (
    Capability,
    RouteRequest,
    Router,
    RoutingError,
    Sensitivity,
)
from investment_agent.sources import source_display_name


@dataclass(frozen=True)
class AgentEvidenceSource:
    evidence_id: int
    display_name: str
    source_uri: str
    source_type: str
    title: str
    excerpt: str
    page_or_section: str | None = None


@dataclass(frozen=True)
class AgentLoopResult:
    run_id: int
    run_key: str
    status: str
    answer: str
    evidence_ids: tuple[int, ...]
    sources: tuple[AgentEvidenceSource, ...]
    iterations: int
    total_tokens: int
    total_estimated_cost_usd: float
    error_code: str | None = None


class AgentLoop:
    def __init__(
        self,
        session: Session,
        model_provider: ModelProvider,
        tool_registry: ToolRegistry,
        *,
        budget: Budget | None = None,
        max_iterations: int = 4,
        model_profile: ModelProfile | None = None,
        router: Router | None = None,
        required_capabilities: frozenset[Capability] | None = None,
        minimum_quality: float = 0.0,
    ) -> None:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        self._repository = AgentRunRepository(session)
        self._model_provider = model_provider
        self._model_profile = model_profile or _default_profile_for_provider(
            model_provider
        )
        self._router = router or Router([self._model_profile])
        self._required_capabilities = required_capabilities or frozenset(
            {Capability.TOOL_CALLING, Capability.STRUCTURED_OUTPUT}
        )
        self._minimum_quality = minimum_quality
        self._tool_registry = tool_registry
        self._budget = budget or Budget(max_tokens=20_000, max_usd=1.0)
        self._max_iterations = max_iterations

    def _route_model(
        self,
        *,
        sensitivity: str,
        redacted: bool,
        selection_mode: str,
        requested_model: str | None,
    ) -> _RuntimeRoute:
        if selection_mode not in {"auto", "manual"}:
            return _RuntimeRoute(
                profile=None,
                reason=f"Unsupported model selection mode: {selection_mode}",
                error_code="invalid_model_selection",
            )
        if selection_mode == "manual" and not requested_model:
            return _RuntimeRoute(
                profile=None,
                reason="Manual model selection requires requested_model",
                error_code="invalid_model_selection",
            )
        if selection_mode == "manual" and requested_model != self._model_profile.name:
            return _RuntimeRoute(
                profile=None,
                reason=(
                    f"Requested model {requested_model} is unavailable or not allowed "
                    "for this request"
                ),
                error_code="model_not_available",
            )
        try:
            route_request = RouteRequest(
                sensitivity=Sensitivity(sensitivity),
                required_capabilities=self._required_capabilities,
                redacted=redacted,
                minimum_quality=self._minimum_quality,
            )
            selected = self._router.route(route_request)
        except ValueError:
            return _RuntimeRoute(
                profile=None,
                reason=f"Unsupported sensitivity: {sensitivity}",
                error_code="invalid_sensitivity",
            )
        except RoutingError as exc:
            return _RuntimeRoute(
                profile=None,
                reason=str(exc),
                error_code="routing_failed",
            )

        if selected.name != self._model_profile.name:
            return _RuntimeRoute(
                profile=None,
                reason=(
                    f"Router selected {selected.name}, but this runtime only has "
                    f"{self._model_profile.name}"
                ),
                error_code="routing_failed",
            )

        capabilities = ", ".join(
            sorted(capability.value for capability in self._required_capabilities)
        )
        selection_prefix = "Auto selected" if selection_mode == "auto" else "Manually selected"
        reason = (
            f"{selection_prefix} {selected.name}: "
            f"deployment={selected.deployment.value}, "
            f"sensitivity={route_request.sensitivity.value}, "
            f"required_capabilities={capabilities}"
        )
        return _RuntimeRoute(profile=selected, reason=reason)

    def run(
        self,
        *,
        objective: str,
        role: str = "research",
        sensitivity: str = "internal",
        as_of_date: date | None = None,
        document_id: int | None = None,
        selection_mode: str = "auto",
        requested_model: str | None = None,
        redacted: bool = False,
        style_context: str | None = None,
    ) -> AgentLoopResult:
        if not objective.strip():
            raise ValueError("objective cannot be empty")

        run_key = f"run-{uuid4().hex}"
        route = self._route_model(
            sensitivity=sensitivity,
            redacted=redacted,
            selection_mode=selection_mode,
            requested_model=requested_model,
        )
        if route.error_code is not None:
            run = self._repository.create_run(
                AgentRunCreate(
                    run_key=run_key,
                    role=role,
                    objective=objective,
                    status="routing_failed",
                    sensitivity=sensitivity,
                    as_of_date=as_of_date,
                    selection_mode=selection_mode,
                    selected_model=None,
                    selection_reason=route.reason,
                    metadata={
                        "error_code": route.error_code,
                        "required_capabilities": sorted(
                            capability.value
                            for capability in self._required_capabilities
                        ),
                    },
                )
            )
            return AgentLoopResult(
                run_id=run.id,
                run_key=run.run_key,
                status="routing_failed",
                answer="",
                evidence_ids=(),
                sources=(),
                iterations=0,
                total_tokens=0,
                total_estimated_cost_usd=0.0,
                error_code=route.error_code,
            )

        selected_profile = route.profile or self._model_profile
        selected_model = selected_profile.name
        run = self._repository.create_run(
            AgentRunCreate(
                run_key=run_key,
                role=role,
                objective=objective,
                status="running",
                sensitivity=sensitivity,
                as_of_date=as_of_date,
                selection_mode=selection_mode,
                selected_model=selected_model,
                selection_reason=route.reason,
                metadata={
                    "max_iterations": self._max_iterations,
                    "required_capabilities": sorted(
                        capability.value for capability in self._required_capabilities
                    ),
                    "redacted": redacted,
                    "document_id": document_id,
                },
            )
        )

        tool_results: list[ToolResult] = []
        total_tokens = 0
        total_cost = 0.0

        for iteration in range(self._max_iterations):
            request = ModelRequest(
                objective=objective,
                role=role,
                sensitivity=sensitivity,
                as_of_date=as_of_date,
                document_id=document_id,
                tool_results=tuple(tool_results),
                iteration=iteration,
                style_context=style_context,
            )
            started_at = perf_counter()
            response = self._model_provider.generate(request)
            model_latency_ms = _elapsed_ms(started_at)
            call_tokens = response.prompt_tokens + response.completion_tokens
            self._repository.record_model_call(
                ModelCallCreate(
                    run_id=run.id,
                    provider=response.provider,
                    model=response.model,
                    deployment=response.deployment.value,
                    serving_engine=response.serving_engine,
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    estimated_cost_usd=response.estimated_cost_usd,
                    latency_ms=model_latency_ms,
                    success=response.success,
                    input_cost_per_million_usd=response.input_cost_per_million_usd,
                    output_cost_per_million_usd=response.output_cost_per_million_usd,
                )
            )

            try:
                self._budget.charge(call_tokens, response.estimated_cost_usd)
            except BudgetExceeded as exc:
                metadata = {
                    "error_code": "budget_exceeded",
                    "message": str(exc),
                    "iterations": iteration + 1,
                }
                self._repository.update_run(
                    run.id,
                    status="budget_exceeded",
                    total_tokens=total_tokens,
                    total_estimated_cost_usd=total_cost,
                    metadata=metadata,
                )
                return AgentLoopResult(
                    run_id=run.id,
                    run_key=run.run_key,
                    status="budget_exceeded",
                    answer="",
                    evidence_ids=(),
                    sources=(),
                    iterations=iteration + 1,
                    total_tokens=total_tokens,
                    total_estimated_cost_usd=total_cost,
                    error_code="budget_exceeded",
                )

            total_tokens += call_tokens
            total_cost += response.estimated_cost_usd

            if not response.success:
                error_code = response.error_code or "model_provider_error"
                self._repository.update_run(
                    run.id,
                    status="failed",
                    total_tokens=total_tokens,
                    total_estimated_cost_usd=total_cost,
                    metadata={
                        "error_code": error_code,
                        "iterations": iteration + 1,
                    },
                )
                return AgentLoopResult(
                    run_id=run.id,
                    run_key=run.run_key,
                    status="failed",
                    answer="",
                    evidence_ids=(),
                    sources=(),
                    iterations=iteration + 1,
                    total_tokens=total_tokens,
                    total_estimated_cost_usd=total_cost,
                    error_code=error_code,
                )

            if response.tool_call is not None:
                tool_started_at = perf_counter()
                tool_result = self._tool_registry.dispatch(response.tool_call)
                self._repository.record_tool_call(
                    ToolCallRecordCreate(
                        run_id=run.id,
                        call_id=response.tool_call.call_id,
                        tool_name=response.tool_call.name,
                        status=tool_result.status,
                        arguments=response.tool_call.arguments,
                        output=_compact_tool_output_for_storage(tool_result.output),
                        error_code=tool_result.error_code,
                        latency_ms=_elapsed_ms(tool_started_at),
                    )
                )
                search_metadata = tool_result.output.get("search")
                result_rows = tool_result.output.get("results")
                if isinstance(search_metadata, dict) and isinstance(result_rows, list):
                    self._repository.record_search_trace(
                        run_id=run.id,
                        search=search_metadata,
                        result_rows=[
                            row for row in result_rows if isinstance(row, dict)
                        ],
                    )
                tool_results.append(tool_result)
                if tool_result.status != "ok":
                    error_code = tool_result.error_code or "tool_error"
                    self._repository.update_run(
                        run.id,
                        status="failed",
                        total_tokens=total_tokens,
                        total_estimated_cost_usd=total_cost,
                        metadata={
                            "error_code": error_code,
                            "iterations": iteration + 1,
                        },
                    )
                    return AgentLoopResult(
                        run_id=run.id,
                        run_key=run.run_key,
                        status="failed",
                        answer="",
                        evidence_ids=(),
                        sources=(),
                        iterations=iteration + 1,
                        total_tokens=total_tokens,
                        total_estimated_cost_usd=total_cost,
                        error_code=error_code,
                    )
                continue

            evidence_ids = _evidence_ids(tool_results)
            sources = _evidence_sources(tool_results)
            if _is_no_evidence_answer(response.content):
                evidence_ids = ()
                sources = ()
            search_metadata = dict(_latest_search_metadata(tool_results))
            search_metadata["answer_evidence_accepted"] = bool(sources)
            gate_metadata = search_metadata.get("evidence_gate")
            if not isinstance(gate_metadata, dict):
                # Compatibility for historical/custom tools that do not yet emit
                # the unified Evidence Gate contract.
                search_metadata["accepted_evidence_ids"] = list(evidence_ids)
            self._repository.mark_answer_evidence(
                run_id=run.id,
                evidence_ids=evidence_ids,
            )
            self._repository.update_run(
                run.id,
                status="complete",
                total_tokens=total_tokens,
                total_estimated_cost_usd=total_cost,
                selection_reason=_completed_selection_reason(
                    route.reason,
                    response=response,
                ),
                metadata={
                    "iterations": iteration + 1,
                    "evidence_ids": list(evidence_ids),
                    "answer": response.content,
                    "answer_sources": [
                        {
                            "evidence_id": source.evidence_id,
                            "display_name": source.display_name,
                            "source_uri": source.source_uri,
                            "source_type": source.source_type,
                            "title": source.title,
                            "excerpt": source.excerpt,
                            "page_or_section": source.page_or_section,
                        }
                        for source in sources
                    ],
                    "search": search_metadata,
                },
            )
            return AgentLoopResult(
                run_id=run.id,
                run_key=run.run_key,
                status="complete",
                answer=response.content,
                evidence_ids=evidence_ids,
                sources=sources,
                iterations=iteration + 1,
                total_tokens=total_tokens,
                total_estimated_cost_usd=total_cost,
            )

        self._repository.update_run(
            run.id,
            status="failed",
            total_tokens=total_tokens,
            total_estimated_cost_usd=total_cost,
            metadata={
                "error_code": "max_iterations_exceeded",
                "iterations": self._max_iterations,
            },
        )
        return AgentLoopResult(
            run_id=run.id,
            run_key=run.run_key,
            status="failed",
            answer="",
            evidence_ids=_evidence_ids(tool_results),
            sources=_evidence_sources(tool_results),
            iterations=self._max_iterations,
            total_tokens=total_tokens,
            total_estimated_cost_usd=total_cost,
            error_code="max_iterations_exceeded",
        )


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


def _evidence_ids(
    tool_results: list[ToolResult],
    *,
    limit: int | None = None,
) -> tuple[int, ...]:
    evidence_ids: list[int] = []
    for tool_result in tool_results:
        for result in tool_result.output.get("results", []):
            evidence_id = result.get("evidence_item_id")
            if isinstance(evidence_id, int) and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
                if limit is not None and len(evidence_ids) >= limit:
                    return tuple(evidence_ids)
    return tuple(evidence_ids)


def _evidence_sources(
    tool_results: list[ToolResult],
    *,
    limit: int | None = None,
) -> tuple[AgentEvidenceSource, ...]:
    sources: list[AgentEvidenceSource] = []
    seen: set[int] = set()
    for tool_result in tool_results:
        for result in tool_result.output.get("results", []):
            evidence_id = result.get("evidence_item_id")
            source_uri = result.get("source_uri")
            source_type = result.get("source_type")
            title = result.get("title")
            if not isinstance(evidence_id, int) or evidence_id in seen:
                continue
            if not isinstance(source_uri, str) or not isinstance(source_type, str):
                continue
            if not isinstance(title, str):
                title = source_display_name(source_uri)
            page_or_section = result.get("page_or_section")
            # Keep the anchor plus bounded neighbor context so a sentence split at a
            # chunk boundary can be completed without storing the full retrieval window.
            excerpt = _bounded_answer_context(result)
            if not isinstance(excerpt, str):
                excerpt = ""
            sources.append(
                AgentEvidenceSource(
                    evidence_id=evidence_id,
                    display_name=source_display_name(source_uri) or title,
                    source_uri=source_uri,
                    source_type=source_type,
                    title=title,
                    excerpt=excerpt,
                    page_or_section=(
                        page_or_section if isinstance(page_or_section, str) else None
                    ),
                )
            )
            seen.add(evidence_id)
            if limit is not None and len(sources) >= limit:
                return tuple(sources)
    return tuple(sources)


def _bounded_answer_context(result: dict[str, object], *, limit: int = 1800) -> str:
    text = result.get("text")
    anchor = text if isinstance(text, str) else ""
    context = result.get("context")
    if not isinstance(context, str) or not context.strip():
        excerpt = result.get("excerpt")
        return anchor or (excerpt if isinstance(excerpt, str) else "")
    if len(context) <= limit:
        return context
    anchor_index = context.find(anchor) if anchor else -1
    if anchor_index < 0:
        return context[:limit]
    start = max(0, anchor_index - 300)
    end = min(len(context), start + limit)
    start = max(0, end - limit)
    return context[start:end]


def _is_no_evidence_answer(answer: str) -> bool:
    return "could not find relevant local evidence" in answer.lower()


def _latest_search_metadata(tool_results: list[ToolResult]) -> dict[str, object]:
    for tool_result in reversed(tool_results):
        search = tool_result.output.get("search")
        if isinstance(search, dict):
            return search
    return {}


def _compact_tool_output_for_storage(output: dict[str, object]) -> dict[str, object]:
    """Keep the trace useful without duplicating full chunks and neighbor context."""

    compacted = dict(output)
    rows = output.get("results")
    if isinstance(rows, list):
        compacted["results"] = [
            {
                key: value
                for key, value in row.items()
                if key not in {"text", "context", "excerpt"}
            }
            for row in rows
            if isinstance(row, dict)
        ]
    return compacted


def _completed_selection_reason(reason: str, *, response: ModelResponse) -> str:
    if (
        response.provider == "argus"
        and response.model == "evidence-sufficiency-guard"
    ):
        return f"{reason}; cloud call skipped by local evidence-sufficiency guard"
    return reason


@dataclass(frozen=True)
class _RuntimeRoute:
    profile: ModelProfile | None
    reason: str
    error_code: str | None = None


def _default_profile_for_provider(model_provider: ModelProvider) -> ModelProfile:
    allowed_sensitivity = (
        frozenset({"public", "internal", "restricted"})
        if model_provider.deployment is Deployment.LOCAL
        else frozenset({"public", "internal"})
    )
    return ModelProfile(
        name=f"{model_provider.provider_name}/{model_provider.model_name}",
        deployment=model_provider.deployment,
        allowed_sensitivity=allowed_sensitivity,
        capabilities=frozenset(
            {
                Capability.SUMMARIZATION.value,
                Capability.TOOL_CALLING.value,
                Capability.STRUCTURED_OUTPUT.value,
            }
        ),
        quality_score=0.5,
        cost_score=1.0,
        latency_score=0.8,
    )
