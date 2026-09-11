from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from investment_agent.api.dependencies import get_db_session
from investment_agent.api.style_packs import resolve_method_documents, resolve_style_pack
from investment_agent.cloud import EventEnvelope
from investment_agent.embeddings import (
    EmbeddingProviderError,
    EmbeddingQuotaExceededError,
)
from investment_agent.method_documents import (
    MAX_METHOD_PANEL_DOCUMENTS,
    combined_method_context,
    combined_method_slots,
)
from investment_agent.research.claims import GeneratedClaim
from investment_agent.research.workflow import LocalResearchWorkflow
from investment_agent.research.web import WebResearchError, WebResearchWorkflow
from investment_agent.repositories import (
    AgentRunRepository,
    ClaimCreate,
    DocumentRepository,
)
from investment_agent.search import ExaSearchProvider
from investment_agent.style_packs import GENERAL_RESEARCH_STYLE_PACK

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

_MODEL_FAILURE_EVENT_CODES = {
    "provider_timeout",
    "provider_authentication_failed",
    "provider_quota_exhausted",
    "model_provider_error",
}


class ChatQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    as_of_date: date | None = None
    document_id: int | None = Field(default=None, gt=0)
    sensitivity: str = Field(default="internal", min_length=1)
    selection_mode: str = Field(default="auto", pattern="^(auto|manual)$")
    requested_model: str | None = Field(default=None, min_length=1)
    evidence_scope: Literal["indexed", "web", "hybrid"] = "indexed"
    style_pack_id: str | None = Field(default=None, min_length=3, max_length=48)
    method_document_id: int | None = Field(default=None, gt=0)
    method_document_ids: list[int] = Field(
        default_factory=list,
        max_length=MAX_METHOD_PANEL_DOCUMENTS,
    )


class ChatModelOption(BaseModel):
    id: str
    label: str
    deployment: str
    available: bool
    unavailable_reason: str | None = None
    input_cost_per_million: float
    output_cost_per_million: float
    supports_market_search: bool = False
    supports_independent_web_search: bool = False


class ChatSource(BaseModel):
    evidence_id: int
    display_name: str
    source_uri: str
    source_type: str
    title: str
    page_or_section: str | None = None


class ChatWebSource(BaseModel):
    citation_id: str
    evidence_key: str
    title: str
    url: str
    author: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime
    excerpt: str


class ChatCriticFinding(BaseModel):
    code: str
    severity: str
    message: str


class ChatCriticReview(BaseModel):
    status: str
    findings: list[ChatCriticFinding]


class ChatClaim(BaseModel):
    claim_id: int | None
    claim_key: str
    claim_text: str
    citation_ids: list[str]
    evidence_ids: list[int]
    relations: dict[str, str]
    confidence: float
    source_names: list[str]
    verification_status: str
    verification_findings: list[str]
    verification_term_overlap: float


class ChatQueryResponse(BaseModel):
    run_id: int
    run_key: str
    status: str
    answer: str
    evidence_ids: list[int]
    sources: list[ChatSource]
    claims: list[ChatClaim]
    critic: ChatCriticReview
    iterations: int
    total_tokens: int
    total_estimated_cost_usd: float
    selected_model: str | None
    deployment: str
    prompt_tokens: int
    completion_tokens: int
    provider_tokens: int
    execution_outcome: str
    answer_generated: bool
    execution_message: str
    evidence_scope: str
    grounding_method: str
    web_sources: list[ChatWebSource]
    style_pack_id: str
    style_pack_name: str
    method_document_id: int | None
    method_document_name: str | None
    method_document_ids: list[int]
    method_document_names: list[str]
    search: dict[str, Any]
    search_provider: str | None
    search_calls: int
    search_estimated_cost_usd: float
    answer_model_estimated_cost_usd: float
    error_code: str | None = None


