from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from investment_agent.api.dependencies import get_db_session
from investment_agent.api.style_packs import (
    resolve_method_documents,
    resolve_style_pack,
)
from investment_agent.method_documents import (
    MAX_METHOD_PANEL_DOCUMENTS,
    CompiledMethodDocument,
)
from investment_agent.portfolio import ProfileGuidanceInput, guide_profile_allocation
from investment_agent.repositories import UserProfileCreate, UserProfileRepository
from investment_agent.storage import UserProfile
from investment_agent.style_packs import normalize_style_pack_id

router = APIRouter(prefix="/profile", tags=["profile"])


CashGoalType = Literal[
    "medical_care",
    "home_or_appliance",
    "vehicle",
    "travel",
    "tuition",
    "insurance_or_tax",
    "family_support",
    "major_purchase",
]
CashGoalPriority = Literal["urgent", "important", "flexible"]


class PlannedCashGoalRequest(BaseModel):
    goal_type: CashGoalType
    target_amount: float | None = Field(default=None, gt=0)
    months_until_needed: int | None = Field(default=None, ge=1, le=120)
    priority: CashGoalPriority = "important"


class ProfileRequest(BaseModel):
    risk_tolerance: str = Field(min_length=1)
    life_stage: str | None = None
    investment_horizon: str | None = None
    investing_experience: str | None = None
    income_stability: str | None = None
    liquidity_needs: str | None = None
    preferred_style: str | None = None
    preferred_method_document_id: int | None = Field(default=None, gt=0)
    preferred_method_document_ids: list[int] = Field(
        default_factory=list,
        max_length=MAX_METHOD_PANEL_DOCUMENTS,
    )
    target_allocation: dict[str, float] = Field(default_factory=dict)
    monthly_net_income: float | None = Field(default=None, ge=0)
    monthly_contribution: float | None = Field(default=None, ge=0)
    monthly_sector_satellite_budget: float | None = Field(default=None, ge=0)
    monthly_total_expenses: float | None = Field(default=None, ge=0)
    primary_financial_priority: str | None = Field(default=None, max_length=256)
    current_age: int | None = Field(default=None, ge=18, le=100)
    planned_retirement_age: int | None = Field(default=None, ge=18, le=99)
    retirement_planning_age: int = Field(default=100, ge=80, le=120)
    retirement_monthly_spending: float | None = Field(default=None, ge=0)
    retirement_monthly_income: float | None = Field(default=None, ge=0)
    retirement_current_savings: float | None = Field(default=None, ge=0)
    retirement_income_taxable: bool = True
    retirement_inflation_rate: float = Field(default=0.025, ge=0, le=0.15)
    retirement_current_tax_rate: float | None = Field(default=None, ge=0, le=0.75)
    retirement_tax_rate: float | None = Field(default=None, ge=0, le=0.75)
    retirement_annual_return: float = Field(default=0.05, ge=-0.5, le=0.5)
    retirement_account_type: Literal[
        "traditional_401k",
        "traditional_ira",
        "roth",
        "taxable_brokerage",
        "mixed",
    ] | None = None
    retirement_taxable_withdrawal_share: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    retirement_adjust_contributions_for_inflation: bool = False
    monthly_essential_expenses: float | None = Field(default=None, ge=0)
    current_cash_savings: float | None = Field(default=None, ge=0)
    emergency_fund_months: float = Field(default=0.0, ge=0, le=24)
    emergency_fund_target_amount: float | None = Field(default=None, ge=0)
    emergency_fund_build_months: int = Field(default=12, ge=1, le=120)
    education_plan: Literal["none", "public", "private"] = "none"
    education_target_year: int | None = Field(default=None, ge=2026, le=2100)
    education_target_amount: float | None = Field(default=None, ge=0)
    near_term_goal_name: str | None = Field(default=None, max_length=256)
    near_term_goal_amount: float | None = Field(default=None, ge=0)
    near_term_goal_months: int | None = Field(default=None, ge=1, le=600)
    cash_goals: list[PlannedCashGoalRequest] = Field(default_factory=list, max_length=8)
    # Legacy compatibility only. Retirement is now a planning horizon, not a cash goal.
    retirement_cash_months: float = Field(default=0.0, ge=0, le=60)
    retirement_cash_target: float | None = Field(default=None, ge=0)
    rebalance_threshold: float = Field(default=0.05, ge=0.01, le=0.25)
    allow_fractional_shares: bool = False
    rebalance_preference: Literal["contributions_first", "target_trades"] = (
        "contributions_first"
    )

    @field_validator("target_allocation")
    @classmethod
    def validate_target_allocation(cls, value: dict[str, float]) -> dict[str, float]:
        for asset_class, weight in value.items():
            if not asset_class.strip():
                raise ValueError("Target allocation asset class cannot be empty.")
            if asset_class.strip().lower() == "cash":
                raise ValueError(
                    "Cash is planned through cash goals, not the investment target allocation."
                )
            if weight < 0 or weight > 1:
                raise ValueError("Target allocation weights must be between 0 and 1.")
        if value and abs(sum(value.values()) - 1.0) > 0.001:
            raise ValueError("Target allocation weights must add up to 100%.")
        return value

    @model_validator(mode="after")
    def validate_profile_relationships(self) -> ProfileRequest:
        if (
            self.current_age is not None
            and self.planned_retirement_age is not None
            and self.planned_retirement_age <= self.current_age
        ):
            raise ValueError("Planned retirement age must be later than current age.")
        if (
            self.planned_retirement_age is not None
            and self.retirement_planning_age <= self.planned_retirement_age
        ):
            raise ValueError(
                "Retirement planning age must be later than planned retirement age."
            )
        if (
            self.monthly_sector_satellite_budget is not None
            and self.monthly_contribution is not None
            and self.monthly_sector_satellite_budget > self.monthly_contribution
        ):
            raise ValueError(
                "The sector/industry satellite budget cannot exceed the total planned "
                "monthly investment."
            )
        if (
            self.retirement_account_type == "mixed"
            and self.retirement_taxable_withdrawal_share is None
        ):
            raise ValueError(
                "Enter the estimated pre-tax share of retirement withdrawals for a "
                "mixed Traditional + Roth account plan."
            )
        if self.education_plan == "none":
            self.education_target_year = None
            self.education_target_amount = None
        if not self.near_term_goal_name:
            self.near_term_goal_name = None
            self.near_term_goal_amount = None
            self.near_term_goal_months = None
        elif not self.cash_goals:
            self.cash_goals = [
                PlannedCashGoalRequest(
                    goal_type="major_purchase",
                    target_amount=self.near_term_goal_amount,
                    months_until_needed=self.near_term_goal_months,
                    priority="important",
                )
            ]
        goal_types = [goal.goal_type for goal in self.cash_goals]
        if len(goal_types) != len(set(goal_types)):
            raise ValueError(
                "Each preset short-term cash-goal type can be selected once."
            )
        if not self.preferred_method_document_ids and self.preferred_method_document_id:
            self.preferred_method_document_ids = [self.preferred_method_document_id]
        self.preferred_method_document_ids = list(
            dict.fromkeys(self.preferred_method_document_ids)
        )
        self.preferred_method_document_id = (
            self.preferred_method_document_ids[0]
            if self.preferred_method_document_ids
            else None
        )
        if self.emergency_fund_target_amount is not None:
            self.emergency_fund_months = 0
        if self.emergency_fund_months == 0 and not self.emergency_fund_target_amount:
            self.emergency_fund_build_months = 12
        return self


