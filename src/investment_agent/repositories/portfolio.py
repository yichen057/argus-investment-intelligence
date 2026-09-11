from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from investment_agent.storage.models import (
    PortfolioPosition,
    PortfolioSnapshot,
    UserProfile,
)


@dataclass(frozen=True)
class PortfolioPositionCreate:
    symbol: str
    name: str
    asset_class: str
    quantity: float
    price: float
    market_value: float
    cost_basis: float | None
    account: str | None
    import_id: str
    as_of_date: date
    source_key: str = "file_upload"
    source_scope: str = "manual"


@dataclass(frozen=True)
class PortfolioSnapshotCreate:
    snapshot_key: str
    source_key: str
    source_name: str
    source_scope: str
    observed_at: datetime
    is_live: bool
    status: str = "complete"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class UserProfileCreate:
    risk_tolerance: str
    life_stage: str | None = None
    investment_horizon: str | None = None
    investing_experience: str | None = None
    income_stability: str | None = None
    liquidity_needs: str | None = None
    preferred_style: str | None = None
    preferred_method_document_id: int | None = None
    preferred_method_document_ids: list[int] = field(default_factory=list)
    target_allocation: dict[str, float] = field(default_factory=dict)
    monthly_net_income: float | None = None
    monthly_contribution: float | None = None
    monthly_sector_satellite_budget: float | None = None
    monthly_total_expenses: float | None = None
    primary_financial_priority: str | None = None
    current_age: int | None = None
    planned_retirement_age: int | None = None
    retirement_planning_age: int = 100
    retirement_monthly_spending: float | None = None
    retirement_monthly_income: float | None = None
    retirement_current_savings: float | None = None
    retirement_income_taxable: bool = True
    retirement_inflation_rate: float = 0.025
    retirement_current_tax_rate: float | None = None
    retirement_tax_rate: float | None = None
    retirement_annual_return: float = 0.05
    retirement_account_type: str | None = None
    retirement_taxable_withdrawal_share: float | None = None
    retirement_adjust_contributions_for_inflation: bool = False
    monthly_essential_expenses: float | None = None
    current_cash_savings: float | None = None
    emergency_fund_months: float = 0.0
    emergency_fund_target_amount: float | None = None
    emergency_fund_build_months: int = 12
    education_plan: str = "none"
    education_target_year: int | None = None
    education_target_amount: float | None = None
    near_term_goal_name: str | None = None
    near_term_goal_amount: float | None = None
    near_term_goal_months: int | None = None
    cash_goals: list[dict[str, object]] = field(default_factory=list)
    retirement_cash_months: float = 0.0
    retirement_cash_target: float | None = None
    rebalance_threshold: float = 0.05
    allow_fractional_shares: bool = False
    rebalance_preference: str = "contributions_first"


class PortfolioRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_positions(
        self,
        positions: list[PortfolioPositionCreate],
    ) -> list[PortfolioPosition]:
        """Compatibility wrapper for the offline manual source."""

        snapshot = PortfolioSnapshotCreate(
            snapshot_key=positions[0].import_id if positions else "empty-file-upload",
            source_key="file_upload",
            source_name="Uploaded portfolio file",
            source_scope="manual",
            observed_at=datetime.now(timezone.utc),
            is_live=False,
        )
        return self.replace_source_positions(positions, snapshot=snapshot)

    def replace_source_positions(
        self,
        positions: list[PortfolioPositionCreate],
        *,
        snapshot: PortfolioSnapshotCreate,
    ) -> list[PortfolioPosition]:
        """Atomically replace one source scope without erasing other sources."""

        # Rows created before the source-aware migration have no snapshot parent.
        # Remove only the matching legacy source the first time that source is
        # refreshed; otherwise those rows would be displayed beside the new snapshot.
        self._session.execute(
            delete(PortfolioPosition).where(
                PortfolioPosition.snapshot_id.is_(None),
                PortfolioPosition.source_key == snapshot.source_key,
                PortfolioPosition.source_scope == snapshot.source_scope,
            )
        )

        previous_ids = list(
            self._session.scalars(
                select(PortfolioSnapshot.id).where(
                    PortfolioSnapshot.source_key == snapshot.source_key,
                    PortfolioSnapshot.source_scope == snapshot.source_scope,
                )
            )
        )
        if previous_ids:
            self._session.execute(
                delete(PortfolioPosition).where(
                    PortfolioPosition.snapshot_id.in_(previous_ids)
                )
            )
            self._session.execute(
                delete(PortfolioSnapshot).where(
                    PortfolioSnapshot.id.in_(previous_ids)
                )
            )
        snapshot_record = PortfolioSnapshot(
            snapshot_key=snapshot.snapshot_key,
            source_key=snapshot.source_key,
            source_name=snapshot.source_name,
            source_scope=snapshot.source_scope,
            observed_at=snapshot.observed_at,
            is_live=snapshot.is_live,
            is_active=True,
            position_count=len(positions),
            status=snapshot.status,
            metadata_json=snapshot.metadata,
        )
        self._session.add(snapshot_record)
        self._session.flush()
        records = [
            PortfolioPosition(
                snapshot_id=snapshot_record.id,
                source_key=snapshot.source_key,
                source_scope=snapshot.source_scope,
                symbol=position.symbol,
                name=position.name,
                asset_class=position.asset_class,
                quantity=position.quantity,
                price=position.price,
                market_value=position.market_value,
                cost_basis=position.cost_basis,
                account=position.account,
                import_id=position.import_id,
                as_of_date=position.as_of_date,
            )
            for position in positions
        ]
        self._session.add_all(records)
        self._session.flush()
        return records

    def list_positions(self) -> list[PortfolioPosition]:
        records = list(
            self._session.scalars(
                select(PortfolioPosition).order_by(
                    PortfolioPosition.market_value.desc()
                )
            )
        )
        return _merge_source_positions(records)