@router.get("/models", response_model=list[ChatModelOption])
def list_chat_models(http_request: Request) -> list[ChatModelOption]:
    settings = http_request.app.state.settings
    exa_available = settings.enable_cloud_services and settings.exa_api_key is not None
    gemini_available = (
        settings.enable_cloud_services and settings.gemini_api_key is not None
    )
    deepseek_available = (
        settings.enable_cloud_services and settings.deepseek_api_key is not None
    )
    kimi_available = (
        settings.enable_cloud_services and settings.kimi_api_key is not None
    )
    return [
        ChatModelOption(
            id="local/deterministic-mock-researcher",
            label="Local evidence extract · no generative AI",
            deployment="local",
            available=True,
            input_cost_per_million=0.0,
            output_cost_per_million=0.0,
            supports_market_search=False,
            supports_independent_web_search=False,
        ),
        ChatModelOption(
            id=f"google/{settings.gemini_model}",
            label=f"Gemini · {settings.gemini_model}",
            deployment="cloud",
            available=gemini_available,
            unavailable_reason=(
                None
                if gemini_available
                else "Cloud services and a Gemini API key must be enabled."
            ),
            input_cost_per_million=settings.gemini_input_cost_per_million,
            output_cost_per_million=settings.gemini_output_cost_per_million,
            supports_market_search=gemini_available and exa_available,
            supports_independent_web_search=gemini_available and exa_available,
        ),
        ChatModelOption(
            id=f"deepseek/{settings.deepseek_model}",
            label=f"DeepSeek · {settings.deepseek_model}",
            deployment="cloud",
            available=deepseek_available,
            unavailable_reason=(
                None
                if deepseek_available
                else "Cloud services and a DeepSeek API key must be enabled."
            ),
            input_cost_per_million=settings.deepseek_input_cost_per_million,
            output_cost_per_million=settings.deepseek_output_cost_per_million,
            supports_market_search=deepseek_available and exa_available,
            supports_independent_web_search=deepseek_available and exa_available,
        ),
        ChatModelOption(
            id=f"moonshot/{settings.kimi_model}",
            label=f"Kimi · {settings.kimi_model}",
            deployment="cloud",
            available=kimi_available,
            unavailable_reason=(
                None
                if kimi_available
                else "Cloud services and a Kimi API key must be enabled."
            ),
            input_cost_per_million=settings.kimi_input_cost_per_million,
            output_cost_per_million=settings.kimi_output_cost_per_million,
            supports_market_search=kimi_available and exa_available,
            supports_independent_web_search=kimi_available and exa_available,
        ),
    ]


