from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
import re
from typing import TYPE_CHECKING

from investment_agent.retrieval.evidence_gate import (
    EvidenceDecision,
    EvidenceGate,
    EvidenceGateResult,
    evidence_gate_metadata,
)
if TYPE_CHECKING:
    from investment_agent.retrieval.hybrid import HybridRetrievalService
    from investment_agent.retrieval.vector import RetrievalResult


class SearchMode(StrEnum):
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass(frozen=True)
class EvidenceSlotSpec:
    slot_id: str
    description: str
    search_terms: tuple[str, ...] = ()
    query_template: str = "{question}"
    minimum_items: int = 1
    minimum_distinct_sources: int = 1
    freshness_days: int | None = None
    required: bool = True

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,47}", self.slot_id):
            raise ValueError(f"Invalid evidence slot id: {self.slot_id}")
        if "{question}" not in self.query_template:
            raise ValueError("Evidence slot query_template must contain {question}")
        if not 1 <= self.minimum_items <= 5:
            raise ValueError("Evidence slot minimum_items must be between 1 and 5")
        if not 1 <= self.minimum_distinct_sources <= 3:
            raise ValueError(
                "Evidence slot minimum_distinct_sources must be between 1 and 3"
            )
        if self.freshness_days is not None and not 1 <= self.freshness_days <= 3650:
            raise ValueError("Evidence slot freshness_days must be between 1 and 3650")


@dataclass(frozen=True)
class SearchPlan:
    mode: SearchMode
    complexity_score: int
    complexity_reasons: tuple[str, ...]
    required_slots: tuple[EvidenceSlotSpec, ...]
    method_hints: tuple[EvidenceSlotSpec, ...]
    max_search_rounds: int
    max_queries: int


@dataclass(frozen=True)
class EvidenceCoverage:
    filled_slots: tuple[str, ...]
    missing_slots: tuple[str, ...]
    optional_missing_slots: tuple[str, ...]

    @property
    def sufficient(self) -> bool:
        return not self.missing_slots


@dataclass(frozen=True)
class SearchQueryTrace:
    round_number: int
    query: str
    target_slot: str
    channel_counts: dict[str, int]
    result_chunk_ids: tuple[int, ...]


@dataclass(frozen=True)
class AdaptiveSearchResult:
    results: tuple[RetrievalResult, ...]
    plan: SearchPlan
    coverage: EvidenceCoverage
    queries: tuple[SearchQueryTrace, ...]
    agent_search_triggered: bool
    stop_reason: str
    evidence_gate: EvidenceGateResult


DEFAULT_EVIDENCE_SLOTS: dict[str, EvidenceSlotSpec] = {
    "primary_evidence": EvidenceSlotSpec(
        slot_id="primary_evidence",
        description="Direct evidence that addresses the question.",
    ),
    "causal_chain": EvidenceSlotSpec(
        slot_id="causal_chain",
        description="Evidence linking a driver to an outcome.",
        search_terms=(
            "because",
            "due",
            "drives",
            "impact",
            "influence",
            "leads",
            "therefore",
            "原因",
            "影响",
            "导致",
        ),
        query_template="causal mechanism drivers impact {question}",
    ),
    "comparison": EvidenceSlotSpec(
        slot_id="comparison",
        description="Comparable evidence for more than one entity or scenario.",
        minimum_items=2,
        query_template="comparison alternatives differences {question}",
    ),
    "current_context": EvidenceSlotSpec(
        slot_id="current_context",
        description="Time-stamped evidence for a current-market claim.",
        query_template="latest current dated market evidence {question}",
        freshness_days=45,
    ),
    "risk": EvidenceSlotSpec(
        slot_id="risk",
        description="Downside, limitation, or uncertainty evidence.",
        search_terms=(
            "downside",
            "limit",
            "risk",
            "uncertain",
            "warning",
            "下行",
            "不确定",
            "限制",
            "风险",
        ),
        query_template="risks downside limitations uncertainty {question}",
    ),
    "counter_evidence": EvidenceSlotSpec(
        slot_id="counter_evidence",
        description="Evidence that challenges the leading thesis.",
        search_terms=(
            "although",
            "but",
            "counter",
            "however",
            "opposite",
            "whereas",
            "反例",
            "但是",
            "相反",
        ),
        query_template="counter evidence opposing view what could invalidate {question}",
    ),
    "valuation": EvidenceSlotSpec(
        slot_id="valuation",
        description="Valuation measure, assumption, or comparable evidence.",
        search_terms=(
            "earnings",
            "multiple",
            "price",
            "valuation",
            "估值",
            "市盈率",
            "价格",
        ),
        query_template="valuation price multiple assumptions {question}",
    ),
    "falsification": EvidenceSlotSpec(
        slot_id="falsification",
        description="Observable condition that would invalidate the thesis.",
        search_terms=(
            "falsify",
            "invalidate",
            "unless",
            "would change",
            "证伪",
            "失效",
        ),
        query_template="falsification invalidation conditions what would change {question}",
    ),
}


