from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


DEFAULT_INFLATION_RATE = 0.025
DEFAULT_ANNUAL_RETURN = 0.05


class RetirementProfileLike(Protocol):
    current_age: int | None
    planned_retirement_age: int | None
    retirement_planning_age: int
    monthly_essential_expenses: float | None
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
    monthly_contribution: float | None


@dataclass(frozen=True)
class RetirementFundingPlan:
    status: str
    current_age: int | None
    retirement_age: int | None
    plan_through_age: int
    years_to_retirement: int | None
    retirement_years: int | None
    monthly_spending_today: float | None
    monthly_reliable_income_today: float
    monthly_reliable_income_after_tax: float | None
    monthly_spending_gap: float | None
    gross_monthly_portfolio_withdrawal: float | None
    current_invested_assets: float
    current_retirement_savings: float
    current_savings_source: str
    target_assets_at_retirement_today_dollars: float | None
    target_assets_at_retirement: float | None
    projected_current_assets_at_retirement: float | None
    required_monthly_investment: float | None
    estimated_monthly_take_home_cost: float | None
    planned_monthly_investment: float
    monthly_investment_gap: float | None
    inflation_rate: float
    annual_return: float
    real_annual_return: float
    accumulation_real_return: float
    retirement_real_return: float
    current_tax_rate: float | None
    retirement_tax_rate: float | None
    income_taxable: bool
    account_type: str | None
    taxable_withdrawal_share: float | None
    adjust_contributions_for_inflation: bool
    ending_balance_target: float
    warnings: tuple[str, ...]
    guidance: tuple[str, ...]
    method: str


