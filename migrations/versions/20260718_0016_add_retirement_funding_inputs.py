"""add retirement funding and sector satellite budget inputs

Revision ID: 20260718_0016
Revises: 20260718_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0016"
down_revision: str | None = "20260718_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("retirement_monthly_spending", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column("retirement_monthly_income", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column("monthly_sector_satellite_budget", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "monthly_sector_satellite_budget")
    op.drop_column("user_profiles", "retirement_monthly_income")
    op.drop_column("user_profiles", "retirement_monthly_spending")