class ProfileResponse(BaseModel):
    id: int
    risk_tolerance: str
    life_stage: str | None
    investment_horizon: str | None
    investing_experience: str | None
    income_stability: str | None
    liquidity_needs: str | None
    preferred_style: str | None
    preferred_method_document_id: int | None
    preferred_method_document_name: str | None
    preferred_method_document_ids: list[int]
    preferred_method_document_names: list[str]
    target_allocation: dict[str, float]
    monthly_net_income: float | None
    monthly_contribution: float | None
    monthly_sector_satellite_budget: float | None
    monthly_total_expenses: float | None
    primary_financial_priority: str | None
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
    cash_goals: list[PlannedCashGoalRequest]
    retirement_cash_months: float
    calculated_retirement_cash_target: float | None
    retirement_cash_target: float | None
    rebalance_threshold: float
    allow_fractional_shares: bool
    rebalance_preference: str
    is_active: bool


class ProfileGuidanceRequest(BaseModel):
    risk_tolerance: str = Field(min_length=1)
    life_stage: str | None = None
    investment_horizon: str | None = None
    investing_experience: str | None = None
    income_stability: str | None = None
    liquidity_needs: str | None = None
    preferred_style: str | None = None
    monthly_net_income: float | None = Field(default=None, ge=0)
    monthly_contribution: float | None = Field(default=None, ge=0)


class ProfileGuidanceReferenceResponse(BaseModel):
    institution: str
    title: str
    principle: str
    url: str