class DeterministicComplexityPolicy:
    """Build an explainable plan from visible query requirements."""

    def plan(
        self,
        query: str,
        *,
        method_slots: tuple[EvidenceSlotSpec, ...] = (),
    ) -> SearchPlan:
        lowered = query.lower()
        score = 0
        reasons: list[str] = []
        slot_ids: list[str] = ["primary_evidence"]

        if _matches_any(
            lowered,
            ("why", "how does", "impact", "influence", "driver", "原因", "影响"),
        ):
            score += 2
            reasons.append("causal or driver analysis")
            slot_ids.append("causal_chain")
        if _matches_any(
            lowered,
            ("compare", " versus ", " vs ", "difference", "对比", "比较"),
        ):
            score += 2
            reasons.append("comparison across entities or scenarios")
            slot_ids.append("comparison")
        if _matches_any(
            lowered,
            ("current", "latest", "today", "now", "market situation", "当前", "最新"),
        ):
            score += 2
            reasons.append("current or time-sensitive evidence")
            slot_ids.append("current_context")
        if _matches_any(lowered, ("risk", "downside", "uncertain", "风险", "下行")):
            score += 1
            reasons.append("explicit downside or risk requirement")
            slot_ids.extend(("risk", "counter_evidence"))
        if _matches_any(
            lowered,
            (
                "recommend",
                "should i",
                "buy",
                "sell",
                "allocate",
                "portfolio",
                "推荐",
                "买入",
                "卖出",
                "配置",
            ),
        ):
            score += 3
            reasons.append("recommendation or portfolio implication")
            slot_ids.extend(("current_context", "risk", "counter_evidence"))
        if _matches_any(lowered, ("valuation", "multiple", "fair value", "估值")):
            score += 1
            reasons.append("valuation evidence")
            slot_ids.append("valuation")
        if _matches_any(lowered, ("falsif", "invalidate", "would change", "证伪")):
            score += 1
            reasons.append("falsification condition")
            slot_ids.append("falsification")

        slots_by_id = {
            slot.slot_id: slot
            for slot in (DEFAULT_EVIDENCE_SLOTS[slot_id] for slot_id in slot_ids)
        }
        required_slots = tuple(slots_by_id.values())
        if score <= 1:
            mode = SearchMode.FAST
            max_rounds = 1
            max_queries = 1
        elif score <= 5:
            mode = SearchMode.STANDARD
            max_rounds = 2
            max_queries = 2
        else:
            mode = SearchMode.DEEP
            max_rounds = 2
            max_queries = 2
        return SearchPlan(
            mode=mode,
            complexity_score=score,
            complexity_reasons=tuple(reasons or ("direct evidence lookup",)),
            required_slots=required_slots,
            method_hints=tuple(
                {slot.slot_id: slot for slot in method_slots}.values()
            ),
            max_search_rounds=max_rounds,
            max_queries=max_queries,
        )


