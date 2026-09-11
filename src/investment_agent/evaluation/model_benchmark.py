from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml

from investment_agent.config import Settings
from investment_agent.harness.types import ToolResult
from investment_agent.providers import OpenAICompatibleModelProvider
from investment_agent.providers.types import ModelProvider, ModelRequest
from investment_agent.research.claims import ClaimEvidence, generate_structured_claims


@dataclass(frozen=True)
class BenchmarkModelSpec:
    model_id: str
    provider_name: str
    model: str
    base_url: str
    serving_engine: str
    api_key: str | None
    input_cost_per_million: float
    output_cost_per_million: float
    availability_note: str | None = None


@dataclass(frozen=True)
class ModelStageScore:
    case_id: str
    model_id: str
    stage: str
    status: str
    quality_score: float
    claim_recall: float
    supported_claim_rate: float
    organization_score: float
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    claim_count: int
    error_code: str | None = None


@dataclass(frozen=True)
class ModelBenchmarkResult:
    dataset_version: int
    dataset_path: str
    started_at: str
    completed_at: str
    requested_models: tuple[str, ...]
    max_cost_usd: float
    total_estimated_cost_usd: float
    scores: tuple[ModelStageScore, ...]
    stage_recommendations: dict[str, dict[str, object]]
    skipped_models: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            "# Argus Model Stage Benchmark",
            "",
            f"- Dataset: `{self.dataset_path}` (v{self.dataset_version})",
            f"- Cost ceiling: ${self.max_cost_usd:.4f}",
            f"- Estimated model cost: ${self.total_estimated_cost_usd:.6f}",
            "- Routing effect: none; recommendations do not change production models automatically.",
            "",
            "| Model | Stage | Case | Quality | Claim recall | Citation support | Organization | Latency | Cost |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for score in self.scores:
            lines.append(
                f"| `{score.model_id}` | {score.stage} | `{score.case_id}` | "
                f"{score.quality_score:.3f} | {score.claim_recall:.3f} | "
                f"{score.supported_claim_rate:.3f} | {score.organization_score:.3f} | "
                f"{score.latency_ms} ms | ${score.estimated_cost_usd:.6f} |"
            )
        lines.extend(["", "## Stage recommendations", ""])
        for stage, recommendation in self.stage_recommendations.items():
            lines.append(
                f"- **{stage}**: `{recommendation.get('model_id') or 'none'}` — "
                f"{recommendation.get('reason', 'No eligible model.')}"
            )
        if self.skipped_models:
            lines.extend(["", "## Skipped models", ""])
            for model_id, reason in self.skipped_models.items():
                lines.append(f"- `{model_id}`: {reason}")
        return "\n".join(lines)


