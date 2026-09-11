from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from investment_agent.storage.models import Chunk, ChunkEmbedding, Document, EvidenceItem


@dataclass(frozen=True)
class DocumentCreate:
    source_uri: str
    source_type: str
    title: str
    content_hash: str
    access_scope: str = "internal"
    parser_version: str = "local-v1"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceItemCreate:
    document_id: int
    source_uri: str
    source_type: str
    title: str
    evidence_grade: str
    excerpt: str
    content_hash: str
    access_scope: str = "internal"
    parser_version: str = "local-v1"
    publisher: str | None = None
    page_or_section: str | None = None
    publication_date: date | None = None
    data_as_of_date: date | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkCreate:
    document_id: int
    evidence_item_id: int | None
    chunk_index: int
    text: str
    content_hash: str
    token_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_document(self, payload: DocumentCreate) -> Document:
        document = Document(
            source_uri=payload.source_uri,
            source_type=payload.source_type,
            title=payload.title,
            content_hash=payload.content_hash,
            access_scope=payload.access_scope,
            parser_version=payload.parser_version,
            metadata_json=payload.metadata,
        )
        self._session.add(document)
        self._session.flush()
        return document

    def get_document(self, document_id: int) -> Document | None:
        return self._session.get(Document, document_id)

    def get_document_by_hash(self, content_hash: str) -> Document | None:
        statement = select(Document).where(Document.content_hash == content_hash)
        return self._session.scalar(statement)

    def list_documents(self) -> list[Document]:
        statement = select(Document).order_by(
            Document.created_at.desc(),
            Document.id.desc(),
        )
        return list(self._session.scalars(statement))

    def delete_document(self, document_id: int) -> bool:
        document = self.get_document(document_id)
        if document is None:
            return False
        self._session.delete(document)
        self._session.flush()
        return True

    def create_evidence_item(self, payload: EvidenceItemCreate) -> EvidenceItem:
        evidence_item = EvidenceItem(
            document_id=payload.document_id,
            source_uri=payload.source_uri,
            source_type=payload.source_type,
            title=payload.title,
            publisher=payload.publisher,
            page_or_section=payload.page_or_section,
            publication_date=payload.publication_date,
            data_as_of_date=payload.data_as_of_date,
            evidence_grade=payload.evidence_grade,
            excerpt=payload.excerpt,
            content_hash=payload.content_hash,
            access_scope=payload.access_scope,
            parser_version=payload.parser_version,
            metadata_json=payload.metadata,
        )
        self._session.add(evidence_item)
        self._session.flush()
        return evidence_item

    def list_evidence_for_document(self, document_id: int) -> list[EvidenceItem]:
        statement = (
            select(EvidenceItem)
            .where(EvidenceItem.document_id == document_id)
            .order_by(EvidenceItem.created_at.asc())
        )
        return list(self._session.scalars(statement))

    def create_chunk(self, payload: ChunkCreate):
        chunk = Chunk(
            document_id=payload.document_id,
            evidence_item_id=payload.evidence_item_id,
            chunk_index=payload.chunk_index,
            text=payload.text,
            token_count=payload.token_count,
            content_hash=payload.content_hash,
            metadata_json=payload.metadata,
        )
        self._session.add(chunk)
        self._session.flush()
        return chunk

    def list_chunks_for_document(self, document_id: int):
        statement = (
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index.asc())
        )
        return list(self._session.scalars(statement))

    def list_chunk_records(
        self,
        *,
        document_id: int | None = None,
        access_scope: str | None = None,
        as_of_date: date | None = None,
    ) -> list[tuple[Chunk, EvidenceItem | None, Document]]:
        """Return filtered chunks with the metadata required by every search channel."""

        statement = (
            select(Chunk, EvidenceItem, Document)
            .join(Document, Document.id == Chunk.document_id)
            .outerjoin(EvidenceItem, EvidenceItem.id == Chunk.evidence_item_id)
        )
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        if access_scope is not None:
            statement = statement.where(Document.access_scope == access_scope)
        if as_of_date is not None:
            statement = statement.where(
                (EvidenceItem.publication_date.is_(None))
                | (EvidenceItem.publication_date <= as_of_date),
                (EvidenceItem.data_as_of_date.is_(None))
                | (EvidenceItem.data_as_of_date <= as_of_date),
            )
        statement = statement.order_by(Document.id.asc(), Chunk.chunk_index.asc())
        return [
            (chunk, evidence, document)
            for chunk, evidence, document in self._session.execute(statement).all()
        ]

    def search_chunks_full_text_postgresql(
        self,
        *,
        query: str,
        top_k: int,
        document_id: int | None = None,
        access_scope: str | None = None,
        as_of_date: date | None = None,
    ) -> list[tuple[Chunk, EvidenceItem | None, Document, float]]:
        """Use PostgreSQL FTS without making it a requirement for SQLite tests."""

        if self._session.get_bind().dialect.name != "postgresql":
            raise RuntimeError("PostgreSQL full-text search requires PostgreSQL")
        search_document = func.to_tsvector("simple", Chunk.text)
        search_query = func.websearch_to_tsquery("simple", query)
        rank = func.ts_rank_cd(search_document, search_query)
        statement = (
            select(Chunk, EvidenceItem, Document, rank)
            .join(Document, Document.id == Chunk.document_id)
            .outerjoin(EvidenceItem, EvidenceItem.id == Chunk.evidence_item_id)
            .where(search_document.op("@@")(search_query))
            .order_by(rank.desc(), Chunk.id.asc())
            .limit(top_k)
        )
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        if access_scope is not None:
            statement = statement.where(Document.access_scope == access_scope)
        if as_of_date is not None:
            statement = statement.where(
                (EvidenceItem.publication_date.is_(None))
                | (EvidenceItem.publication_date <= as_of_date),
                (EvidenceItem.data_as_of_date.is_(None))
                | (EvidenceItem.data_as_of_date <= as_of_date),
            )
        return [
            (chunk, evidence, document, float(score))
            for chunk, evidence, document, score in self._session.execute(statement).all()
        ]

    def list_neighbor_chunks(
        self,
        *,
        document_id: int,
        chunk_index: int,
        window: int = 1,
        as_of_date: date | None = None,
    ) -> list[Chunk]:
        if window < 0:
            raise ValueError("Neighbor window cannot be negative")
        statement = (
            select(Chunk)
            .outerjoin(EvidenceItem, EvidenceItem.id == Chunk.evidence_item_id)
            .where(
                Chunk.document_id == document_id,
                Chunk.chunk_index >= chunk_index - window,
                Chunk.chunk_index <= chunk_index + window,
            )
            .order_by(Chunk.chunk_index.asc())
        )
        if as_of_date is not None:
            statement = statement.where(
                (EvidenceItem.publication_date.is_(None))
                | (EvidenceItem.publication_date <= as_of_date),
                (EvidenceItem.data_as_of_date.is_(None))
                | (EvidenceItem.data_as_of_date <= as_of_date),
            )
        return list(self._session.scalars(statement))

    def upsert_chunk_embedding(
        self,
        *,
        chunk_id: int,
        provider: str,
        model: str,
        dimensions: int,
        embedding: list[float],
    ) -> bool:
        embedding_vector = (
            embedding
            if self._session.get_bind().dialect.name == "postgresql"
            and dimensions == 768
            else None
        )
        statement = select(ChunkEmbedding).where(
            ChunkEmbedding.chunk_id == chunk_id,
            ChunkEmbedding.provider == provider,
            ChunkEmbedding.model == model,
        )
        existing = self._session.scalar(statement)
        if existing is not None:
            existing.dimensions = dimensions
            existing.embedding_json = embedding
            existing.embedding_vector = embedding_vector
            self._session.flush()
            return False

        self._session.add(
            ChunkEmbedding(
                chunk_id=chunk_id,
                provider=provider,
                model=model,
                dimensions=dimensions,
                embedding_json=embedding,
                embedding_vector=embedding_vector,
            )
        )
        self._session.flush()
        return True

    def list_embeddings_for_document(self, document_id: int) -> list[ChunkEmbedding]:
        statement = (
            select(ChunkEmbedding)
            .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index.asc())
        )
        return list(self._session.scalars(statement))

    def list_embedding_chunk_ids(
        self,
        *,
        document_id: int,
        provider: str,
        model: str,
    ) -> set[int]:
        statement = (
            select(ChunkEmbedding.chunk_id)
            .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
            .where(
                Chunk.document_id == document_id,
                ChunkEmbedding.provider == provider,
                ChunkEmbedding.model == model,
            )
        )
        return set(self._session.scalars(statement))

    def list_chunk_embeddings(
        self,
        *,
        provider: str,
        model: str,
        document_id: int | None = None,
        access_scope: str | None = None,
        as_of_date: date | None = None,
    ) -> list[tuple[ChunkEmbedding, Chunk, EvidenceItem | None, Document]]:
        statement = (
            select(ChunkEmbedding, Chunk, EvidenceItem, Document)
            .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
            .join(Document, Document.id == Chunk.document_id)
            .outerjoin(EvidenceItem, EvidenceItem.id == Chunk.evidence_item_id)
            .where(
                ChunkEmbedding.provider == provider,
                ChunkEmbedding.model == model,
            )
        )
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        if access_scope is not None:
            statement = statement.where(Document.access_scope == access_scope)
        if as_of_date is not None:
            statement = statement.where(
                (EvidenceItem.publication_date.is_(None))
                | (EvidenceItem.publication_date <= as_of_date),
                (EvidenceItem.data_as_of_date.is_(None))
                | (EvidenceItem.data_as_of_date <= as_of_date),
            )
        return list(self._session.execute(statement).all())

    def search_chunk_embeddings_pgvector(
        self,
        *,
        embedding: list[float],
        provider: str,
        model: str,
        top_k: int,
        document_id: int | None = None,
        access_scope: str | None = None,
        as_of_date: date | None = None,
    ) -> list[tuple[ChunkEmbedding, Chunk, EvidenceItem | None, Document, float]]:
        if self._session.get_bind().dialect.name != "postgresql":
            raise RuntimeError("pgvector search requires PostgreSQL")

        distance = ChunkEmbedding.embedding_vector.cosine_distance(embedding)
        statement = (
            select(ChunkEmbedding, Chunk, EvidenceItem, Document, distance)
            .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
            .join(Document, Document.id == Chunk.document_id)
            .outerjoin(EvidenceItem, EvidenceItem.id == Chunk.evidence_item_id)
            .where(
                ChunkEmbedding.provider == provider,
                ChunkEmbedding.model == model,
                ChunkEmbedding.embedding_vector.is_not(None),
            )
            .order_by(distance.asc())
            .limit(top_k)
        )
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        if access_scope is not None:
            statement = statement.where(Document.access_scope == access_scope)
        if as_of_date is not None:
            statement = statement.where(
                (EvidenceItem.publication_date.is_(None))
                | (EvidenceItem.publication_date <= as_of_date),
                (EvidenceItem.data_as_of_date.is_(None))
                | (EvidenceItem.data_as_of_date <= as_of_date),
            )
        return list(self._session.execute(statement).all())
