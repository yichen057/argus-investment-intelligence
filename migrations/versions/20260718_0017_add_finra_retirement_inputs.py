"""add FINRA-style retirement calculator inputs

Revision ID: 20260718_0017
Revises: 20260718_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0017"
down_revision: str | None = "20260718_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("retirement_current_savings", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "retirement_income_taxable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "retirement_inflation_rate",
            sa.Float(),
            nullable=False,
            server_default="0.025",
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column("retirement_current_tax_rate", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column("retirement_tax_rate", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "retirement_annual_return",
            sa.Float(),
            nullable=False,
            server_default="0.05",
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column("retirement_account_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "retirement_adjust_contributions_for_inflation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "user_profiles", "retirement_adjust_contributions_for_inflation"
    )
    op.drop_column("user_profiles", "retirement_account_type")
    op.drop_column("user_profiles", "retirement_annual_return")
    op.drop_column("user_profiles", "retirement_tax_rate")
    op.drop_column("user_profiles", "retirement_current_tax_rate")
    op.drop_column("user_profiles", "retirement_inflation_rate")
    op.drop_column("user_profiles", "retirement_income_taxable")
    op.drop_column("user_profiles", "retirement_current_savings")