@router.post("/query", response_model=ChatQueryResponse)
def query_chat(
    request: ChatQueryRequest,
    http_request: Request,
    session: Session = Depends(get_db_session),
) -> ChatQueryResponse:
    documents = DocumentRepository(session).list_documents()
    if request.evidence_scope in {"indexed", "hybrid"} and not documents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "No research sources are indexed. Upload at least one Markdown, TXT, "
                "PDF, or CSV file before asking a source-backed question."
            ),
        )
    if request.document_id is not None and not any(
        document.id == request.document_id for document in documents
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected research source no longer exists. Refresh the source list.",
        )
    # Research frameworks are optional for every evidence scope. When omitted, use
    # the explicit neutral pack instead of normalize_style_pack_id(None), which would
    # silently impose the strategic-index investment style.
    style_pack = (
        GENERAL_RESEARCH_STYLE_PACK
        if request.style_pack_id is None
        else resolve_style_pack(session, request.style_pack_id)
    )
    requested_method_ids = list(request.method_document_ids)
    if not requested_method_ids and request.method_document_id is not None:
        requested_method_ids = [request.method_document_id]
    method_documents = resolve_method_documents(session, requested_method_ids)
    if request.evidence_scope in {"web", "hybrid"}:
        return _query_web_research(
            request,
            http_request=http_request,
            session=session,
            style_pack=style_pack,
            method_documents=method_documents,
        )
    try:
        workflow_result = LocalResearchWorkflow(
            session,
            settings=http_request.app.state.settings,
        ).run(
            query=request.query,
            sensitivity=request.sensitivity,
            as_of_date=request.as_of_date,
            document_id=request.document_id,
            selection_mode=request.selection_mode,
            requested_model=request.requested_model,
            style_context=combined_method_context(style_pack, method_documents),
            method_slots=combined_method_slots(style_pack, method_documents),
        )
    except EmbeddingQuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    result = workflow_result.agent_result
    run_repository = AgentRunRepository(session)
    run_record = run_repository.get_run(result.run_id)
    if run_record is not None:
        run_repository.update_run(
            run_record.id,
            status=run_record.status,
            total_tokens=run_record.total_tokens,
            total_estimated_cost_usd=float(run_record.total_estimated_cost_usd),
            metadata={
                **(run_record.metadata_json or {}),
                "evidence_scope": "indexed",
                "grounding_method": "Argus indexed evidence retrieval",
                "style_pack_id": style_pack.id,
                "style_pack_name": style_pack.name,
                "style_pack": style_pack.model_dump(mode="json"),
                "method_documents": [
                    document.model_dump(mode="json") for document in method_documents
                ],
            },
        )
    model_calls = run_repository.list_model_calls(run_id=result.run_id)
    cloud_calls = [call for call in model_calls if call.deployment == "cloud"]
    billed_calls = cloud_calls or model_calls
    prompt_tokens = sum(call.prompt_tokens for call in billed_calls)
    completion_tokens = sum(call.completion_tokens for call in billed_calls)
    provider_tokens = sum(
        call.prompt_tokens + call.completion_tokens for call in cloud_calls
    )
    deployment = (
        "cloud" if any(call.deployment == "cloud" for call in model_calls) else "local"
    )
    cloud_requested = bool(
        run_record is not None
        and run_record.selected_model
        and not run_record.selected_model.startswith("local/")
    )
    if result.status == "failed":
        execution_outcome = "cloud_provider_failed"
        execution_message = (
            "The selected external model failed. Argus did not switch providers; "
            "the bounded failure category is available in Runs and the Kafka audit view."
        )
    elif cloud_requested and deployment == "local" and not result.sources:
        execution_outcome = "cloud_skipped_no_evidence"
        execution_message = (
            "The external model was selected, but Argus found no sufficiently relevant "
            "passage in the indexed source scope, so no question or excerpt was sent "
            "to the provider and no provider API cost was incurred."
        )
    elif deployment == "cloud" and not result.sources:
        execution_outcome = "cloud_declined_unsupported"
        execution_message = (
            "The selected external model was called and provider tokens were billed, "
            "but it declined to answer because the retrieved passages did not directly "
            "support the question. Choose a more relevant source or revise the question."
        )
    elif deployment == "cloud":
        execution_outcome = "cloud_completed"
        execution_message = (
            "The selected external model generated this source-backed answer."
        )
    else:
        execution_outcome = "local_completed"
        execution_message = "The local evidence extractor generated this answer without calling a paid model API."
    answer_generated = bool(result.sources) and execution_outcome in {
        "cloud_completed",
        "local_completed",
    }
    if (
        result.status == "failed"
        and result.error_code is not None
        and _is_answer_model_failure_code(result.error_code)
        and request.requested_model is not None
    ):
        _publish_sanitized_model_failure_event(
            http_request=http_request,
            requested_model=request.requested_model,
            run_id=result.run_id,
            error_code=result.error_code,
            total_tokens=result.total_tokens,
            total_estimated_cost_usd=result.total_estimated_cost_usd,
        )
    elif result.status == "complete":
        http_request.app.state.event_publisher.publish(
            EventEnvelope(
                event_type="agent.run.completed.v1",
                aggregate_id=str(result.run_id),
                payload={
                    "run_id": result.run_id,
                    "status": result.status,
                    "total_tokens": result.total_tokens,
                    "total_estimated_cost_usd": result.total_estimated_cost_usd,
                    "execution_outcome": execution_outcome,
                    "answer_generated": answer_generated,
                },
            )
        )
    critic_review = workflow_result.critic
    claim_records = [
        (
            run_repository.record_claim(
                ClaimCreate(
                    run_id=result.run_id,
                    claim_text=claim.claim_text,
                    evidence_ids=list(claim.evidence_ids),
                    relations=claim.relations,
                    confidence=claim.confidence,
                )
            ),
            claim,
        )
        for claim in workflow_result.claims
    ]

    return ChatQueryResponse(
        run_id=result.run_id,
        run_key=result.run_key,
        status=result.status,
        answer=result.answer,
        evidence_ids=list(result.evidence_ids),
        sources=[
            ChatSource(
                evidence_id=source.evidence_id,
                display_name=source.display_name,
                source_uri=source.source_uri,
                source_type=source.source_type,
                title=source.title,
                page_or_section=source.page_or_section,
            )
            for source in result.sources
        ],
        claims=[
            ChatClaim(
                claim_id=record.id,
                claim_key=claim.claim_key,
                claim_text=claim.claim_text,
                citation_ids=list(claim.citation_ids),
                evidence_ids=list(claim.evidence_ids),
                relations=claim.relations,
                confidence=claim.confidence,
                source_names=list(claim.source_names),
                verification_status=claim.verification.status,
                verification_findings=list(claim.verification.findings),
                verification_term_overlap=claim.verification.term_overlap,
            )
            for record, claim in claim_records
        ],
        critic=ChatCriticReview(
            status=critic_review.status,
            findings=[
                ChatCriticFinding(
                    code=finding.code,
                    severity=finding.severity,
                    message=finding.message,
                )
                for finding in critic_review.findings
            ],
        ),
        iterations=result.iterations,
        total_tokens=result.total_tokens,
        total_estimated_cost_usd=result.total_estimated_cost_usd,
        selected_model=run_record.selected_model if run_record is not None else None,
        deployment=deployment,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        provider_tokens=provider_tokens,
        execution_outcome=execution_outcome,
        answer_generated=answer_generated,
        execution_message=execution_message,
        evidence_scope="indexed",
        grounding_method="Argus indexed evidence retrieval",
        web_sources=[],
        style_pack_id=style_pack.id,
        style_pack_name=style_pack.name,
        method_document_id=method_documents[0].id if method_documents else None,
        method_document_name=method_documents[0].name if method_documents else None,
        method_document_ids=[document.id for document in method_documents],
        method_document_names=[document.name for document in method_documents],
        search=(
            run_record.metadata_json.get("search", {})
            if run_record is not None and isinstance(run_record.metadata_json, dict)
            else {}
        ),
        search_provider=None,
        search_calls=0,
        search_estimated_cost_usd=0.0,
        answer_model_estimated_cost_usd=result.total_estimated_cost_usd,
        error_code=result.error_code,
    )


