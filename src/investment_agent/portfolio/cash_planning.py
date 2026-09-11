from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Protocol


@dataclass(frozen=True)
class CashGoalDefinition:
    goal_type: str
    title: str
    description: str


CASH_GOAL_CATALOG = (
    CashGoalDefinition(
        "medical_care",
        "Planned medical / dental care",
        "A known bill, deductible, procedure, therapy, or dental expense.",
    ),
    CashGoalDefinition(
        "home_or_appliance",
        "Home / appliance repair or replacement",
        "A move, repair, renovation, appliance, or other housing-related cash need.",
    ),
    CashGoalDefinition(
        "vehicle",
        "Vehicle purchase or major repair",
        "A down payment, replacement vehicle, or significant repair.",
    ),
    CashGoalDefinition(
        "travel",
        "Travel",
        "A planned trip that should be funded outside the investment portfolio.",
    ),
    CashGoalDefinition(
        "tuition",
        "Tuition / education",
        "A near-term tuition bill, course, certificate, or school deposit.",
    ),
    CashGoalDefinition(
        "insurance_or_tax",
        "Annual insurance / tax bill",
        "A predictable non-monthly premium, tax payment, or similar annual bill.",
    ),
    CashGoalDefinition(
        "family_support",
        "Family support / caregiving",
        "A planned contribution for relatives, caregiving, or family formation.",
    ),
    CashGoalDefinition(
        "major_purchase",
        "Other major purchase",
        "A known large purchase that does not fit the preset categories above.",
    ),
)
CASH_GOAL_DEFINITIONS = {
    definition.goal_type: definition for definition in CASH_GOAL_CATALOG
}
_PRIORITY_ORDER = {"urgent": 10, "important": 30, "flexible": 60}


class CashProfileLike(Protocol):
    monthly_net_income: float | None
    monthly_contribution: float | None
    monthly_total_expenses: float | None
    primary_financial_priority: str | None
    current_age: int | None
    planned_retirement_age: int | None
    retirement_planning_age: int
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
    cash_goals_json: list[dict[str, object]]


@dataclass(frozen=True)
class CashGoal:
    code: str
    title: str
    target_amount: float
    allocated_current_savings: float
    remaining_gap: float
    months_remaining: int
    monthly_required: float
    deadline_label: str
    rationale: str
    priority: str
    funding_status: str


@dataclass(frozen=True)
class CashPlan:
    status: str
    as_of_date: date
    current_cash_savings: float
    total_target: float
    remaining_gap: float
    monthly_required: float
    monthly_net_income: float | None
    monthly_total_expenses: float | None
    monthly_investment: float
    monthly_capacity_for_cash_goals: float | None
    monthly_shortfall: float | None
    feasibility_status: str
    primary_financial_priority: str | None
    goals: tuple[CashGoal, ...]
    warnings: tuple[str, ...]
    guidance: tuple[str, ...]
    method: str = "deterministic_cash_goal_plan_v3"


@dataclass(frozen=True)
class _GoalSpec:
    sort_order: int
    code: str
    title: str
    target: float
    months: int
    deadline: str
    rationale: str
    priority: str


def _within_months(months: int) -> str:
    unit = "month" if months == 1 else "months"
    return f"within {months} {unit}"


