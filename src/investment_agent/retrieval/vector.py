from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from investment_agent.embeddings import RETRIEVAL_QUERY, EmbeddingProvider
from investment_agent.repositories import DocumentRepository
from investment_agent.storage.models import Chunk, Document, EvidenceItem


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: int
    document_id: int
    evidence_item_id: int | None
    score: float
    text: str
    source_uri: str
    source_type: str
    title: str
    page_or_section: str | None
    evidence_grade: str | None
    excerpt: str | None
    publication_date: date | None = None
    data_as_of_date: date | None = None
    semantic_score: float | None = None
    fused_score: float | None = None
    match_signals: tuple[str, ...] = ()
    channel_ranks: tuple[tuple[str, int], ...] = ()
    context_text: str | None = None


class VectorRetrievalService:
    def __init__(self, session: Session, embedding_provider: EmbeddingProvider) -> None:
        self._session = session
        self._repository = DocumentRepository(session)
        self._provider = embedding_provider

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        document_id: int | None = None,
        access_scope: str | None = None,
        as_of_date: date | None = None,
    ) -> list[RetrievalResult]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        query_embedding = self._provider.embed(query, task_type=RETRIEVAL_QUERY)
        if (
            self._session.get_bind().dialect.name == "postgresql"
            and query_embedding.dimensions == 768
        ):
            pg_rows = self._repository.search_chunk_embeddings_pgvector(
                embedding=list(query_embedding.values),
                provider=query_embedding.provider,
                model=query_embedding.model,
                top_k=top_k,
                document_id=document_id,
                access_scope=access_scope,
                as_of_date=as_of_date,
            )
            return [
                _retrieval_result(
                    chunk=chunk,
                    evidence=evidence,
                    document=document,
                    score=max(-1.0, min(1.0, 1.0 - float(distance))),
                )
                for _, chunk, evidence, document, distance in pg_rows
            ]

        embedding_rows = self._repository.list_chunk_embeddings(
            provider=query_embedding.provider,
            model=query_embedding.model,
            document_id=document_id,
            access_scope=access_scope,
            as_of_date=as_of_date,
        )

        results: list[RetrievalResult] = []
        for embedding, chunk, evidence, document in embedding_rows:
            score = cosine_similarity(
                list(query_embedding.values), embedding.embedding_json
            )
            results.append(
                _retrieval_result(
                    chunk=chunk,
                    evidence=evidence,
                    document=document,
                    score=score,
                )
            )

        return sorted(results, key=lambda result: result.score, reverse=True)[:top_k]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Vectors must have the same dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    return dot / (left_norm * right_norm)


def _retrieval_result(
    *,
    chunk: Chunk,
    evidence: EvidenceItem | None,
    document: Document,
    score: float,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk.id,
        document_id=document.id,
        evidence_item_id=evidence.id if evidence is not None else None,
        score=score,
        text=chunk.text,
        source_uri=document.source_uri,
        source_type=document.source_type,
        title=document.title,
        page_or_section=evidence.page_or_section if evidence is not None else None,
        evidence_grade=evidence.evidence_grade if evidence is not None else None,
        excerpt=evidence.excerpt if evidence is not None else None,
        publication_date=(
            evidence.publication_date if evidence is not None else None
        ),
        data_as_of_date=(
            evidence.data_as_of_date if evidence is not None else None
        ),
        semantic_score=score,
        match_signals=("semantic",),
    )