def _merge_source_positions(
    records: list[PortfolioPosition],
) -> list[PortfolioPosition]:
    """Prefer Robinhood for a ticker while preserving unrelated uploaded assets.

    The user has one Robinhood Investments account and explicitly chose Robinhood as
    the source of truth for overlapping securities. File-only assets (for example a
    bank CD or outside retirement account) remain visible when Robinhood does not
    return the same symbol. Raw source snapshots remain separately auditable.
    """

    robinhood_symbols = {
        record.symbol.upper()
        for record in records
        if record.source_key == "robinhood_mcp"
    }
    selected: dict[tuple[str, str], PortfolioPosition] = {}
    for record in records:
        if (
            record.source_key != "robinhood_mcp"
            and record.symbol.upper() in robinhood_symbols
        ):
            continue
        key = (record.symbol.upper(), (record.account or "").strip().lower())
        if key not in selected:
            selected[key] = record
    return sorted(selected.values(), key=lambda item: item.market_value, reverse=True)


class UserProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active_profile(self) -> UserProfile | None:
        return self._session.scalar(
            select(UserProfile)
            .where(UserProfile.is_active.is_(True))
            .order_by(UserProfile.created_at.desc())
        )

    def save_active_profile(self, payload: UserProfileCreate) -> UserProfile:
        self._session.execute(
            update(UserProfile)
            .where(UserProfile.is_active.is_(True))
            .values(is_active=False)
        )
        profile = UserProfile(
            risk_tolerance=payload.risk_tolerance,
            life_stage=payload.life_stage,
            investment_horizon=payload.investment_horizon,
            investing_experience=payload.investing_experience,
            income_stability=payload.income_stability,
            liquidity_needs=payload.liquidity_needs,
            preferred_style=payload.preferred_style,
            preferred_method_document_id=payload.preferred_method_document_id,
            preferred_method_document_ids_json=payload.preferred_method_document_ids,
            target_allocation_json=payload.target_allocation,
            monthly_net_income=payload.monthly_net_income,
            monthly_contribution=payload.monthly_contribution,
            monthly_sector_satellite_budget=payload.monthly_sector_satellite_budget,
            monthly_total_expenses=payload.monthly_total_expenses,
            primary_financial_priority=payload.primary_financial_priority,
            current_age=payload.current_age,
            planned_retirement_age=payload.planned_retirement_age,
            retirement_planning_age=payload.retirement_planning_age,
            retirement_monthly_spending=payload.retirement_monthly_spending,
            retirement_monthly_income=payload.retirement_monthly_income,
            retirement_current_savings=payload.retirement_current_savings,
            retirement_income_taxable=payload.retirement_income_taxable,
            retirement_inflation_rate=payload.retirement_inflation_rate,
            retirement_current_tax_rate=payload.retirement_current_tax_rate,
            retirement_tax_rate=payload.retirement_tax_rate,
            retirement_annual_return=payload.retirement_annual_return,
            retirement_account_type=payload.retirement_account_type,
            retirement_taxable_withdrawal_share=(
                payload.retirement_taxable_withdrawal_share
            ),
            retirement_adjust_contributions_for_inflation=(
                payload.retirement_adjust_contributions_for_inflation
            ),
            monthly_essential_expenses=payload.monthly_essential_expenses,
            current_cash_savings=payload.current_cash_savings,
            emergency_fund_months=payload.emergency_fund_months,
            emergency_fund_target_amount=payload.emergency_fund_target_amount,
            emergency_fund_build_months=payload.emergency_fund_build_months,
            education_plan=payload.education_plan,
            education_target_year=payload.education_target_year,
            education_target_amount=payload.education_target_amount,
            near_term_goal_name=payload.near_term_goal_name,
            near_term_goal_amount=payload.near_term_goal_amount,
            near_term_goal_months=payload.near_term_goal_months,
            cash_goals_json=payload.cash_goals,
            retirement_cash_months=payload.retirement_cash_months,
            retirement_cash_target=payload.retirement_cash_target,
            rebalance_threshold=payload.rebalance_threshold,
            allow_fractional_shares=payload.allow_fractional_shares,
            rebalance_preference=payload.rebalance_preference,
            is_active=True,
        )
        self._session.add(profile)
        self._session.flush()
        return profile

    def clear_active_profiles(self) -> int:
        profiles = list(
            self._session.scalars(
                select(UserProfile).where(UserProfile.is_active.is_(True))
            )
        )
        for profile in profiles:
            profile.is_active = False
        self._session.flush()
        return len(profiles)
