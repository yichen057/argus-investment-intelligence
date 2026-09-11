"""separate persistent API usage from deletable run traces

Revision ID: 20260720_0019
Revises: 20260720_0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_0019"
down_revision: str | None = "20260720_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_usage_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usage_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("run_id_snapshot", sa.Integer(), nullable=True),
        sa.Column("model_call_id_snapshot", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("deployment", sa.String(length=64), nullable=False),
        sa.Column("serving_engine", sa.String(length=128), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "completion_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("input_cost_per_million_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("output_cost_per_million_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "estimated_cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "source", sa.String(length=32), nullable=False, server_default="runtime"
        ),
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
        "ix_api_usage_ledger_run_id_snapshot", "api_usage_ledger", ["run_id_snapshot"]
    )
    op.create_index(
        "ix_api_usage_ledger_model_call_id_snapshot",
        "api_usage_ledger",
        ["model_call_id_snapshot"],
    )
    op.create_index(
        "ix_api_usage_ledger_provider_model", "api_usage_ledger", ["provider", "model"]
    )
    op.create_index(
        "ix_api_usage_ledger_created_at", "api_usage_ledger", ["created_at"]
    )

    op.create_table(
        "provider_billing_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("actual_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=True),
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
        "ix_provider_billing_snapshots_provider_period",
        "provider_billing_snapshots",
        ["provider", "period_start", "period_end"],
    )

    # Preserve every ModelCall that still exists at migration time. Older calls
    # already deleted with their Runs cannot be reconstructed and are not invented.
    op.execute(
        sa.text(
            """
            INSERT INTO api_usage_ledger (
                usage_key,
                run_id_snapshot,
                model_call_id_snapshot,
                provider,
                model,
                deployment,
                serving_engine,
                prompt_tokens,
                completion_tokens,
                request_count,
                estimated_cost_usd,
                latency_ms,
                success,
                source,
                created_at,
                updated_at
            )
            SELECT
                'migration:model_call:' || CAST(id AS VARCHAR),
                run_id,
                id,
                provider,
                model,
                deployment,
                serving_engine,
                prompt_tokens,
                completion_tokens,
                1,
                estimated_cost_usd,
                latency_ms,
                success,
                'migration_backfill',
                created_at,
                updated_at
            FROM model_calls
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_billing_snapshots_provider_period",
        table_name="provider_billing_snapshots",
    )
    op.drop_table("provider_billing_snapshots")
    op.drop_index("ix_api_usage_ledger_created_at", table_name="api_usage_ledger")
    op.drop_index("ix_api_usage_ledger_provider_model", table_name="api_usage_ledger")
    op.drop_index(
        "ix_api_usage_ledger_model_call_id_snapshot", table_name="api_usage_ledger"
    )
    op.drop_index("ix_api_usage_ledger_run_id_snapshot", table_name="api_usage_ledger")
    op.drop_table("api_usage_ledger")
