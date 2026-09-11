from __future__ import annotations

from dataclasses import dataclass

from investment_agent.research import ClaimEvidence, ClaimGenerator
from investment_agent.research.claims import generate_structured_claims


@dataclass(frozen=True)
class Source:
    evidence_id: int
    display_name: str


def test_claim_generator_creates_supported_claim() -> None:
    claims = ClaimGenerator().generate(
        answer="Based on the strongest local source, Gold demand strengthened.",
        sources=(Source(evidence_id=7, display_name="gold.md"),),
    )

    assert len(claims) == 1
    assert claims[0].claim_text == "Gold demand strengthened."
    assert claims[0].evidence_ids == (7,)
    assert claims[0].relations == {"7": "supports"}
    assert claims[0].source_names == ("gold.md",)


def test_claim_generator_skips_no_evidence_answer() -> None:
    claims = ClaimGenerator().generate(
        answer="I could not find relevant local evidence for this question.",
        sources=(),
    )

    assert claims == ()


def test_claim_generator_cleans_markdown_heading_and_truncated_tail() -> None:
    claims = ClaimGenerator().generate(
        answer=(
            "Based on the strongest local source, # Gold And Real Yields "
            "Gold demand strengthened as real yields fell and central banks "
            "bought more reserves. Lower real yields can reduce the opportunity "
            "cost of holding gold, which may support investment demand when i..."
        ),
        sources=(Source(evidence_id=7, display_name="gold.md"),),
    )

    assert len(claims) == 1
    assert claims[0].claim_text == (
        "Gold demand strengthened as real yields fell and central banks bought "
        "more reserves."
    )


def test_external_claim_requires_its_own_explicit_citation() -> None:
    claims = generate_structured_claims(
        answer="Gold demand strengthened as real yields fell.",
        evidence=(
            ClaimEvidence(
                citation_id="W1",
                text="Gold demand strengthened as real yields fell.",
                display_name="Market note",
            ),
        ),
        require_explicit_citations=True,
    )

    assert len(claims) == 1
    assert claims[0].citation_ids == ()
    assert claims[0].verification.status == "unsupported"
    assert claims[0].verification.findings == ("missing_citation",)


def test_claim_numeric_verifier_preserves_currency_and_percent_units() -> None:
    claims = generate_structured_claims(
        answer="The allocation rose to 5% [source:W1].",
        evidence=(
            ClaimEvidence(
                citation_id="W1",
                text="The transaction cost was $5.",
                display_name="Cost note",
            ),
        ),
        require_explicit_citations=True,
    )

    assert claims[0].verification.status == "unsupported"
    assert "number_not_in_cited_evidence:5%" in claims[0].verification.findings


def test_structured_dataset_allows_header_defined_display_units() -> None:
    claims = generate_structured_claims(
        answer="Gold return rose to 19% in 2025 [source:E7].",
        evidence=(
            ClaimEvidence(
                citation_id="E7",
                text="year,gold_return_pct\n2025,19",
                display_name="gold.csv",
                structured_numeric=True,
            ),
        ),
        require_explicit_citations=True,
    )

    assert claims[0].verification.status == "supported"
