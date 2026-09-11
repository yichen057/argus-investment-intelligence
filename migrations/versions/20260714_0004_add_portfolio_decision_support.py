"""add dated portfolio snapshots and recommendation preferences

Revision ID: 20260714_0004
Revises: 20260712_0003
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0004"
down_revision: str | None = "20260712_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portfolio_positions",
        sa.Column(
            "as_of_date",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column("monthly_contribution", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "rebalance_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.05",
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "allow_fractional_shares",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "rebalance_preference",
            sa.String(length=32),
            nullable=False,
            server_default="contributions_first",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "rebalance_preference")
    op.drop_column("user_profiles", "allow_fractional_shares")
    op.drop_column("user_profiles", "rebalance_threshold")
    op.drop_column("user_profiles", "monthly_contribution")
    op.drop_column("portfolio_positions", "as_of_date")
