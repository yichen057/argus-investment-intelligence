from __future__ import annotations

import pytest

from investment_agent.portfolio import (
    ProfileGuidanceInput,
    guide_profile_allocation,
)


def test_guidance_uses_horizon_income_stability_and_liquidity() -> None:
    cautious = guide_profile_allocation(
        ProfileGuidanceInput(
            risk_tolerance="moderate",
            life_stage="Student",
            investment_horizon="Under 3 years",
            investing_experience="No experience",
            income_stability="Low",
            liquidity_needs="High",
            preferred_style="Capital preservation",
            monthly_net_income=0,
            monthly_contribution=500,
        )
    )
    long_term = guide_profile_allocation(
        ProfileGuidanceInput(
            risk_tolerance="moderate",
            life_stage="Early career, single",
            investment_horizon="10+ years",
            income_stability="High",
            liquidity_needs="Low",
            preferred_style="Broad index / passive",
            monthly_net_income=5000,
            monthly_contribution=500,
        )
    )

    assert sum(cautious.target_allocation.values()) == pytest.approx(1.0)
    assert sum(long_term.target_allocation.values()) == pytest.approx(1.0)
    assert "Cash" not in cautious.target_allocation
    assert "Cash" not in long_term.target_allocation
    cautious_equity = (
        cautious.target_allocation["Equity"]
        + cautious.target_allocation["International Equity"]
    )
    long_term_equity = (
        long_term.target_allocation["Equity"]
        + long_term.target_allocation["International Equity"]
    )
    assert cautious_equity < long_term_equity
    assert cautious.target_allocation["Commodity / Gold"] == pytest.approx(0.075)
    assert cautious.target_allocation["Alternatives"] == 0
    assert any("No recurring net income" in item for item in cautious.warnings)
    assert any("simpler broad-fund" in item for item in cautious.rationale)
    assert long_term.contribution_rate == pytest.approx(0.1)
    assert "do not prescribe these exact percentages" in long_term.method_summary
    assert {reference.institution for reference in long_term.references} == {
        "U.S. SEC Investor.gov",
        "FINRA",
        "World Gold Council",
    }


def test_guidance_warns_when_contribution_is_high_relative_to_income() -> None:
    guidance = guide_profile_allocation(
        ProfileGuidanceInput(
            risk_tolerance="moderate",
            investment_horizon="10+ years",
            investing_experience="7+ years",
            income_stability="Moderate",
            liquidity_needs="Moderate",
            monthly_net_income=1000,
            monthly_contribution=600,
        )
    )

    assert guidance.contribution_rate == pytest.approx(0.6)
    assert any("exceeds 50%" in item for item in guidance.warnings)
