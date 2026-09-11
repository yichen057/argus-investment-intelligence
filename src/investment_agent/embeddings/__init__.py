"""Embedding provider abstractions and local implementations."""

from investment_agent.embeddings.providers import (
    DeterministicHashEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingQuotaExceededError,
    EmbeddingVector,
    GeminiEmbeddingProvider,
    RETRIEVAL_DOCUMENT,
    RETRIEVAL_QUERY,
)
from investment_agent.embeddings.service import EmbeddingIndexResult, EmbeddingService

__all__ = [
    "DeterministicHashEmbeddingProvider",
    "EmbeddingIndexResult",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingQuotaExceededError",
    "EmbeddingService",
    "EmbeddingVector",
    "GeminiEmbeddingProvider",
    "RETRIEVAL_DOCUMENT",
    "RETRIEVAL_QUERY",
]
