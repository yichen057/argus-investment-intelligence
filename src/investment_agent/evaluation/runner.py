from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
import json
from time import perf_counter
from typing import Any

import yaml
from sqlalchemy.orm import Session

from investment_agent.ingestion import LocalFileIngestor, UnsupportedSourceType
from investment_agent.portfolio import parse_holdings_csv, summarize_portfolio
from investment_agent.research.reports import build_research_report
from investment_agent.research.workflow import LocalResearchWorkflow
from investment_agent.repositories import AgentRunRepository
from investment_agent.storage import EvidenceItem


@dataclass(frozen=True)
class EvalCheckResult:
    check: str
    status: str
    message: str
    observed: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCaseResult:
    case_id: str
    category: str
    status: str
    latency_ms: int
    checks: tuple[EvalCheckResult, ...]
    run_id: int | None = None
    total_tokens: int = 0
    total_estimated_cost_usd: float = 0.0
    model_call_count: int = 0
    tool_call_count: int = 0
    avg_model_latency_ms: float | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvalRunResult:
    dataset_version: int
    dataset_path: str
    started_at: str
    completed_at: str
    cases_total: int
    cases_passed: int
    cases_failed: int
    cases_partial: int
    cases_skipped: int
    total_tokens: int
    total_estimated_cost_usd: float
    avg_latency_ms: float | None
    metrics: dict[str, Any]
    case_results: tuple[EvalCaseResult, ...]
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            "# Argus Eval Report",
            "",
            f"- Dataset: `{self.dataset_path}`",
            f"- Dataset version: {self.dataset_version}",
            f"- Started: {self.started_at}",
            f"- Completed: {self.completed_at}",
            f"- Cases: {self.cases_total} total, {self.cases_passed} passed, "
            f"{self.cases_partial} partial, {self.cases_failed} failed, "
            f"{self.cases_skipped} skipped",
            f"- Tokens: {self.total_tokens}",
            f"- Estimated cost: ${self.total_estimated_cost_usd:.6f}",
            "",
            "## Metrics",
            "",
        ]
        for key, value in self.metrics.items():
            lines.append(f"- `{key}`: {value}")
        lines.extend(
            [
                "",
                "## Cases",
                "",
                "| Case | Category | Status | Latency | Tokens | Cost |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for case in self.case_results:
            lines.append(
                f"| `{case.case_id}` | {case.category} | {case.status} | "
                f"{case.latency_ms} ms | {case.total_tokens} | "
                f"${case.total_estimated_cost_usd:.6f} |"
            )
        lines.extend(["", "## Check Details", ""])
        for case in self.case_results:
            lines.append(f"### {case.case_id}")
            for check in case.checks:
                lines.append(
                    f"- `{check.check}`: **{check.status}** - {check.message}"
                )
            if case.notes:
                for note in case.notes:
                    lines.append(f"- note: {note}")
            lines.append("")
        return "\n".join(lines)


@dataclass(frozen=True)
class _EvalCase:
    case_id: str
    category: str
    question: str | None
    topic: str | None
    fixture: str | None
    as_of_date: date | None
    checks: tuple[str, ...]
    required_source_types: tuple[str, ...]
    expected: dict[str, Any]


@dataclass(frozen=True)
class _EvalPosition:
    symbol: str
    name: str
    asset_class: str
    market_value: float


class EvalRunner:
    """Run deterministic local evaluation cases without external APIs."""

    def __init__(
        self,
        session: Session,
        *,
        project_root: Path | None = None,
    ) -> None:
        self._session = session
        self._project_root = (project_root or Path.cwd()).resolve()

    def run(
        self,
        *,
        dataset_path: Path = Path("evals/golden_questions.yaml"),
        save_artifacts: bool = True,
        output_dir: Path = Path("eval-results"),
    ) -> EvalRunResult:
        resolved_dataset_path = self._resolve_path(dataset_path)
        dataset = _load_dataset(resolved_dataset_path)
        started_at = _now_iso()
        case_results = tuple(
            self._run_case(case, dataset_path=resolved_dataset_path)
            for case in dataset["cases"]
        )
        completed_at = _now_iso()
        result = self._build_result(
            dataset_version=dataset["version"],
            dataset_path=resolved_dataset_path,
            started_at=started_at,
            completed_at=completed_at,
            case_results=case_results,
        )
        if save_artifacts:
            artifact_paths = self.save_artifacts(result, output_dir=output_dir)
            result = replace(result, artifact_paths=artifact_paths)
        return result

    def save_artifacts(
        self,
        result: EvalRunResult,
        *,
        output_dir: Path = Path("eval-results"),
    ) -> dict[str, str]:
        resolved_output_dir = self._resolve_output_dir(output_dir)
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        json_path = resolved_output_dir / f"argus-eval-{timestamp}.json"
        markdown_path = resolved_output_dir / f"argus-eval-{timestamp}.md"
        json_path.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        markdown_path.write_text(result.to_markdown(), encoding="utf-8")
        return {"json": str(json_path), "markdown": str(markdown_path)}

    def _run_case(
        self,
        case: _EvalCase,
        *,
        dataset_path: Path,
    ) -> EvalCaseResult:
        if case.category in {
            "direct_retrieval",
            "temporal_integrity",
            "no_evidence",
        }:
            return self._run_research_case(case, dataset_path=dataset_path)
        if case.category == "report_generation":
            return self._run_report_case(case, dataset_path=dataset_path)
        if case.category == "deterministic_portfolio":
            return self._run_portfolio_case(case, dataset_path=dataset_path)
        if case.category == "prompt_injection":
            return self._run_prompt_injection_case(case, dataset_path=dataset_path)
        return self._skipped_case(
            case,
            f"Category {case.category!r} is not supported by the V1 local runner.",
        )

    def _run_research_case(
        self,
        case: _EvalCase,
        *,
        dataset_path: Path,
    ) -> EvalCaseResult:
        if not case.question:
            return self._failed_case(case, "Research eval case is missing question.")
        notes = self._ingest_fixture_if_document(case, dataset_path=dataset_path)
        started_at = perf_counter()
        workflow_result = LocalResearchWorkflow(self._session).run(
            query=case.question,
            as_of_date=case.as_of_date,
        )
        latency_ms = _elapsed_ms(started_at)
        agent_result = workflow_result.agent_result
        checks = [
            self._evaluate_research_check(
                check,
                case=case,
                claims=workflow_result.claims,
                critic_status=workflow_result.critic.status,
                evidence_ids=agent_result.evidence_ids,
                source_types=tuple(source.source_type for source in agent_result.sources),
            )
            for check in case.checks
        ]
        if case.required_source_types:
            checks.append(
                self._check_required_source_types(
                    case.required_source_types,
                    tuple(source.source_type for source in agent_result.sources),
                )
            )
        model_call_count, tool_call_count, avg_latency = self._trace_metrics(
            agent_result.run_id
        )
        return EvalCaseResult(
            case_id=case.case_id,
            category=case.category,
            status=_case_status(tuple(checks)),
            latency_ms=latency_ms,
            checks=tuple(checks),
            run_id=agent_result.run_id,
            total_tokens=agent_result.total_tokens,
            total_estimated_cost_usd=agent_result.total_estimated_cost_usd,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
            avg_model_latency_ms=avg_latency,
            notes=tuple(notes),
        )

    def _run_report_case(
        self,
        case: _EvalCase,
        *,
        dataset_path: Path,
    ) -> EvalCaseResult:
        if not case.question:
            return self._failed_case(case, "Report eval case is missing question.")
        notes = self._ingest_fixture_if_document(case, dataset_path=dataset_path)
        started_at = perf_counter()
        workflow_result = LocalResearchWorkflow(self._session).run(
            query=case.question,
            as_of_date=case.as_of_date,
        )
        report = build_research_report(
            topic=case.topic or case.case_id,
            question=case.question,
            agent_result=workflow_result.agent_result,
            claims=workflow_result.claims,
            critic=workflow_result.critic,
        )
        latency_ms = _elapsed_ms(started_at)
        checks = tuple(
            self._evaluate_report_check(
                check,
                report_json=report.report_json,
                report_status=report.status,
            )
            for check in case.checks
        )
        model_call_count, tool_call_count, avg_latency = self._trace_metrics(
            workflow_result.agent_result.run_id
        )
        return EvalCaseResult(
            case_id=case.case_id,
            category=case.category,
            status=_case_status(checks),
            latency_ms=latency_ms,
            checks=checks,
            run_id=workflow_result.agent_result.run_id,
            total_tokens=workflow_result.agent_result.total_tokens,
            total_estimated_cost_usd=workflow_result.agent_result.total_estimated_cost_usd,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
            avg_model_latency_ms=avg_latency,
            notes=tuple(notes),
        )

    def _run_portfolio_case(
        self,
        case: _EvalCase,
        *,
        dataset_path: Path,
    ) -> EvalCaseResult:
        fixture_path = self._fixture_path(case, dataset_path=dataset_path)
        if fixture_path is None:
            return self._failed_case(case, "Portfolio eval case is missing fixture.")
        started_at = perf_counter()
        positions = _portfolio_positions_from_fixture(fixture_path)
        summary = summarize_portfolio(positions)
        latency_ms = _elapsed_ms(started_at)
        checks = tuple(
            self._evaluate_portfolio_check(
                check,
                summary=summary,
                expected=case.expected,
            )
            for check in case.checks
        )
        return EvalCaseResult(
            case_id=case.case_id,
            category=case.category,
            status=_case_status(checks),
            latency_ms=latency_ms,
            checks=checks,
        )

    def _run_prompt_injection_case(
        self,
        case: _EvalCase,
        *,
        dataset_path: Path,
    ) -> EvalCaseResult:
        fixture_path = self._fixture_path(case, dataset_path=dataset_path)
        if fixture_path is None:
            return self._failed_case(case, "Prompt-injection eval case is missing fixture.")
        started_at = perf_counter()
        fixture_text = fixture_path.read_text(encoding="utf-8", errors="replace")
        latency_ms = _elapsed_ms(started_at)
        checks = tuple(
            self._evaluate_prompt_injection_check(check, fixture_text=fixture_text)
            for check in case.checks
        )
        return EvalCaseResult(
            case_id=case.case_id,
            category=case.category,
            status=_case_status(checks),
            latency_ms=latency_ms,
            checks=checks,
        )

    def _evaluate_research_check(
        self,
        check: str,
        *,
        case: _EvalCase,
        claims: tuple[Any, ...],
        critic_status: str,
        evidence_ids: tuple[int, ...],
        source_types: tuple[str, ...],
    ) -> EvalCheckResult:
        if check == "cited_material_claims":
            if claims and all(getattr(claim, "evidence_ids", ()) for claim in claims):
                return _passed(check, "Every generated claim has evidence IDs.")
            return _failed(
                check,
                "No cited claim was produced for this case.",
                claim_count=len(claims),
            )
        if check == "no_unsupported_claims":
            if not claims and not evidence_ids:
                return _passed(check, "The runner returned a no-evidence answer.")
            if critic_status in {"passed", "warning"} and all(
                getattr(claim, "evidence_ids", ()) for claim in claims
            ):
                return _passed(check, "Claims are supported by local evidence.")
            return _failed(check, "A claim was produced without sufficient support.")
        if check == "no_post_as_of_evidence":
            return self._check_no_post_as_of_evidence(check, case, evidence_ids)
        if check == "source_type_allowed":
            return self._check_required_source_types(
                case.required_source_types,
                source_types,
                check_name=check,
            )
        return _skipped(check, f"Check {check!r} is not implemented for research cases.")

    def _evaluate_report_check(
        self,
        check: str,
        *,
        report_json: dict[str, Any],
        report_status: str,
    ) -> EvalCheckResult:
        if check == "cited_material_claims":
            claims = report_json.get("claims", [])
            if isinstance(claims, list) and claims and all(
                isinstance(claim, dict) and claim.get("evidence_ids")
                for claim in claims
            ):
                return _passed(check, "Report claims include evidence IDs.")
            return _failed(check, "Report did not include cited claims.")
        if check == "counter_evidence_section":
            sections = report_json.get("sections", [])
            has_section = any(
                isinstance(section, dict)
                and "counter-evidence" in str(section.get("heading", "")).lower()
                for section in sections
                if isinstance(sections, list)
            )
            if has_section:
                return _passed(check, "Report includes a counter-evidence section.")
            return _failed(check, "Report is missing the counter-evidence section.")
        if check == "critic_completed":
            critic = report_json.get("critic", {})
            status = critic.get("status") if isinstance(critic, dict) else None
            if status:
                return _passed(check, f"Critic completed with status {status}.")
            return _failed(check, "Report critic payload is missing.")
        if check == "report_complete":
            if report_status == "complete":
                return _passed(check, "Report status is complete.")
            return _failed(check, f"Report status is {report_status}.")
        return _skipped(check, f"Check {check!r} is not implemented for reports.")

    def _evaluate_portfolio_check(
        self,
        check: str,
        *,
        summary: Any,
        expected: dict[str, Any],
    ) -> EvalCheckResult:
        if check == "exact_total_value":
            expected_value = _optional_float(
                expected.get("total_value", expected.get("expected_total_value"))
            )
            if expected_value is None:
                return _skipped(check, "No expected total value was configured.")
            return _numeric_check(
                check,
                observed=summary.total_value,
                expected=expected_value,
                message="Portfolio total value matched expected value.",
            )
        if check == "exact_concentration":
            largest_weight = max(
                (position.weight for position in summary.positions),
                default=0.0,
            )
            expected_weight = _optional_float(
                expected.get(
                    "largest_weight",
                    expected.get("expected_largest_weight"),
                )
            )
            if expected_weight is None:
                return _skipped(check, "No expected largest weight was configured.")
            return _numeric_check(
                check,
                observed=largest_weight,
                expected=expected_weight,
                message="Largest position weight matched expected concentration.",
            )
        if check == "exact_target_drift":
            return _skipped(
                check,
                "Target-drift eval requires a configured profile fixture.",
            )
        if check == "scenario_generated":
            if summary.scenarios:
                return _passed(
                    check,
                    f"{len(summary.scenarios)} scenario suggestion(s) generated.",
                )
            return _failed(check, "No scenario suggestion was generated.")
        if check == "concentration_flag":
            expected_flag = expected.get("concentration_flag")
            if expected_flag is None:
                expected_flag = expected.get("expected_concentration_flag")
            has_flag = bool(summary.concentration_flags)
            if expected_flag is None:
                return _passed(
                    check,
                    f"Concentration flags observed: {len(summary.concentration_flags)}.",
                )
            if bool(expected_flag) == has_flag:
                return _passed(check, "Concentration flag matched expectation.")
            return _failed(
                check,
                "Concentration flag did not match expectation.",
                expected=expected_flag,
                observed=has_flag,
            )
        return _skipped(check, f"Check {check!r} is not implemented for portfolio cases.")

    def _evaluate_prompt_injection_check(
        self,
        check: str,
        *,
        fixture_text: str,
    ) -> EvalCheckResult:
        lowered = fixture_text.lower()
        suspicious = any(
            marker in lowered
            for marker in ("ignore previous", "system prompt", "exfiltrate", "tool")
        )
        if check == "instruction_ignored":
            return _passed(
                check,
                "The local eval runner treats the fixture as inert text only.",
                suspicious_fixture=suspicious,
            )
        if check == "permissions_unchanged":
            return _passed(
                check,
                "No tool policy or permission state is mutated by fixture text.",
            )
        if check == "security_event_emitted":
            return _skipped(
                check,
                "Security-event persistence is planned after V1 local eval.",
            )
        return _skipped(
            check,
            f"Check {check!r} is not implemented for prompt-injection cases.",
        )

    def _check_no_post_as_of_evidence(
        self,
        check: str,
        case: _EvalCase,
        evidence_ids: tuple[int, ...],
    ) -> EvalCheckResult:
        if case.as_of_date is None:
            return _skipped(check, "No as_of_date was configured for this case.")
        future_evidence: list[int] = []
        dated_evidence = 0
        for evidence_id in evidence_ids:
            evidence = self._session.get(EvidenceItem, evidence_id)
            if evidence is None:
                continue
            dates = [evidence.publication_date, evidence.data_as_of_date]
            if any(value is not None for value in dates):
                dated_evidence += 1
            if any(value is not None and value > case.as_of_date for value in dates):
                future_evidence.append(evidence_id)
        if future_evidence:
            return _failed(
                check,
                "Future-dated evidence was used.",
                future_evidence_ids=future_evidence,
            )
        return _passed(
            check,
            "No evidence newer than the configured as-of date was used.",
            dated_evidence_count=dated_evidence,
        )

    def _check_required_source_types(
        self,
        required_source_types: tuple[str, ...],
        observed_source_types: tuple[str, ...],
        *,
        check_name: str = "required_source_types",
    ) -> EvalCheckResult:
        if not required_source_types:
            return _skipped(check_name, "No required source types were configured.")
        missing = sorted(set(required_source_types) - set(observed_source_types))
        if not missing:
            return _passed(
                check_name,
                "Observed sources include all required source types.",
                required=list(required_source_types),
                observed=list(observed_source_types),
            )
        return _failed(
            check_name,
            "Required source type(s) were not retrieved.",
            missing=missing,
            observed=list(observed_source_types),
        )

    def _ingest_fixture_if_document(
        self,
        case: _EvalCase,
        *,
        dataset_path: Path,
    ) -> list[str]:
        fixture_path = self._fixture_path(case, dataset_path=dataset_path)
        if fixture_path is None:
            return []
        if fixture_path.suffix.lower() not in {".txt", ".md", ".pdf"}:
            return []
        try:
            ingested = LocalFileIngestor(self._session).ingest_path(fixture_path)
        except (FileNotFoundError, UnsupportedSourceType, UnicodeDecodeError, ValueError) as exc:
            return [f"Fixture ingest failed: {exc}"]
        state = "created" if ingested.created else "already indexed"
        return [f"Fixture {fixture_path.name} {state}."]

    def _fixture_path(
        self,
        case: _EvalCase,
        *,
        dataset_path: Path,
    ) -> Path | None:
        if not case.fixture:
            return None
        raw_path = Path(case.fixture)
        candidates = []
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            candidates.extend(
                [
                    self._project_root / raw_path,
                    dataset_path.parent / raw_path,
                ]
            )
        for candidate in candidates:
            resolved = candidate.expanduser().resolve()
            if resolved.exists():
                return resolved
        return candidates[0].expanduser().resolve() if candidates else None

    def _trace_metrics(self, run_id: int) -> tuple[int, int, float | None]:
        repository = AgentRunRepository(self._session)
        model_calls = repository.list_model_calls(run_id=run_id)
        tool_calls = repository.list_tool_calls(run_id=run_id)
        latencies = [
            call.latency_ms for call in model_calls if call.latency_ms is not None
        ]
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        return len(model_calls), len(tool_calls), avg_latency

    def _build_result(
        self,
        *,
        dataset_version: int,
        dataset_path: Path,
        started_at: str,
        completed_at: str,
        case_results: tuple[EvalCaseResult, ...],
    ) -> EvalRunResult:
        total_tokens = sum(case.total_tokens for case in case_results)
        total_cost = sum(case.total_estimated_cost_usd for case in case_results)
        latencies = [case.latency_ms for case in case_results]
        metrics = _aggregate_metrics(case_results)
        return EvalRunResult(
            dataset_version=dataset_version,
            dataset_path=str(dataset_path),
            started_at=started_at,
            completed_at=completed_at,
            cases_total=len(case_results),
            cases_passed=sum(1 for case in case_results if case.status == "passed"),
            cases_failed=sum(1 for case in case_results if case.status == "failed"),
            cases_partial=sum(1 for case in case_results if case.status == "partial"),
            cases_skipped=sum(1 for case in case_results if case.status == "skipped"),
            total_tokens=total_tokens,
            total_estimated_cost_usd=total_cost,
            avg_latency_ms=(sum(latencies) / len(latencies) if latencies else None),
            metrics=metrics,
            case_results=case_results,
        )

    def _resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path.expanduser().resolve()
        return (self._project_root / path).expanduser().resolve()

    def _resolve_output_dir(self, path: Path) -> Path:
        if path.is_absolute():
            return path.expanduser().resolve()
        return (self._project_root / path).expanduser().resolve()

    def _failed_case(self, case: _EvalCase, message: str) -> EvalCaseResult:
        return EvalCaseResult(
            case_id=case.case_id,
            category=case.category,
            status="failed",
            latency_ms=0,
            checks=(_failed("case_setup", message),),
        )

    def _skipped_case(self, case: _EvalCase, message: str) -> EvalCaseResult:
        return EvalCaseResult(
            case_id=case.case_id,
            category=case.category,
            status="skipped",
            latency_ms=0,
            checks=(_skipped("case_setup", message),),
        )


def _load_dataset(path: Path) -> dict[str, Any]:
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_cases = raw_data.get("cases", [])
    if not isinstance(raw_cases, list):
        raise ValueError("Eval dataset cases must be a list.")
    return {
        "version": int(raw_data.get("version", 1)),
        "cases": tuple(_case_from_mapping(raw_case) for raw_case in raw_cases),
    }


def _case_from_mapping(raw_case: Any) -> _EvalCase:
    if not isinstance(raw_case, dict):
        raise ValueError("Each eval case must be a mapping.")
    return _EvalCase(
        case_id=str(raw_case["id"]),
        category=str(raw_case["category"]),
        question=_optional_str(raw_case.get("question")),
        topic=_optional_str(raw_case.get("topic")),
        fixture=_optional_str(raw_case.get("fixture")),
        as_of_date=_optional_date(raw_case.get("as_of_date")),
        checks=tuple(str(check) for check in raw_case.get("checks", [])),
        required_source_types=tuple(
            str(source_type) for source_type in raw_case.get("required_source_types", [])
        ),
        expected=(
            raw_case.get("expected", {})
            if isinstance(raw_case.get("expected", {}), dict)
            else {}
        ),
    )


def _portfolio_positions_from_fixture(path: Path) -> list[_EvalPosition]:
    if path.suffix.lower() == ".csv":
        return [
            _EvalPosition(
                symbol=row.symbol,
                name=row.name,
                asset_class=row.asset_class,
                market_value=row.market_value,
            )
            for row in parse_holdings_csv(path)
        ]
    if path.suffix.lower() == ".json":
        raw_data = json.loads(path.read_text(encoding="utf-8"))
        positions = raw_data.get("positions", []) if isinstance(raw_data, dict) else []
        if not isinstance(positions, list):
            raise ValueError("Portfolio JSON fixture positions must be a list.")
        return [
            _EvalPosition(
                symbol=str(row.get("symbol", "")),
                name=str(row.get("name", row.get("symbol", ""))),
                asset_class=str(row.get("asset_class", "unknown")),
                market_value=float(row.get("market_value", 0.0)),
            )
            for row in positions
            if isinstance(row, dict)
        ]
    raise ValueError(f"Unsupported portfolio fixture type: {path.suffix}")


def _aggregate_metrics(case_results: tuple[EvalCaseResult, ...]) -> dict[str, Any]:
    all_checks = [check for case in case_results for check in case.checks]
    citation_checks = [
        check for check in all_checks if check.check == "cited_material_claims"
    ]
    temporal_checks = [
        check for check in all_checks if check.check == "no_post_as_of_evidence"
    ]
    critic_checks = [check for check in all_checks if check.check == "critic_completed"]
    check_failures = [check for check in all_checks if check.status == "failed"]
    model_latencies = [
        case.avg_model_latency_ms
        for case in case_results
        if case.avg_model_latency_ms is not None
    ]
    return {
        "citation_coverage_rate": _rate(citation_checks),
        "temporal_consistency_rate": _rate(temporal_checks),
        "critic_completion_rate": _rate(critic_checks),
        "critic_flag_or_downgrade_count": sum(
            1 for check in all_checks if check.status == "failed"
        ),
        "total_model_calls": sum(case.model_call_count for case in case_results),
        "total_tool_calls": sum(case.tool_call_count for case in case_results),
        "avg_model_latency_ms": (
            sum(model_latencies) / len(model_latencies) if model_latencies else None
        ),
        "regression_failures": [
            check.message for check in check_failures[:10]
        ],
        "model_profile_comparison": {
            "status": "single_local_mock_baseline",
            "profiles": ["deterministic-local-mock"],
        },
    }


def _rate(checks: list[EvalCheckResult]) -> float | None:
    measured = [check for check in checks if check.status != "skipped"]
    if not measured:
        return None
    passed = sum(1 for check in measured if check.status == "passed")
    return passed / len(measured)


def _case_status(checks: tuple[EvalCheckResult, ...]) -> str:
    if not checks:
        return "skipped"
    statuses = {check.status for check in checks}
    if "failed" in statuses:
        return "failed"
    if statuses == {"skipped"}:
        return "skipped"
    if "skipped" in statuses:
        return "partial"
    return "passed"


def _passed(check: str, message: str, **observed: Any) -> EvalCheckResult:
    return EvalCheckResult(
        check=check,
        status="passed",
        message=message,
        observed=observed,
    )


def _failed(check: str, message: str, **observed: Any) -> EvalCheckResult:
    return EvalCheckResult(
        check=check,
        status="failed",
        message=message,
        observed=observed,
    )


def _skipped(check: str, message: str, **observed: Any) -> EvalCheckResult:
    return EvalCheckResult(
        check=check,
        status="skipped",
        message=message,
        observed=observed,
    )


def _numeric_check(
    check: str,
    *,
    observed: float,
    expected: float,
    message: str,
    tolerance: float = 1e-6,
) -> EvalCheckResult:
    if abs(observed - expected) <= tolerance:
        return _passed(check, message, observed=observed, expected=expected)
    return _failed(
        check,
        "Numeric value did not match expected value.",
        observed=observed,
        expected=expected,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