class AdaptiveSearchService:
    """Run one retrieval and at most one Evidence-Gate-directed follow-up."""

    def __init__(
        self,
        retriever: HybridRetrievalService,
        *,
        policy: DeterministicComplexityPolicy | None = None,
        evidence_gate: EvidenceGate | None = None,
    ) -> None:
        self._retriever = retriever
        self._policy = policy or DeterministicComplexityPolicy()
        self._evidence_gate = evidence_gate or EvidenceGate()

    def search(
        self,
        query: str,
        *,
        top_k: int,
        document_id: int | None,
        access_scope: str | None,
        as_of_date: date | None,
        method_slots: tuple[EvidenceSlotSpec, ...] = (),
    ) -> AdaptiveSearchResult:
        plan = self._policy.plan(query, method_slots=method_slots)
        first = self._retriever.retrieve(
            query,
            top_k=max(top_k, 5),
            document_id=document_id,
            access_scope=access_scope,
            as_of_date=as_of_date,
        )
        query_results: list[tuple[str, tuple[RetrievalResult, ...]]] = [
            ("primary_evidence", first.results)
        ]
        traces = [
            SearchQueryTrace(
                round_number=1,
                query=query,
                target_slot="primary_evidence",
                channel_counts=first.diagnostics.channel_counts,
                result_chunk_ids=tuple(result.chunk_id for result in first.results),
            )
        ]
        combined = _merge_query_rankings(query_results, limit=max(top_k * 3, 10))
        gate = self._evidence_gate.evaluate(
            query,
            combined,
            final_attempt=plan.max_queries == 1,
            method_query_hints=tuple(
                slot.query_template for slot in plan.method_hints
            ),
        )
        agent_triggered = False

        if (
            gate.decision is EvidenceDecision.GAP
            and gate.follow_up_query
            and plan.max_search_rounds > 1
            and plan.max_queries > 1
        ):
            agent_triggered = True
            seen_queries = {_normalized_query(trace.query) for trace in traces}
            targeted_query = gate.follow_up_query
            normalized_target = _normalized_query(targeted_query)
            if normalized_target and normalized_target not in seen_queries:
                response = self._retriever.retrieve(
                    targeted_query,
                    top_k=max(top_k, 5),
                    document_id=document_id,
                    access_scope=access_scope,
                    as_of_date=as_of_date,
                )
                query_results.append((gate.gap_id or "direct_support", response.results))
                traces.append(
                    SearchQueryTrace(
                        round_number=2,
                        query=targeted_query,
                        target_slot=gate.gap_id or "direct_support",
                        channel_counts=response.diagnostics.channel_counts,
                        result_chunk_ids=tuple(
                            result.chunk_id for result in response.results
                        ),
                    )
                )
                combined = _merge_query_rankings(
                    query_results,
                    limit=max(top_k * 3, 10),
                )
            gate = self._evidence_gate.evaluate(
                query,
                combined,
                final_attempt=True,
                method_query_hints=tuple(
                    slot.query_template for slot in plan.method_hints
                ),
            )

        accepted_results = [item.result for item in gate.accepted]
        coverage = evaluate_coverage(
            plan.required_slots,
            accepted_results,
            as_of_date=as_of_date,
        )
        if gate.decision is EvidenceDecision.SUPPORTED:
            stop_reason = "evidence_gate_supported"
        elif plan.mode is SearchMode.FAST:
            stop_reason = "evidence_gate_refused_fast_budget"
        elif agent_triggered:
            stop_reason = "evidence_gate_refused_after_follow_up"
        else:
            stop_reason = "evidence_gate_refused_no_safe_follow_up"
        return AdaptiveSearchResult(
            results=tuple(accepted_results[:top_k]),
            plan=plan,
            coverage=coverage,
            queries=tuple(traces),
            agent_search_triggered=agent_triggered,
            stop_reason=stop_reason,
            evidence_gate=gate,
        )


