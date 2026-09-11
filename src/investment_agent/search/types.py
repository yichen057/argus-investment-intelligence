from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


class WebSearchError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        estimated_cost_usd: float = 0.0,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.estimated_cost_usd = estimated_cost_usd
        self.retryable = retryable


@dataclass(frozen=True)
class WebEvidence:
    evidence_key: str
    title: str
    url: str
    author: str | None
    published_at: datetime | None
    retrieved_at: datetime
    text: str
    highlights: tuple[str, ...]
    highlight_scores: tuple[float, ...]

    @property
    def passage(self) -> str:
        if self.highlights:
            return "\n".join(self.highlights).strip()
        return self.text.strip()


@dataclass(frozen=True)
class WebSearchResponse:
    provider: str
    query: str
    request_id: str | None
    search_type: str
    results: tuple[WebEvidence, ...]
    estimated_cost_usd: float


class WebSearchProvider(Protocol):
    provider_name: str

    def search(
        self,
        query: str,
        *,
        as_of_date: date | None = None,
        exclude_domains: tuple[str, ...] = (),
    ) -> WebSearchResponse: ...
