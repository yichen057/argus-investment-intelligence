"""add mixed retirement account withdrawal share

Revision ID: 20260720_0018
Revises: 20260718_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_0018"
down_revision: str | None = "20260718_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "retirement_taxable_withdrawal_share",
            sa.Float(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "retirement_taxable_withdrawal_share")
