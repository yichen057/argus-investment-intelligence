"""link a saved profile to its optional expert method document

Revision ID: 20260718_0014
Revises: 20260717_0013
Create Date: 2026-07-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0014"
down_revision: Union[str, None] = "20260717_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("preferred_method_document_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_user_profiles_preferred_method_document_id",
        "user_profiles",
        ["preferred_method_document_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_user_profiles_preferred_method_document_id",
        "user_profiles",
        "investment_method_documents",
        ["preferred_method_document_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_user_profiles_preferred_method_document_id",
        "user_profiles",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_user_profiles_preferred_method_document_id",
        table_name="user_profiles",
    )
    op.drop_column("user_profiles", "preferred_method_document_id")
