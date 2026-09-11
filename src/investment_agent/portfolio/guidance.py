from __future__ import annotations

from dataclasses import dataclass

from investment_agent.style_packs import (
    BUILTIN_STYLE_BY_ID,
    StylePackDefinition,
    normalize_style_pack_id,
)


@dataclass(frozen=True)
class ProfileGuidanceInput:
    risk_tolerance: str
    life_stage: str | None = None
    investment_horizon: str | None = None
    investing_experience: str | None = None
    income_stability: str | None = None
    liquidity_needs: str | None = None
    preferred_style: str | None = None
    style_pack: StylePackDefinition | None = None
    monthly_net_income: float | None = None
    monthly_contribution: float | None = None


@dataclass(frozen=True)
class GuidanceReference:
    institution: str
    title: str
    principle: str
    url: str


@dataclass(frozen=True)
class ProfileGuidance:
    target_allocation: dict[str, float]
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]
    contribution_rate: float | None
    references: tuple[GuidanceReference, ...]
    method: str = "deterministic_profile_guidance_v1"
    method_summary: str = (
        "Investor.gov and FINRA identify the decision factors; they do not prescribe "
        "these exact percentages. Argus applies its own educational example policy: "
        "start from the selected risk level, then adjust for time horizon, income "
        "stability, liquidity needs, life stage, style, and cash-flow warnings. "
        "Cash goals are calculated separately from the 100% investment mix."
    )
    disclaimer: str = (
        "Educational starting point only. Review goals, expenses, emergency savings, "
        "debts, taxes, and account constraints before saving it as policy."
    )


def guide_profile_allocation(payload: ProfileGuidanceInput) -> ProfileGuidance:
    risk = _normalized(payload.risk_tolerance)
    horizon = _normalized(payload.investment_horizon)
    experience = _normalized(payload.investing_experience)
    stability = _normalized(payload.income_stability)
    liquidity = _normalized(payload.liquidity_needs)
    life_stage = _normalized(payload.life_stage)
    style_pack = payload.style_pack or BUILTIN_STYLE_BY_ID[
        normalize_style_pack_id(payload.preferred_style)
    ]
    rationale: list[str] = []
    warnings: list[str] = []

    equity = {
        "conservative": 40.0,
        "moderate": 60.0,
        "aggressive": 80.0,
    }.get(risk, 55.0)
    if risk in {"conservative", "moderate", "aggressive"}:
        rationale.append(
            f"The {risk} risk setting starts the stock allocation at {equity:.0f}%."
        )
    else:
        warnings.append("Risk tolerance is missing or unrecognized; a neutral base was used.")

    if "under 3" in horizon:
        equity -= 25.0
        rationale.append("A horizon under three years reduces market-risk exposure.")
    elif "3-10" in horizon or "3 to 10" in horizon:
        equity -= 5.0
        rationale.append("A medium horizon keeps a balanced growth and stability mix.")
    elif "10+" in horizon or "over 10" in horizon:
        equity += 10.0
        rationale.append("A horizon over ten years allows more time to absorb volatility.")
    else:
        warnings.append("Set an investment horizon before relying on this starting mix.")

    if experience in {"no experience", "under 1 year"}:
        rationale.append(
            "Limited investing experience favors a simpler broad-fund implementation; "
            "it does not reduce the time horizon or automatically change risk capacity."
        )
    elif not experience:
        warnings.append(
            "Investing experience is not set; Argus cannot tailor the implementation "
            "complexity or education prompts."
        )

    if stability == "low":
        equity -= 10.0
        rationale.append("Low income stability reduces investment risk capacity.")
    elif stability == "high":
        equity += 5.0
        rationale.append("High income stability supports a modestly higher risk capacity.")
    elif not stability:
        warnings.append("Income stability is not set.")

    if "medical" in liquidity:
        equity -= 10.0
        rationale.append(
            "High medical or care liquidity needs reduce investment risk capacity."
        )
    elif liquidity == "high":
        equity -= 5.0
        rationale.append("High liquidity needs reduce investment risk capacity.")
    elif not liquidity:
        warnings.append("Liquidity needs are not set.")

    if life_stage == "student":
        equity -= 5.0
        rationale.append("Student status applies a small uncertainty buffer.")
    elif "family forming" in life_stage or "children at home" in life_stage:
        equity -= 5.0
        rationale.append("Near-term family obligations apply a small liquidity buffer.")
    elif "caregiver" in life_stage or "homemaker" in life_stage:
        equity -= 10.0
        rationale.append("Caregiving or homemaking applies an income-capacity buffer.")
    elif "children near or in college" in life_stage:
        equity -= 10.0
        rationale.append("Potential college spending reduces the starting risk level.")
    elif "pre-retirement" in life_stage:
        equity -= 15.0
        rationale.append("Pre-retirement reduces sequence-of-returns exposure.")
    elif "retired" in life_stage:
        equity -= 20.0
        rationale.append("Retirement increases the emphasis on stability and liquidity.")

    style_policy = style_pack.allocation_policy
    equity += style_policy.equity_adjustment_points
    if style_policy.equity_adjustment_points:
        direction = "adds" if style_policy.equity_adjustment_points > 0 else "removes"
        rationale.append(
            f"The {style_pack.name} Style Pack {direction} "
            f"{abs(style_policy.equity_adjustment_points):g} percentage points of "
            "equity exposure within its bounded policy."
        )
    else:
        rationale.append(
            f"The {style_pack.name} Style Pack changes the analysis lens without "
            "changing total equity exposure."
        )

    monthly_income = payload.monthly_net_income
    monthly_contribution = float(payload.monthly_contribution or 0.0)
    contribution_rate: float | None = None
    if monthly_income is not None:
        if monthly_income == 0:
            equity -= 10.0
            warnings.append(
                "No recurring net income was entered; prioritize near-term cash needs "
                "before committing a recurring investment amount."
            )
        elif monthly_income > 0:
            contribution_rate = monthly_contribution / monthly_income
            if contribution_rate > 0.50:
                warnings.append(
                    "The monthly contribution exceeds 50% of recurring net income; "
                    "review expenses and emergency savings."
                )
            elif contribution_rate > 0.25:
                warnings.append(
                    "The monthly contribution exceeds 25% of recurring net income; "
                    "confirm that it is sustainable after expenses."
                )
            elif monthly_contribution > 0:
                rationale.append(
                    f"The planned contribution is {contribution_rate:.1%} of recurring net income."
                )
    else:
        warnings.append(
            "Monthly net income is not set, so contribution affordability was not checked."
        )

    gold = {
        "conservative": 5.0,
        "moderate": 7.5,
        "aggressive": 10.0,
    }.get(risk, 5.0)
    gold = _clamp(gold + style_policy.gold_adjustment_points, 2.5, 12.5)
    rationale.append(
        f"Commodity / Gold starts at {gold:g}% within the World Gold Council's "
        "2.5%-10% hypothetical allocations; this is an Argus example policy, not "
        "a personal recommendation."
    )
    equity = _clamp(equity, 15.0, 85.0)
    alternatives = style_policy.alternatives_points
    if equity + gold + alternatives > 90.0:
        equity = 90.0 - gold - alternatives
    bond = 100.0 - equity - gold - alternatives
    international_equity = round(
        equity * style_policy.international_share_of_equity,
        1,
    )
    us_equity = round(equity - international_equity, 1)

    targets = {
        "Equity": us_equity / 100,
        "International Equity": international_equity / 100,
        "Bond": round(bond, 1) / 100,
        "Commodity / Gold": round(gold, 1) / 100,
        "Alternatives": round(alternatives, 1) / 100,
    }
    if alternatives == 0:
        warnings.append("Alternatives remains at 0% unless you explicitly opt in.")
    warnings.append(
        "Cash is intentionally outside this investment allocation. Use the separate "
        "cash-goal inputs for emergency, education, and retirement liquidity planning."
    )
    return ProfileGuidance(
        target_allocation=targets,
        rationale=tuple(rationale),
        warnings=tuple(warnings),
        contribution_rate=contribution_rate,
        references=_GUIDANCE_REFERENCES,
    )


