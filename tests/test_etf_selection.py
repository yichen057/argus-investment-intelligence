from datetime import datetime, timezone
from types import SimpleNamespace

from investment_agent.portfolio.etf_selection import (
    DETERMINISTIC_AUDITOR_VERSION,
    DETERMINISTIC_SELECTION_VERSION,
    EtfSelectionResult,
    audit_etf_selection,
    select_etf_candidates,
)


NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)


def _candidate(
    symbol: str,
    exposure: str,
    *,
    related_holdings: tuple[str, ...] = (),
    category: str = "industry_research",
):
    return SimpleNamespace(
        symbol=symbol,
        name=f"{exposure} ETF",
        candidate_category=category,
        exposure_key=exposure,
        related_holdings=related_holdings,
        source_url=f"https://issuer.example/{symbol.lower()}",
    )


def _row(citation_id: str, text: str, *, domain: str = "sec.gov"):
    return {
        "citation_id": citation_id,
        "title": text,
        "supported_passage": text,
        "source_uri": f"https://{domain}/research/{citation_id.lower()}",
        "publication_date": "2026-07-19",
        "retrieved_at": NOW.isoformat(),
    }


def _profile():
    return SimpleNamespace(
        risk_tolerance="aggressive",
        investment_horizon="10+ years",
        investing_experience="3-7 years",
        liquidity_needs="low",
        preferred_style="macro",
        monthly_sector_satellite_budget=200,
    )


def test_fixed_selector_scores_and_ranks_candidate_specific_evidence() -> None:
    candidates = [
        _candidate("XSD", "Semiconductors", related_holdings=("NVDA",)),
        _candidate("XBI", "Biotechnology"),
    ]
    positions = [SimpleNamespace(symbol="NVDA", market_value=10_000)]
    evidence = [
        _row(
            "W1",
            "XSD semiconductor demand growth is resilient; expense ratio is 0.35% "
            "and the fund remains liquid, although elevated valuation is a downside risk.",
        ),
        _row(
            "W2",
            "XBI biotechnology earnings revisions rose and liquidity remains strong; "
            "expense ratio is 0.35%, but policy uncertainty is a headwind.",
            domain="spglobal.com",
        ),
    ]

    result = select_etf_candidates(
        candidates=candidates,
        positions=positions,
        profile=_profile(),
        evidence_rows=evidence,
        generated_at=NOW,
    )

    assert result.version == DETERMINISTIC_SELECTION_VERSION
    assert [item.rank for item in result.decisions] == list(
        range(1, len(result.decisions) + 1)
    )
    assert {item.symbol for item in result.decisions} == {"XSD", "XBI"}
    xsd = next(item for item in result.decisions if item.symbol == "XSD")
    assert xsd.recommendation_mode == "diversifying_replacement"
    assert xsd.dca_suitable is False
    assert dict(xsd.score_components)["profile_holdings_fit"] == 25.0
    assert dict(xsd.score_components)["timestamped_market_signal"] > 0
    assert dict(xsd.score_components)["evidence_quality"] == 17.0
    assert "expense_ratio_missing" not in dict(xsd.penalties)

    audit = audit_etf_selection(
        result,
        candidates=candidates,
        positions=positions,
        allowed_citation_ids={"W1", "W2"},
    )
    assert audit.status == "passed"
    assert audit.version == DETERMINISTIC_AUDITOR_VERSION


def test_peer_group_requires_symbol_specific_evidence_and_records_missing_data() -> None:
    candidates = [
        _candidate("XSD", "Semiconductors"),
        _candidate("SOXX", "Semiconductors"),
    ]
    result = select_etf_candidates(
        candidates=candidates,
        positions=[],
        profile=_profile(),
        evidence_rows=[
            _row(
                "W1",
                "Semiconductor demand growth remains resilient, but valuations are elevated.",
            )
        ],
        generated_at=NOW,
    )

    assert result.decisions == ()
    assert all(not item.eligible for item in result.outcomes)
    assert all(
        "no_candidate_specific_accepted_evidence" in item.validation_codes
        for item in result.outcomes
    )


def test_independent_auditor_rejects_tampered_rank_order() -> None:
    candidate = _candidate("XBI", "Biotechnology")
    result = select_etf_candidates(
        candidates=[candidate],
        positions=[],
        profile=_profile(),
        evidence_rows=[
            _row(
                "W1",
                "XBI biotechnology demand growth is resilient and the ETF is liquid; "
                "expense ratio is 0.35% while valuation risk remains.",
            )
        ],
        generated_at=NOW,
    )
    decision = result.decisions[0]
    tampered = EtfSelectionResult(
        decisions=(
            type(decision)(
                **{**decision.__dict__, "rank": 2},
            ),
        ),
        outcomes=result.outcomes,
    )

    audit = audit_etf_selection(
        tampered,
        candidates=[candidate],
        positions=[],
        allowed_citation_ids={"W1"},
    )

    assert audit.status == "failed"
    assert "non_contiguous_rank" in audit.codes