class ModelBenchmarkRunner:
    """Explicit, cost-capped A/B tests; never changes the production route."""

    def __init__(
        self,
        settings: Settings,
        *,
        providers: dict[str, ModelProvider] | None = None,
    ) -> None:
        self._settings = settings
        self._providers = providers

    def run(
        self,
        *,
        dataset_path: Path,
        model_ids: tuple[str, ...],
        max_cost_usd: float | None = None,
    ) -> ModelBenchmarkResult:
        if not model_ids:
            raise ValueError("Choose at least one model for an explicit benchmark.")
        ceiling = (
            self._settings.model_benchmark_max_cost_usd
            if max_cost_usd is None
            else max_cost_usd
        )
        if ceiling <= 0:
            raise ValueError("Model benchmark cost ceiling must be positive.")
        dataset = _load_benchmark_dataset(dataset_path)
        specs = benchmark_model_specs(self._settings)
        providers = self._providers or {}
        skipped: dict[str, str] = {}
        active: dict[str, ModelProvider] = {}
        for model_id in model_ids:
            if model_id in providers:
                active[model_id] = providers[model_id]
                continue
            spec = specs.get(model_id)
            if spec is None:
                skipped[model_id] = "Unknown benchmark model ID."
                continue
            if not spec.api_key:
                skipped[model_id] = "API key is not configured."
                continue
            if spec.availability_note:
                skipped[model_id] = spec.availability_note
                continue
            active[model_id] = _provider_for_spec(spec, settings=self._settings)

        started_at = _now_iso()
        scores: list[ModelStageScore] = []
        spent = 0.0
        for model_id in model_ids:
            provider = active.get(model_id)
            if provider is None:
                continue
            spec = specs.get(model_id)
            for case in dataset["cases"]:
                for stage in ("evidence_extraction", "answer_synthesis"):
                    call_ceiling = (
                        _benchmark_call_cost_ceiling(spec, case=case, stage=stage)
                        if spec is not None
                        else 0.0
                    )
                    if spent >= ceiling or spent + call_ceiling > ceiling:
                        skipped[model_id] = (
                            "Stopped before the next call because its conservative "
                            f"maximum would cross the ${ceiling:.4f} cost ceiling."
                        )
                        break
                    score = _run_stage(
                        provider,
                        model_id=model_id,
                        case=case,
                        stage=stage,
                    )
                    scores.append(score)
                    spent = round(spent + score.estimated_cost_usd, 10)
                if spent >= ceiling:
                    break
        completed_at = _now_iso()
        return ModelBenchmarkResult(
            dataset_version=int(dataset["version"]),
            dataset_path=str(dataset_path.resolve()),
            started_at=started_at,
            completed_at=completed_at,
            requested_models=model_ids,
            max_cost_usd=ceiling,
            total_estimated_cost_usd=spent,
            scores=tuple(scores),
            stage_recommendations=_stage_recommendations(scores),
            skipped_models=skipped,
        )


def benchmark_model_specs(settings: Settings) -> dict[str, BenchmarkModelSpec]:
    specs = {
        f"deepseek/{settings.deepseek_model}": BenchmarkModelSpec(
            model_id=f"deepseek/{settings.deepseek_model}",
            provider_name="deepseek",
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
            serving_engine="deepseek-api",
            api_key=settings.deepseek_api_key,
            input_cost_per_million=settings.deepseek_input_cost_per_million,
            output_cost_per_million=settings.deepseek_output_cost_per_million,
        ),
        f"deepseek/{settings.deepseek_pro_model}": BenchmarkModelSpec(
            model_id=f"deepseek/{settings.deepseek_pro_model}",
            provider_name="deepseek",
            model=settings.deepseek_pro_model,
            base_url=settings.deepseek_base_url,
            serving_engine="deepseek-api",
            api_key=settings.deepseek_api_key,
            input_cost_per_million=settings.deepseek_pro_input_cost_per_million,
            output_cost_per_million=settings.deepseek_pro_output_cost_per_million,
        ),
        f"moonshot/{settings.kimi_model}": BenchmarkModelSpec(
            model_id=f"moonshot/{settings.kimi_model}",
            provider_name="moonshot",
            model=settings.kimi_model,
            base_url=settings.kimi_base_url,
            serving_engine="kimi-api",
            api_key=settings.kimi_api_key,
            input_cost_per_million=settings.kimi_input_cost_per_million,
            output_cost_per_million=settings.kimi_output_cost_per_million,
        ),
        f"openai/{settings.openai_model}": BenchmarkModelSpec(
            model_id=f"openai/{settings.openai_model}",
            provider_name="openai",
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            serving_engine="openai-api",
            api_key=settings.openai_api_key,
            input_cost_per_million=settings.openai_input_cost_per_million,
            output_cost_per_million=settings.openai_output_cost_per_million,
        ),
    }
    if settings.kimi_candidate_model:
        candidate_id = f"moonshot/{settings.kimi_candidate_model}"
        prices_missing = (
            settings.kimi_candidate_input_cost_per_million <= 0
            or settings.kimi_candidate_output_cost_per_million <= 0
        )
        specs[candidate_id] = BenchmarkModelSpec(
            model_id=candidate_id,
            provider_name="moonshot",
            model=settings.kimi_candidate_model,
            base_url=settings.kimi_base_url,
            serving_engine="kimi-api",
            api_key=settings.kimi_api_key,
            input_cost_per_million=settings.kimi_candidate_input_cost_per_million,
            output_cost_per_million=settings.kimi_candidate_output_cost_per_million,
            availability_note=(
                "Candidate remains disabled until Moonshot confirms the exact model ID "
                "and token prices are configured."
                if prices_missing
                else None
            ),
        )
    return specs