def _query_web_research(
    request: ChatQueryRequest,
    *,
    http_request: Request,
    session: Session,
    style_pack,
    method_documents,
) -> ChatQueryResponse:
    if request.sensitivity != "public":
        raise HTTPException(
            status_code=422,
            detail="Web research sends the question to an external provider; use public sensitivity.",
        )
    if request.selection_mode != "manual" or request.requested_model is None:
        raise HTTPException(
            status_code=422,
            detail="Web research requires an explicitly selected answer model.",
        )
    settings = http_request.app.state.settings
    search_provider = _exa_search_provider(settings)
    answer_provider = _independent_search_answer_provider(
        session=session,
        settings=settings,
        requested_model=request.requested_model,
    )
    try:
        result = WebResearchWorkflow(session).run(
            query=request.query,
            search_provider=search_provider,
            answer_provider=answer_provider,
            requested_model=request.requested_model,
            evidence_scope=request.evidence_scope,
            style_pack=style_pack,
            method_documents=method_documents,
            as_of_date=request.as_of_date,
            document_id=request.document_id,
            max_search_calls=settings.web_search_max_calls,
        )
    except WebResearchError as exc:
        # Failed external calls are still audit and cost events. Persist the failed
        # Run before FastAPI propagates the error and the request session rolls back.
        session.commit()
        _publish_model_failure_event(
            http_request=http_request,
            requested_model=request.requested_model,
            error=exc,
        )
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": str(exc),
                "run_id": exc.run_id,
            },
        ) from exc

    execution_outcome = (
        f"{request.evidence_scope}_evidence_completed"
        if result.prompt_tokens + result.completion_tokens > 0
        else "web_skipped_no_supported_evidence"
    )
    answer_generated = result.prompt_tokens + result.completion_tokens > 0
    http_request.app.state.event_publisher.publish(
        EventEnvelope(
            event_type="agent.run.completed.v1",
            aggregate_id=str(result.run_id),
            payload={
                "run_id": result.run_id,
                "status": result.status,
                "total_tokens": result.prompt_tokens + result.completion_tokens,
                "total_estimated_cost_usd": result.total_estimated_cost_usd,
                "execution_outcome": execution_outcome,
                "answer_generated": answer_generated,
            },
        )
    )
    local_sources = [
        ChatSource(
            evidence_id=source.evidence_id,
            display_name=source.display_name,
            source_uri=source.source_uri,
            source_type=source.source_type,
            title=source.title,
            page_or_section=source.page_or_section,
        )
        for source in result.local_sources
    ]
    return ChatQueryResponse(
        run_id=result.run_id,
        run_key=result.run_key,
        status="complete",
        answer=result.answer,
        evidence_ids=[source.evidence_id for source in result.local_sources],
        sources=local_sources,
        claims=[
            ChatClaim(
                claim_id=None,
                claim_key=claim.claim_key,
                claim_text=claim.claim_text,
                citation_ids=list(claim.citation_ids),
                evidence_ids=list(claim.evidence_ids),
                relations=claim.relations,
                confidence=claim.confidence,
                source_names=list(claim.source_names),
                verification_status=claim.verification.status,
                verification_findings=list(claim.verification.findings),
                verification_term_overlap=claim.verification.term_overlap,
            )
            for claim in result.claims
        ],
        critic=_web_critic(result.citation_status, claims=result.claims),
        iterations=result.iterations,
        total_tokens=result.prompt_tokens + result.completion_tokens,
        total_estimated_cost_usd=result.total_estimated_cost_usd,
        selected_model=request.requested_model,
        deployment="cloud",
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        provider_tokens=result.prompt_tokens + result.completion_tokens,
        execution_outcome=execution_outcome,
        answer_generated=answer_generated,
        execution_message=_web_execution_message(result.citation_status),
        evidence_scope=request.evidence_scope,
        grounding_method=result.grounding_method,
        web_sources=[
            ChatWebSource(
                citation_id=f"W{index}",
                evidence_key=source.evidence_key,
                title=source.title,
                url=source.url,
                author=source.author,
                published_at=source.published_at,
                retrieved_at=source.retrieved_at,
                excerpt=source.passage[:1_200],
            )
            for index, source in enumerate(result.web_sources, start=1)
        ],
        style_pack_id=style_pack.id,
        style_pack_name=style_pack.name,
        method_document_id=method_documents[0].id if method_documents else None,
        method_document_name=method_documents[0].name if method_documents else None,
        method_document_ids=[document.id for document in method_documents],
        method_document_names=[document.name for document in method_documents],
        search=result.search,
        search_provider="exa",
        search_calls=int(result.search.get("search_calls", 0)),
        search_estimated_cost_usd=result.search_estimated_cost_usd,
        answer_model_estimated_cost_usd=result.model_estimated_cost_usd,
    )


