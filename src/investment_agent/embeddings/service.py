from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from investment_agent.embeddings.providers import (
    RETRIEVAL_DOCUMENT,
    EmbeddingProvider,
)
from investment_agent.repositories.documents import DocumentRepository


@dataclass(frozen=True)
class EmbeddingIndexResult:
    document_id: int
    embedded_count: int


class EmbeddingService:
    def __init__(self, session: Session, provider: EmbeddingProvider) -> None:
        self._repository = DocumentRepository(session)
        self._provider = provider

    def embed_document_chunks(self, document_id: int) -> EmbeddingIndexResult:
        chunks = self._repository.list_chunks_for_document(document_id)
        indexed_chunk_ids = self._repository.list_embedding_chunk_ids(
            document_id=document_id,
            provider=self._provider.provider_name,
            model=self._provider.model_name,
        )
        embedded_count = 0
        for chunk in chunks:
            if chunk.id in indexed_chunk_ids:
                continue
            vector = self._provider.embed(
                chunk.text,
                task_type=RETRIEVAL_DOCUMENT,
            )
            created = self._repository.upsert_chunk_embedding(
                chunk_id=chunk.id,
                provider=vector.provider,
                model=vector.model,
                dimensions=vector.dimensions,
                embedding=list(vector.values),
            )
            if created:
                embedded_count += 1
        return EmbeddingIndexResult(
            document_id=document_id,
            embedded_count=embedded_count,
        )
