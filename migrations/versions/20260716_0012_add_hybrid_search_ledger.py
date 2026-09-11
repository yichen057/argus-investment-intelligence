"""add hybrid search index and normalized evidence ledger

Revision ID: 20260716_0012
Revises: 20260715_0011
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_0012"
down_revision: Union[str, None] = "20260715_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_ledger_queries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("target_slot", sa.String(length=48), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("search_mode", sa.String(length=16), nullable=False),
        sa.Column("channel_counts_json", sa.JSON(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_ledger_queries_run_id",
        "evidence_ledger_queries",
        ["run_id"],
    )
    op.create_table(
        "evidence_ledger_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=True),
        sa.Column("evidence_item_id", sa.Integer(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("fused_score", sa.Float(), nullable=True),
        sa.Column("match_signals_json", sa.JSON(), nullable=False),
        sa.Column("channel_ranks_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["evidence_item_id"],
            ["evidence_items.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["query_id"],
            ["evidence_ledger_queries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "query_id",
            "chunk_id",
            name="uq_evidence_ledger_query_chunk",
        ),
    )
    op.create_index(
        "ix_evidence_ledger_links_run_id",
        "evidence_ledger_links",
        ["run_id"],
    )
    op.create_index(
        "ix_evidence_ledger_links_query_id",
        "evidence_ledger_links",
        ["query_id"],
    )
    op.create_index(
        "ix_evidence_ledger_links_chunk_id",
        "evidence_ledger_links",
        ["chunk_id"],
    )
    op.create_index(
        "ix_evidence_ledger_links_evidence_item_id",
        "evidence_ledger_links",
        ["evidence_item_id"],
    )
    op.execute(
        "CREATE INDEX ix_chunks_text_fts ON chunks "
        "USING gin (to_tsvector('simple', text))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_text_fts")
    op.drop_index(
        "ix_evidence_ledger_links_evidence_item_id",
        table_name="evidence_ledger_links",
    )
    op.drop_index(
        "ix_evidence_ledger_links_chunk_id",
        table_name="evidence_ledger_links",
    )
    op.drop_index(
        "ix_evidence_ledger_links_query_id",
        table_name="evidence_ledger_links",
    )
    op.drop_index(
        "ix_evidence_ledger_links_run_id",
        table_name="evidence_ledger_links",
    )
    op.drop_table("evidence_ledger_links")
    op.drop_index(
        "ix_evidence_ledger_queries_run_id",
        table_name="evidence_ledger_queries",
    )
    op.drop_table("evidence_ledger_queries")
