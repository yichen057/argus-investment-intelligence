from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import date, datetime, time, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from investment_agent.search.types import (
    WebEvidence,
    WebSearchError,
    WebSearchResponse,
)

_ALLOWED_SEARCH_TYPES = {"instant", "fast", "auto"}


class ExaSearchProvider:
    """Independent Exa Search adapter returning extractive evidence, not answers."""

    provider_name = "exa"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.exa.ai",
        search_type: str = "auto",
        timeout_ms: int = 15_000,
        max_results: int = 5,
        highlight_max_characters: int = 2_000,
        search_cost_per_request: float = 0.007,
        transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        if not api_key.strip() and transport is None:
            raise ValueError("Exa API key is required")
        if search_type not in _ALLOWED_SEARCH_TYPES:
            raise ValueError("Exa search type must be instant, fast, or auto")
        if timeout_ms <= 0:
            raise ValueError("Exa timeout must be positive")
        if max_results <= 0 or max_results > 10:
            raise ValueError("Exa max results must be between 1 and 10")
        if highlight_max_characters <= 0:
            raise ValueError("Exa highlight character limit must be positive")
        if search_cost_per_request < 0:
            raise ValueError("Exa search price cannot be negative")

        self._api_key = api_key
        self._endpoint = f"{base_url.rstrip('/')}/search"
        self._search_type = search_type
        self._timeout_seconds = timeout_ms / 1000
        self._max_results = max_results
        self._highlight_max_characters = highlight_max_characters
        self._search_cost_per_request = search_cost_per_request
        self._transport = transport or self._post_json

    def search(
        self,
        query: str,
        *,
        as_of_date: date | None = None,
        exclude_domains: tuple[str, ...] = (),
    ) -> WebSearchResponse:
        normalized_query = " ".join(query.split()).strip()
        if not normalized_query:
            raise ValueError("Exa search query cannot be empty")

        payload: dict[str, Any] = {
            "query": normalized_query,
            "type": self._search_type,
            "numResults": self._max_results,
            "contents": {
                "highlights": {
                    "query": normalized_query,
                    "maxCharacters": self._highlight_max_characters,
                }
            },
        }
        normalized_exclusions = tuple(
            dict.fromkeys(
                domain.strip().lower()
                for domain in exclude_domains
                if domain.strip()
            )
        )
        if normalized_exclusions:
            payload["excludeDomains"] = list(normalized_exclusions[:50])
        if as_of_date is not None:
            cutoff = datetime.combine(
                as_of_date,
                time(23, 59, 59),
                tzinfo=timezone.utc,
            )
            payload["endPublishedDate"] = cutoff.isoformat().replace("+00:00", "Z")

        try:
            response = self._transport(payload)
        except WebSearchError:
            raise
        except Exception as exc:
            raise WebSearchError(
                "web_search_provider_error",
                "Exa search failed before Argus received evidence.",
            ) from exc

        if not isinstance(response, dict):
            raise WebSearchError(
                "invalid_web_search_response",
                "Exa returned a response that was not a JSON object.",
            )
        raw_results = response.get("results")
        if not isinstance(raw_results, list):
            raise WebSearchError(
                "invalid_web_search_response",
                "Exa returned no results array.",
                estimated_cost_usd=_estimated_cost(
                    response,
                    fallback=self._search_cost_per_request,
                ),
            )

        retrieved_at = datetime.now(timezone.utc)
        results: list[WebEvidence] = []
        seen_urls: set[str] = set()
        seen_passages: list[tuple[str, str]] = []
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                continue
            evidence = _parse_evidence(
                raw_result,
                retrieved_at=retrieved_at,
                max_characters=self._highlight_max_characters,
            )
            if evidence is None or evidence.url in seen_urls:
                continue
            if (
                as_of_date is not None
                and evidence.published_at is not None
                and evidence.published_at.date() > as_of_date
            ):
                continue
            if not evidence.passage:
                continue
            hostname = (urlparse(evidence.url).hostname or "").lower()
            if any(
                hostname == prior_hostname
                and _near_duplicate_passage(evidence.passage, prior_passage)
                for prior_hostname, prior_passage in seen_passages
            ):
                continue
            results.append(evidence)
            seen_urls.add(evidence.url)
            seen_passages.append((hostname, evidence.passage))

        return WebSearchResponse(
            provider=self.provider_name,
            query=normalized_query,
            request_id=_optional_string(response.get("requestId")),
            search_type=self._search_type,
            results=tuple(results),
            estimated_cost_usd=_estimated_cost(
                response,
                fallback=self._search_cost_per_request,
            ),
        )

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self._endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self._api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise WebSearchError(
                _http_error_code(exc.code),
                _http_error_message(exc.code, detail),
                status_code=exc.code,
                retryable=exc.code in {408, 429, 500, 502, 503, 504},
            ) from exc
        except (TimeoutError, URLError) as exc:
            raise WebSearchError(
                "web_search_unavailable",
                "Exa search timed out or could not be reached.",
                retryable=True,
            ) from exc
        except json.JSONDecodeError as exc:
            raise WebSearchError(
                "invalid_web_search_response",
                "Exa returned invalid JSON.",
            ) from exc
        if not isinstance(decoded, dict):
            raise WebSearchError(
                "invalid_web_search_response",
                "Exa returned a response that was not a JSON object.",
            )
        return decoded


