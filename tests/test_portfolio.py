from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from io import BytesIO

import pytest
from openpyxl import Workbook

from investment_agent.portfolio import (
    CandidateQuote,
    HoldingRow,
    parse_holdings_bytes,
    parse_holdings_csv,
    summarize_portfolio,
)


@dataclass(frozen=True)
class Profile:
    risk_tolerance: str
    target_allocation_json: dict[str, float]
    investment_horizon: str | None = None
    preferred_style: str | None = None
    monthly_net_income: float | None = None
    monthly_contribution: float | None = None
    monthly_sector_satellite_budget: float | None = None
    monthly_total_expenses: float | None = None
    primary_financial_priority: str | None = None
    rebalance_threshold: float = 0.05
    allow_fractional_shares: bool = False
    rebalance_preference: str = "contributions_first"
    current_age: int | None = None
    planned_retirement_age: int | None = None
    monthly_essential_expenses: float | None = None
    current_cash_savings: float | None = None
    emergency_fund_months: float = 6.0
    emergency_fund_target_amount: float | None = None
    emergency_fund_build_months: int = 12
    education_plan: str = "none"
    education_target_year: int | None = None
    education_target_amount: float | None = None
    near_term_goal_name: str | None = None
    near_term_goal_amount: float | None = None
    near_term_goal_months: int | None = None
    cash_goals_json: list[dict[str, object]] = field(default_factory=list)
    retirement_planning_age: int = 100
    retirement_monthly_spending: float | None = None
    retirement_monthly_income: float | None = None
    retirement_current_savings: float | None = None
    retirement_income_taxable: bool = True
    retirement_inflation_rate: float = 0.025
    retirement_current_tax_rate: float | None = None
    retirement_tax_rate: float | None = None
    retirement_annual_return: float = 0.05
    retirement_account_type: str | None = "taxable_brokerage"
    retirement_taxable_withdrawal_share: float | None = None
    retirement_adjust_contributions_for_inflation: bool = False
    retirement_cash_months: float = 0.0
    retirement_cash_target: float | None = None


