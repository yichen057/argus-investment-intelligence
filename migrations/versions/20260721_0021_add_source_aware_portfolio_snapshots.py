"""add source-aware portfolio snapshots

Revision ID: 20260721_0021
Revises: 20260720_0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0021"
down_revision: str | None = "20260720_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("source_scope", sa.String(length=128), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_live", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
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
        "ix_portfolio_snapshots_source_active",
        "portfolio_snapshots",
        ["source_key", "source_scope", "is_active"],
    )
    op.add_column(
        "portfolio_positions",
        sa.Column("snapshot_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "portfolio_positions",
        sa.Column(
            "source_key",
            sa.String(length=64),
            nullable=False,
            server_default="file_upload",
        ),
    )
    op.add_column(
        "portfolio_positions",
        sa.Column(
            "source_scope",
            sa.String(length=128),
            nullable=False,
            server_default="manual",
        ),
    )
    op.create_index(
        "ix_portfolio_positions_snapshot_id",
        "portfolio_positions",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_portfolio_positions_source_key",
        "portfolio_positions",
        ["source_key"],
    )
    op.create_foreign_key(
        "fk_portfolio_positions_snapshot_id",
        "portfolio_positions",
        "portfolio_snapshots",
        ["snapshot_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_portfolio_positions_snapshot_id",
        "portfolio_positions",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_portfolio_positions_source_key", table_name="portfolio_positions"
    )
    op.drop_index(
        "ix_portfolio_positions_snapshot_id", table_name="portfolio_positions"
    )
    op.drop_column("portfolio_positions", "source_scope")
    op.drop_column("portfolio_positions", "source_key")
    op.drop_column("portfolio_positions", "snapshot_id")
    op.drop_index(
        "ix_portfolio_snapshots_source_active", table_name="portfolio_snapshots"
    )
    op.drop_table("portfolio_snapshots")
