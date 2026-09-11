from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from investment_agent.retrieval.policy import EvidenceSlotSpec


ResearchLens = Literal[
    "fundamentals",
    "valuation",
    "quality",
    "growth",
    "income",
    "macro",
    "momentum",
    "downside_risk",
    "diversification",
    "fees_and_taxes",
    "counter_evidence",
]
PortfolioPriority = Literal[
    "broad_diversification",
    "low_cost",
    "value_tilt",
    "quality_tilt",
    "growth_tilt",
    "income_tilt",
    "inflation_resilience",
    "capital_preservation",
    "liquidity",
]
ProductPreference = Literal[
    "broad_market_etf",
    "factor_etf",
    "dividend_etf",
    "bond_etf",
    "individual_stock_satellite",
]
ReportSection = Literal[
    "executive_summary",
    "thesis",
    "drivers",
    "valuation",
    "quality",
    "risks",
    "counter_evidence",
    "falsification",
    "portfolio_implications",
    "next_checks",
]


class StyleAllocationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equity_adjustment_points: float = Field(default=0.0, ge=-10.0, le=10.0)
    international_share_of_equity: float = Field(default=0.20, ge=0.15, le=0.40)
    gold_adjustment_points: float = Field(default=0.0, ge=-2.5, le=2.5)
    alternatives_points: float = Field(default=0.0, ge=0.0, le=5.0)


class StyleReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    principle: str = Field(min_length=1, max_length=500)
    url: str = Field(pattern=r"^https://", max_length=1000)


