from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from math import floor
from typing import Mapping, Protocol
from urllib.parse import quote_plus

from investment_agent.portfolio.cash_planning import CashPlan, calculate_cash_plan
from investment_agent.portfolio.retirement_planning import (
    RetirementFundingPlan,
    calculate_retirement_funding_plan,
)


_SINGLE_POSITION_REVIEW_THRESHOLD = 0.25
_ASSET_CLASS_REVIEW_THRESHOLD = 0.70


class PositionLike(Protocol):
    symbol: str
    name: str
    asset_class: str
    quantity: float
    price: float
    market_value: float
    account: str | None
    as_of_date: date | None


class ProfileLike(Protocol):
    risk_tolerance: str
    investment_horizon: str | None
    preferred_style: str | None
    target_allocation_json: dict[str, float]
    monthly_net_income: float | None
    monthly_contribution: float | None
    monthly_sector_satellite_budget: float | None
    monthly_total_expenses: float | None
    primary_financial_priority: str | None
    rebalance_threshold: float
    allow_fractional_shares: bool
    rebalance_preference: str
    current_age: int | None
    planned_retirement_age: int | None
    retirement_planning_age: int
    retirement_monthly_spending: float | None
    retirement_monthly_income: float | None
    retirement_current_savings: float | None
    retirement_income_taxable: bool
    retirement_inflation_rate: float
    retirement_current_tax_rate: float | None
    retirement_tax_rate: float | None
    retirement_annual_return: float
    retirement_account_type: str | None
    retirement_taxable_withdrawal_share: float | None
    retirement_adjust_contributions_for_inflation: bool
    monthly_essential_expenses: float | None
    current_cash_savings: float | None
    emergency_fund_months: float
    emergency_fund_target_amount: float | None
    emergency_fund_build_months: int
    education_plan: str
    education_target_year: int | None
    education_target_amount: float | None
    near_term_goal_name: str | None
    near_term_goal_amount: float | None
    near_term_goal_months: int | None
    retirement_cash_months: float
    retirement_cash_target: float | None


@dataclass(frozen=True)
class AllocationSlice:
    asset_class: str
    market_value: float
    weight: float


@dataclass(frozen=True)
class ConcentrationFlag:
    code: str
    severity: str
    message: str
    symbol: str | None = None
    asset_class: str | None = None
    weight: float | None = None
    threshold: float | None = None
    excess_percentage_points: float | None = None


@dataclass(frozen=True)
class ScenarioSuggestion:
    scenario: str
    rationale: str


@dataclass(frozen=True)
class PortfolioPositionSummary:
    symbol: str
    name: str
    asset_class: str
    market_value: float
    weight: float


@dataclass(frozen=True)
class InvestmentCandidate:
    symbol: str
    name: str
    instrument_type: str
    asset_class: str
    portfolio_role: str
    rationale: str
    source_name: str
    source_url: str
    dca_eligible: bool
    satellite: bool = False
    candidate_category: str = "core"
    issuer: str = ""
    exposure_key: str = ""
    related_holdings: tuple[str, ...] = ()
    source_link_kind: str = "official_profile"
    source_link_note: str = "Official fund profile."
    source_checked_at: date | None = None


@dataclass(frozen=True)
class CandidateQuote:
    """Trusted provider quote used only to price an unheld approved candidate."""

    symbol: str
    price: float
    as_of_date: date | None
    source_name: str
    is_live: bool


@dataclass(frozen=True)
class RebalanceAction:
    action: str
    asset_class: str
    symbol: str | None
    name: str | None
    amount: float
    estimated_shares: float | None
    reference_price: float | None
    price_as_of_date: date | None
    current_weight: float
    target_weight: float
    drift: float
    reference_kind: str
    reference_label: str
    rationale: str
    warnings: tuple[str, ...]
    asset_description: str
    asset_url: str | None
    asset_source: str | None


@dataclass(frozen=True)
class ScenarioAllocation:
    asset_class: str
    market_value: float
    weight: float


@dataclass(frozen=True)
class ScenarioTrade:
    action: str
    asset_class: str
    symbol: str | None
    name: str | None
    amount: float
    estimated_shares: float | None
    reference_price: float | None
    price_as_of_date: date | None


