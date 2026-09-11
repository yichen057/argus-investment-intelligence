"""separate provider balances from provider charges

Revision ID: 20260720_0020
Revises: 20260720_0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_0020"
down_revision: str | None = "20260720_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "provider_billing_snapshots",
        "actual_cost",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Numeric(20, 10),
        existing_nullable=False,
    )
    op.create_table(
        "provider_account_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("billing_tier", sa.String(length=64), nullable=True),
        sa.Column("billing_status", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("available_balance", sa.Numeric(20, 10), nullable=True),
        sa.Column("paid_balance", sa.Numeric(20, 10), nullable=True),
        sa.Column("promotional_balance", sa.Numeric(20, 10), nullable=True),
        sa.Column("source_reference", sa.String(length=512), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_provider_account_snapshots_provider_created",
        "provider_account_snapshots",
        ["provider", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_account_snapshots_provider_created",
        table_name="provider_account_snapshots",
    )
    op.drop_table("provider_account_snapshots")
    op.alter_column(
        "provider_billing_snapshots",
        "actual_cost",
        existing_type=sa.Numeric(20, 10),
        type_=sa.Numeric(18, 6),
        existing_nullable=False,
    )