def test_parse_holdings_csv_and_summarize_portfolio(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text(
        "\n".join(
            [
                "symbol,name,asset_class,quantity,price,market_value,cost_basis,account",
                "AAPL,Apple Inc,Equity,10,200,2000,1500,Taxable",
                "BND,Vanguard Bond ETF,Bond,20,50,1000,950,IRA",
                "CASH,Cash Sweep,Cash,1,500,500,500,Taxable",
            ]
        ),
        encoding="utf-8",
    )

    holdings = parse_holdings_csv(source)
    summary = summarize_portfolio(
        holdings,
        profile=Profile(
            risk_tolerance="conservative",
            target_allocation_json={"Equity": 0.5, "Bond": 0.5},
        ),
    )

    assert len(holdings) == 3
    assert holdings[0].symbol == "AAPL"
    assert summary.total_value == 3500
    assert summary.positions[0].symbol == "AAPL"
    assert summary.positions[0].weight == pytest.approx(2000 / 3500)
    assert summary.allocation[0].asset_class == "Equity"
    assert summary.allocation[0].weight == pytest.approx(2000 / 3500)
    assert summary.concentration_flags[0].code == "single_position_concentration"
    assert summary.concentration_flags[0].threshold == 0.25
    assert summary.concentration_flags[0].excess_percentage_points == pytest.approx(
        (2000 / 3000 - 0.25) * 100
    )
    assert (
        "invested assets after excluding cash" in summary.concentration_flags[0].message
    )
    assert (
        "25% single-holding concentration review threshold"
        in summary.concentration_flags[0].message
    )
    assert (
        "separate from the Profile rebalance drift threshold"
        in summary.concentration_flags[0].message
    )
    assert "not an automatic sell instruction" in summary.concentration_flags[0].message
    assert {scenario.scenario for scenario in summary.scenarios} >= {
        "Reduce concentration",
        "Rebalance toward target allocation",
    }
    assert len(summary.sector_candidates) == 41
    assert {candidate.symbol for candidate in summary.sector_candidates} >= {
        "XLK",
        "XLV",
        "XLE",
        "XLF",
        "SOXX",
        "XAR",
        "XBI",
        "XSD",
        "XTN",
        "KCE",
        "KIE",
        "KRE",
        "XES",
        "VGT",
        "VCR",
    }
    assert all(
        candidate.candidate_category in {"sector_research", "industry_research"}
        and not candidate.dca_eligible
        for candidate in summary.sector_candidates
    )
    xlks = [
        candidate
        for candidate in summary.sector_candidates
        if candidate.exposure_key == "Technology"
    ]
    assert {candidate.symbol for candidate in xlks} == {"XLK", "VGT"}
    assert all(candidate.related_holdings == ("AAPL",) for candidate in xlks)
    assert all(candidate.source_url.startswith("https://") for candidate in xlks)
    xsd = next(
        candidate for candidate in summary.sector_candidates if candidate.symbol == "XSD"
    )
    assert xsd.source_link_kind == "issuer_directory"
    assert xsd.source_url == "https://www.ssga.com/us/en/intermediary/fund-finder"
    assert "search for XSD" in xsd.source_link_note
    xlb = next(
        candidate for candidate in summary.sector_candidates if candidate.symbol == "XLB"
    )
    assert xlb.source_link_kind == "official_profile"
    assert xlb.source_url.endswith("state-street-materials-select-sector-spdr-etf-xlb")


def test_asset_class_concentration_uses_explicit_seventy_percent_threshold() -> None:
    positions = [
        HoldingRow("EQ1", "Equity 1", "Equity", 1, 24, 24, None, None, None),
        HoldingRow("EQ2", "Equity 2", "Equity", 1, 23, 23, None, None, None),
        HoldingRow("EQ3", "Equity 3", "Equity", 1, 23, 23, None, None, None),
        HoldingRow("B1", "Bond 1", "Bond", 1, 15, 15, None, None, None),
        HoldingRow("B2", "Bond 2", "Bond", 1, 15, 15, None, None, None),
    ]

    summary = summarize_portfolio(positions)

    assert len(summary.concentration_flags) == 1
    flag = summary.concentration_flags[0]
    assert flag.code == "asset_class_concentration"
    assert flag.asset_class == "Equity"
    assert flag.weight == pytest.approx(0.70)
    assert flag.threshold == 0.70
    assert flag.excess_percentage_points == pytest.approx(0.0)


def test_parse_holdings_csv_requires_expected_columns(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text("symbol,market_value\nAAPL,2000\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing columns"):
        parse_holdings_csv(source)


def test_parse_holdings_xlsx_preserves_numeric_cells() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Holdings"
    worksheet.append(
        [
            "symbol",
            "name",
            "asset_class",
            "quantity",
            "price",
            "market_value",
            "cost_basis",
            "account",
        ]
    )
    worksheet.append(["AAPL", "Apple Inc", "Equity", 10, 200, 2000, 1500, "Taxable"])
    worksheet.append(["BND", "Vanguard Bond ETF", "Bond", 20, 50, 1000, None, "IRA"])
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()

    holdings = parse_holdings_bytes(
        filename="holdings.xlsx",
        raw_content=buffer.getvalue(),
    )

    assert len(holdings) == 2
    assert holdings[0].symbol == "AAPL"
    assert holdings[0].market_value == 2000
    assert holdings[1].cost_basis is None


def test_parse_holdings_rejects_unsupported_file_type() -> None:
    with pytest.raises(ValueError, match="must use one of"):
        parse_holdings_bytes(filename="holdings.numbers", raw_content=b"not empty")


def test_parse_holdings_preserves_one_snapshot_date() -> None:
    content = "\n".join(
        [
            (
                "symbol,name,asset_class,quantity,price,market_value,cost_basis,"
                "account,as_of_date"
            ),
            "VOO,Vanguard S&P 500 ETF,Equity,5,600,3000,2500,IRA,2026-07-10",
            "BND,Vanguard Bond ETF,Bond,10,75,750,700,IRA,2026-07-10",
        ]
    ).encode()

    holdings = parse_holdings_bytes(filename="holdings.csv", raw_content=content)

    assert {holding.as_of_date for holding in holdings} == {date(2026, 7, 10)}


def test_parse_holdings_rejects_mixed_snapshot_dates() -> None:
    content = "\n".join(
        [
            (
                "symbol,name,asset_class,quantity,price,market_value,cost_basis,"
                "account,as_of_date"
            ),
            "VOO,Vanguard S&P 500 ETF,Equity,5,600,3000,2500,IRA,2026-07-10",
            "BND,Vanguard Bond ETF,Bond,10,75,750,700,IRA,2026-07-11",
        ]
    ).encode()

    with pytest.raises(ValueError, match="multiple as_of_date"):
        parse_holdings_bytes(filename="holdings.csv", raw_content=content)


def test_rebalance_actions_include_amounts_shares_gaps_and_dca(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text(
        "\n".join(
            [
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,"
                    "account,as_of_date"
                ),
                "AAPL,Apple Inc,Equity,10,200,2000,1500,Taxable,2026-07-10",
                "BND,Vanguard Bond ETF,Bond,20,50,1000,950,IRA,2026-07-10",
                "CASH,Cash Sweep,Cash,1,500,500,500,Taxable,2026-07-10",
            ]
        ),
        encoding="utf-8",
    )
    holdings = parse_holdings_csv(source)

    summary = summarize_portfolio(
        holdings,
        profile=Profile(
            risk_tolerance="moderate",
            investment_horizon="10+ years",
            preferred_style="Broad index / passive",
            target_allocation_json={"Equity": 0.5, "Bond": 0.5},
            monthly_contribution=500,
        ),
    )

    aapl_sell = next(
        action
        for action in summary.rebalance_actions
        if action.action == "SELL" and action.symbol == "AAPL"
    )
    bnd_buy = next(
        action
        for action in summary.rebalance_actions
        if action.action == "BUY" and action.symbol == "BND"
    )
    assert aapl_sell.amount == 400
    assert aapl_sell.estimated_shares == 2
    assert aapl_sell.price_as_of_date == date(2026, 7, 10)
    assert any("taxable" in warning.lower() for warning in aapl_sell.warnings)
    assert bnd_buy.amount == 500
    assert bnd_buy.estimated_shares == 10
    assert any("U.S. equity core" in gap.asset_class for gap in summary.coverage_gaps)
    assert any(item.symbol == "BND" for item in summary.dca_suggestions)
    assert sum(item.monthly_amount for item in summary.dca_suggestions) == 500
    assert all(item.monthly_amount.is_integer() for item in summary.dca_suggestions)
    assert all(item.asset_class != "Cash" for item in summary.dca_suggestions)
    assert all(action.asset_class != "Cash" for action in summary.rebalance_actions)
    assert summary.cash_plan.status == "inputs_required"
    assert bnd_buy.asset_url is not None
    assert "bond" in bnd_buy.asset_description.lower()
    contribution_scenario = next(
        scenario
        for scenario in summary.rebalance_scenarios
        if scenario.code == "new_contributions"
    )
    assert all(trade.asset_class != "Cash" for trade in contribution_scenario.trades)
    assert not summary.recommendation_context.live_market_data


def test_unheld_candidate_uses_trusted_market_quote_for_shares() -> None:
    summary = summarize_portfolio(
        [
            HoldingRow(
                "AAPL",
                "Apple Inc",
                "Equity",
                10,
                200,
                2000,
                1500,
                "Taxable",
                date(2026, 7, 21),
            )
        ],
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={"Equity": 0.5, "Bond": 0.5},
            monthly_contribution=500,
        ),
        candidate_quotes={
            "BND": CandidateQuote(
                symbol="BND",
                price=100,
                as_of_date=date(2026, 7, 22),
                source_name="Robinhood Market Data",
                is_live=True,
            )
        },
    )

    bnd_buy = next(
        action for action in summary.rebalance_actions if action.symbol == "BND"
    )
    bnd_dca = next(item for item in summary.dca_suggestions if item.symbol == "BND")
    contribution_scenario = next(
        scenario
        for scenario in summary.rebalance_scenarios
        if scenario.code == "new_contributions"
    )
    bnd_contribution = next(
        trade for trade in contribution_scenario.trades if trade.symbol == "BND"
    )

    assert bnd_buy.reference_price == 100
    assert bnd_buy.estimated_shares == 10
    assert bnd_buy.price_as_of_date == date(2026, 7, 22)
    assert not any("No sourced quote" in warning for warning in bnd_buy.warnings)
    assert bnd_dca.reference_price == 100
    assert bnd_dca.estimated_shares == 5
    assert bnd_contribution.reference_price == 100
    assert bnd_contribution.estimated_shares == 5
    assert bnd_contribution.price_as_of_date == date(2026, 7, 22)
    assert summary.recommendation_context.live_market_data is True
    assert summary.recommendation_context.price_source == (
        "position_snapshot_with_live_candidate_quotes"
    )


def test_equity_etf_alias_counts_toward_equity_target(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text(
        "\n".join(
            [
                "symbol,name,asset_class,quantity,price,market_value,cost_basis,account",
                "QQQ,Invesco QQQ,Equity ETF,10,500,5000,4000,IRA",
            ]
        ),
        encoding="utf-8",
    )

    summary = summarize_portfolio(
        parse_holdings_csv(source),
        profile=Profile(
            risk_tolerance="aggressive",
            target_allocation_json={"Equity": 1.0},
        ),
    )

    assert summary.rebalance_actions == ()


def test_legacy_robinhood_long_direction_counts_toward_equity_target() -> None:
    summary = summarize_portfolio(
        [
            HoldingRow(
                symbol="AAPL",
                name="Apple",
                asset_class="Long",
                quantity=10,
                price=200,
                market_value=2000,
                cost_basis=1500,
                account="Robinhood",
                as_of_date=date(2026, 7, 21),
            )
        ],
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={"Equity": 1.0},
        ),
    )

    assert summary.allocation[0].asset_class == "Equity"
    assert summary.rebalance_actions == ()


def test_whole_share_rounding_residual_is_not_a_second_sell_recommendation() -> None:
    positions = [
        HoldingRow(
            "QQQ",
            "Invesco QQQ",
            "Equity",
            73,
            410,
            30000,
            None,
            None,
            date(2026, 7, 18),
        ),
        HoldingRow(
            "TSLA", "Tesla", "Equity", 4, 400, 1680, None, None, date(2026, 7, 18)
        ),
        HoldingRow(
            "BND", "Bond fund", "Bond", 326, 50, 16320, None, None, date(2026, 7, 18)
        ),
    ]
    summary = summarize_portfolio(
        positions,
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={"Equity": 0.48, "Bond": 0.52},
            allow_fractional_shares=False,
        ),
    )

    qqq = next(action for action in summary.rebalance_actions if action.symbol == "QQQ")
    tsla = next(
        action for action in summary.rebalance_actions if action.symbol == "TSLA"
    )
    assert qqq.action == "SELL"
    assert qqq.amount == 8610
    assert tsla.action == "REVIEW"
    assert tsla.amount == pytest.approx(30)
    assert "below one whole TSLA share" in tsla.rationale
    assert any("Rounding review only" in warning for warning in tsla.warnings)