@dataclass(frozen=True)
class RebalanceScenario:
    code: str
    title: str
    description: str
    rebalancing_amount: float
    projected_total_value: float
    projected_allocation: tuple[ScenarioAllocation, ...]
    trades: tuple[ScenarioTrade, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class CoverageGap:
    asset_class: str
    current_weight: float
    target_weight: float | None
    gap_amount: float | None
    rationale: str
    candidates: tuple[InvestmentCandidate, ...]


@dataclass(frozen=True)
class DcaSuggestion:
    asset_class: str
    symbol: str | None
    name: str | None
    monthly_amount: float
    estimated_shares: float | None
    reference_price: float | None
    price_as_of_date: date | None
    rationale: str
    warnings: tuple[str, ...]
    asset_description: str
    asset_url: str | None
    asset_source: str | None


@dataclass(frozen=True)
class RecommendationContext:
    status: str
    portfolio_as_of_date: date | None
    price_source: str
    generated_at: datetime
    live_market_data: bool
    analysis_method: str
    analysis_method_description: str
    policy: str
    disclaimer: str


@dataclass(frozen=True)
class PortfolioSummary:
    total_value: float
    positions: tuple[PortfolioPositionSummary, ...]
    allocation: tuple[AllocationSlice, ...]
    concentration_flags: tuple[ConcentrationFlag, ...]
    scenarios: tuple[ScenarioSuggestion, ...]
    rebalance_actions: tuple[RebalanceAction, ...]
    rebalance_scenarios: tuple[RebalanceScenario, ...]
    coverage_gaps: tuple[CoverageGap, ...]
    dca_suggestions: tuple[DcaSuggestion, ...]
    sector_candidates: tuple[InvestmentCandidate, ...]
    recommendation_context: RecommendationContext
    cash_plan: CashPlan
    retirement_plan: RetirementFundingPlan


_CANDIDATES = (
    InvestmentCandidate(
        symbol="VTI",
        name="Vanguard Total Stock Market ETF",
        instrument_type="ETF",
        asset_class="Equity",
        portfolio_role="Diversified U.S. equity core",
        rationale="Broad U.S. market exposure for a core allocation.",
        source_name="Vanguard fund profile",
        source_url="https://investor.vanguard.com/investment-products/etfs/profile/vti",
        dca_eligible=True,
    ),
    InvestmentCandidate(
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        instrument_type="ETF",
        asset_class="Equity",
        portfolio_role="Large-cap U.S. equity core",
        rationale="Tracks the S&P 500 and is intended for long-term growth goals.",
        source_name="Vanguard fund profile",
        source_url="https://investor.vanguard.com/investment-products/etfs/profile/voo",
        dca_eligible=True,
    ),
    InvestmentCandidate(
        symbol="QQQ",
        name="Invesco QQQ",
        instrument_type="ETF",
        asset_class="Equity",
        portfolio_role="Growth satellite",
        rationale=(
            "Nasdaq-100 exposure; treat as a concentrated growth tilt rather than "
            "a complete equity core."
        ),
        source_name="Invesco fund profile",
        source_url=(
            "https://www.invesco.com/us/financial-products/etfs/"
            "product-detail?productId=QQQ"
        ),
        dca_eligible=True,
        satellite=True,
    ),
    InvestmentCandidate(
        symbol="VXUS",
        name="Vanguard Total International Stock ETF",
        instrument_type="ETF",
        asset_class="International Equity",
        portfolio_role="Diversified non-U.S. equity sleeve",
        rationale="Broad international equity exposure outside the United States.",
        source_name="Vanguard fund profile",
        source_url="https://investor.vanguard.com/investment-products/etfs/profile/vxus",
        dca_eligible=True,
    ),
    InvestmentCandidate(
        symbol="BND",
        name="Vanguard Total Bond Market ETF",
        instrument_type="ETF",
        asset_class="Bond",
        portfolio_role="Diversified U.S. investment-grade bond core",
        rationale="Broad bond exposure for a target fixed-income allocation.",
        source_name="Vanguard fund profile",
        source_url="https://investor.vanguard.com/investment-products/etfs/profile/bnd",
        dca_eligible=True,
    ),
    InvestmentCandidate(
        symbol="GLD",
        name="SPDR Gold Shares",
        instrument_type="ETF",
        asset_class="Commodity / Gold",
        portfolio_role="Physically backed gold exposure",
        rationale=(
            "Tracks gold bullion less expenses; it is a commodity allocation, not "
            "an operating company or income-producing stock."
        ),
        source_name="SPDR Gold Shares fund profile",
        source_url="https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld",
        dca_eligible=True,
    ),
)


_STATE_STREET_FUND_DIRECTORY = "https://www.ssga.com/us/en/intermediary/fund-finder"
_STATE_STREET_SECTOR_SLUGS = {
    "XLC": "state-street-communication-services-select-sector-spdr-etf-xlc",
    "XLY": "state-street-consumer-discretionary-select-sector-spdr-etf-xly",
    "XLP": "state-street-consumer-staples-select-sector-spdr-etf-xlp",
    "XLE": "state-street-energy-select-sector-spdr-etf-xle",
    "XLF": "state-street-financial-select-sector-spdr-etf-xlf",
    "XLV": "state-street-health-care-select-sector-spdr-etf-xlv",
    "XLI": "state-street-industrial-select-sector-spdr-etf-xli",
    "XLB": "state-street-materials-select-sector-spdr-etf-xlb",
    "XLRE": "state-street-real-estate-select-sector-spdr-etf-xlre",
    "XLK": "state-street-technology-select-sector-spdr-etf-xlk",
    "XLU": "state-street-utilities-select-sector-spdr-etf-xlu",
}


def _state_street_fund_url(symbol: str) -> str:
    slug = _STATE_STREET_SECTOR_SLUGS.get(symbol.upper())
    if slug is None:
        return _STATE_STREET_FUND_DIRECTORY
    return f"https://www.ssga.com/us/en/intermediary/etfs/{slug}"


def _sector_candidate(symbol: str, name: str, sector: str) -> InvestmentCandidate:
    return InvestmentCandidate(
        symbol=symbol,
        name=name,
        instrument_type="ETF",
        asset_class="Equity",
        portfolio_role=f"{sector} sector research satellite",
        rationale=(
            f"Targeted {sector.lower()} exposure for research or a bounded satellite "
            "tilt; it is narrower than a diversified equity core."
        ),
        source_name=f"State Street {symbol} official fund profile",
        source_url=_state_street_fund_url(symbol),
        dca_eligible=False,
        satellite=True,
        candidate_category="sector_research",
        issuer="State Street",
        exposure_key=sector,
        source_link_kind="official_profile",
        source_link_note="Verified official fund profile.",
        source_checked_at=date(2026, 7, 20),
    )


def _industry_candidate(symbol: str, name: str, industry: str) -> InvestmentCandidate:
    return InvestmentCandidate(
        symbol=symbol,
        name=name,
        instrument_type="ETF",
        asset_class="Equity",
        portfolio_role=f"{industry} industry research satellite",
        rationale=(
            f"Targeted {industry.lower()} exposure for evidence-based research. It is "
            "more concentrated than both a broad-market fund and a broad sector fund."
        ),
        source_name="State Street ETF directory",
        source_url=_state_street_fund_url(symbol),
        dca_eligible=False,
        satellite=True,
        candidate_category="industry_research",
        issuer="State Street",
        exposure_key=industry,
        source_link_kind="issuer_directory",
        source_link_note=(
            f"The prior {symbol} shortcut did not resolve to a verified product page. "
            f"Open State Street's ETF directory and search for {symbol}."
        ),
        source_checked_at=date(2026, 7, 20),
    )


def _vanguard_sector_candidate(
    symbol: str,
    name: str,
    sector: str,
) -> InvestmentCandidate:
    return InvestmentCandidate(
        symbol=symbol,
        name=name,
        instrument_type="ETF",
        asset_class="Equity",
        portfolio_role=f"{sector} sector research satellite",
        rationale=(
            f"Broad U.S. {sector.lower()} sector exposure for comparison with other "
            "issuers in the same controlled peer group."
        ),
        source_name=f"Vanguard {symbol} official fund profile",
        source_url=(
            "https://investor.vanguard.com/investment-products/etfs/profile/"
            f"{symbol.lower()}"
        ),
        dca_eligible=False,
        satellite=True,
        candidate_category="sector_research",
        issuer="Vanguard",
        exposure_key=sector,
        source_link_kind="official_profile",
        source_link_note="Verified official fund profile.",
        source_checked_at=date(2026, 7, 20),
    )


_VANGUARD_SECTOR_CANDIDATES = (
    _vanguard_sector_candidate("VOX", "Vanguard Communication Services ETF", "Communication Services"),
    _vanguard_sector_candidate("VCR", "Vanguard Consumer Discretionary ETF", "Consumer Discretionary"),
    _vanguard_sector_candidate("VDC", "Vanguard Consumer Staples ETF", "Consumer Staples"),
    _vanguard_sector_candidate("VDE", "Vanguard Energy ETF", "Energy"),
    _vanguard_sector_candidate("VFH", "Vanguard Financials ETF", "Financials"),
    _vanguard_sector_candidate("VHT", "Vanguard Health Care ETF", "Health Care"),
    _vanguard_sector_candidate("VIS", "Vanguard Industrials ETF", "Industrials"),
    _vanguard_sector_candidate("VAW", "Vanguard Materials ETF", "Materials"),
    _vanguard_sector_candidate("VNQ", "Vanguard Real Estate ETF", "Real Estate"),
    _vanguard_sector_candidate("VGT", "Vanguard Information Technology ETF", "Technology"),
    _vanguard_sector_candidate("VPU", "Vanguard Utilities ETF", "Utilities"),
)


_SECTOR_CANDIDATES = (
    _sector_candidate(
        "XLC",
        "Communication Services Select Sector SPDR Fund",
        "Communication Services",
    ),
    _sector_candidate(
        "XLY",
        "Consumer Discretionary Select Sector SPDR Fund",
        "Consumer Discretionary",
    ),
    _sector_candidate(
        "XLP", "Consumer Staples Select Sector SPDR Fund", "Consumer Staples"
    ),
    _sector_candidate("XLE", "Energy Select Sector SPDR Fund", "Energy"),
    _sector_candidate("XLF", "Financial Select Sector SPDR Fund", "Financials"),
    _sector_candidate("XLV", "Health Care Select Sector SPDR Fund", "Health Care"),
    _sector_candidate("XLI", "Industrial Select Sector SPDR Fund", "Industrials"),
    _sector_candidate("XLB", "Materials Select Sector SPDR Fund", "Materials"),
    _sector_candidate("XLRE", "Real Estate Select Sector SPDR Fund", "Real Estate"),
    _sector_candidate("XLK", "Technology Select Sector SPDR Fund", "Technology"),
    _sector_candidate("XLU", "Utilities Select Sector SPDR Fund", "Utilities"),
    *_VANGUARD_SECTOR_CANDIDATES,
    _industry_candidate(
        "XAR", "SPDR S&P Aerospace & Defense ETF", "Aerospace & Defense"
    ),
    _industry_candidate("KBE", "SPDR S&P Bank ETF", "Banks"),
    _industry_candidate("XBI", "SPDR S&P Biotech ETF", "Biotechnology"),
    _industry_candidate("KCE", "SPDR S&P Capital Markets ETF", "Capital Markets"),
    _industry_candidate("XHB", "SPDR S&P Homebuilders ETF", "Homebuilders"),
    _industry_candidate(
        "XHE", "SPDR S&P Health Care Equipment ETF", "Health Care Equipment"
    ),
    _industry_candidate(
        "XHS", "SPDR S&P Health Care Services ETF", "Health Care Services"
    ),
    _industry_candidate("KIE", "SPDR S&P Insurance ETF", "Insurance"),
    _industry_candidate("XME", "SPDR S&P Metals & Mining ETF", "Metals & Mining"),
    _industry_candidate(
        "XES",
        "SPDR S&P Oil & Gas Equipment & Services ETF",
        "Oil & Gas Equipment & Services",
    ),
    _industry_candidate(
        "XOP", "SPDR S&P Oil & Gas Exploration & Production ETF", "Oil & Gas E&P"
    ),
    _industry_candidate("XPH", "SPDR S&P Pharmaceuticals ETF", "Pharmaceuticals"),
    _industry_candidate("KRE", "SPDR S&P Regional Banking ETF", "Regional Banks"),
    _industry_candidate("XRT", "SPDR S&P Retail ETF", "Retail"),
    _industry_candidate("XSD", "SPDR S&P Semiconductor ETF", "Semiconductors"),
    _industry_candidate(
        "XSW", "SPDR S&P Software & Services ETF", "Software & Services"
    ),
    _industry_candidate("XTL", "SPDR S&P Telecom ETF", "Telecom"),
    _industry_candidate("XTN", "SPDR S&P Transportation ETF", "Transportation"),
    InvestmentCandidate(
        symbol="SOXX",
        name="iShares Semiconductor ETF",
        instrument_type="ETF",
        asset_class="Equity",
        portfolio_role="Semiconductors industry research satellite",
        rationale=(
            "Targeted semiconductor value-chain exposure for evidence-based research; "
            "it is narrower and more concentrated than a broad technology or equity core."
        ),
        source_name="iShares Semiconductor ETF official profile",
        source_url=(
            "https://www.ishares.com/us/products/239705/ishares-semiconductor-etf"
        ),
        dca_eligible=False,
        satellite=True,
        candidate_category="industry_research",
        issuer="BlackRock / iShares",
        exposure_key="Semiconductors",
        source_link_kind="official_profile",
        source_link_note="Verified official fund profile.",
        source_checked_at=date(2026, 7, 20),
    ),
)


_DIRECT_STOCK_EXPOSURES: dict[str, tuple[str, ...]] = {
    "AAPL": ("Technology",),
    "MSFT": ("Technology",),
    "NVDA": ("Technology", "Semiconductors"),
    "AMD": ("Technology", "Semiconductors"),
    "AVGO": ("Technology", "Semiconductors"),
    "INTC": ("Technology", "Semiconductors"),
    "QCOM": ("Technology", "Semiconductors"),
    "TSM": ("Technology", "Semiconductors"),
    "GOOG": ("Communication Services",),
    "GOOGL": ("Communication Services",),
    "META": ("Communication Services",),
    "NFLX": ("Communication Services",),
    "AMZN": ("Consumer Discretionary",),
    "TSLA": ("Consumer Discretionary",),
    "HD": ("Consumer Discretionary", "Homebuilders"),
    "MCD": ("Consumer Discretionary",),
    "SBUX": ("Consumer Discretionary",),
    "PG": ("Consumer Staples",),
    "KO": ("Consumer Staples",),
    "PEP": ("Consumer Staples",),
    "COST": ("Consumer Staples",),
    "WMT": ("Consumer Staples",),
    "XOM": ("Energy", "Oil & Gas E&P"),
    "CVX": ("Energy", "Oil & Gas E&P"),
    "JPM": ("Financials", "Banks"),
    "BAC": ("Financials", "Banks"),
    "WFC": ("Financials", "Banks"),
    "GS": ("Financials", "Capital Markets"),
    "MS": ("Financials", "Capital Markets"),
    "BRK.B": ("Financials", "Insurance"),
    "BRK-B": ("Financials", "Insurance"),
    "PGR": ("Financials", "Insurance"),
    "JNJ": ("Health Care",),
    "UNH": ("Health Care", "Health Care Services"),
    "LLY": ("Health Care", "Pharmaceuticals"),
    "PFE": ("Health Care", "Pharmaceuticals"),
    "MRK": ("Health Care", "Pharmaceuticals"),
    "ABBV": ("Health Care", "Pharmaceuticals"),
    "BA": ("Industrials", "Aerospace & Defense"),
    "RTX": ("Industrials", "Aerospace & Defense"),
    "LMT": ("Industrials", "Aerospace & Defense"),
    "NOC": ("Industrials", "Aerospace & Defense"),
    "CAT": ("Industrials",),
    "GE": ("Industrials",),
    "HON": ("Industrials",),
    "LIN": ("Materials",),
    "APD": ("Materials",),
    "PLD": ("Real Estate",),
    "AMT": ("Real Estate", "Telecom"),
    "EQIX": ("Real Estate",),
    "NEE": ("Utilities",),
    "DUK": ("Utilities",),
    "SO": ("Utilities",),
}


def _sector_candidates_for_positions(
    positions: list[PositionLike],
) -> tuple[InvestmentCandidate, ...]:
    stock_symbols = {
        str(position.symbol).strip().upper()
        for position in positions
        if "etf" not in str(position.asset_class).lower()
    }
    return tuple(
        replace(
            candidate,
            related_holdings=tuple(
                sorted(
                    symbol
                    for symbol in stock_symbols
                    if candidate.exposure_key
                    in _DIRECT_STOCK_EXPOSURES.get(symbol, ())
                )
            ),
        )
        for candidate in _SECTOR_CANDIDATES
    )


def summarize_portfolio(
    positions: list[PositionLike],
    *,
    profile: ProfileLike | None = None,
    candidate_quotes: Mapping[str, CandidateQuote] | None = None,
) -> PortfolioSummary:
    normalized_candidate_quotes = {
        symbol.strip().upper(): quote
        for symbol, quote in (candidate_quotes or {}).items()
        if quote.price > 0
    }
    total_value = sum(float(position.market_value) for position in positions)
    position_summaries = tuple(
        PortfolioPositionSummary(
            symbol=position.symbol,
            name=position.name,
            asset_class=_display_asset_class(_position_class_key(position)),
            market_value=float(position.market_value),
            weight=_weight(float(position.market_value), total_value),
        )
        for position in sorted(
            positions,
            key=lambda item: item.market_value,
            reverse=True,
        )
    )
    allocation = _allocation(positions, total_value)
    investable_positions = [
        position
        for position in positions
        if _position_class_key(position) != _canonical_asset_class("Cash")
    ]
    investable_total = sum(
        float(position.market_value) for position in investable_positions
    )
    investable_summaries = tuple(
        PortfolioPositionSummary(
            symbol=position.symbol,
            name=position.name,
            asset_class=_display_asset_class(_position_class_key(position)),
            market_value=float(position.market_value),
            weight=_weight(float(position.market_value), investable_total),
        )
        for position in sorted(
            investable_positions,
            key=lambda item: item.market_value,
            reverse=True,
        )
    )
    investable_allocation = _allocation(investable_positions, investable_total)
    concentration_flags = _concentration_flags(
        investable_summaries, investable_allocation
    )
    rebalance_actions = _rebalance_actions(
        investable_positions,
        total_value=investable_total,
        concentration_flags=concentration_flags,
        profile=profile,
        candidate_quotes=normalized_candidate_quotes,
    )
    dca_suggestions = _dca_suggestions(
        investable_positions,
        total_value=investable_total,
        profile=profile,
        candidate_quotes=normalized_candidate_quotes,
    )
    context = _recommendation_context(
        positions,
        profile=profile,
        candidate_quotes=normalized_candidate_quotes,
    )
    return PortfolioSummary(
        total_value=total_value,
        positions=position_summaries,
        allocation=allocation,
        concentration_flags=concentration_flags,
        scenarios=_scenarios(
            allocation=investable_allocation,
            concentration_flags=concentration_flags,
            profile=profile,
        ),
        rebalance_actions=rebalance_actions,
        rebalance_scenarios=_rebalance_scenarios(
            investable_positions,
            total_value=investable_total,
            concentration_flags=concentration_flags,
            profile=profile,
            rebalance_actions=rebalance_actions,
            dca_suggestions=dca_suggestions,
        ),
        coverage_gaps=_coverage_gaps(
            investable_positions,
            total_value=investable_total,
            profile=profile,
        ),
        dca_suggestions=dca_suggestions,
        sector_candidates=_sector_candidates_for_positions(positions),
        recommendation_context=context,
        cash_plan=calculate_cash_plan(
            profile,
            as_of_date=context.portfolio_as_of_date or date.today(),
        ),
        retirement_plan=calculate_retirement_funding_plan(
            profile,
            current_invested_assets=investable_total,
        ),
    )


def _allocation(
    positions: list[PositionLike],
    total_value: float,
) -> tuple[AllocationSlice, ...]:
    totals: dict[str, float] = {}
    for position in positions:
        class_key = _position_class_key(position)
        totals[class_key] = totals.get(class_key, 0.0) + float(position.market_value)
    return tuple(
        AllocationSlice(
            asset_class=_display_asset_class(asset_class),
            market_value=value,
            weight=_weight(value, total_value),
        )
        for asset_class, value in sorted(
            totals.items(), key=lambda item: item[1], reverse=True
        )
    )


def _concentration_flags(
    positions: tuple[PortfolioPositionSummary, ...],
    allocation: tuple[AllocationSlice, ...],
) -> tuple[ConcentrationFlag, ...]:
    flags: list[ConcentrationFlag] = []
    for position in positions:
        if position.weight >= _SINGLE_POSITION_REVIEW_THRESHOLD:
            excess_percentage_points = (
                position.weight - _SINGLE_POSITION_REVIEW_THRESHOLD
            ) * 100
            flags.append(
                ConcentrationFlag(
                    code="single_position_concentration",
                    severity="warning",
                    message=(
                        f"{position.symbol} is {position.weight:.1%} of invested assets "
                        "after excluding cash, "
                        f"which is {excess_percentage_points:.1f} percentage points "
                        "above the Argus 25% single-holding concentration review "
                        "threshold. A large "
                        f"move in {position.symbol} can therefore have an outsized "
                        "effect on the portfolio. This concentration screen is separate "
                        "from the Profile rebalance drift threshold and is not an "
                        "automatic sell instruction."
                    ),
                    symbol=position.symbol,
                    weight=position.weight,
                    threshold=_SINGLE_POSITION_REVIEW_THRESHOLD,
                    excess_percentage_points=excess_percentage_points,
                )
            )
    for allocation_slice in allocation:
        if allocation_slice.weight >= _ASSET_CLASS_REVIEW_THRESHOLD:
            excess_percentage_points = (
                allocation_slice.weight - _ASSET_CLASS_REVIEW_THRESHOLD
            ) * 100
            flags.append(
                ConcentrationFlag(
                    code="asset_class_concentration",
                    severity="warning",
                    message=(
                        f"{allocation_slice.asset_class} is "
                        f"{allocation_slice.weight:.1%} of invested assets after "
                        "excluding cash, above the "
                        "Argus 70% asset-class concentration review threshold by "
                        f"{excess_percentage_points:.1f} percentage points. Results may "
                        "depend heavily on one part of the market. This concentration "
                        "screen is separate from the Profile rebalance drift threshold "
                        "and is not a personal suitability conclusion."
                    ),
                    asset_class=allocation_slice.asset_class,
                    weight=allocation_slice.weight,
                    threshold=_ASSET_CLASS_REVIEW_THRESHOLD,
                    excess_percentage_points=excess_percentage_points,
                )
            )
    return tuple(flags)


def _rebalance_actions(
    positions: list[PositionLike],
    *,
    total_value: float,
    concentration_flags: tuple[ConcentrationFlag, ...],
    profile: ProfileLike | None,
    candidate_quotes: Mapping[str, CandidateQuote],
) -> tuple[RebalanceAction, ...]:
    if total_value <= 0:
        return ()
    targets = _target_map(profile)
    if not targets:
        return _concentration_reviews(
            positions,
            total_value=total_value,
            concentration_flags=concentration_flags,
        )

    current = _current_totals(positions)
    threshold = float(getattr(profile, "rebalance_threshold", 0.05))
    allow_fractional = bool(getattr(profile, "allow_fractional_shares", False))
    preference = str(getattr(profile, "rebalance_preference", "contributions_first"))
    actions: list[RebalanceAction] = []
    class_keys = set(current) | set(targets)

    for class_key in sorted(class_keys):
        current_value = current.get(class_key, 0.0)
        target_label, target_weight = targets.get(
            class_key,
            (_display_asset_class(class_key), 0.0),
        )
        current_weight = _weight(current_value, total_value)
        drift = current_weight - target_weight
        if drift < threshold:
            continue
        remaining = max(0.0, current_value - (target_weight * total_value))
        class_positions = sorted(
            (
                position
                for position in positions
                if _position_class_key(position) == class_key
            ),
            key=lambda item: item.market_value,
            reverse=True,
        )
        for position in class_positions:
            if remaining <= 0.005:
                break
            requested = min(float(position.market_value), remaining)
            shares, executable_amount = _estimated_trade(
                requested,
                price=float(position.price),
                allow_fractional=allow_fractional,
            )
            warnings = list(_position_warnings(position))
            action = "SELL"
            amount = executable_amount
            rationale = (
                f"Reduce {target_label} from {current_weight:.1%} toward "
                f"the {target_weight:.1%} target. Argus starts with the largest "
                "holding in the overweight asset class to minimize trade count."
            )
            if shares is None:
                action = "REVIEW"
                amount = requested
                rationale = (
                    f"After the larger {target_label} reduction, only ${requested:,.2f} "
                    f"remains. That is below one whole {position.symbol} share at "
                    f"${float(position.price):,.2f}, so no {position.symbol} sale is "
                    "proposed unless fractional shares are enabled."
                )
                warnings.append(
                    "Rounding review only: this row is the small residual after the "
                    "larger sale, not a separate recommendation to reduce this holding."
                )
            if preference == "contributions_first":
                warnings.append(
                    "Apply planned contributions first and recalculate before selling."
                )
            actions.append(
                RebalanceAction(
                    action=action,
                    asset_class=target_label,
                    symbol=position.symbol,
                    name=position.name,
                    amount=amount,
                    estimated_shares=shares,
                    reference_price=float(position.price),
                    price_as_of_date=getattr(position, "as_of_date", None),
                    current_weight=current_weight,
                    target_weight=target_weight,
                    drift=drift,
                    reference_kind="policy_target",
                    reference_label="Saved Profile target",
                    rationale=rationale,
                    warnings=tuple(dict.fromkeys(warnings)),
                    asset_description=_held_asset_context(position, target_label)[0],
                    asset_url=_held_asset_context(position, target_label)[1],
                    asset_source=_held_asset_context(position, target_label)[2],
                )
            )
            remaining -= executable_amount if shares is not None else requested

    for class_key in sorted(class_keys):
        current_value = current.get(class_key, 0.0)
        target_label, target_weight = targets.get(
            class_key,
            (_display_asset_class(class_key), 0.0),
        )
        current_weight = _weight(current_value, total_value)
        drift = current_weight - target_weight
        if drift > -threshold:
            continue
        requested = max(0.0, (target_weight * total_value) - current_value)
        is_cash = class_key == _canonical_asset_class("Cash")
        candidate, held_position = (None, None)
        if not is_cash:
            candidate, held_position = _select_candidate(
                class_key,
                positions,
                profile=profile,
            )
        symbol = candidate.symbol if candidate else None
        name = (
            candidate.name
            if candidate
            else "Portfolio cash reserve"
            if is_cash
            else None
        )
        candidate_quote = _candidate_quote(candidate, candidate_quotes)
        price = (
            float(held_position.price)
            if held_position is not None
            else candidate_quote.price
            if candidate_quote is not None
            else None
        )
        price_date = (
            getattr(held_position, "as_of_date", None)
            if held_position is not None
            else candidate_quote.as_of_date
            if candidate_quote is not None
            else None
        )
        shares: float | None = None
        amount = requested
        warnings: list[str] = []
        if price is not None:
            shares, executable_amount = _estimated_trade(
                requested,
                price=price,
                allow_fractional=allow_fractional,
            )
            if shares is not None:
                amount = executable_amount
        elif symbol is not None:
            warnings.append(
                "No sourced quote is available for this candidate; fetch a current "
                "quote before converting the dollar target to shares."
            )
        if candidate is not None and candidate.satellite:
            warnings.append(
                "This is a satellite growth exposure, not a complete diversified core."
            )
        if is_cash:
            warnings.append(
                "Cash can mean uninvested brokerage cash or bank savings, CDs, "
                "Treasury bills, and money-market cash equivalents that you included "
                "in this portfolio. A brokerage-only upload does not include outside "
                "bank balances; no stock quote or share count is required."
            )
        actions.append(
            RebalanceAction(
                action="HOLD" if is_cash else "BUY",
                asset_class=target_label,
                symbol=symbol,
                name=name,
                amount=amount,
                estimated_shares=shares,
                reference_price=price,
                price_as_of_date=price_date,
                current_weight=current_weight,
                target_weight=target_weight,
                drift=drift,
                reference_kind="policy_target",
                reference_label="Saved Profile target",
                rationale=(
                    f"Keep ${amount:,.2f} liquid inside the chosen portfolio scope "
                    f"to move from {current_weight:.1%} toward the "
                    f"{target_weight:.1%} target."
                    if is_cash
                    else f"Increase {target_label} from {current_weight:.1%} toward "
                    f"the {target_weight:.1%} target."
                ),
                warnings=tuple(warnings),
                asset_description=(
                    f"{candidate.portfolio_role}. {candidate.rationale}"
                    if candidate is not None
                    else "No approved instrument is assigned to this asset class."
                ),
                asset_url=candidate.source_url if candidate is not None else None,
                asset_source=candidate.source_name if candidate is not None else None,
            )
        )
    return tuple(actions)


def _concentration_reviews(
    positions: list[PositionLike],
    *,
    total_value: float,
    concentration_flags: tuple[ConcentrationFlag, ...],
) -> tuple[RebalanceAction, ...]:
    flagged_symbols = {
        flag.symbol
        for flag in concentration_flags
        if flag.code == "single_position_concentration" and flag.symbol
    }
    reviews: list[RebalanceAction] = []
    for position in positions:
        if position.symbol not in flagged_symbols:
            continue
        current_weight = _weight(float(position.market_value), total_value)
        review_amount = max(0.0, float(position.market_value) - (0.20 * total_value))
        reference_price = float(getattr(position, "price", 0.0) or 0.0)
        shares, amount = _estimated_trade(
            review_amount,
            price=reference_price,
            allow_fractional=False,
        )
        reviews.append(
            RebalanceAction(
                action="REVIEW",
                asset_class=_display_asset_class(_position_class_key(position)),
                symbol=position.symbol,
                name=position.name,
                amount=amount if shares is not None else review_amount,
                estimated_shares=shares,
                reference_price=reference_price or None,
                price_as_of_date=getattr(position, "as_of_date", None),
                current_weight=current_weight,
                target_weight=0.20,
                drift=current_weight - 0.20,
                reference_kind="example_review_level",
                reference_label="Example review level — not your personal target",
                rationale=(
                    "Illustrates the amount above a 20% example review level. This "
                    "is not a personal target or an instruction to sell."
                ),
                warnings=_position_warnings(position),
                asset_description=_held_asset_context(
                    position,
                    _display_asset_class(_position_class_key(position)),
                )[0],
                asset_url=_held_asset_context(
                    position,
                    _display_asset_class(_position_class_key(position)),
                )[1],
                asset_source=_held_asset_context(
                    position,
                    _display_asset_class(_position_class_key(position)),
                )[2],
            )
        )
    return tuple(reviews)


def _coverage_gaps(
    positions: list[PositionLike],
    *,
    total_value: float,
    profile: ProfileLike | None,
) -> tuple[CoverageGap, ...]:
    if total_value <= 0:
        return ()
    current = _current_totals(positions)
    targets = _target_map(profile)
    threshold = float(getattr(profile, "rebalance_threshold", 0.05))
    gaps: list[CoverageGap] = []
    seen: set[str] = set()

    for class_key, (label, target_weight) in targets.items():
        current_value = current.get(class_key, 0.0)
        current_weight = _weight(current_value, total_value)
        gap_amount = max(0.0, (target_weight * total_value) - current_value)
        if target_weight - current_weight < threshold:
            continue
        gaps.append(
            CoverageGap(
                asset_class=label,
                current_weight=current_weight,
                target_weight=target_weight,
                gap_amount=gap_amount,
                rationale=(
                    f"The saved policy target is {target_weight:.1%}, versus "
                    f"{current_weight:.1%} currently."
                ),
                candidates=_candidates_for(class_key, profile=profile),
            )
        )
        seen.add(class_key)

    held_symbols = {position.symbol.upper() for position in positions}
    equity_key = _canonical_asset_class("Equity")
    if current.get(equity_key, 0.0) > 0 and not held_symbols.intersection(
        {"VTI", "VOO", "IVV", "SPY"}
    ):
        gaps.append(
            CoverageGap(
                asset_class="Diversified U.S. equity core",
                current_weight=_weight(current.get(equity_key, 0.0), total_value),
                target_weight=None,
                gap_amount=None,
                rationale=(
                    "No broad U.S. equity core ETF was identified by symbol. Review "
                    "whether individual positions are providing the intended "
                    "diversification."
                ),
                candidates=_candidates_for(equity_key, profile=profile),
            )
        )

    international_key = _canonical_asset_class("International Equity")
    horizon = str(getattr(profile, "investment_horizon", "") or "").lower()
    risk = str(getattr(profile, "risk_tolerance", "") or "").lower()
    if (
        "10+" in horizon
        and risk != "conservative"
        and current.get(international_key, 0.0) <= 0
        and not held_symbols.intersection({"VXUS", "IXUS", "VEA", "VWO"})
        and international_key not in seen
        and international_key not in targets
    ):
        gaps.append(
            CoverageGap(
                asset_class="International Equity review",
                current_weight=0.0,
                target_weight=None,
                gap_amount=None,
                rationale=(
                    "No international equity sleeve was identified. Decide whether it "
                    "belongs in the policy allocation before assigning an amount."
                ),
                candidates=_candidates_for(international_key, profile=profile),
            )
        )
    return tuple(gaps)


def _dca_suggestions(
    positions: list[PositionLike],
    *,
    total_value: float,
    profile: ProfileLike | None,
    candidate_quotes: Mapping[str, CandidateQuote],
) -> tuple[DcaSuggestion, ...]:
    total_monthly = float(getattr(profile, "monthly_contribution", 0.0) or 0.0)
    satellite_budget = min(
        total_monthly,
        float(getattr(profile, "monthly_sector_satellite_budget", 0.0) or 0.0),
    )
    monthly = max(0.0, total_monthly - satellite_budget)
    targets = _target_map(profile)
    if total_value <= 0 or monthly <= 0 or not targets:
        return ()
    allow_fractional = bool(getattr(profile, "allow_fractional_shares", False))
    current = _current_totals(positions)
    post_contribution_total = total_value + monthly
    deficits = {
        class_key: max(
            0.0,
            (target_weight * post_contribution_total) - current.get(class_key, 0.0),
        )
        for class_key, (_, target_weight) in targets.items()
    }
    positive_total = sum(deficits.values())
    if positive_total <= 0:
        deficits = {
            class_key: target_weight
            for class_key, (_, target_weight) in targets.items()
            if target_weight > 0
        }
        positive_total = sum(deficits.values())

    monthly_allocations = _whole_dollar_allocations(
        monthly,
        deficits,
        positive_total=positive_total,
    )

    suggestions: list[DcaSuggestion] = []
    for class_key, deficit in deficits.items():
        if deficit <= 0:
            continue
        monthly_amount = monthly_allocations.get(class_key, 0.0)
        if monthly_amount <= 0:
            continue
        label = targets[class_key][0]
        is_cash = class_key == _canonical_asset_class("Cash")
        candidate, held_position = (None, None)
        if not is_cash:
            candidate, held_position = _select_candidate(
                class_key,
                positions,
                profile=profile,
            )
        candidate_quote = _candidate_quote(candidate, candidate_quotes)
        price = (
            float(held_position.price)
            if held_position is not None
            else candidate_quote.price
            if candidate_quote is not None
            else None
        )
        price_date = (
            getattr(held_position, "as_of_date", None)
            if held_position is not None
            else candidate_quote.as_of_date
            if candidate_quote is not None
            else None
        )
        shares: float | None = None
        warnings: list[str] = []
        if price is not None:
            shares, executable_amount = _estimated_trade(
                monthly_amount,
                price=price,
                allow_fractional=allow_fractional,
            )
            if shares is not None and executable_amount + 0.005 < monthly_amount:
                warnings.append(
                    f"Whole-share execution uses ${executable_amount:,.0f}; keep the "
                    f"remaining ${monthly_amount - executable_amount:,.0f} for a later purchase."
                )
        elif candidate is not None:
            warnings.append(
                "Fetch a current quote before turning this monthly dollar amount into "
                "shares."
            )
        if candidate is not None and candidate.satellite:
            warnings.append(
                "QQQ is treated as a growth satellite; confirm a diversified core "
                "allocation first."
            )
        if is_cash:
            warnings.append(
                "Cash can mean uninvested brokerage cash or included bank savings, "
                "CDs, Treasury bills, and money-market cash equivalents. A "
                "brokerage-only upload does not include outside bank balances, and "
                "this line is not a stock purchase."
            )
        elif candidate is None and held_position is None:
            warnings.append(
                "No approved instrument is assigned to this target. Set the Profile "
                "target to 0% if you do not want this asset class."
            )
        suggestions.append(
            DcaSuggestion(
                asset_class=label,
                symbol=candidate.symbol if candidate else None,
                name=(
                    candidate.name
                    if candidate
                    else "Portfolio cash reserve"
                    if is_cash
                    else None
                ),
                monthly_amount=monthly_amount,
                estimated_shares=shares,
                reference_price=price,
                price_as_of_date=price_date,
                rationale=(
                    "Keep this amount liquid inside the chosen portfolio scope before "
                    "investing the remainder; it is not a stock purchase."
                    if is_cash
                    else f"Direct recurring contributions toward the {label} deficit "
                    "before considering sales."
                ),
                warnings=tuple(warnings),
                asset_description=(
                    f"{candidate.portfolio_role}. {candidate.rationale}"
                    if candidate is not None
                    else "No approved instrument is assigned to this asset class."
                ),
                asset_url=candidate.source_url if candidate is not None else None,
                asset_source=candidate.source_name if candidate is not None else None,
            )
        )
    return tuple(suggestions)


def _whole_dollar_allocations(
    monthly: float,
    deficits: dict[str, float],
    *,
    positive_total: float,
) -> dict[str, float]:
    total_dollars = int(floor(monthly + 0.5))
    positive = {
        class_key: deficit for class_key, deficit in deficits.items() if deficit > 0
    }
    if total_dollars <= 0 or positive_total <= 0 or not positive:
        return {}
    exact = {
        class_key: total_dollars * deficit / positive_total
        for class_key, deficit in positive.items()
    }
    allocated = {class_key: floor(amount) for class_key, amount in exact.items()}
    remaining = total_dollars - sum(allocated.values())
    ranked = sorted(
        positive,
        key=lambda class_key: (-(exact[class_key] - allocated[class_key]), class_key),
    )
    for class_key in ranked[:remaining]:
        allocated[class_key] += 1
    return {class_key: float(amount) for class_key, amount in allocated.items()}


def _rebalance_scenarios(
    positions: list[PositionLike],
    *,
    total_value: float,
    concentration_flags: tuple[ConcentrationFlag, ...],
    profile: ProfileLike | None,
    rebalance_actions: tuple[RebalanceAction, ...],
    dca_suggestions: tuple[DcaSuggestion, ...],
) -> tuple[RebalanceScenario, ...]:
    del concentration_flags, dca_suggestions
    current = _current_totals(positions)
    maintain = RebalanceScenario(
        code="maintain",
        title="Maintain current allocation",
        description="Make no trade and keep the uploaded snapshot allocation.",
        rebalancing_amount=0.0,
        projected_total_value=total_value,
        projected_allocation=_scenario_allocations(current, total_value),
        trades=(),
        limitations=(
            "Concentration and target drift remain unchanged.",
            "Weights will move as market prices change after the uploaded snapshot.",
        ),
    )
    dilute = _contribution_scenario(
        positions,
        current=current,
        total_value=total_value,
        profile=profile,
        rebalance_actions=rebalance_actions,
    )
    sell_and_reallocate = _sell_and_reallocate_scenario(
        current=current,
        total_value=total_value,
        profile=profile,
        rebalance_actions=rebalance_actions,
    )
    return (maintain, dilute, sell_and_reallocate)


def _contribution_scenario(
    positions: list[PositionLike],
    *,
    current: dict[str, float],
    total_value: float,
    profile: ProfileLike | None,
    rebalance_actions: tuple[RebalanceAction, ...],
) -> RebalanceScenario:
    targets = _target_map(profile)
    monthly = float(getattr(profile, "monthly_contribution", 0.0) or 0.0)
    contribution = monthly
    description = (
        "Apply one saved monthly contribution to underweight Profile targets."
        if monthly > 0 and targets
        else "Add new money instead of selling an existing holding."
    )
    limitations: list[str] = [
        "Projection uses uploaded snapshot prices; current quotes may produce different shares."
    ]

    if contribution <= 0 and targets:
        threshold = float(getattr(profile, "rebalance_threshold", 0.05))
        required_amounts = (
            [
                (current_value / target_weight) - total_value
                for class_key, (_, target_weight) in targets.items()
                if target_weight > 0
                and (current_value := current.get(class_key, 0.0)) / total_value
                >= target_weight + threshold
            ]
            if total_value > 0
            else []
        )
        contribution = max([0.0, *required_amounts])
        if contribution > 0:
            description = (
                "Shows the new money required to dilute the largest policy drift "
                "without selling."
            )
            limitations.append(
                "This may require much more cash than a normal monthly contribution."
            )

    if contribution <= 0 and not targets:
        review_actions = [
            action
            for action in rebalance_actions
            if action.reference_kind == "example_review_level"
            and action.current_weight > action.target_weight
        ]
        if review_actions:
            reference = max(review_actions, key=lambda item: item.current_weight)
            position_value = reference.current_weight * total_value
            contribution = max(
                0.0,
                (position_value / reference.target_weight) - total_value,
            )
            description = (
                f"Shows how much new money would dilute {reference.symbol} to the "
                "20% example review line without selling it."
            )
            limitations.extend(
                (
                    "The 20% line is an example review reference, not your personal target.",
                    "A destination asset is not selected until Profile targets are saved.",
                )
            )

    projected = dict(current)
    trades: list[ScenarioTrade] = []
    projected_total = total_value + contribution
    if contribution > 0 and targets:
        deficits = {
            class_key: max(
                0.0,
                (target_weight * projected_total) - current.get(class_key, 0.0),
            )
            for class_key, (_, target_weight) in targets.items()
        }
        denominator = sum(deficits.values())
        if denominator <= 0:
            deficits = {
                class_key: target_weight
                for class_key, (_, target_weight) in targets.items()
                if target_weight > 0
            }
            denominator = sum(deficits.values())
        allocated = 0.0
        positive_items = [item for item in deficits.items() if item[1] > 0]
        for index, (class_key, deficit) in enumerate(positive_items):
            amount = (
                contribution - allocated
                if index == len(positive_items) - 1
                else contribution * deficit / denominator
            )
            allocated += amount
            projected[class_key] = projected.get(class_key, 0.0) + amount
            is_cash = class_key == _canonical_asset_class("Cash")
            candidate, held_position = (None, None)
            if not is_cash:
                candidate, held_position = _select_candidate(
                    class_key,
                    positions,
                    profile=profile,
                )
            priced_action = next(
                (
                    action
                    for action in rebalance_actions
                    if candidate is not None
                    and action.symbol == candidate.symbol
                    and action.reference_price is not None
                ),
                None,
            )
            price = (
                float(held_position.price)
                if held_position is not None
                else priced_action.reference_price
                if priced_action is not None
                else None
            )
            price_as_of_date = (
                getattr(held_position, "as_of_date", None)
                if held_position is not None
                else priced_action.price_as_of_date
                if priced_action is not None
                else None
            )
            shares = _scenario_shares(
                amount,
                price=price,
                allow_fractional=bool(
                    getattr(profile, "allow_fractional_shares", False)
                ),
            )
            trades.append(
                ScenarioTrade(
                    action=(
                        "HOLD"
                        if is_cash
                        else "BUY"
                        if candidate is not None
                        else "UNASSIGNED"
                    ),
                    asset_class=targets[class_key][0],
                    symbol=candidate.symbol if candidate is not None else None,
                    name=(
                        candidate.name
                        if candidate is not None
                        else "Portfolio cash reserve"
                        if is_cash
                        else "No approved instrument assigned"
                    ),
                    amount=amount,
                    estimated_shares=shares,
                    reference_price=price,
                    price_as_of_date=price_as_of_date,
                )
            )
            if candidate is None and not is_cash:
                limitations.append(
                    f"{targets[class_key][0]} has a positive saved target but no "
                    "approved instrument; set it to 0% in Profile or assign one before investing."
                )
        limitations.append(
            "Allocation follows saved target deficits; taxes and transaction fees are excluded."
        )
    elif contribution > 0:
        projected["unallocated contribution"] = contribution
        trades.append(
            ScenarioTrade(
                action="CONTRIBUTE",
                asset_class="Destination not selected",
                symbol=None,
                name=None,
                amount=contribution,
                estimated_shares=None,
                reference_price=None,
                price_as_of_date=None,
            )
        )
    else:
        projected_total = total_value
        limitations.append(
            "No contribution amount can be calculated from the current settings."
        )

    return RebalanceScenario(
        code="new_contributions",
        title="Dilute with new contributions",
        description=description,
        rebalancing_amount=contribution,
        projected_total_value=projected_total,
        projected_allocation=_scenario_allocations(projected, projected_total),
        trades=tuple(trades),
        limitations=tuple(dict.fromkeys(limitations)),
    )


def _sell_and_reallocate_scenario(
    *,
    current: dict[str, float],
    total_value: float,
    profile: ProfileLike | None,
    rebalance_actions: tuple[RebalanceAction, ...],
) -> RebalanceScenario:
    targets = _target_map(profile)
    projected = dict(current)
    trades: list[ScenarioTrade] = []
    limitations: list[str] = [
        "Projection excludes taxes, tax-lot selection, fees, spreads, and market movement."
    ]
    available_proceeds = 0.0

    if targets:
        sell_actions = [
            action for action in rebalance_actions if action.action == "SELL"
        ]
        for action in sell_actions:
            class_key = _canonical_asset_class(action.asset_class)
            amount = min(action.amount, projected.get(class_key, 0.0))
            projected[class_key] = max(0.0, projected.get(class_key, 0.0) - amount)
            available_proceeds += amount
            trades.append(_scenario_trade_from_action(action, amount=amount))

        funding_actions = [
            action
            for action in rebalance_actions
            if action.action == "BUY"
            or (
                action.action == "HOLD"
                and _canonical_asset_class(action.asset_class)
                == _canonical_asset_class("Cash")
            )
        ]
        requested_funding = sum(action.amount for action in funding_actions)
        available_funding = min(available_proceeds, requested_funding)
        allocated_funding = 0.0
        remaining = available_proceeds
        for index, action in enumerate(funding_actions):
            if available_funding <= 0 or requested_funding <= 0:
                break
            amount = (
                available_funding - allocated_funding
                if index == len(funding_actions) - 1
                else available_funding * action.amount / requested_funding
            )
            allocated_funding += amount
            remaining -= amount
            class_key = _canonical_asset_class(action.asset_class)
            projected[class_key] = projected.get(class_key, 0.0) + amount
            trades.append(
                _scenario_trade_from_action(
                    action,
                    amount=amount,
                    allow_fractional=bool(
                        getattr(profile, "allow_fractional_shares", False)
                    ),
                )
            )
        if remaining > 0.005:
            projected["cash"] = projected.get("cash", 0.0) + remaining
            cash_trade_index = next(
                (
                    index
                    for index in range(len(trades) - 1, -1, -1)
                    if trades[index].action == "HOLD"
                    and _canonical_asset_class(trades[index].asset_class)
                    == _canonical_asset_class("Cash")
                ),
                None,
            )
            if cash_trade_index is None:
                trades.append(
                    ScenarioTrade(
                        action="HOLD",
                        asset_class="Cash",
                        symbol=None,
                        name="Unallocated sale proceeds",
                        amount=remaining,
                        estimated_shares=None,
                        reference_price=None,
                        price_as_of_date=None,
                    )
                )
            else:
                cash_trade = trades[cash_trade_index]
                trades[cash_trade_index] = ScenarioTrade(
                    action=cash_trade.action,
                    asset_class=cash_trade.asset_class,
                    symbol=cash_trade.symbol,
                    name=cash_trade.name,
                    amount=cash_trade.amount + remaining,
                    estimated_shares=None,
                    reference_price=None,
                    price_as_of_date=None,
                )
        if not sell_actions:
            limitations.append(
                "No policy-based sale crosses the saved drift threshold, so this scenario makes no trade."
            )
        if requested_funding > available_proceeds:
            limitations.append(
                "Sale proceeds fund only part of the underweight targets; additional cash would be required."
            )
        description = (
            "Partially sell overweight holdings and direct the proceeds to underweight "
            "saved Profile targets."
        )
    else:
        review_actions = sorted(
            (
                action
                for action in rebalance_actions
                if action.reference_kind == "example_review_level"
            ),
            key=lambda item: item.drift,
            reverse=True,
        )
        if review_actions:
            action = review_actions[0]
            class_key = _canonical_asset_class(action.asset_class)
            amount = min(action.amount, projected.get(class_key, 0.0))
            projected[class_key] = max(0.0, projected.get(class_key, 0.0) - amount)
            projected["reallocation proceeds"] = amount
            available_proceeds = amount
            trades.append(
                _scenario_trade_from_action(
                    action,
                    action_name="SELL (illustrative)",
                    amount=amount,
                )
            )
            trades.append(
                ScenarioTrade(
                    action="REALLOCATE",
                    asset_class="Destination not selected",
                    symbol=None,
                    name="Sale proceeds awaiting Profile targets",
                    amount=amount,
                    estimated_shares=None,
                    reference_price=None,
                    price_as_of_date=None,
                )
            )
            limitations.extend(
                (
                    "The 20% line is an example review reference, not your personal target.",
                    "The receiving asset and its share count require saved Profile targets and a current quote.",
                )
            )
        else:
            limitations.append(
                "No concentrated position triggered the example review line."
            )
        description = (
            "Illustrate a partial sale, while leaving the destination unassigned until "
            "you save a personal target allocation."
        )

    return RebalanceScenario(
        code="partial_sell_reallocate",
        title="Partially sell and reallocate",
        description=description,
        rebalancing_amount=available_proceeds,
        projected_total_value=total_value,
        projected_allocation=_scenario_allocations(projected, total_value),
        trades=tuple(trades),
        limitations=tuple(dict.fromkeys(limitations)),
    )


def _scenario_allocations(
    values: dict[str, float],
    total_value: float,
) -> tuple[ScenarioAllocation, ...]:
    return tuple(
        ScenarioAllocation(
            asset_class=_display_asset_class(class_key),
            market_value=value,
            weight=_weight(value, total_value),
        )
        for class_key, value in sorted(
            ((key, value) for key, value in values.items() if value > 0.005),
            key=lambda item: item[1],
            reverse=True,
        )
    )


def _scenario_trade_from_action(
    action: RebalanceAction,
    *,
    amount: float,
    action_name: str | None = None,
    allow_fractional: bool = False,
) -> ScenarioTrade:
    shares = action.estimated_shares
    if abs(amount - action.amount) > 0.005:
        shares = _scenario_shares(
            amount,
            price=action.reference_price,
            allow_fractional=allow_fractional,
        )
    return ScenarioTrade(
        action=action_name or action.action,
        asset_class=action.asset_class,
        symbol=action.symbol,
        name=action.name,
        amount=amount,
        estimated_shares=shares,
        reference_price=action.reference_price,
        price_as_of_date=action.price_as_of_date,
    )


def _scenario_shares(
    amount: float,
    *,
    price: float | None,
    allow_fractional: bool,
) -> float | None:
    if price is None:
        return None
    shares, _ = _estimated_trade(
        amount,
        price=price,
        allow_fractional=allow_fractional,
    )
    return shares


def _recommendation_context(
    positions: list[PositionLike],
    *,
    profile: ProfileLike | None,
    candidate_quotes: Mapping[str, CandidateQuote] | None = None,
) -> RecommendationContext:
    dates = [
        item
        for position in positions
        if (item := getattr(position, "as_of_date", None)) is not None
    ]
    source_keys = {
        str(source_key)
        for position in positions
        if (source_key := getattr(position, "source_key", None))
    }
    robinhood_only = source_keys == {"robinhood_mcp"}
    includes_robinhood = "robinhood_mcp" in source_keys
    targets = _target_map(profile)
    status = "snapshot_pricing"
    if not positions:
        status = "empty_portfolio"
    elif not targets:
        status = "target_allocation_required"
    policy = (
        "Amounts use your saved Profile targets and drift threshold. Market moves "
        "do not silently change those policy targets."
        if targets
        else (
            "The 20% concentration line is an example review reference, not your "
            "personal target. Save Profile targets before treating any amount as a "
            "policy-based trade."
        )
    )
    trusted_candidate_quotes = tuple((candidate_quotes or {}).values())
    live_candidate_quotes = tuple(
        quote for quote in trusted_candidate_quotes if quote.is_live
    )
    if live_candidate_quotes:
        price_source = "position_snapshot_with_live_candidate_quotes"
        provider_names = ", ".join(
            sorted({quote.source_name for quote in live_candidate_quotes})
        )
        analysis_input = (
            f"the active holdings snapshot and current read-only {provider_names} "
            "quotes for approved candidates not already held"
        )
    elif robinhood_only:
        price_source = "robinhood_mcp_snapshot"
        analysis_input = "the active Robinhood holdings snapshot"
    elif includes_robinhood:
        price_source = "mixed_position_snapshots"
        analysis_input = "the active mixed-source holdings snapshots"
    else:
        price_source = "uploaded_holdings"
        analysis_input = "the active uploaded holdings"
    return RecommendationContext(
        status=status,
        portfolio_as_of_date=max(dates) if dates else None,
        price_source=price_source,
        generated_at=datetime.now(timezone.utc),
        # Stored positions remain snapshots. Only approved unheld candidates may
        # receive a current read-only provider quote overlay.
        live_market_data=bool(live_candidate_quotes),
        analysis_method="deterministic_portfolio_rules",
        analysis_method_description=(
            "Reason / limits and amounts are calculated by deterministic Python "
            f"rules from {analysis_input} and saved Profile; the selected answer "
            "model does not change these numbers."
        ),
        policy=policy,
        disclaimer=(
            "Decision support only; review current quotes, taxes, fees, liquidity, "
            "and personal circumstances before trading."
        ),
    )


def _candidate_quote(
    candidate: InvestmentCandidate | None,
    candidate_quotes: Mapping[str, CandidateQuote],
) -> CandidateQuote | None:
    if candidate is None:
        return None
    return candidate_quotes.get(candidate.symbol.strip().upper())


def _scenarios(
    *,
    allocation: tuple[AllocationSlice, ...],
    concentration_flags: tuple[ConcentrationFlag, ...],
    profile: ProfileLike | None,
) -> tuple[ScenarioSuggestion, ...]:
    scenarios: list[ScenarioSuggestion] = []
    if concentration_flags:
        scenarios.append(
            ScenarioSuggestion(
                scenario="Reduce concentration",
                rationale="Review positions or asset classes above the risk threshold.",
            )
        )
    current = {
        _canonical_asset_class(item.asset_class): item.weight for item in allocation
    }
    for class_key, (label, target_weight) in _target_map(profile).items():
        current_weight = current.get(class_key, 0.0)
        if abs(current_weight - target_weight) >= float(
            getattr(profile, "rebalance_threshold", 0.05)
        ):
            scenarios.append(
                ScenarioSuggestion(
                    scenario="Rebalance toward target allocation",
                    rationale=(
                        f"{label} is {current_weight:.1%} versus a "
                        f"{target_weight:.1%} target."
                    ),
                )
            )
            break
    if not scenarios:
        scenarios.append(
            ScenarioSuggestion(
                scenario="Maintain current allocation",
                rationale="No saved drift or concentration threshold was triggered.",
            )
        )
    return tuple(scenarios)


def _target_map(
    profile: ProfileLike | None,
) -> dict[str, tuple[str, float]]:
    if profile is None:
        return {}
    raw_targets = getattr(profile, "target_allocation_json", {}) or {}
    return {
        _canonical_asset_class(label): (label, float(weight))
        for label, weight in raw_targets.items()
        if float(weight) >= 0
        and _canonical_asset_class(label) != _canonical_asset_class("Cash")
    }


def _current_totals(positions: list[PositionLike]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for position in positions:
        class_key = _position_class_key(position)
        totals[class_key] = totals.get(class_key, 0.0) + float(position.market_value)
    return totals


def _position_class_key(position: PositionLike) -> str:
    symbol = str(position.symbol).strip().upper()
    symbol_overrides = {
        "GLD": "commodity",
        "IAU": "commodity",
        "SLV": "commodity",
        "GDX": "commodity",
        "VXUS": "international equity",
        "IXUS": "international equity",
        "VEA": "international equity",
        "VWO": "international equity",
        "FLKR": "international equity",
        "BND": "bond",
        "AGG": "bond",
        "IEF": "bond",
        "TLT": "bond",
        "BIL": "bond",
        "SGOV": "bond",
        "CASH": "cash",
    }
    return symbol_overrides.get(symbol, _canonical_asset_class(position.asset_class))


def _canonical_asset_class(value: str) -> str:
    normalized = " ".join(value.strip().lower().replace("_", " ").split())
    aliases = {
        # Compatibility for snapshots imported before Robinhood position
        # direction was separated from asset classification.  ``long`` is not
        # a target-allocation class; these records came from the equity
        # positions endpoint and belong in Equity.
        "long": "equity",
        "long position": "equity",
        "stock": "equity",
        "stocks": "equity",
        "us stock": "equity",
        "us equity": "equity",
        "equity etf": "equity",
        "stock etf": "equity",
        "us equity etf": "equity",
        "fixed income": "bond",
        "bonds": "bond",
        "bond etf": "bond",
        "fixed income etf": "bond",
        "cash equivalent": "cash",
        "cash equivalents": "cash",
        "international stock": "international equity",
        "international stocks": "international equity",
        "international equity etf": "international equity",
        "non-us equity": "international equity",
        "non us equity": "international equity",
        "commodity / gold": "commodity",
        "commodity etf": "commodity",
        "commodities": "commodity",
        "gold": "commodity",
        "gold etf": "commodity",
        "precious metals": "commodity",
        "alternative": "alternatives",
        "alternative etf": "alternatives",
        "alternatives etf": "alternatives",
    }
    return aliases.get(normalized, normalized)


def _display_asset_class(class_key: str) -> str:
    labels = {
        "commodity": "Commodity / Gold",
        "international equity": "International Equity",
        "alternatives": "Alternatives",
    }
    return labels.get(class_key, class_key.title() if class_key else "Unclassified")


def _candidates_for(
    class_key: str,
    *,
    profile: ProfileLike | None,
) -> tuple[InvestmentCandidate, ...]:
    candidates = [
        candidate
        for candidate in _CANDIDATES
        if candidate.candidate_category == "core"
        and _canonical_asset_class(candidate.asset_class) == class_key
    ]
    style = str(getattr(profile, "preferred_style", "") or "").lower()
    if "growth" not in style:
        candidates.sort(key=lambda item: (item.satellite, item.symbol))
    return tuple(candidates)


def _select_candidate(
    class_key: str,
    positions: list[PositionLike],
    *,
    profile: ProfileLike | None,
) -> tuple[InvestmentCandidate | None, PositionLike | None]:
    candidates = _candidates_for(class_key, profile=profile)
    by_symbol = {position.symbol.upper(): position for position in positions}
    style = str(getattr(profile, "preferred_style", "") or "").lower()
    held_candidates = [
        candidate for candidate in candidates if candidate.symbol in by_symbol
    ]
    if held_candidates:
        if "growth" in style:
            held_candidates.sort(
                key=lambda item: (item.symbol != "QQQ", item.satellite, item.symbol)
            )
        else:
            held_candidates.sort(key=lambda item: (item.satellite, item.symbol))
        candidate = held_candidates[0]
        return candidate, by_symbol[candidate.symbol]
    if candidates:
        return candidates[0], None
    return None, None


def _estimated_trade(
    amount: float,
    *,
    price: float,
    allow_fractional: bool,
) -> tuple[float | None, float]:
    if amount <= 0 or price <= 0:
        return None, max(amount, 0.0)
    if allow_fractional:
        shares = round(amount / price, 4)
    else:
        shares = float(floor(amount / price))
    if shares <= 0:
        return None, amount
    return shares, round(shares * price, 2)


def _position_warnings(position: PositionLike) -> tuple[str, ...]:
    account = str(getattr(position, "account", "") or "").lower()
    if "taxable" in account or "brokerage" in account:
        return (
            "A sale in a taxable account may create capital gains or losses; tax-lot "
            "data is not available in this portfolio file.",
        )
    return ()


def _held_asset_context(
    position: PositionLike,
    asset_class: str,
) -> tuple[str, str, str]:
    candidate = next(
        (
            item
            for item in _CANDIDATES
            if item.symbol == str(position.symbol).strip().upper()
        ),
        None,
    )
    if candidate is not None:
        return (
            f"{candidate.portfolio_role}. {candidate.rationale}",
            candidate.source_url,
            candidate.source_name,
        )
    symbol = str(position.symbol).strip().upper()
    return (
        f"{position.name} is classified as {asset_class} in the uploaded holdings. "
        "Use the issuer's filings to review its business, risks, and disclosures.",
        f"https://www.sec.gov/edgar/search/#/q={quote_plus(symbol)}",
        "SEC EDGAR company and filing search",
    )


def _weight(value: float, total_value: float) -> float:
    if total_value <= 0:
        return 0.0
    return value / total_value
