from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from investment_agent.retrieval.vector import RetrievalResult


class EvidenceDecision(StrEnum):
    """Authoritative outcome shared by retrieval, generation, and reporting."""

    SUPPORTED = "supported"
    GAP = "gap"
    REFUSE = "refuse"


@dataclass(frozen=True)
class AcceptedEvidence:
    result: RetrievalResult
    supported_passage: str


@dataclass(frozen=True)
class EvidenceGateResult:
    decision: EvidenceDecision
    accepted: tuple[AcceptedEvidence, ...]
    gap_id: str | None
    material_gaps: tuple[str, ...]
    follow_up_query: str | None
    report_eligible: bool
    reasons: tuple[str, ...]
    evaluated_candidate_count: int

    @property
    def accepted_evidence_ids(self) -> tuple[int, ...]:
        evidence_ids: list[int] = []
        for item in self.accepted:
            evidence_id = item.result.evidence_item_id
            if evidence_id is not None and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
        return tuple(evidence_ids)


class EvidenceGate:
    """Accept only passages that directly support the user's actual question.

    Retrieval scores rank candidates; they never prove support. This gate is the
    single deterministic contract used before a model call and before a report can
    consume evidence.
    """

    def evaluate(
        self,
        query: str,
        results: list[RetrievalResult],
        *,
        final_attempt: bool,
        method_query_hints: tuple[str, ...] = (),
    ) -> EvidenceGateResult:
        accepted: list[AcceptedEvidence] = []
        seen: set[tuple[str, int]] = set()
        for result in results:
            passage = _direct_support(result, query=query)
            if passage is None:
                continue
            # Normal fact lookup deduplicates chunks from the same evidence item
            # (usually one PDF page). A document summary is the deliberate exception:
            # several representative chunks from a long single page may all be needed
            # to summarize it without silently dropping most of the document.
            summary_chunk = (
                is_document_summary_query(query)
                and "document_summary" in result.match_signals
            )
            identity = (
                "chunk"
                if summary_chunk or result.evidence_item_id is None
                else "evidence",
                result.chunk_id
                if summary_chunk or result.evidence_item_id is None
                else result.evidence_item_id,
            )
            if identity in seen:
                continue
            seen.add(identity)
            accepted.append(AcceptedEvidence(result=result, supported_passage=passage))

        if accepted:
            return EvidenceGateResult(
                decision=EvidenceDecision.SUPPORTED,
                accepted=tuple(accepted),
                gap_id=None,
                material_gaps=(),
                follow_up_query=None,
                report_eligible=_report_eligible(accepted),
                reasons=(
                    "At least one complete passage directly overlaps the question.",
                    "Requested years, when present, are covered by the accepted passage.",
                ),
                evaluated_candidate_count=len(results),
            )

        gap_id, gap_message, query_template = _material_gap(query)
        follow_up_query = None
        if not final_attempt:
            hint = method_query_hints[0] if method_query_hints else query_template
            follow_up_query = hint.format(question=query)
            follow_up_query = re.sub(r"\s+", " ", follow_up_query).strip()
            if follow_up_query.lower() == query.strip().lower():
                follow_up_query = query_template.format(question=query)

        return EvidenceGateResult(
            decision=(
                EvidenceDecision.REFUSE if final_attempt else EvidenceDecision.GAP
            ),
            accepted=(),
            gap_id=gap_id,
            material_gaps=(gap_message,),
            follow_up_query=follow_up_query,
            report_eligible=False,
            reasons=(
                "Retrieved candidates did not contain a complete passage that directly supports the question.",
            ),
            evaluated_candidate_count=len(results),
        )


def evidence_gate_metadata(result: EvidenceGateResult) -> dict[str, object]:
    return {
        "decision": result.decision.value,
        "accepted_evidence_ids": list(result.accepted_evidence_ids),
        "material_gaps": list(result.material_gaps),
        "follow_up_query": result.follow_up_query,
        "report_eligible": result.report_eligible,
        "reasons": list(result.reasons),
        "evaluated_candidate_count": result.evaluated_candidate_count,
    }


def tool_result_passes_evidence_gate(tool_result: Any) -> bool:
    if getattr(tool_result, "status", None) != "ok":
        return False
    output = getattr(tool_result, "output", {})
    if not isinstance(output, dict):
        return False
    search = output.get("search")
    if not isinstance(search, dict):
        return False
    gate = search.get("evidence_gate")
    return isinstance(gate, dict) and gate.get("decision") == "supported"