def test_core_dca_reserves_the_user_capped_sector_satellite_budget() -> None:
    positions = [
        HoldingRow(
            "VTI", "US equity", "Equity", 10, 100, 1000, None, None, date(2026, 7, 18)
        ),
    ]
    summary = summarize_portfolio(
        positions,
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={"Equity": 0.5, "Bond": 0.5},
            monthly_contribution=500,
            monthly_sector_satellite_budget=100,
        ),
    )

    assert sum(item.monthly_amount for item in summary.dca_suggestions) == 400


def test_retirement_plan_backsolves_monthly_investment() -> None:
    positions = [
        HoldingRow(
            "VTI",
            "US equity",
            "Equity",
            2000,
            100,
            200000,
            None,
            None,
            date(2026, 7, 18),
        ),
    ]
    summary = summarize_portfolio(
        positions,
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={"Equity": 1.0},
            current_age=40,
            planned_retirement_age=65,
            retirement_planning_age=100,
            retirement_monthly_spending=6000,
            retirement_monthly_income=2500,
            retirement_income_taxable=False,
            retirement_account_type="taxable_brokerage",
            monthly_contribution=1500,
        ),
    )

    plan = summary.retirement_plan
    assert plan.monthly_spending_gap == 3500
    assert plan.years_to_retirement == 25
    assert plan.retirement_years == 35
    assert plan.target_assets_at_retirement is not None
    assert plan.target_assets_at_retirement > 1_000_000
    assert plan.required_monthly_investment is not None
    assert plan.required_monthly_investment > 0
    assert plan.status in {"funding_gap", "on_track"}