def calculate_retirement_funding_plan(
    profile: RetirementProfileLike | None,
    *,
    current_invested_assets: float,
) -> RetirementFundingPlan:
    plan_through_age = int(getattr(profile, "retirement_planning_age", 100) or 100)
    current_age = getattr(profile, "current_age", None)
    retirement_age = getattr(profile, "planned_retirement_age", None)
    explicit_spending = getattr(profile, "retirement_monthly_spending", None)
    essential_spending = getattr(profile, "monthly_essential_expenses", None)
    monthly_spending = (
        float(explicit_spending)
        if explicit_spending is not None
        else float(essential_spending)
        if essential_spending is not None
        else None
    )
    monthly_income = float(getattr(profile, "retirement_monthly_income", None) or 0.0)
    income_taxable = bool(getattr(profile, "retirement_income_taxable", True))
    inflation_rate = float(
        getattr(profile, "retirement_inflation_rate", DEFAULT_INFLATION_RATE)
        if profile is not None
        else DEFAULT_INFLATION_RATE
    )
    annual_return = float(
        getattr(profile, "retirement_annual_return", DEFAULT_ANNUAL_RETURN)
        if profile is not None
        else DEFAULT_ANNUAL_RETURN
    )
    current_tax_rate = getattr(profile, "retirement_current_tax_rate", None)
    retirement_tax_rate = getattr(profile, "retirement_tax_rate", None)
    account_type = getattr(profile, "retirement_account_type", None)
    entered_taxable_share = getattr(
        profile, "retirement_taxable_withdrawal_share", None
    )
    taxable_withdrawal_share = _taxable_withdrawal_share(
        account_type,
        entered_taxable_share,
    )
    adjust_for_inflation = bool(
        getattr(profile, "retirement_adjust_contributions_for_inflation", False)
    )
    planned_monthly = float(getattr(profile, "monthly_contribution", None) or 0.0)
    uploaded_investments = max(0.0, float(current_invested_assets))
    entered_savings = getattr(profile, "retirement_current_savings", None)
    if entered_savings is None:
        current_savings = uploaded_investments
        savings_source = "uploaded_investment_portfolio"
    else:
        current_savings = max(0.0, float(entered_savings))
        savings_source = "profile_input"

    real_return = (1.0 + annual_return) / (1.0 + inflation_rate) - 1.0
    warnings: list[str] = []
    if current_age is None:
        warnings.append("Enter your current age in Profile.")
    if retirement_age is None:
        warnings.append("Enter your planned retirement age in Profile.")
    if monthly_spending is None or monthly_spending <= 0:
        warnings.append(
            "Enter desired after-tax retirement spending, or essential monthly expenses "
            "as a fallback."
        )
    if account_type is None:
        warnings.append("Select the retirement-account tax treatment in Profile.")
    if account_type == "mixed" and taxable_withdrawal_share is None:
        warnings.append(
            "Enter the estimated percentage of retirement withdrawals that will come "
            "from pre-tax Traditional accounts."
        )
    requires_retirement_tax_rate = (
        (income_taxable and monthly_income > 0)
        or bool(taxable_withdrawal_share and taxable_withdrawal_share > 0)
    )
    if requires_retirement_tax_rate and retirement_tax_rate is None:
        warnings.append(
            "Retirement tax rate is blank. Argus calculated a tax-excluded baseline "
            "instead of blocking the projection; taxable income and pre-tax withdrawals "
            "will require a higher gross amount."
        )
    if (
        account_type in {"traditional_401k", "traditional_ira"}
        and current_tax_rate is None
    ):
        warnings.append(
            "Current marginal tax rate is blank, so Argus cannot estimate the take-home "
            "cash cost of a deductible pre-tax deposit."
        )

    invalid_timing = (
        current_age is None
        or retirement_age is None
        or retirement_age <= current_age
        or plan_through_age <= retirement_age
    )
    missing_required = (
        invalid_timing
        or monthly_spending is None
        or monthly_spending <= 0
        or account_type is None
        or (account_type == "mixed" and taxable_withdrawal_share is None)
    )
    years_to_retirement = (
        retirement_age - current_age
        if current_age is not None
        and retirement_age is not None
        and retirement_age > current_age
        else None
    )
    retirement_years = (
        plan_through_age - retirement_age
        if retirement_age is not None and plan_through_age > retirement_age
        else None
    )

    effective_retirement_tax_rate = float(retirement_tax_rate or 0.0)
    income_after_tax = (
        monthly_income * (1.0 - effective_retirement_tax_rate)
        if income_taxable
        else monthly_income
    )
    after_tax_gap = (
        max(0.0, monthly_spending - income_after_tax)
        if monthly_spending is not None
        else None
    )
    withdrawal_tax_rate = effective_retirement_tax_rate * float(
        taxable_withdrawal_share or 0.0
    )
    gross_withdrawal = (
        after_tax_gap / (1.0 - withdrawal_tax_rate)
        if after_tax_gap is not None and withdrawal_tax_rate < 1.0
        else None
    )

    if missing_required:
        return RetirementFundingPlan(
            status="inputs_required",
            current_age=current_age,
            retirement_age=retirement_age,
            plan_through_age=plan_through_age,
            years_to_retirement=years_to_retirement,
            retirement_years=retirement_years,
            monthly_spending_today=monthly_spending,
            monthly_reliable_income_today=monthly_income,
            monthly_reliable_income_after_tax=(
                income_after_tax if not requires_retirement_tax_rate or retirement_tax_rate is not None else None
            ),
            monthly_spending_gap=after_tax_gap,
            gross_monthly_portfolio_withdrawal=gross_withdrawal,
            current_invested_assets=uploaded_investments,
            current_retirement_savings=current_savings,
            current_savings_source=savings_source,
            target_assets_at_retirement_today_dollars=None,
            target_assets_at_retirement=None,
            projected_current_assets_at_retirement=None,
            required_monthly_investment=None,
            estimated_monthly_take_home_cost=None,
            planned_monthly_investment=planned_monthly,
            monthly_investment_gap=None,
            inflation_rate=inflation_rate,
            annual_return=annual_return,
            real_annual_return=real_return,
            accumulation_real_return=real_return,
            retirement_real_return=real_return,
            current_tax_rate=current_tax_rate,
            retirement_tax_rate=retirement_tax_rate,
            income_taxable=income_taxable,
            account_type=account_type,
            taxable_withdrawal_share=taxable_withdrawal_share,
            adjust_contributions_for_inflation=adjust_for_inflation,
            ending_balance_target=0.0,
            warnings=tuple(warnings),
            guidance=(
                "Complete the missing Profile inputs before relying on a retirement estimate.",
            ),
            method="FINRA-inspired nominal accumulation and retirement-withdrawal model.",
        )

    assert years_to_retirement is not None
    assert retirement_years is not None
    assert after_tax_gap is not None
    assert gross_withdrawal is not None
    accumulation_months = years_to_retirement * 12
    withdrawal_months = retirement_years * 12
    real_monthly_rate = _monthly_rate(real_return)
    nominal_monthly_rate = _monthly_rate(annual_return)

    target_today = _annuity_present_value(
        gross_withdrawal,
        monthly_rate=real_monthly_rate,
        months=withdrawal_months,
    )
    target_nominal = target_today * ((1.0 + inflation_rate) ** years_to_retirement)
    projected_current = current_savings * (
        (1.0 + annual_return) ** years_to_retirement
    )
    remaining_target = max(0.0, target_nominal - projected_current)
    contribution_factor = _monthly_contribution_future_value_factor(
        months=accumulation_months,
        monthly_return=nominal_monthly_rate,
        annual_inflation=inflation_rate,
        adjust_for_inflation=adjust_for_inflation,
    )
    required_monthly = (
        remaining_target / contribution_factor if contribution_factor > 0 else 0.0
    )
    investment_gap = max(0.0, required_monthly - planned_monthly)
    take_home_cost = required_monthly
    if account_type in {"traditional_401k", "traditional_ira"}:
        take_home_cost = (
            required_monthly * (1.0 - float(current_tax_rate))
            if current_tax_rate is not None
            else None
        )
    elif account_type == "mixed":
        take_home_cost = None
        warnings.append(
            "Argus cannot estimate one take-home deposit cost for a mixed account plan "
            "without a separate contribution split between Traditional and Roth accounts."
        )

    if after_tax_gap <= 0:
        status = "income_covers_spending"
        guidance = (
            "Entered after-tax retirement income covers the spending target. Verify the "
            "income and tax assumptions and plan separately for shocks.",
        )
    elif remaining_target <= 0:
        status = "already_funded"
        guidance = (
            "The projected value of the entered retirement savings reaches this "
            "deterministic target under the stated assumptions.",
        )
    elif investment_gap <= 0:
        status = "on_track"
        guidance = (
            "The entered planned monthly investment meets or exceeds the modeled starting "
            "deposit. Review the assumptions at least annually.",
        )
    else:
        status = "funding_gap"
        guidance = (
            "Close the gap by saving more, entering reliable income, lowering the spending "
            "target, or retiring later. Do not assume more portfolio risk will reliably "
            "solve the shortfall.",
        )

    if account_type == "taxable_brokerage":
        warnings.append(
            "For a taxable brokerage account, Argus treats the entered return as net of "
            "investment taxes and fees; cost basis and capital-gains timing are not modeled."
        )
    if current_savings == uploaded_investments and savings_source == "uploaded_investment_portfolio":
        warnings.append(
            "No separate retirement-savings amount was entered, so Argus used the entire "
            "uploaded non-cash investment portfolio."
        )

    return RetirementFundingPlan(
        status=status,
        current_age=current_age,
        retirement_age=retirement_age,
        plan_through_age=plan_through_age,
        years_to_retirement=years_to_retirement,
        retirement_years=retirement_years,
        monthly_spending_today=monthly_spending,
        monthly_reliable_income_today=monthly_income,
        monthly_reliable_income_after_tax=income_after_tax,
        monthly_spending_gap=after_tax_gap,
        gross_monthly_portfolio_withdrawal=gross_withdrawal,
        current_invested_assets=uploaded_investments,
        current_retirement_savings=current_savings,
        current_savings_source=savings_source,
        target_assets_at_retirement_today_dollars=target_today,
        target_assets_at_retirement=target_nominal,
        projected_current_assets_at_retirement=projected_current,
        required_monthly_investment=required_monthly,
        estimated_monthly_take_home_cost=take_home_cost,
        planned_monthly_investment=planned_monthly,
        monthly_investment_gap=investment_gap,
        inflation_rate=inflation_rate,
        annual_return=annual_return,
        real_annual_return=real_return,
        accumulation_real_return=real_return,
        retirement_real_return=real_return,
        current_tax_rate=current_tax_rate,
        retirement_tax_rate=retirement_tax_rate,
        income_taxable=income_taxable,
        account_type=account_type,
        taxable_withdrawal_share=taxable_withdrawal_share,
        adjust_contributions_for_inflation=adjust_for_inflation,
        ending_balance_target=0.0,
        warnings=tuple(warnings),
        guidance=guidance,
        method="FINRA-inspired nominal accumulation and retirement-withdrawal model.",
    )


