from __future__ import annotations

from dataclasses import dataclass

from investment_agent.research import EvidenceCritic


@dataclass(frozen=True)
class Source:
    evidence_id: int
    display_name: str
    excerpt: str


def test_critic_passes_supported_answer() -> None:
    review = EvidenceCritic().review_answer(
        answer=(
            "Gold demand strengthened as real yields fell and central banks "
            "bought more reserves."
        ),
        sources=(
            Source(
                evidence_id=1,
                display_name="gold.md",
                excerpt=(
                    "Gold demand strengthened as real yields fell and central "
                    "banks bought more reserves."
                ),
            ),
        ),
    )

    assert review.status == "passed"
    assert review.findings == ()


def test_critic_warns_no_evidence_answer_without_sources() -> None:
    review = EvidenceCritic().review_answer(
        answer="I could not find relevant local evidence for this question.",
        sources=(),
    )

    assert review.status == "warning"
    assert review.findings[0].code == "no_evidence_retrieved"


def test_critic_fails_claim_without_source() -> None:
    review = EvidenceCritic().review_answer(
        answer="ACME revenue improved because enterprise software margins expanded.",
        sources=(),
    )

    assert review.status == "failed"
    assert review.findings[0].code == "missing_source"


def test_critic_warns_when_answer_has_weak_source_overlap() -> None:
    review = EvidenceCritic().review_answer(
        answer="ACME revenue improved because enterprise software margins expanded.",
        sources=(
            Source(
                evidence_id=1,
                display_name="gold.md",
                excerpt="Gold demand strengthened as real yields fell.",
            ),
        ),
    )

    assert review.status == "warning"
    assert review.findings[0].code == "weak_source_overlap"


def test_critic_rejects_truncated_table_fragment() -> None:
    review = EvidenceCritic().review_answer(
        answer="Based on the source, Gold | sanctions | capital controls | Va...",
        sources=(
            Source(
                evidence_id=3,
                display_name="macro.md",
                excerpt="Gold and capital controls were discussed in the source.",
            ),
        ),
    )

    assert review.status == "warning"
    assert review.findings[0].code == "incomplete_answer"


def test_critic_rejects_sentence_ending_in_dangling_conjunction() -> None:
    review = EvidenceCritic().review_answer(
        answer="Gold rallied in nominal and real terms, and.",
        sources=(
            Source(
                evidence_id=4,
                display_name="gold.pdf",
                excerpt="Gold rallied in nominal and real terms, and",
            ),
        ),
    )

    assert review.status == "warning"
    assert review.findings[0].code == "incomplete_answer"