def test_retirement_formula_backsolves_zero_return_case_exactly() -> None:
    summary = summarize_portfolio(
        [],
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={},
            current_age=30,
            planned_retirement_age=31,
            retirement_planning_age=32,
            retirement_monthly_spending=1000,
            retirement_monthly_income=0,
            retirement_income_taxable=False,
            retirement_current_savings=0,
            retirement_inflation_rate=0,
            retirement_annual_return=0,
            retirement_account_type="roth",
        ),
    )

    plan = summary.retirement_plan
    assert plan.status == "funding_gap"
    assert plan.target_assets_at_retirement_today_dollars == pytest.approx(12_000)
    assert plan.target_assets_at_retirement == pytest.approx(12_000)
    assert plan.required_monthly_investment == pytest.approx(1_000)
    assert plan.ending_balance_target == 0


def test_retirement_formula_grosses_up_pre_tax_withdrawals() -> None:
    summary = summarize_portfolio(
        [],
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={},
            current_age=30,
            planned_retirement_age=31,
            retirement_planning_age=32,
            retirement_monthly_spending=1000,
            retirement_monthly_income=0,
            retirement_current_savings=0,
            retirement_inflation_rate=0,
            retirement_annual_return=0,
            retirement_current_tax_rate=0.25,
            retirement_tax_rate=0.25,
            retirement_account_type="traditional_401k",
        ),
    )

    plan = summary.retirement_plan
    assert plan.gross_monthly_portfolio_withdrawal == pytest.approx(1_000 / 0.75)
    assert plan.required_monthly_investment == pytest.approx(1_000 / 0.75)
    assert plan.estimated_monthly_take_home_cost == pytest.approx(1_000)