def _parse_evidence(
    payload: dict[str, Any],
    *,
    retrieved_at: datetime,
    max_characters: int,
) -> WebEvidence | None:
    url = str(payload.get("url") or "").strip()
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return None
    title = str(payload.get("title") or parsed_url.netloc).strip()
    raw_highlights = payload.get("highlights")
    highlights = (
        tuple(
            _bounded_text(str(value), max_characters=max_characters)
            for value in raw_highlights
            if isinstance(value, str) and value.strip()
        )
        if isinstance(raw_highlights, list)
        else ()
    )
    raw_scores = payload.get("highlightScores")
    highlight_scores = (
        tuple(
            float(value)
            for value in raw_scores
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
        if isinstance(raw_scores, list)
        else ()
    )
    text_value = str(payload.get("text") or "").strip()
    text = _bounded_text(text_value, max_characters=max_characters * 2)
    published_at = _parse_datetime(payload.get("publishedDate"))
    digest = hashlib.sha256(
        f"{url}\n{' '.join(highlights)}\n{text}".encode()
    ).hexdigest()
    return WebEvidence(
        evidence_key=f"web-{digest[:16]}",
        title=title or parsed_url.netloc,
        url=url,
        author=_optional_string(payload.get("author")),
        published_at=published_at,
        retrieved_at=retrieved_at,
        text=text,
        highlights=highlights,
        highlight_scores=highlight_scores,
    )


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bounded_text(value: str, *, max_characters: int) -> str:
    normalized = " ".join(value.split()).strip()
    if len(normalized) <= max_characters:
        return normalized
    truncated = normalized[:max_characters].rsplit(" ", 1)[0].strip()
    return truncated or normalized[:max_characters].strip()


def _near_duplicate_passage(left: str, right: str) -> bool:
    left_tokens = set(re.findall(r"[a-z0-9]+", left.lower()))
    right_tokens = set(re.findall(r"[a-z0-9]+", right.lower()))
    if min(len(left_tokens), len(right_tokens)) < 12:
        return left.strip() == right.strip()
    overlap = len(left_tokens & right_tokens) / min(
        len(left_tokens),
        len(right_tokens),
    )
    return overlap >= 0.88


def _estimated_cost(payload: dict[str, Any], *, fallback: float) -> float:
    cost = payload.get("costDollars")
    if isinstance(cost, dict):
        total = cost.get("total")
        if (
            isinstance(total, (int, float))
            and not isinstance(total, bool)
            and total >= 0
        ):
            return float(total)
    return fallback


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _http_error_code(status_code: int) -> str:
    if status_code in {401, 403}:
        return "web_search_authentication_failed"
    if status_code == 429:
        return "web_search_rate_limited"
    if status_code == 400:
        return "web_search_invalid_request"
    return "web_search_unavailable"


def _http_error_message(status_code: int, detail: str) -> str:
    if status_code in {401, 403}:
        return "Exa rejected the API key or its permissions."
    if status_code == 429:
        return "Exa rate-limited the search request; Argus did not switch providers."
    if status_code == 400:
        return "Exa rejected the bounded search request as invalid."
    suffix = "" if not detail.strip() else " Check the Exa status and API dashboard."
    return f"Exa search returned HTTP {status_code}.{suffix}"