def _publish_model_failure_event(
    *,
    http_request: Request,
    requested_model: str,
    error: WebResearchError,
) -> None:
    """Publish a bounded failure notice without masking the provider error."""

    if error.run_id is None or error.code.startswith("web_search_"):
        return
    _publish_sanitized_model_failure_event(
        http_request=http_request,
        requested_model=requested_model,
        run_id=error.run_id,
        error_code=error.code,
        total_tokens=error.prompt_tokens + error.completion_tokens,
        total_estimated_cost_usd=error.estimated_cost_usd,
    )


def _publish_sanitized_model_failure_event(
    *,
    http_request: Request,
    requested_model: str,
    run_id: int,
    error_code: str,
    total_tokens: int,
    total_estimated_cost_usd: float,
) -> None:
    """Publish one safe model-failure contract for indexed and web research."""

    provider, separator, model = requested_model.partition("/")
    if not separator:
        provider = "unknown"
        model = requested_model
    event = EventEnvelope(
        event_type="agent.run.failed.v1",
        aggregate_id=str(run_id),
        payload={
            "run_id": run_id,
            "status": "failed",
            "error_code": _normalized_model_failure_code(error_code),
            "failure_stage": "answer_model",
            "provider": provider,
            "model": model,
            "total_tokens": total_tokens,
            "total_estimated_cost_usd": total_estimated_cost_usd,
        },
    )
    try:
        http_request.app.state.event_publisher.publish(event)
    except Exception:
        # PostgreSQL Runs remain the source of truth. A Kafka outage must not replace
        # the original provider failure returned to the user.
        logger.exception(
            "Failed to publish sanitized model-failure event for Run %s",
            run_id,
        )