def test_retirement_formula_allows_tax_excluded_baseline_when_rate_is_blank() -> None:
    summary = summarize_portfolio(
        [],
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={},
            current_age=30,
            planned_retirement_age=31,
            retirement_planning_age=32,
            retirement_monthly_spending=1000,
            retirement_monthly_income=0,
            retirement_current_savings=0,
            retirement_inflation_rate=0,
            retirement_annual_return=0,
            retirement_current_tax_rate=None,
            retirement_tax_rate=None,
            retirement_account_type="traditional_401k",
        ),
    )

    plan = summary.retirement_plan
    assert plan.status == "funding_gap"
    assert plan.required_monthly_investment == pytest.approx(1_000)
    assert plan.estimated_monthly_take_home_cost is None
    assert any("tax-excluded baseline" in warning for warning in plan.warnings)


def test_retirement_formula_supports_mixed_traditional_and_roth_accounts() -> None:
    summary = summarize_portfolio(
        [],
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={},
            current_age=30,
            planned_retirement_age=31,
            retirement_planning_age=32,
            retirement_monthly_spending=1000,
            retirement_monthly_income=0,
            retirement_current_savings=0,
            retirement_inflation_rate=0,
            retirement_annual_return=0,
            retirement_tax_rate=0.20,
            retirement_account_type="mixed",
            retirement_taxable_withdrawal_share=0.50,
        ),
    )

    plan = summary.retirement_plan
    assert plan.taxable_withdrawal_share == 0.50
    assert plan.gross_monthly_portfolio_withdrawal == pytest.approx(1_000 / 0.90)
    assert plan.required_monthly_investment == pytest.approx(1_000 / 0.90)
    assert plan.estimated_monthly_take_home_cost is None
    assert any("mixed account plan" in warning for warning in plan.warnings)


