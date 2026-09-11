"""add pgvector embedding storage

Revision ID: 20260712_0002
Revises: 20260709_0001
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260712_0002"
down_revision: str | None = "20260709_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.add_column(
            "chunk_embeddings",
            sa.Column("embedding_vector", Vector(16), nullable=True),
        )
        op.create_index(
            "ix_chunk_embeddings_vector_hnsw",
            "chunk_embeddings",
            ["embedding_vector"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding_vector": "vector_cosine_ops"},
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "ix_chunk_embeddings_vector_hnsw",
            table_name="chunk_embeddings",
            postgresql_using="hnsw",
        )
        op.drop_column("chunk_embeddings", "embedding_vector")