def _normalized(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


_GUIDANCE_REFERENCES = (
    GuidanceReference(
        institution="World Gold Council",
        title="Gold as a strategic asset: 2026 edition",
        principle=(
            "Its hypothetical USD portfolio analysis tests 2.5%, 5%, 7.5%, and "
            "10% gold allocations and states that the suitable amount varies with "
            "the portfolio's risk and allocation decisions."
        ),
        url=(
            "https://www.gold.org/goldhub/research/relevance-of-gold-as-a-strategic-asset/"
            "portfolio-impact"
        ),
    ),
    GuidanceReference(
        institution="U.S. SEC Investor.gov",
        title="Asset Allocation and Diversification",
        principle=(
            "Asset allocation is personal and should reflect time horizon and risk "
            "tolerance; longer horizons may support more volatility."
        ),
        url=(
            "https://www.investor.gov/introduction-investing/getting-started/"
            "asset-allocation"
        ),
    ),
    GuidanceReference(
        institution="U.S. SEC Investor.gov",
        title="Beginner's Guide to Asset Allocation",
        principle=(
            "Cash equivalents can include savings deposits, CDs, Treasury bills, "
            "money-market deposit accounts, and money-market funds."
        ),
        url=(
            "https://www.investor.gov/additional-resources/general-resources/"
            "publications-research/info-sheets/beginners-guide-asset"
        ),
    ),
    GuidanceReference(
        institution="FINRA",
        title="Investment Strategies",
        principle=(
            "Strategy suitability can vary with age, income, assets, risk tolerance, "
            "family obligations, lifestyle, and other personal factors."
        ),
        url="https://www.finra.org/investors/investing/investing-basics/investment-strategies",
    ),
    GuidanceReference(
        institution="FINRA",
        title="Alternative and Emerging Products",
        principle=(
            "There is no single formal alternatives definition; examples can include "
            "real estate, commodities, private investments, and complex strategies."
        ),
        url=(
            "https://www.finra.org/investors/investing/investment-products/"
            "alternative-and-emerging-products"
        ),
    ),
)