def test_cash_plan_is_goal_driven_and_separate_from_dca(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text(
        "\n".join(
            [
                "symbol,name,asset_class,quantity,price,market_value,cost_basis,account,as_of_date",
                "VTI,Vanguard Total Market,Equity,10,100,1000,900,IRA,2026-07-15",
            ]
        ),
        encoding="utf-8",
    )

    summary = summarize_portfolio(
        parse_holdings_csv(source),
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={"Equity": 1.0},
            monthly_contribution=500,
            monthly_essential_expenses=2000,
            current_cash_savings=3000,
            emergency_fund_months=6,
            emergency_fund_build_months=12,
            education_plan="public",
            education_target_year=2027,
            education_target_amount=6000,
        ),
    )

    assert summary.cash_plan.status == "ready"
    assert summary.cash_plan.total_target == 18000
    emergency, education = summary.cash_plan.goals
    assert emergency.allocated_current_savings == 3000
    assert emergency.remaining_gap == 9000
    assert emergency.monthly_required == 750
    assert education.allocated_current_savings == 0
    assert education.monthly_required == 1000
    assert all(item.asset_class != "Cash" for item in summary.dca_suggestions)


def test_cash_plan_accepts_direct_emergency_amount_and_explains_funded_zero(
    tmp_path,
) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text(
        "symbol,name,asset_class,quantity,price,market_value,cost_basis,account,as_of_date\n"
        "VTI,Vanguard Total Market,Equity,10,100,1000,900,IRA,2026-07-15",
        encoding="utf-8",
    )

    summary = summarize_portfolio(
        parse_holdings_csv(source),
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={"Equity": 1.0},
            monthly_net_income=4000,
            monthly_total_expenses=4000,
            current_cash_savings=36000,
            emergency_fund_months=0,
            emergency_fund_target_amount=36000,
            emergency_fund_build_months=12,
        ),
    )

    goal = summary.cash_plan.goals[0]
    assert goal.title == "Emergency cash reserve"
    assert goal.target_amount == 36000
    assert goal.funding_status == "funded"
    assert goal.monthly_required == 0
    assert any("already covered" in item for item in summary.cash_plan.guidance)


def test_cash_plan_reports_monthly_shortfall_without_increasing_risk(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text(
        "\n".join(
            [
                "symbol,name,asset_class,quantity,price,market_value,cost_basis,account,as_of_date",
                "VTI,Vanguard Total Market,Equity,10,100,1000,900,IRA,2026-07-15",
            ]
        ),
        encoding="utf-8",
    )
    summary = summarize_portfolio(
        parse_holdings_csv(source),
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={"Equity": 1.0},
            monthly_net_income=4000,
            monthly_total_expenses=3200,
            monthly_contribution=500,
            primary_financial_priority="career transition",
            monthly_essential_expenses=2000,
            current_cash_savings=0,
            emergency_fund_months=6,
            emergency_fund_build_months=12,
        ),
    )

    assert summary.cash_plan.monthly_capacity_for_cash_goals == 300
    assert summary.cash_plan.monthly_required == 1000
    assert summary.cash_plan.monthly_shortfall == 700
    assert summary.cash_plan.feasibility_status == "shortfall"
    assert summary.cash_plan.primary_financial_priority == "career transition"
    assert any("career transition" in item for item in summary.cash_plan.guidance)
    assert any(
        "without increasing portfolio risk" in item
        for item in summary.cash_plan.guidance
    )