def calculate_cash_plan(
    profile: CashProfileLike | None,
    *,
    as_of_date: date,
) -> CashPlan:
    if profile is None:
        return CashPlan(
            status="profile_required",
            as_of_date=as_of_date,
            current_cash_savings=0.0,
            total_target=0.0,
            remaining_gap=0.0,
            monthly_required=0.0,
            monthly_net_income=None,
            monthly_total_expenses=None,
            monthly_investment=0.0,
            monthly_capacity_for_cash_goals=None,
            monthly_shortfall=None,
            feasibility_status="inputs_required",
            primary_financial_priority=None,
            goals=(),
            warnings=("Save Profile cash-goal inputs to calculate a plan.",),
            guidance=(),
        )

    available = max(
        0.0,
        float(getattr(profile, "current_cash_savings", None) or 0.0),
    )
    initial_available = available
    goal_specs: list[_GoalSpec] = []
    warnings: list[str] = []

    expenses = max(
        0.0,
        float(getattr(profile, "monthly_essential_expenses", None) or 0.0),
    )
    emergency_months = max(
        0.0,
        float(getattr(profile, "emergency_fund_months", 6.0) or 0.0),
    )
    direct_emergency_target = max(
        0.0,
        float(getattr(profile, "emergency_fund_target_amount", None) or 0.0),
    )
    if direct_emergency_target > 0:
        build_months = max(
            1,
            int(getattr(profile, "emergency_fund_build_months", 12) or 12),
        )
        goal_specs.append(
            _GoalSpec(
                0,
                "emergency_fund",
                "Emergency cash reserve",
                direct_emergency_target,
                build_months,
                _within_months(build_months),
                (
                    "Uses the emergency-reserve amount and saving deadline entered in "
                    "Profile. It is kept liquid and separate from investing."
                ),
                "urgent",
            )
        )
    elif expenses > 0 and emergency_months > 0:
        build_months = max(
            1,
            int(getattr(profile, "emergency_fund_build_months", 12) or 12),
        )
        goal_specs.append(
            _GoalSpec(
                0,
                "emergency_fund",
                "Emergency fund",
                expenses * emergency_months,
                build_months,
                _within_months(build_months),
                (
                    f"Target equals {emergency_months:g} months of the entered "
                    f"${expenses:,.0f} essential monthly expenses."
                ),
                "urgent",
            )
        )
    elif emergency_months > 0:
        warnings.append(
            "Add essential monthly expenses to calculate the enabled emergency-fund target."
        )

    selected_goals = getattr(profile, "cash_goals_json", None) or []
    if selected_goals:
        for index, selected in enumerate(selected_goals):
            if not isinstance(selected, dict):
                warnings.append("A saved short-term cash goal has an invalid format.")
                continue
            goal_type = str(selected.get("goal_type") or "")
            definition = CASH_GOAL_DEFINITIONS.get(goal_type)
            if definition is None:
                warnings.append(f"Unknown short-term cash-goal type: {goal_type or 'blank'}.")
                continue
            target = max(0.0, float(selected.get("target_amount") or 0.0))
            raw_months = selected.get("months_until_needed")
            priority = str(selected.get("priority") or "important")
            if priority not in _PRIORITY_ORDER:
                priority = "important"
            if target <= 0 or raw_months is None:
                warnings.append(
                    f"{definition.title} is selected; add an estimated amount and months-until-needed before relying on its calculation."
                )
                continue
            months = max(1, int(raw_months))
            goal_specs.append(
                _GoalSpec(
                    _PRIORITY_ORDER[priority] + index,
                    f"planned_{goal_type}",
                    definition.title,
                    target,
                    months,
                    _within_months(months),
                    (
                        f"Preset short-term goal with {priority} priority. It reduces "
                        "cash available for investing until funded, but does not increase "
                        "a separate retirement projection."
                    ),
                    priority,
                )
            )
    else:
        near_term_name = str(
            getattr(profile, "near_term_goal_name", None) or ""
        ).strip()
        near_term_amount = max(
            0.0,
            float(getattr(profile, "near_term_goal_amount", None) or 0.0),
        )
        near_term_months = getattr(profile, "near_term_goal_months", None)
        if near_term_name:
            if near_term_amount > 0 and near_term_months is not None:
                months = max(1, int(near_term_months))
                goal_specs.append(
                    _GoalSpec(
                        30,
                        "near_term_cash",
                        near_term_name,
                        near_term_amount,
                        months,
                        _within_months(months),
                        (
                            "Legacy known cash need; it is kept outside the investment "
                            "allocation and is separate from retirement planning."
                        ),
                        "important",
                    )
                )
            else:
                warnings.append(
                    "A legacy near-term cash goal is named; add both its amount and months-until-needed."
                )

    education_plan = str(
        getattr(profile, "education_plan", "none") or "none"
    ).strip().lower()
    education_amount = max(
        0.0,
        float(getattr(profile, "education_target_amount", None) or 0.0),
    )
    education_year = getattr(profile, "education_target_year", None)
    if education_plan != "none":
        if education_amount > 0 and education_year is not None:
            months = max(
                1,
                (education_year - as_of_date.year) * 12 - as_of_date.month + 1,
            )
            goal_specs.append(
                _GoalSpec(
                    50,
                    "education",
                    f"Child education · {education_plan}",
                    education_amount,
                    months,
                    str(education_year),
                    (
                        "Uses the amount you entered; school type is context only because "
                        "tuition varies by school, location, aid, and inflation."
                    ),
                    "important",
                )
            )
        else:
            warnings.append(
                "Education plan selected; add a target year and amount before relying on it."
            )

    goals: list[CashGoal] = []
    for spec in sorted(goal_specs, key=lambda item: item.sort_order):
        allocated = min(available, spec.target)
        available -= allocated
        gap = max(0.0, spec.target - allocated)
        monthly = float(ceil(gap / spec.months)) if gap > 0 else 0.0
        goals.append(
            CashGoal(
                code=spec.code,
                title=spec.title,
                target_amount=round(spec.target, 2),
                allocated_current_savings=round(allocated, 2),
                remaining_gap=round(gap, 2),
                months_remaining=spec.months,
                monthly_required=monthly,
                deadline_label=spec.deadline,
                rationale=spec.rationale,
                priority=spec.priority,
                funding_status=(
                    "funded"
                    if gap <= 0.005
                    else "partially_funded"
                    if allocated > 0
                    else "not_funded"
                ),
            )
        )

    total_target = sum(goal.target_amount for goal in goals)
    remaining_gap = sum(goal.remaining_gap for goal in goals)
    monthly_required = sum(goal.monthly_required for goal in goals)
    monthly_income = _optional_nonnegative(
        getattr(profile, "monthly_net_income", None)
    )
    monthly_total_expenses = _optional_nonnegative(
        getattr(profile, "monthly_total_expenses", None)
    )
    monthly_investment = max(
        0.0,
        float(getattr(profile, "monthly_contribution", None) or 0.0),
    )
    capacity: float | None = None
    shortfall: float | None = None
    feasibility_status = "inputs_required"
    guidance: list[str] = []
    priority = str(
        getattr(profile, "primary_financial_priority", None) or ""
    ).strip()
    if monthly_income is not None and monthly_total_expenses is not None:
        capacity = max(
            0.0,
            monthly_income - monthly_total_expenses - monthly_investment,
        )
        shortfall = max(0.0, monthly_required - capacity)
        feasibility_status = "shortfall" if shortfall > 0 else "feasible"
        if priority:
            guidance.append(
                f"Your stated priority is “{priority}”; preserve it before adjusting lower-priority goals."
            )
        if shortfall > 0:
            guidance.append(
                "Protect the emergency fund and known near-term cash needs before optional investing."
            )
            if monthly_investment > 0:
                redirect = min(monthly_investment, shortfall)
                guidance.append(
                    f"Redirecting up to ${redirect:,.0f}/month from planned investing "
                    "to cash goals would reduce the gap without increasing portfolio risk."
                )
            guidance.extend(
                (
                    "For flexible goals, compare extending the deadline or lowering the target before taking more investment risk.",
                    f"The remaining capacity gap is ${shortfall:,.0f}/month. An income plan must sustainably cover that amount after total spending and investing.",
                    "Specific career, industry, employer, or salary guidance requires your skills, location, work constraints, and current cited labor-market data; it should be researched separately rather than guessed by the portfolio model.",
                    "If spending, timing, and realistic income changes still cannot close the gap, lower or defer the least important goal instead of assuming unusually high investment returns.",
                )
            )
        else:
            guidance.append(
                "Entered monthly net income covers total spending, planned investing, and the calculated minimum cash-goal saving."
            )
            if remaining_gap <= 0:
                guidance.append(
                    "All listed cash goals are already covered by the current cash savings entered in Profile, so no additional monthly saving is required unless those balances are unavailable for these goals."
                )
    else:
        guidance.append(
            "Add monthly net income and normalized monthly spending to check whether the cash-goal schedule is affordable."
        )
    return CashPlan(
        status="ready" if goals else "inputs_required",
        as_of_date=as_of_date,
        current_cash_savings=initial_available,
        total_target=round(total_target, 2),
        remaining_gap=round(remaining_gap, 2),
        monthly_required=round(monthly_required, 2),
        monthly_net_income=monthly_income,
        monthly_total_expenses=monthly_total_expenses,
        monthly_investment=round(monthly_investment, 2),
        monthly_capacity_for_cash_goals=(
            round(capacity, 2) if capacity is not None else None
        ),
        monthly_shortfall=(round(shortfall, 2) if shortfall is not None else None),
        feasibility_status=feasibility_status,
        primary_financial_priority=priority or None,
        goals=tuple(goals),
        warnings=tuple(warnings),
        guidance=tuple(guidance),
    )


def _optional_nonnegative(value: object) -> float | None:
    if value is None:
        return None
    return max(0.0, float(value))
