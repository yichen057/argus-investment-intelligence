"""add recurring net income to user profiles

Revision ID: 20260715_0005
Revises: 20260714_0004
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0005"
down_revision: str | None = "20260714_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("monthly_net_income", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "monthly_net_income")