def _direct_support(result: RetrievalResult, *, query: str) -> str | None:
    # Imported lazily to keep the evidence contract independent from provider
    # package initialization. The deterministic passage/CSV extractors are shared
    # implementation details; no model is called here.
    from investment_agent.providers.mock import (
        _answer_from_csv_result,
        _result_covers_requested_years,
        _supported_passage,
    )

    row = _result_mapping(result)
    if result.source_type == "csv":
        return _answer_from_csv_result(row, query=query)
    if not _result_covers_requested_years(row, query=query):
        return None

    text = result.text.strip()
    context = (result.context_text or "").strip()
    primary = context if len(context) > len(text) else text
    # A bounded document-summary request is different from a fact lookup: the user
    # asks what the selected upload says, so requiring Chinese/English keyword overlap
    # with every source paragraph would incorrectly reject the document itself. Only
    # the dedicated local summary channel may use this exception; public-web results
    # and ordinary questions still need direct lexical support.
    if is_document_summary_query(query) and "document_summary" in result.match_signals:
        if result.source_type == "web" or result.document_id <= 0:
            return None
        return _supported_passage(primary, query="")
    passage = _supported_passage(primary, query=query)
    if passage is None and context and context != text:
        passage = _supported_passage(text, query=query)
    return passage


def is_document_summary_query(query: str) -> bool:
    """Return True only for explicit requests to summarize source material."""

    normalized = " ".join(query.lower().split())
    return bool(
        re.search(
            r"\b(summar(?:y|ize|ise|ized|ised)|key points?|main points?|"
            r"executive summary|recap)\b",
            normalized,
        )
        or re.search(r"(总结|概括|摘要|提炼.{0,8}要点|文档要点|文件要点)", query)
    )


def _result_mapping(result: RetrievalResult) -> dict[str, Any]:
    return {
        "source_type": result.source_type,
        "text": result.text,
        "context": result.context_text,
        "title": result.title,
        "publication_date": (
            result.publication_date.isoformat()
            if result.publication_date is not None
            else None
        ),
        "data_as_of_date": (
            result.data_as_of_date.isoformat()
            if result.data_as_of_date is not None
            else None
        ),
    }


def _material_gap(query: str) -> tuple[str, str, str]:
    lowered = f" {query.lower()} "
    if _contains_any(
        lowered,
        (
            " why ",
            " how do ",
            " how does ",
            " how did ",
            " impact ",
            " influence ",
            " driver ",
            "原因",
            "影响",
        ),
    ):
        return (
            "causal_mechanism",
            "No complete passage directly explains the requested causal mechanism.",
            "causal mechanism linking cause to outcome {question}",
        )
    if _contains_any(
        lowered,
        (" compare ", " versus ", " vs ", " difference ", "对比", "比较"),
    ):
        return (
            "comparison",
            "No accepted evidence directly compares the requested alternatives.",
            "direct comparison differences alternatives {question}",
        )
    if _contains_any(
        lowered,
        (" current ", " latest ", " today ", " now ", "当前", "最新"),
    ):
        return (
            "current_context",
            "No accepted time-stamped passage supports the requested current context.",
            "latest dated primary evidence {question}",
        )
    if _contains_any(
        lowered,
        (" risk ", " downside ", " uncertain ", "风险", "下行"),
    ):
        return (
            "risk",
            "No complete passage directly identifies the requested downside or risk.",
            "downside risk limitation evidence {question}",
        )
    return (
        "direct_support",
        "No complete passage directly supports the requested claim.",
        "direct evidence answering {question}",
    )


def _report_eligible(accepted: list[AcceptedEvidence]) -> bool:
    if any(item.result.source_type == "csv" for item in accepted):
        return True
    combined = " ".join(item.supported_passage for item in accepted)
    word_count = len(re.findall(r"\b[\w'-]+\b", combined))
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", combined))
    # The Evidence Gate only grants an evidence-level eligibility signal. The
    # report endpoint still applies answer completeness and critic checks.
    return word_count >= 18 or cjk_count >= 24 or len(accepted) >= 2


def _contains_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in value for pattern in patterns)
