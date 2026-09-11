"""separate investment allocation from cash goal planning

Revision ID: 20260715_0006
Revises: 20260715_0005
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0006"
down_revision: str | None = "20260715_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = (
        sa.Column("current_age", sa.Integer(), nullable=True),
        sa.Column("planned_retirement_age", sa.Integer(), nullable=True),
        sa.Column("monthly_essential_expenses", sa.Float(), nullable=True),
        sa.Column("current_cash_savings", sa.Float(), nullable=True),
        sa.Column(
            "emergency_fund_months",
            sa.Float(),
            nullable=False,
            server_default="6",
        ),
        sa.Column(
            "emergency_fund_build_months",
            sa.Integer(),
            nullable=False,
            server_default="12",
        ),
        sa.Column(
            "education_plan",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
        sa.Column("education_target_year", sa.Integer(), nullable=True),
        sa.Column("education_target_amount", sa.Float(), nullable=True),
        sa.Column("retirement_cash_target", sa.Float(), nullable=True),
    )
    for column in columns:
        op.add_column("user_profiles", column)

    connection = op.get_bind()
    profiles = sa.table(
        "user_profiles",
        sa.column("id", sa.Integer()),
        sa.column("target_allocation_json", sa.JSON()),
    )
    rows = connection.execute(
        sa.select(profiles.c.id, profiles.c.target_allocation_json)
    ).mappings()
    for row in rows:
        allocation = dict(row["target_allocation_json"] or {})
        allocation = {
            label: float(weight)
            for label, weight in allocation.items()
            if label.strip().lower() != "cash"
        }
        total = sum(allocation.values())
        normalized = (
            {label: weight / total for label, weight in allocation.items()}
            if total > 0
            else {}
        )
        connection.execute(
            sa.update(profiles)
            .where(profiles.c.id == row["id"])
            .values(target_allocation_json=normalized)
        )


def downgrade() -> None:
    for name in (
        "retirement_cash_target",
        "education_target_amount",
        "education_target_year",
        "education_plan",
        "emergency_fund_build_months",
        "emergency_fund_months",
        "current_cash_savings",
        "monthly_essential_expenses",
        "planned_retirement_age",
        "current_age",
    ):
        op.drop_column("user_profiles", name)