class MethodEvidenceSlot(BaseModel):
    """Declarative evidence requirement; it cannot raise Argus search budgets."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,47}$")
    description: str = Field(min_length=10, max_length=240)
    search_terms: list[str] = Field(default_factory=list, max_length=12)
    query_template: str = Field(min_length=10, max_length=240)
    minimum_items: int = Field(default=1, ge=1, le=5)
    minimum_distinct_sources: int = Field(default=1, ge=1, le=3)
    freshness_days: int | None = Field(default=None, ge=1, le=3650)
    required: bool = True

    @field_validator("search_terms")
    @classmethod
    def validate_search_terms(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 40 or "\n" in value for value in normalized):
            raise ValueError("Evidence slot search terms must be 1-40 characters.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Evidence slot search terms must be unique.")
        return normalized

    @field_validator("query_template")
    @classmethod
    def validate_query_template(cls, value: str) -> str:
        if value.count("{question}") != 1:
            raise ValueError("Evidence slot query template must contain {question} once.")
        remainder = value.replace("{question}", "")
        if "{" in remainder or "}" in remainder or "\n" in value:
            raise ValueError("Evidence slot query template contains unsupported syntax.")
        return value.strip()

    def to_spec(self) -> EvidenceSlotSpec:
        return EvidenceSlotSpec(
            slot_id=self.id,
            description=self.description,
            search_terms=tuple(self.search_terms),
            query_template=self.query_template,
            minimum_items=self.minimum_items,
            minimum_distinct_sources=self.minimum_distinct_sources,
            freshness_days=self.freshness_days,
            required=self.required,
        )


class StylePackDefinition(BaseModel):
    """A declarative, non-executable investment-analysis preference pack."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,47}$")
    name: str = Field(min_length=3, max_length=80)
    description: str = Field(min_length=10, max_length=500)
    research_lenses: list[ResearchLens] = Field(min_length=1, max_length=8)
    portfolio_priorities: list[PortfolioPriority] = Field(min_length=1, max_length=6)
    product_preferences: list[ProductPreference] = Field(min_length=1, max_length=5)
    report_section_order: list[ReportSection] = Field(min_length=5, max_length=9)
    allocation_policy: StyleAllocationPolicy = Field(
        default_factory=StyleAllocationPolicy
    )
    references: list[StyleReference] = Field(default_factory=list, max_length=8)
    required_evidence_slots: list[MethodEvidenceSlot] = Field(
        default_factory=list,
        max_length=8,
    )

    @field_validator(
        "research_lenses",
        "portfolio_priorities",
        "product_preferences",
        "report_section_order",
    )
    @classmethod
    def unique_ordered_values(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Style Pack list values must be unique.")
        return values

    @field_validator("required_evidence_slots")
    @classmethod
    def unique_evidence_slots(
        cls,
        values: list[MethodEvidenceSlot],
    ) -> list[MethodEvidenceSlot]:
        slot_ids = [value.id for value in values]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("Method Pack evidence slot IDs must be unique.")
        return values

    def prompt_context(self) -> str:
        """Return only controlled enum data for model prompts, never executable text."""

        return json.dumps(
            {
                "style_id": self.id,
                "style_name": self.name,
                "research_lenses": self.research_lenses,
                "portfolio_priorities": self.portfolio_priorities,
                "product_preferences": self.product_preferences,
                "report_section_order": self.report_section_order,
                "required_evidence_slots": [
                    slot.id for slot in self.required_evidence_slots
                ],
            },
            ensure_ascii=False,
        )

    def evidence_slot_specs(self) -> tuple[EvidenceSlotSpec, ...]:
        return tuple(slot.to_spec() for slot in self.required_evidence_slots)


class GeneralResearchStylePack(StylePackDefinition):
    """Internal neutral context; uploaded investment packs keep stricter fields."""

    portfolio_priorities: list[PortfolioPriority] = Field(default_factory=list, max_length=0)
    product_preferences: list[ProductPreference] = Field(default_factory=list, max_length=0)


_SEC_ALLOCATION = StyleReference(
    institution="U.S. SEC Investor.gov",
    title="Asset Allocation and Diversification",
    principle=(
        "Allocation is personal and should reflect time horizon and risk tolerance; "
        "diversification spreads risk across and within asset classes."
    ),
    url="https://www.investor.gov/introduction-investing/getting-started/asset-allocation",
)
_VANGUARD_PRINCIPLES = StyleReference(
    institution="Vanguard",
    title="Four principles for investing success",
    principle=(
        "A long-term plan should connect goals, a balanced diversified mix, low costs, "
        "and discipline."
    ),
    url=(
        "https://ownyourfuture.vanguard.com/content/en/learn/financial-planning/"
        "vanguards-4-principles-for-investing-success.html"
    ),
)
_MSCI_FACTORS = StyleReference(
    institution="MSCI",
    title="MSCI Factor Indexes",
    principle=(
        "Value, quality, yield, momentum, growth, and other factors are systematic "
        "equity characteristics with distinct definitions and risks."
    ),
    url="https://www.msci.com/indexes/factor-indexes/msci-factor-indexes",
)
_MSCI_QUALITY = StyleReference(
    institution="MSCI",
    title="Quality Indexes",
    principle=(
        "MSCI quality scores use profitability, earnings stability, and low financial "
        "leverage; a quality tilt is not a guarantee of outperformance."
    ),
    url="https://www.msci.com/indexes/group/quality-indexes",
)
_MSCI_DIVIDEND = StyleReference(
    institution="MSCI",
    title="Quality and High Dividend Yield Indexes",
    principle=(
        "High-dividend index construction can screen for dividend sustainability and "
        "persistence instead of selecting on headline yield alone."
    ),
    url=(
        "https://www.msci.com/indexes/factor-indexes/"
        "quality-and-high-dividend-yield-indexes"
    ),
)
_WGC_GOLD = StyleReference(
    institution="World Gold Council",
    title="Gold as a strategic asset: 2026 edition",
    principle=(
        "Its research discusses gold as a potential source of diversification and "
        "liquidity, while noting portfolio outcomes are hypothetical."
    ),
    url="https://www.gold.org/goldhub/research/relevance-of-gold-as-a-strategic-asset",
)


# This internal pack is intentionally not included in BUILTIN_STYLE_PACKS. It lets a
# public-web question remain auditable without silently imposing an investment style
# that the user did not select.
GENERAL_RESEARCH_STYLE_PACK = GeneralResearchStylePack(
    id="general_research",
    name="General evidence-first research",
    description=(
        "Neutral source-backed research without a selected investment framework, "
        "portfolio tilt, or product preference."
    ),
    research_lenses=["fundamentals", "downside_risk", "counter_evidence"],
    portfolio_priorities=[],
    product_preferences=[],
    report_section_order=[
        "executive_summary",
        "thesis",
        "drivers",
        "risks",
        "counter_evidence",
        "falsification",
        "next_checks",
    ],
)


BUILTIN_STYLE_PACKS: tuple[StylePackDefinition, ...] = (
    StylePackDefinition(
        id="strategic_index",
        name="Strategic index / diversified",
        description=(
            "Long-term, low-cost, broadly diversified core portfolio with disciplined "
            "rebalancing and explicit counter-evidence."
        ),
        research_lenses=[
            "fundamentals",
            "diversification",
            "fees_and_taxes",
            "downside_risk",
            "counter_evidence",
        ],
        portfolio_priorities=["broad_diversification", "low_cost"],
        product_preferences=["broad_market_etf", "bond_etf"],
        report_section_order=[
            "executive_summary",
            "thesis",
            "drivers",
            "risks",
            "counter_evidence",
            "falsification",
            "portfolio_implications",
            "next_checks",
        ],
        references=[_SEC_ALLOCATION, _VANGUARD_PRINCIPLES],
    ),
    StylePackDefinition(
        id="value_aware",
        name="Value-aware",
        description=(
            "Emphasizes valuation, fundamental durability, downside risk, and the "
            "possibility that an apparently cheap asset is a value trap."
        ),
        research_lenses=[
            "valuation",
            "fundamentals",
            "quality",
            "downside_risk",
            "counter_evidence",
        ],
        portfolio_priorities=[
            "broad_diversification",
            "low_cost",
            "value_tilt",
        ],
        product_preferences=["broad_market_etf", "factor_etf"],
        report_section_order=[
            "executive_summary",
            "valuation",
            "thesis",
            "drivers",
            "risks",
            "counter_evidence",
            "falsification",
            "portfolio_implications",
            "next_checks",
        ],
        allocation_policy=StyleAllocationPolicy(
            international_share_of_equity=0.25
        ),
        references=[_SEC_ALLOCATION, _MSCI_FACTORS],
    ),
    StylePackDefinition(
        id="quality_growth",
        name="Quality growth",
        description=(
            "Looks for durable growth supported by profitability, earnings stability, "
            "balance-sheet quality, valuation discipline, and falsification tests."
        ),
        research_lenses=[
            "growth",
            "quality",
            "fundamentals",
            "valuation",
            "downside_risk",
            "counter_evidence",
        ],
        portfolio_priorities=[
            "broad_diversification",
            "quality_tilt",
            "growth_tilt",
        ],
        product_preferences=[
            "broad_market_etf",
            "factor_etf",
            "individual_stock_satellite",
        ],
        report_section_order=[
            "executive_summary",
            "drivers",
            "thesis",
            "quality",
            "valuation",
            "risks",
            "counter_evidence",
            "falsification",
            "portfolio_implications",
        ],
        allocation_policy=StyleAllocationPolicy(equity_adjustment_points=5.0),
        references=[_SEC_ALLOCATION, _MSCI_QUALITY],
    ),
    StylePackDefinition(
        id="income_quality",
        name="Income with quality screens",
        description=(
            "Prioritizes sustainable income, balance-sheet strength, rate sensitivity, "
            "and total return rather than selecting securities on yield alone."
        ),
        research_lenses=[
            "income",
            "quality",
            "fundamentals",
            "downside_risk",
            "fees_and_taxes",
            "counter_evidence",
        ],
        portfolio_priorities=[
            "broad_diversification",
            "income_tilt",
            "capital_preservation",
        ],
        product_preferences=["dividend_etf", "bond_etf", "broad_market_etf"],
        report_section_order=[
            "executive_summary",
            "drivers",
            "thesis",
            "risks",
            "counter_evidence",
            "falsification",
            "portfolio_implications",
            "next_checks",
        ],
        allocation_policy=StyleAllocationPolicy(equity_adjustment_points=-5.0),
        references=[_SEC_ALLOCATION, _MSCI_DIVIDEND],
    ),
    StylePackDefinition(
        id="macro_risk_balanced",
        name="Macro / risk-balanced",
        description=(
            "Frames assets through growth, inflation, real rates, liquidity, and regime "
            "risk while retaining diversified strategic anchors."
        ),
        research_lenses=[
            "macro",
            "momentum",
            "diversification",
            "downside_risk",
            "counter_evidence",
        ],
        portfolio_priorities=[
            "broad_diversification",
            "inflation_resilience",
            "liquidity",
        ],
        product_preferences=["broad_market_etf", "bond_etf", "factor_etf"],
        report_section_order=[
            "executive_summary",
            "drivers",
            "thesis",
            "risks",
            "counter_evidence",
            "falsification",
            "portfolio_implications",
            "next_checks",
        ],
        allocation_policy=StyleAllocationPolicy(
            equity_adjustment_points=-5.0,
            international_share_of_equity=0.25,
            gold_adjustment_points=2.5,
        ),
        references=[_SEC_ALLOCATION, _WGC_GOLD],
    ),
)


BUILTIN_STYLE_BY_ID = {pack.id: pack for pack in BUILTIN_STYLE_PACKS}
DEFAULT_STYLE_PACK_ID = "strategic_index"

_LEGACY_STYLE_ALIASES = {
    "broad index / passive": "strategic_index",
    "growth": "quality_growth",
    "value": "value_aware",
    "dividend income": "income_quality",
    "macro / economic-cycle driven": "macro_risk_balanced",
    "macro": "macro_risk_balanced",
    "capital preservation": "income_quality",
    "not sure": "strategic_index",
}


def normalize_style_pack_id(value: str | None) -> str:
    normalized = " ".join(str(value or "").strip().lower().split())
    return _LEGACY_STYLE_ALIASES.get(normalized, normalized or DEFAULT_STYLE_PACK_ID)
