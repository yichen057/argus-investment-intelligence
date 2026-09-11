"""add bounded expert method panel and direct emergency target

Revision ID: 20260718_0015
Revises: 20260718_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0015"
down_revision: str | None = "20260718_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "preferred_method_document_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column("emergency_fund_target_amount", sa.Float(), nullable=True),
    )
    op.execute(
        "UPDATE user_profiles "
        "SET preferred_method_document_ids_json = "
        "json_build_array(preferred_method_document_id) "
        "WHERE preferred_method_document_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "emergency_fund_target_amount")
    op.drop_column("user_profiles", "preferred_method_document_ids_json")
