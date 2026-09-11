"""resize pgvector column for semantic embeddings

Revision ID: 20260712_0003
Revises: 20260712_0002
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260712_0003"
down_revision: str | None = "20260712_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index(
        "ix_chunk_embeddings_vector_hnsw",
        table_name="chunk_embeddings",
        postgresql_using="hnsw",
    )
    op.execute("UPDATE chunk_embeddings SET embedding_vector = NULL")
    op.execute(
        "ALTER TABLE chunk_embeddings ALTER COLUMN embedding_vector "
        "TYPE vector(768) USING NULL::vector(768)"
    )
    op.execute(
        "CREATE INDEX ix_chunk_embeddings_vector_hnsw ON chunk_embeddings "
        "USING hnsw (embedding_vector vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index(
        "ix_chunk_embeddings_vector_hnsw",
        table_name="chunk_embeddings",
        postgresql_using="hnsw",
    )
    op.execute("UPDATE chunk_embeddings SET embedding_vector = NULL")
    op.execute(
        "ALTER TABLE chunk_embeddings ALTER COLUMN embedding_vector "
        "TYPE vector(16) USING NULL::vector(16)"
    )
    op.execute(
        "CREATE INDEX ix_chunk_embeddings_vector_hnsw ON chunk_embeddings "
        "USING hnsw (embedding_vector vector_cosine_ops)"
    )
