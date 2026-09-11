from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol


RETRIEVAL_DOCUMENT = "RETRIEVAL_DOCUMENT"
RETRIEVAL_QUERY = "RETRIEVAL_QUERY"


class EmbeddingProviderError(RuntimeError):
    """Base error for external embedding provider failures."""


class EmbeddingQuotaExceededError(EmbeddingProviderError):
    """Raised when the provider rejects a request because quota is exhausted."""


@dataclass(frozen=True)
class EmbeddingVector:
    values: tuple[float, ...]
    provider: str
    model: str

    @property
    def dimensions(self) -> int:
        return len(self.values)


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    dimensions: int

    def embed(
        self,
        text: str,
        *,
        task_type: str = RETRIEVAL_DOCUMENT,
    ) -> EmbeddingVector:
        ...


class DeterministicHashEmbeddingProvider:
    """Small local embedding provider for deterministic tests and demos.

    This is not a semantic embedding model. It produces stable vectors so the
    ingestion -> embedding -> storage path can be tested without cloud APIs.
    """

    provider_name = "local"
    model_name = "deterministic-hash-v1"

    def __init__(self, *, dimensions: int = 16) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def embed(
        self,
        text: str,
        *,
        task_type: str = RETRIEVAL_DOCUMENT,
    ) -> EmbeddingVector:
        del task_type
        buckets = [0.0] * self.dimensions
        tokens = [token for token in text.lower().split() if token]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            buckets[bucket] += sign

        norm = math.sqrt(sum(value * value for value in buckets))
        if norm:
            buckets = [value / norm for value in buckets]

        return EmbeddingVector(
            values=tuple(buckets),
            provider=self.provider_name,
            model=self.model_name,
        )


class GeminiEmbeddingProvider:
    """Semantic embeddings for explicitly public research content."""

    provider_name = "google"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-embedding-001",
        dimensions: int = 768,
        timeout_ms: int = 20_000,
        max_attempts: int = 3,
        retry_backoff_ms: int = 100,
        client: object | None = None,
    ) -> None:
        if not api_key.strip() and client is None:
            raise ValueError("Gemini API key is required")
        if dimensions <= 0:
            raise ValueError("Embedding dimensions must be positive")
        if timeout_ms <= 0 or max_attempts <= 0 or retry_backoff_ms < 0:
            raise ValueError("Embedding timeout, attempts, and backoff are invalid")
        self.model_name = model
        self.dimensions = dimensions
        if client is None:
            from google import genai

            client = genai.Client(
                api_key=api_key,
                http_options={
                    "timeout": timeout_ms,
                    "retry_options": {
                        "attempts": max_attempts,
                        "initial_delay": retry_backoff_ms / 1000,
                    },
                },
            )
        self._client = client

    def embed(
        self,
        text: str,
        *,
        task_type: str = RETRIEVAL_DOCUMENT,
    ) -> EmbeddingVector:
        if task_type not in {RETRIEVAL_DOCUMENT, RETRIEVAL_QUERY}:
            raise ValueError(f"Unsupported embedding task type: {task_type}")
        try:
            response = self._client.models.embed_content(  # type: ignore[attr-defined]
                model=self.model_name,
                contents=text,
                config={
                    "task_type": task_type,
                    "output_dimensionality": self.dimensions,
                },
            )
        except Exception as exc:
            if _is_quota_error(exc):
                raise EmbeddingQuotaExceededError(
                    "Gemini Free Tier quota is exhausted or rate-limited. "
                    "Argus will not upgrade billing automatically; wait for the "
                    "quota reset or enable billing manually in Google AI Studio."
                ) from exc
            raise EmbeddingProviderError(
                "Gemini could not create a semantic embedding."
            ) from exc

        embeddings = getattr(response, "embeddings", None)
        values = (
            getattr(embeddings[0], "values", None)
            if isinstance(embeddings, list) and embeddings
            else None
        )
        if not isinstance(values, list) or len(values) != self.dimensions:
            raise EmbeddingProviderError(
                "Gemini returned an invalid embedding vector."
            )
        normalized = _normalize([float(value) for value in values])
        return EmbeddingVector(
            values=tuple(normalized),
            provider=self.provider_name,
            model=self.model_name,
        )


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if not norm:
        return values
    return [value / norm for value in values]


def _is_quota_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    message = str(exc).lower()
    return status_code == 429 or any(
        marker in message
        for marker in ("429", "resource_exhausted", "quota exceeded", "rate limit")
    )
