"""add preview-only market review alerts

Revision ID: 20260728_0023
Revises: 20260722_0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0023"
down_revision: str | None = "20260722_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_alert_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("delivery_mode", sa.String(32), nullable=False, server_default="preview_only"),
        sa.Column("scope", sa.String(32), nullable=False, server_default="holdings"),
        sa.Column("sensitivity", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="America/Los_Angeles"),
        sa.Column("quiet_hours_start", sa.String(5), nullable=False, server_default="21:00"),
        sa.Column("quiet_hours_end", sa.String(5), nullable=False, server_default="07:00"),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "market_alert_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="preview"),
        sa.Column("holding_quantity", sa.Float(), nullable=False),
        sa.Column("portfolio_weight", sa.Float(), nullable=False),
        sa.Column("latest_close", sa.Float(), nullable=False),
        sa.Column("market_as_of_date", sa.Date(), nullable=False),
        sa.Column("holdings_as_of_date", sa.Date(), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("counter_evidence_json", sa.JSON(), nullable=False),
        sa.Column("invalidation_conditions_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("deduplication_key", sa.String(128), nullable=False),
        sa.Column("feedback", sa.String(32), nullable=True),
        sa.Column("feedback_action", sa.String(256), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("deduplication_key", name="uq_market_alert_deduplication_key"),
    )
    op.create_index(
        "ix_market_alert_symbol_created",
        "market_alert_snapshots",
        ["symbol", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_alert_symbol_created", table_name="market_alert_snapshots")
    op.drop_table("market_alert_snapshots")
    op.drop_table("market_alert_settings")