def evaluate_coverage(
    slots: tuple[EvidenceSlotSpec, ...],
    results: list[RetrievalResult],
    *,
    as_of_date: date | None,
) -> EvidenceCoverage:
    filled: list[str] = []
    missing: list[str] = []
    optional_missing: list[str] = []
    reference_date = as_of_date or date.today()
    for slot in slots:
        matching = _matching_results(slot, results, reference_date=reference_date)
        distinct_sources = {result.document_id for result in matching}
        slot_filled = (
            len(matching) >= slot.minimum_items
            and len(distinct_sources) >= slot.minimum_distinct_sources
        )
        if slot_filled:
            filled.append(slot.slot_id)
        elif slot.required:
            missing.append(slot.slot_id)
        else:
            optional_missing.append(slot.slot_id)
    return EvidenceCoverage(
        filled_slots=tuple(filled),
        missing_slots=tuple(missing),
        optional_missing_slots=tuple(optional_missing),
    )


def search_result_metadata(result: AdaptiveSearchResult) -> dict[str, object]:
    return {
        "mode": result.plan.mode.value,
        "complexity_score": result.plan.complexity_score,
        "complexity_reasons": list(result.plan.complexity_reasons),
        "query_evidence_rubric": [
            slot.slot_id for slot in result.plan.required_slots if slot.required
        ],
        "method_evidence_hints": [
            slot.slot_id for slot in result.plan.method_hints
        ],
        "agent_search_triggered": result.agent_search_triggered,
        "stop_reason": result.stop_reason,
        "evidence_gate": evidence_gate_metadata(result.evidence_gate),
        "answer_evidence_accepted": (
            result.evidence_gate.decision is EvidenceDecision.SUPPORTED
        ),
        "accepted_evidence_ids": list(
            result.evidence_gate.accepted_evidence_ids
        ),
        "limits": {
            "max_search_rounds": result.plan.max_search_rounds,
            "max_queries": result.plan.max_queries,
        },
        "queries": [
            {
                "round": trace.round_number,
                "query": trace.query,
                "target_slot": trace.target_slot,
                "channel_counts": trace.channel_counts,
                "result_chunk_ids": list(trace.result_chunk_ids),
            }
            for trace in result.queries
        ],
    }


def _matching_results(
    slot: EvidenceSlotSpec,
    results: list[RetrievalResult],
    *,
    reference_date: date,
) -> list[RetrievalResult]:
    if slot.slot_id == "primary_evidence":
        candidates = results
    elif slot.slot_id == "comparison":
        candidates = results if len({result.document_id for result in results}) >= 2 else []
    elif slot.search_terms:
        required_terms = _search_terms(" ".join(slot.search_terms))
        candidates = [
            result
            for result in results
            if required_terms
            & _search_terms(
                " ".join((result.title, result.text, result.context_text or ""))
            )
        ]
    else:
        candidates = results
    if slot.freshness_days is None:
        return candidates
    fresh: list[RetrievalResult] = []
    for result in candidates:
        evidence_date = result.data_as_of_date or result.publication_date
        if evidence_date is None:
            continue
        age_days = (reference_date - evidence_date).days
        if 0 <= age_days <= slot.freshness_days:
            fresh.append(result)
    return fresh


def _merge_query_rankings(
    query_results: list[tuple[str, tuple[RetrievalResult, ...]]],
    *,
    limit: int,
) -> list[RetrievalResult]:
    scores: dict[int, float] = {}
    candidates: dict[int, RetrievalResult] = {}
    for target_slot, results in query_results:
        weight = 1.0 if target_slot == "primary_evidence" else 0.85
        for rank, result in enumerate(results, start=1):
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + weight / (
                60 + rank
            )
            candidates.setdefault(result.chunk_id, result)
    ranked = sorted(
        candidates.values(),
        key=lambda result: (-scores[result.chunk_id], result.chunk_id),
    )
    return ranked[:limit]


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    padded = f" {value} "
    return any(pattern in padded for pattern in patterns)


def _normalized_query(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _search_terms(value: str) -> set[str]:
    # Lazy import avoids a package-initialization cycle: style-pack schemas reuse
    # EvidenceSlotSpec while the hybrid retriever imports repository schemas.
    from investment_agent.retrieval.hybrid import _terms

    return _terms(value)