def _is_answer_model_failure_code(code: str) -> bool:
    return code in {
        *_MODEL_FAILURE_EVENT_CODES,
        "answer_model_provider_error",
        "provider_auth_expired",
        "provider_auth_required",
        "provider_balance_exhausted",
        "provider_daily_limit_exhausted",
        "provider_overloaded",
        "provider_rate_limited",
    }


def _normalized_model_failure_code(code: str) -> str:
    if code in _MODEL_FAILURE_EVENT_CODES:
        return code
    if code in {
        "provider_balance_exhausted",
        "provider_rate_limited",
        "provider_daily_limit_exhausted",
    }:
        return "provider_quota_exhausted"
    if code in {"provider_auth_required", "provider_auth_expired"}:
        return "provider_authentication_failed"
    return "model_provider_error"


def _exa_search_provider(settings) -> ExaSearchProvider:
    if not settings.enable_cloud_services or not settings.exa_api_key:
        raise HTTPException(
            status_code=422,
            detail=(
                "Independent web research requires cloud services and "
                "ARGUS_EXA_API_KEY."
            ),
        )
    return ExaSearchProvider(
        api_key=settings.exa_api_key,
        base_url=settings.exa_base_url,
        search_type=settings.exa_search_type,
        timeout_ms=settings.exa_timeout_ms,
        max_results=settings.exa_max_results,
        highlight_max_characters=settings.exa_highlight_max_characters,
        search_cost_per_request=settings.exa_search_cost_per_request,
    )


def _independent_search_answer_provider(
    *,
    session: Session,
    settings,
    requested_model: str,
):
    configured = {
        f"google/{settings.gemini_model}": settings.gemini_api_key,
        f"deepseek/{settings.deepseek_model}": settings.deepseek_api_key,
        f"moonshot/{settings.kimi_model}": settings.kimi_api_key,
    }
    if (
        not settings.enable_cloud_services
        or requested_model not in configured
        or not configured[requested_model]
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Choose one configured Gemini, DeepSeek, or Kimi answer model. "
                "Exa performs search independently, and Argus will not switch models."
            ),
        )
    return LocalResearchWorkflow(session, settings=settings).model_provider(
        sensitivity="public",
        selection_mode="manual",
        requested_model=requested_model,
    )


def _web_critic(
    citation_status: str,
    *,
    claims: tuple[GeneratedClaim, ...],
) -> ChatCriticReview:
    unsupported = [
        claim for claim in claims if claim.verification.status != "supported"
    ]
    if citation_status == "validated" and not unsupported:
        return ChatCriticReview(status="web_evidence_validated", findings=[])
    if citation_status == "validated":
        return ChatCriticReview(
            status="warning",
            findings=[
                ChatCriticFinding(
                    code="claim_citation_not_supported",
                    severity="warning",
                    message=(
                        f"{claim.claim_key} is {claim.verification.status}: "
                        f"{', '.join(claim.verification.findings)}."
                    ),
                )
                for claim in unsupported
            ],
        )
    if citation_status == "not_applicable":
        code = "web_evidence_insufficient"
        message = (
            "Exa search completed, but the Evidence Gate did not accept enough direct "
            "support. Argus stopped before calling the selected answer model."
        )
    else:
        code = f"answer_citations_{citation_status}"
        message = (
            "The answer model did not preserve the supplied Argus citation IDs. "
            "The answer is shown for review but cannot generate a report."
        )
    return ChatCriticReview(
        status="warning",
        findings=[ChatCriticFinding(code=code, severity="warning", message=message)],
    )


def _web_execution_message(citation_status: str) -> str:
    if citation_status == "validated":
        return (
            "Exa retrieved direct-URL evidence, Argus accepted it through the Evidence "
            "Gate, and the selected answer model cited the supplied evidence IDs."
        )
    if citation_status == "not_applicable":
        return (
            "Exa search ran, but evidence remained insufficient after the bounded "
            "search loop; the selected answer model was not called."
        )
    return (
        "Exa and the selected answer model ran, but citation validation failed; "
        "Argus will not allow report generation from this answer."
    )