def test_cash_plan_supports_multiple_preset_short_term_goals(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text(
        "\n".join(
            [
                "symbol,name,asset_class,quantity,price,market_value,cost_basis,account,as_of_date",
                "VTI,Vanguard Total Market,Equity,10,100,1000,900,IRA,2026-07-15",
            ]
        ),
        encoding="utf-8",
    )
    summary = summarize_portfolio(
        parse_holdings_csv(source),
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={"Equity": 1.0},
            monthly_net_income=5000,
            monthly_total_expenses=3000,
            monthly_contribution=500,
            monthly_essential_expenses=2000,
            current_cash_savings=0,
            emergency_fund_months=0,
            retirement_cash_months=0,
            cash_goals_json=[
                {
                    "goal_type": "travel",
                    "target_amount": 2400,
                    "months_until_needed": 12,
                    "priority": "flexible",
                },
                {
                    "goal_type": "medical_care",
                    "target_amount": 1200,
                    "months_until_needed": 6,
                    "priority": "urgent",
                },
            ],
        ),
    )

    assert [goal.code for goal in summary.cash_plan.goals] == [
        "planned_medical_care",
        "planned_travel",
    ]
    assert summary.cash_plan.monthly_required == 400
    assert all(
        "separate retirement projection" in goal.rationale
        for goal in summary.cash_plan.goals
    )


def test_no_profile_uses_example_reference_and_three_scenarios(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text(
        "\n".join(
            [
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,"
                    "account,as_of_date"
                ),
                "GLD,SPDR Gold Shares,Commodity,40,100,4000,3000,Taxable,2026-07-14",
                "AAPL,Apple Inc,Equity,10,200,2000,1500,IRA,2026-07-14",
                "MSFT,Microsoft,Equity,4,500,2000,1500,IRA,2026-07-14",
                "VTI,Vanguard Total Market ETF,Equity,8,250,2000,1800,IRA,2026-07-14",
            ]
        ),
        encoding="utf-8",
    )

    summary = summarize_portfolio(parse_holdings_csv(source))

    review = next(
        action for action in summary.rebalance_actions if action.symbol == "GLD"
    )
    assert review.reference_kind == "example_review_level"
    assert "not your personal target" in review.reference_label
    assert review.amount == 2000
    assert review.estimated_shares == 20
    assert summary.recommendation_context.analysis_method == (
        "deterministic_portfolio_rules"
    )
    assert "selected answer model does not change these numbers" in (
        summary.recommendation_context.analysis_method_description
    )

    assert [scenario.code for scenario in summary.rebalance_scenarios] == [
        "maintain",
        "new_contributions",
        "partial_sell_reallocate",
    ]
    dilute = summary.rebalance_scenarios[1]
    assert dilute.rebalancing_amount == 10000
    assert next(
        item
        for item in dilute.projected_allocation
        if item.asset_class == "Commodity / Gold"
    ).weight == pytest.approx(0.20)
    partial_sale = summary.rebalance_scenarios[2]
    assert partial_sale.rebalancing_amount == 2000
    assert partial_sale.trades[0].estimated_shares == 20
    assert next(
        item
        for item in partial_sale.projected_allocation
        if item.asset_class == "Commodity / Gold"
    ).weight == pytest.approx(0.20)


def test_expanded_asset_classes_match_saved_profile_targets(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text(
        "\n".join(
            [
                "symbol,name,asset_class,quantity,price,market_value,cost_basis,account",
                "GLD,SPDR Gold Shares,Equity ETF,20,100,2000,1500,IRA",
                "VXUS,Vanguard International,Equity ETF,30,100,3000,2500,IRA",
                "BTGO,Alternative Fund,Alternative ETF,10,100,1000,900,IRA",
                "VTI,Vanguard Total Market,Equity ETF,40,100,4000,3500,IRA",
            ]
        ),
        encoding="utf-8",
    )

    summary = summarize_portfolio(
        parse_holdings_csv(source),
        profile=Profile(
            risk_tolerance="moderate",
            target_allocation_json={
                "Equity": 0.4,
                "Commodity / Gold": 0.2,
                "International Equity": 0.3,
                "Alternatives": 0.1,
            },
        ),
    )

    assert summary.rebalance_actions == ()
    assert {
        item.asset_class: item.weight for item in summary.allocation
    } == pytest.approx(
        {
            "Equity": 0.4,
            "International Equity": 0.3,
            "Commodity / Gold": 0.2,
            "Alternatives": 0.1,
        }
    )
