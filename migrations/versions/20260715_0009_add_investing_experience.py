"""add investing experience to user profiles

Revision ID: 20260715_0009
Revises: 20260715_0008
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0009"
down_revision: str | None = "20260715_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("investing_experience", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "investing_experience")