class ProfileGuidanceResponse(BaseModel):
    target_allocation: dict[str, float]
    rationale: list[str]
    warnings: list[str]
    contribution_rate: float | None
    method: str
    method_summary: str
    references: list[ProfileGuidanceReferenceResponse]
    disclaimer: str


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def save_profile(
    request: ProfileRequest,
    session: Session = Depends(get_db_session),
) -> ProfileResponse:
    style_pack = resolve_style_pack(session, request.preferred_style)
    method_documents = resolve_method_documents(
        session, request.preferred_method_document_ids
    )
    profile = UserProfileRepository(session).save_active_profile(
        UserProfileCreate(
            risk_tolerance=request.risk_tolerance,
            life_stage=request.life_stage,
            investment_horizon=request.investment_horizon,
            investing_experience=request.investing_experience,
            income_stability=request.income_stability,
            liquidity_needs=request.liquidity_needs,
            preferred_style=style_pack.id,
            preferred_method_document_id=(
                method_documents[0].id if method_documents else None
            ),
            preferred_method_document_ids=[
                document.id for document in method_documents
            ],
            target_allocation=request.target_allocation,
            monthly_net_income=request.monthly_net_income,
            monthly_contribution=request.monthly_contribution,
            monthly_sector_satellite_budget=request.monthly_sector_satellite_budget,
            monthly_total_expenses=request.monthly_total_expenses,
            primary_financial_priority=request.primary_financial_priority,
            current_age=request.current_age,
            planned_retirement_age=request.planned_retirement_age,
            retirement_planning_age=request.retirement_planning_age,
            retirement_monthly_spending=request.retirement_monthly_spending,
            retirement_monthly_income=request.retirement_monthly_income,
            retirement_current_savings=request.retirement_current_savings,
            retirement_income_taxable=request.retirement_income_taxable,
            retirement_inflation_rate=request.retirement_inflation_rate,
            retirement_current_tax_rate=request.retirement_current_tax_rate,
            retirement_tax_rate=request.retirement_tax_rate,
            retirement_annual_return=request.retirement_annual_return,
            retirement_account_type=request.retirement_account_type,
            retirement_taxable_withdrawal_share=(
                request.retirement_taxable_withdrawal_share
            ),
            retirement_adjust_contributions_for_inflation=(
                request.retirement_adjust_contributions_for_inflation
            ),
            monthly_essential_expenses=request.monthly_essential_expenses,
            current_cash_savings=request.current_cash_savings,
            emergency_fund_months=request.emergency_fund_months,
            emergency_fund_target_amount=request.emergency_fund_target_amount,
            emergency_fund_build_months=request.emergency_fund_build_months,
            education_plan=request.education_plan,
            education_target_year=request.education_target_year,
            education_target_amount=request.education_target_amount,
            near_term_goal_name=request.near_term_goal_name,
            near_term_goal_amount=request.near_term_goal_amount,
            near_term_goal_months=request.near_term_goal_months,
            cash_goals=[goal.model_dump() for goal in request.cash_goals],
            retirement_cash_months=request.retirement_cash_months,
            retirement_cash_target=request.retirement_cash_target,
            rebalance_threshold=request.rebalance_threshold,
            allow_fractional_shares=request.allow_fractional_shares,
            rebalance_preference=request.rebalance_preference,
        )
    )
    return _profile_response(
        profile,
        method_documents=method_documents,
    )


@router.post("/guidance", response_model=ProfileGuidanceResponse)
def get_profile_guidance(
    request: ProfileGuidanceRequest,
    session: Session = Depends(get_db_session),
) -> ProfileGuidanceResponse:
    style_pack = resolve_style_pack(session, request.preferred_style)
    guidance = guide_profile_allocation(
        ProfileGuidanceInput(
            risk_tolerance=request.risk_tolerance,
            life_stage=request.life_stage,
            investment_horizon=request.investment_horizon,
            investing_experience=request.investing_experience,
            income_stability=request.income_stability,
            liquidity_needs=request.liquidity_needs,
            preferred_style=request.preferred_style,
            style_pack=style_pack,
            monthly_net_income=request.monthly_net_income,
            monthly_contribution=request.monthly_contribution,
        )
    )
    return ProfileGuidanceResponse(
        target_allocation=guidance.target_allocation,
        rationale=list(guidance.rationale),
        warnings=list(guidance.warnings),
        contribution_rate=guidance.contribution_rate,
        method=guidance.method,
        method_summary=guidance.method_summary,
        references=[
            ProfileGuidanceReferenceResponse(
                institution=reference.institution,
                title=reference.title,
                principle=reference.principle,
                url=reference.url,
            )
            for reference in guidance.references
        ],
        disclaimer=guidance.disclaimer,
    )