def save_model_benchmark(
    result: ModelBenchmarkResult,
    *,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"model-stage-benchmark-{stamp}.json"
    markdown_path = output_dir / f"model-stage-benchmark-{stamp}.md"
    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(result.to_markdown(), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def _provider_for_spec(
    spec: BenchmarkModelSpec,
    *,
    settings: Settings,
) -> OpenAICompatibleModelProvider:
    return OpenAICompatibleModelProvider(
        provider_name=spec.provider_name,
        api_key=spec.api_key or "",
        model=spec.model,
        base_url=spec.base_url,
        serving_engine=spec.serving_engine,
        timeout_ms=settings.model_timeout_ms,
        max_attempts=1,
        retry_backoff_ms=settings.model_retry_backoff_ms,
        input_cost_per_million=spec.input_cost_per_million,
        output_cost_per_million=spec.output_cost_per_million,
        max_tokens=500,
    )


def _benchmark_call_cost_ceiling(
    spec: BenchmarkModelSpec,
    *,
    case: dict[str, Any],
    stage: str,
) -> float:
    """Reserve a conservative per-call maximum before spending provider budget."""
    evidence_characters = sum(
        len(str(item.get("text") or "")) for item in case.get("evidence", [])
    )
    prompt_characters = len(_stage_prompt(case, stage=stage)) + evidence_characters
    estimated_input_tokens = max(1, (prompt_characters + 999) // 3)
    return (
        estimated_input_tokens * spec.input_cost_per_million
        + 500 * spec.output_cost_per_million
    ) / 1_000_000


def _run_stage(
    provider: ModelProvider,
    *,
    model_id: str,
    case: dict[str, Any],
    stage: str,
) -> ModelStageScore:
    evidence = tuple(
        ClaimEvidence(
            citation_id=str(item["citation_id"]),
            text=str(item["text"]),
            display_name=str(item["title"]),
        )
        for item in case["evidence"]
    )
    rows = [
        {
            "citation_id": item.citation_id,
            "title": item.display_name,
            "source_uri": f"benchmark://{case['id']}/{item.citation_id}",
            "source_type": "benchmark",
            "supported_passage": item.text,
            "text": item.text,
        }
        for item in evidence
    ]
    prompt = _stage_prompt(case, stage=stage)
    tool_result = ToolResult(
        call_id=f"benchmark-{case['id']}-{stage}",
        status="ok",
        output={
            "search": {"evidence_gate": {"decision": "supported"}},
            "results": rows,
        },
    )
    started = perf_counter()
    response = provider.generate(
        ModelRequest(
            objective=prompt,
            role="research",
            sensitivity="public",
            as_of_date=None,
            tool_results=(tool_result,),
            iteration=1,
        )
    )
    latency_ms = int((perf_counter() - started) * 1000)
    if not response.success:
        return ModelStageScore(
            case_id=str(case["id"]),
            model_id=model_id,
            stage=stage,
            status="failed",
            quality_score=0.0,
            claim_recall=0.0,
            supported_claim_rate=0.0,
            organization_score=0.0,
            latency_ms=latency_ms,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            estimated_cost_usd=response.estimated_cost_usd,
            claim_count=0,
            error_code=response.error_code,
        )
    claims = generate_structured_claims(
        answer=response.content,
        evidence=evidence,
        require_explicit_citations=True,
    )
    recall = _claim_recall(response.content, case["expected_claim_terms"])
    support = (
        sum(claim.verification.status == "supported" for claim in claims) / len(claims)
        if claims
        else 0.0
    )
    organization = _organization_score(
        response.content,
        required_headings=case.get("required_headings", []),
        stage=stage,
        claim_count=len(claims),
    )
    quality = round(0.45 * recall + 0.40 * support + 0.15 * organization, 4)
    return ModelStageScore(
        case_id=str(case["id"]),
        model_id=model_id,
        stage=stage,
        status="complete",
        quality_score=quality,
        claim_recall=round(recall, 4),
        supported_claim_rate=round(support, 4),
        organization_score=round(organization, 4),
        latency_ms=latency_ms,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        estimated_cost_usd=response.estimated_cost_usd,
        claim_count=len(claims),
    )


def _stage_prompt(case: dict[str, Any], *, stage: str) -> str:
    question = str(case["question"])
    if stage == "evidence_extraction":
        return (
            "Evidence extraction benchmark. Answer the question as a list of atomic, "
            "independently verifiable factual claims. Put [source:ID] on every claim. "
            "Preserve dates, numbers, direction, and uncertainty exactly; do not add "
            f"background knowledge. Question: {question}"
        )
    headings = "\n".join(f"## {item}" for item in case["required_headings"])
    return (
        "Answer synthesis benchmark. Organize a concise research answer using exactly "
        "the headings below. Every material factual claim needs [source:ID]. Do not "
        "invent evidence or personalized trades.\n"
        f"{headings}\nQuestion: {question}"
    )


def _claim_recall(answer: str, expected_groups: list[list[str]]) -> float:
    lowered = " ".join(answer.lower().split())
    if not expected_groups:
        return 1.0
    matched = sum(
        all(str(term).lower() in lowered for term in group) for group in expected_groups
    )
    return matched / len(expected_groups)


def _organization_score(
    answer: str,
    *,
    required_headings: list[str],
    stage: str,
    claim_count: int,
) -> float:
    if stage == "evidence_extraction":
        return 1.0 if 1 <= claim_count <= 8 else 0.0
    if not required_headings:
        return 1.0
    return sum(f"## {heading}" in answer for heading in required_headings) / len(
        required_headings
    )


def _stage_recommendations(
    scores: list[ModelStageScore],
) -> dict[str, dict[str, object]]:
    recommendations: dict[str, dict[str, object]] = {}
    for stage in ("evidence_extraction", "answer_synthesis"):
        by_model: dict[str, list[ModelStageScore]] = {}
        for score in scores:
            if score.stage == stage and score.status == "complete":
                by_model.setdefault(score.model_id, []).append(score)
        summaries = [
            {
                "model_id": model_id,
                "quality": sum(item.quality_score for item in rows) / len(rows),
                "support": sum(item.supported_claim_rate for item in rows) / len(rows),
                "cost": sum(item.estimated_cost_usd for item in rows),
            }
            for model_id, rows in by_model.items()
        ]
        eligible = [
            item
            for item in summaries
            if item["quality"] >= 0.70 and item["support"] >= 0.80
        ]
        if not eligible:
            recommendations[stage] = {
                "model_id": None,
                "reason": "No model passed the quality and per-claim citation thresholds.",
                "candidates": summaries,
            }
            continue
        top_quality = max(float(item["quality"]) for item in eligible)
        near_top = [
            item for item in eligible if float(item["quality"]) >= top_quality - 0.03
        ]
        winner = min(near_top, key=lambda item: float(item["cost"]))
        recommendations[stage] = {
            "model_id": winner["model_id"],
            "reason": (
                "Lowest measured cost among models within 0.03 of the best quality "
                "score and above the citation threshold."
            ),
            "candidates": summaries,
        }
    return recommendations


def _load_benchmark_dataset(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("Model benchmark dataset requires a cases list.")
    return payload


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
