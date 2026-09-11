"""add profile cash-flow feasibility and generated retirement runway

Revision ID: 20260715_0007
Revises: 20260715_0006
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0007"
down_revision: str | None = "20260715_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("monthly_total_expenses", sa.Float()))
    op.add_column(
        "user_profiles",
        sa.Column("primary_financial_priority", sa.String(length=256)),
    )
    op.add_column(
        "user_profiles", sa.Column("near_term_goal_name", sa.String(length=256))
    )
    op.add_column("user_profiles", sa.Column("near_term_goal_amount", sa.Float()))
    op.add_column("user_profiles", sa.Column("near_term_goal_months", sa.Integer()))
    op.add_column(
        "user_profiles",
        sa.Column(
            "retirement_cash_months",
            sa.Float(),
            nullable=False,
            server_default="12",
        ),
    )

    connection = op.get_bind()
    profiles = sa.table(
        "user_profiles",
        sa.column("id", sa.Integer()),
        sa.column("monthly_essential_expenses", sa.Float()),
        sa.column("retirement_cash_target", sa.Float()),
        sa.column("retirement_cash_months", sa.Float()),
        sa.column("education_plan", sa.String()),
        sa.column("education_target_year", sa.Integer()),
        sa.column("education_target_amount", sa.Float()),
    )
    connection.execute(
        sa.update(profiles)
        .where(profiles.c.education_plan == "none")
        .values(education_target_year=None, education_target_amount=None)
    )
    rows = connection.execute(
        sa.select(
            profiles.c.id,
            profiles.c.monthly_essential_expenses,
            profiles.c.retirement_cash_target,
        )
    ).mappings()
    for row in rows:
        expenses = float(row["monthly_essential_expenses"] or 0)
        target = float(row["retirement_cash_target"] or 0)
        if expenses > 0 and target > 0:
            months = min(60.0, max(0.0, target / expenses))
            connection.execute(
                sa.update(profiles)
                .where(profiles.c.id == row["id"])
                .values(retirement_cash_months=months)
            )


def downgrade() -> None:
    for name in (
        "retirement_cash_months",
        "near_term_goal_months",
        "near_term_goal_amount",
        "near_term_goal_name",
        "primary_financial_priority",
        "monthly_total_expenses",
    ):
        op.drop_column("user_profiles", name)