@router.get("", response_model=ProfileResponse)
def get_profile(
    session: Session = Depends(get_db_session),
) -> ProfileResponse:
    profile = UserProfileRepository(session).get_active_profile()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active profile has been saved.",
        )
    method_document_ids = list(profile.preferred_method_document_ids_json or [])
    if not method_document_ids and profile.preferred_method_document_id is not None:
        method_document_ids = [profile.preferred_method_document_id]
    method_documents = resolve_method_documents(session, method_document_ids)
    return _profile_response(
        profile,
        method_documents=method_documents,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_profile(
    session: Session = Depends(get_db_session),
) -> Response:
    UserProfileRepository(session).clear_active_profiles()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _profile_response(
    profile: UserProfile,
    *,
    method_documents: tuple[CompiledMethodDocument, ...],
) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        risk_tolerance=profile.risk_tolerance,
        life_stage=profile.life_stage,
        investment_horizon=profile.investment_horizon,
        investing_experience=profile.investing_experience,
        income_stability=profile.income_stability,
        liquidity_needs=profile.liquidity_needs,
        preferred_style=normalize_style_pack_id(profile.preferred_style),
        preferred_method_document_id=profile.preferred_method_document_id,
        preferred_method_document_name=(
            method_documents[0].name if method_documents else None
        ),
        preferred_method_document_ids=[document.id for document in method_documents],
        preferred_method_document_names=[
            document.name for document in method_documents
        ],
        target_allocation=profile.target_allocation_json,
        monthly_net_income=profile.monthly_net_income,
        monthly_contribution=profile.monthly_contribution,
        monthly_sector_satellite_budget=profile.monthly_sector_satellite_budget,
        monthly_total_expenses=profile.monthly_total_expenses,
        primary_financial_priority=profile.primary_financial_priority,
        current_age=profile.current_age,
        planned_retirement_age=profile.planned_retirement_age,
        retirement_planning_age=profile.retirement_planning_age,
        retirement_monthly_spending=profile.retirement_monthly_spending,
        retirement_monthly_income=profile.retirement_monthly_income,
        retirement_current_savings=profile.retirement_current_savings,
        retirement_income_taxable=profile.retirement_income_taxable,
        retirement_inflation_rate=profile.retirement_inflation_rate,
        retirement_current_tax_rate=profile.retirement_current_tax_rate,
        retirement_tax_rate=profile.retirement_tax_rate,
        retirement_annual_return=profile.retirement_annual_return,
        retirement_account_type=profile.retirement_account_type,
        retirement_taxable_withdrawal_share=(
            profile.retirement_taxable_withdrawal_share
        ),
        retirement_adjust_contributions_for_inflation=(
            profile.retirement_adjust_contributions_for_inflation
        ),
        monthly_essential_expenses=profile.monthly_essential_expenses,
        current_cash_savings=profile.current_cash_savings,
        emergency_fund_months=profile.emergency_fund_months,
        emergency_fund_target_amount=profile.emergency_fund_target_amount,
        emergency_fund_build_months=profile.emergency_fund_build_months,
        education_plan=profile.education_plan,
        education_target_year=(
            profile.education_target_year if profile.education_plan != "none" else None
        ),
        education_target_amount=(
            profile.education_target_amount
            if profile.education_plan != "none"
            else None
        ),
        near_term_goal_name=profile.near_term_goal_name,
        near_term_goal_amount=profile.near_term_goal_amount,
        near_term_goal_months=profile.near_term_goal_months,
        cash_goals=_saved_cash_goals(profile),
        retirement_cash_months=profile.retirement_cash_months,
        calculated_retirement_cash_target=None,
        retirement_cash_target=None,
        rebalance_threshold=profile.rebalance_threshold,
        allow_fractional_shares=profile.allow_fractional_shares,
        rebalance_preference=profile.rebalance_preference,
        is_active=profile.is_active,
    )


def _saved_cash_goals(profile: UserProfile) -> list[PlannedCashGoalRequest]:
    goals: list[PlannedCashGoalRequest] = []
    for raw_goal in profile.cash_goals_json or []:
        try:
            goals.append(PlannedCashGoalRequest.model_validate(raw_goal))
        except ValueError:
            continue
    return goals
