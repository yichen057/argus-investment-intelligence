from __future__ import annotations

from investment_agent.retrieval.evidence_gate import EvidenceDecision, EvidenceGate
from investment_agent.retrieval.vector import RetrievalResult


def test_gate_accepts_complete_direct_causal_support() -> None:
    result = _result(
        1,
        (
            "Lower real yields reduce the opportunity cost of holding gold, which "
            "can strengthen investor demand for the metal."
        ),
    )

    gate = EvidenceGate().evaluate(
        "How do lower real yields affect gold?",
        [result],
        final_attempt=False,
    )

    assert gate.decision is EvidenceDecision.SUPPORTED
    assert gate.accepted_evidence_ids == (1,)
    assert "opportunity cost" in gate.accepted[0].supported_passage
    assert gate.follow_up_query is None


def test_gate_rejects_incomplete_fragment_even_when_keywords_overlap() -> None:
    result = _result(
        1,
        "Gold prices have rallied to records as real yields changed, and.",
    )

    gate = EvidenceGate().evaluate(
        "How do real yields affect gold prices?",
        [result],
        final_attempt=True,
    )

    assert gate.decision is EvidenceDecision.REFUSE
    assert gate.accepted == ()
    assert gate.gap_id == "causal_mechanism"
    assert gate.report_eligible is False


def test_gate_names_one_gap_and_one_targeted_follow_up() -> None:
    result = _result(1, "Gold prices reached a record nominal level in 2025.")

    gate = EvidenceGate().evaluate(
        "Why might gold benefit when real yields fall?",
        [result],
        final_attempt=False,
    )

    assert gate.decision is EvidenceDecision.GAP
    assert gate.gap_id == "causal_mechanism"
    assert len(gate.material_gaps) == 1
    assert gate.follow_up_query is not None
    assert "causal mechanism" in gate.follow_up_query


def test_gate_deduplicates_multiple_chunks_from_same_evidence_item() -> None:
    first = _result(
        1,
        "Lower real yields reduce the opportunity cost of holding gold.",
    )
    duplicate = _result(
        2,
        "Falling real yields can make non-yielding gold relatively more attractive.",
        evidence_item_id=1,
    )

    gate = EvidenceGate().evaluate(
        "How do lower real yields affect gold?",
        [first, duplicate],
        final_attempt=True,
    )

    assert gate.decision is EvidenceDecision.SUPPORTED
    assert gate.accepted_evidence_ids == (1,)
    assert len(gate.accepted) == 1


def test_gate_keeps_representative_chunks_for_explicit_document_summary() -> None:
    first = _result(
        1,
        "Meta's infrastructure teams need clearer ownership and stronger operating discipline.",
        match_signals=("document_summary",),
    )
    second = _result(
        2,
        "The document recommends resetting incentives, decision rights, and team culture.",
        evidence_item_id=1,
        match_signals=("document_summary",),
    )

    gate = EvidenceGate().evaluate(
        "总结上传的 Meta 文档并提炼文档要点",
        [first, second],
        final_attempt=True,
    )

    assert gate.decision is EvidenceDecision.SUPPORTED
    assert len(gate.accepted) == 2
    assert gate.accepted_evidence_ids == (1,)


def test_gate_never_uses_document_summary_exception_for_web_evidence() -> None:
    result = _result(
        1,
        "A public article discusses semiconductor factory capacity during the quarter.",
        match_signals=("document_summary",),
        source_type="web",
        document_id=-1,
    )

    gate = EvidenceGate().evaluate(
        "总结上传的 Meta 文档并提炼文档要点",
        [result],
        final_attempt=True,
    )

    assert gate.decision is EvidenceDecision.REFUSE
    assert gate.accepted == ()


def _result(
    chunk_id: int,
    text: str,
    *,
    evidence_item_id: int | None = None,
    match_signals: tuple[str, ...] = ("exact", "full_text"),
    source_type: str = "markdown",
    document_id: int = 1,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=document_id,
        evidence_item_id=evidence_item_id or chunk_id,
        score=0.9,
        text=text,
        source_uri="file:///gold.md",
        source_type=source_type,
        title="Gold and real yields",
        page_or_section="page 1",
        evidence_grade="source",
        excerpt=text,
        context_text=text,
        fused_score=0.04,
        match_signals=match_signals,
    )