def _taxable_withdrawal_share(
    account_type: str | None,
    entered_share: float | None,
) -> float | None:
    if account_type in {"traditional_401k", "traditional_ira"}:
        return 1.0
    if account_type in {"roth", "taxable_brokerage"}:
        return 0.0
    if account_type == "mixed":
        return (
            min(1.0, max(0.0, float(entered_share)))
            if entered_share is not None
            else None
        )
    return None


def _monthly_rate(annual_rate: float) -> float:
    return (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0


def _annuity_present_value(
    monthly_amount: float,
    *,
    monthly_rate: float,
    months: int,
) -> float:
    if monthly_amount <= 0 or months <= 0:
        return 0.0
    if abs(monthly_rate) < 1e-12:
        return monthly_amount * months
    return monthly_amount * (1.0 - (1.0 + monthly_rate) ** (-months)) / monthly_rate


def _monthly_contribution_future_value_factor(
    *,
    months: int,
    monthly_return: float,
    annual_inflation: float,
    adjust_for_inflation: bool,
) -> float:
    """Future value of a $1 starting monthly deposit made at month-start."""

    factor = 0.0
    for month in range(months):
        deposit_scale = (
            (1.0 + annual_inflation) ** (month // 12)
            if adjust_for_inflation
            else 1.0
        )
        growth_months = months - month
        factor += deposit_scale * ((1.0 + monthly_return) ** growth_months)
    return factor
