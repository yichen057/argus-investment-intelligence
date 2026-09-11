from __future__ import annotations

from datetime import date

import pytest

from investment_agent.search import ExaSearchProvider, WebSearchError
from investment_agent.research.web import (
    _citation_status,
    _normalize_known_citations,
)


def test_exa_search_returns_bounded_extractable_evidence() -> None:
    payloads: list[dict[str, object]] = []

    def transport(payload: dict[str, object]) -> dict[str, object]:
        payloads.append(payload)
        return {
            "requestId": "exa-request-1",
            "costDollars": {"total": 0.007},
            "results": [
                {
                    "title": "Federal Reserve real yields note",
                    "url": "https://www.federalreserve.gov/example.htm",
                    "author": "Federal Reserve",
                    "publishedDate": "2026-06-30T12:00:00Z",
                    "highlights": [
                        "When real yields fall, the opportunity cost of holding "
                        "non-yielding gold also falls."
                    ],
                    "highlightScores": [0.91],
                }
            ],
        }

    provider = ExaSearchProvider(
        api_key="test",
        search_type="auto",
        max_results=5,
        highlight_max_characters=500,
        transport=transport,
    )

    result = provider.search(
        "How do real yields affect gold?",
        as_of_date=date(2026, 7, 1),
        exclude_domains=("example.com", "www.example.com"),
    )

    assert result.provider == "exa"
    assert result.request_id == "exa-request-1"
    assert result.estimated_cost_usd == pytest.approx(0.007)
    assert len(result.results) == 1
    assert result.results[0].evidence_key.startswith("web-")
    assert "opportunity cost" in result.results[0].passage
    assert payloads[0]["type"] == "auto"
    assert payloads[0]["numResults"] == 5
    assert payloads[0]["endPublishedDate"] == "2026-07-01T23:59:59Z"
    assert payloads[0]["excludeDomains"] == ["example.com", "www.example.com"]
    assert payloads[0]["contents"] == {
        "highlights": {
            "query": "How do real yields affect gold?",
            "maxCharacters": 500,
        }
    }


def test_exa_search_deduplicates_urls_and_enforces_cutoff() -> None:
    shared = {
        "title": "Gold outlook",
        "url": "https://example.com/gold",
        "highlights": ["Gold and real yields are inversely related in this study."],
    }
    provider = ExaSearchProvider(
        api_key="test",
        transport=lambda payload: {
            "results": [
                {**shared, "publishedDate": "2026-07-01T00:00:00Z"},
                {**shared, "publishedDate": "2026-07-01T00:00:00Z"},
                {
                    "title": "Future article",
                    "url": "https://example.com/future",
                    "publishedDate": "2027-01-01T00:00:00Z",
                    "highlights": ["Future evidence must not leak into the answer."],
                },
            ],
            "costDollars": {"total": 0.0},
        },
    )

    result = provider.search("gold real yields", as_of_date=date(2026, 7, 1))

    assert [item.url for item in result.results] == ["https://example.com/gold"]
    assert result.estimated_cost_usd == 0.0


def test_exa_search_deduplicates_same_host_mirrors_but_keeps_other_sources() -> None:
    shared_passage = (
        "Gold prices are influenced by long-term real yields because higher real "
        "rates increase the opportunity cost of holding a non-yielding asset while "
        "lower real rates reduce that opportunity cost for diversified investors."
    )
    provider = ExaSearchProvider(
        api_key="test",
        transport=lambda payload: {
            "results": [
                {
                    "title": "Global edition",
                    "url": "https://example.com/global/gold",
                    "highlights": [shared_passage],
                },
                {
                    "title": "US mirror",
                    "url": "https://example.com/us/gold",
                    "highlights": [f"{shared_passage} Read more."],
                },
                {
                    "title": "Independent corroboration",
                    "url": "https://other.example/gold",
                    "highlights": [shared_passage],
                },
            ]
        },
    )

    result = provider.search("gold real yields")

    assert [item.url for item in result.results] == [
        "https://example.com/global/gold",
        "https://other.example/gold",
    ]


def test_exa_search_rejects_missing_results_contract() -> None:
    provider = ExaSearchProvider(
        api_key="test",
        search_cost_per_request=0.007,
        transport=lambda payload: {"requestId": "broken"},
    )

    with pytest.raises(WebSearchError) as exc_info:
        provider.search("gold")

    assert exc_info.value.code == "invalid_web_search_response"
    assert exc_info.value.estimated_cost_usd == pytest.approx(0.007)


def test_exa_search_does_not_accept_deep_mode_in_bounded_adapter() -> None:
    with pytest.raises(ValueError, match="instant, fast, or auto"):
        ExaSearchProvider(api_key="test", search_type="deep")


def test_known_answer_citation_variants_are_normalized_without_accepting_unknown_ids() -> (
    None
):
    normalized = _normalize_known_citations(
        "Supported by source W1 and source W2/W3. Unknown source W99.",
        allowed_citation_ids={"W1", "W2", "W3"},
    )

    assert "[source:W1]" in normalized
    assert "[source:W2] [source:W3]" in normalized
    assert "source W99" in normalized
    assert (
        _citation_status(
            normalized,
            allowed_citation_ids={"W1", "W2", "W3"},
        )
        == "invalid"
    )
