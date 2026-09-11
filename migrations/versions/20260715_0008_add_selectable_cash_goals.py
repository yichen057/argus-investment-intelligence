"""add selectable short-term cash goals

Revision ID: 20260715_0008
Revises: 20260715_0007
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0008"
down_revision: str | None = "20260715_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "cash_goals_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )

    connection = op.get_bind()
    profiles = sa.table(
        "user_profiles",
        sa.column("id", sa.Integer()),
        sa.column("near_term_goal_name", sa.String()),
        sa.column("near_term_goal_amount", sa.Float()),
        sa.column("near_term_goal_months", sa.Integer()),
        sa.column("cash_goals_json", sa.JSON()),
    )
    rows = connection.execute(
        sa.select(
            profiles.c.id,
            profiles.c.near_term_goal_name,
            profiles.c.near_term_goal_amount,
            profiles.c.near_term_goal_months,
        ).where(profiles.c.near_term_goal_name.is_not(None))
    ).mappings()
    for row in rows:
        connection.execute(
            sa.update(profiles)
            .where(profiles.c.id == row["id"])
            .values(
                cash_goals_json=[
                    {
                        "goal_type": "major_purchase",
                        "target_amount": row["near_term_goal_amount"],
                        "months_until_needed": row["near_term_goal_months"],
                        "priority": "important",
                    }
                ]
            )
        )


def downgrade() -> None:
    op.drop_column("user_profiles", "cash_goals_json")
