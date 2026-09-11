from __future__ import annotations

import pytest

from investment_agent.harness.types import ToolResult
from investment_agent.providers.openai_compatible import (
    OpenAICompatibleModelProvider,
    ProviderHttpError,
)
from investment_agent.providers.types import ModelRequest


def _request(*, tool_results: tuple[ToolResult, ...] = ()) -> ModelRequest:
    return ModelRequest(
        objective="Why might gold respond to real yields?",
        role="researcher",
        sensitivity="public",
        as_of_date=None,
        iteration=1,
        tool_results=tool_results,
    )


def test_openai_compatible_provider_retrieves_before_external_generation() -> None:
    provider = OpenAICompatibleModelProvider(
        provider_name="deepseek",
        api_key="test",
        model="deepseek-v4-flash",
        base_url="https://example.test",
        serving_engine="deepseek-api",
        transport=lambda payload: {},
    )

    result = provider.generate(_request())

    assert result.tool_call is not None
    assert result.tool_call.name == "retrieve_evidence"
    assert result.deployment.value == "local"


def test_openai_compatible_provider_uses_usage_for_cost() -> None:
    captured: dict[str, object] = {}

    def transport(payload: dict[str, object]) -> dict[str, object]:
        captured.update(payload)
        return {
            "choices": [{"message": {"content": "Supported [evidence:7]"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }

    provider = OpenAICompatibleModelProvider(
        provider_name="moonshot",
        api_key="test",
        model="kimi-k2.6",
        base_url="https://example.test/v1",
        serving_engine="kimi-api",
        input_cost_per_million=0.95,
        output_cost_per_million=4.0,
        transport=transport,
    )
    tool_result = ToolResult(
        call_id="retrieve-1",
        status="ok",
        output={
            "search": {"evidence_gate": {"decision": "supported"}},
            "results": [
                {
                    "evidence_item_id": 7,
                    "title": "Gold note",
                    "source_type": "markdown",
                    "page_or_section": "full document",
                    "text": "Gold benefited when real yields fell.",
                    "supported_passage": "Gold benefited when real yields fell.",
                    "score": 0.9,
                }
            ]
        },
    )

    result = provider.generate(_request(tool_results=(tool_result,)))

    assert result.success
    assert result.content == "Supported [evidence:7]"
    assert result.prompt_tokens == 1000
    assert result.completion_tokens == 500
    assert result.estimated_cost_usd == pytest.approx(0.00295)
    assert captured["model"] == "kimi-k2.6"
    assert captured["thinking"] == {"type": "disabled"}


def test_deepseek_research_disables_paid_thinking_tokens() -> None:
    captured: dict[str, object] = {}

    def transport(payload: dict[str, object]) -> dict[str, object]:
        captured.update(payload)
        return {
            "choices": [{"message": {"content": "Supported [evidence:7]"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    provider = OpenAICompatibleModelProvider(
        provider_name="deepseek",
        api_key="test",
        model="deepseek-v4-flash",
        base_url="https://example.test",
        serving_engine="deepseek-api",
        transport=transport,
    )
    tool_result = ToolResult(
        call_id="retrieve-1",
        status="ok",
        output={
            "search": {"evidence_gate": {"decision": "supported"}},
            "results": [
                {
                    "evidence_item_id": 7,
                    "title": "Gold note",
                    "source_type": "markdown",
                    "text": "Gold benefited when real yields fell.",
                    "supported_passage": "Gold benefited when real yields fell.",
                    "score": 0.9,
                }
            ]
        },
    )

    result = provider.generate(_request(tool_results=(tool_result,)))

    assert result.success
    assert captured["thinking"] == {"type": "disabled"}


def test_openai_compatible_provider_maps_429_after_retry() -> None:
    calls = 0

    def transport(payload: dict[str, object]) -> dict[str, object]:
        del payload
        nonlocal calls
        calls += 1
        raise ProviderHttpError(429, "rate limited")

    provider = OpenAICompatibleModelProvider(
        provider_name="deepseek",
        api_key="test",
        model="deepseek-v4-flash",
        base_url="https://example.test",
        serving_engine="deepseek-api",
        max_attempts=2,
        retry_backoff_ms=0,
        transport=transport,
    )
    tool_result = ToolResult(
        call_id="retrieve-1",
        status="ok",
        output={
            "search": {"evidence_gate": {"decision": "supported"}},
            "results": [
                {
                    "evidence_item_id": 7,
                    "title": "Gold note",
                    "source_type": "markdown",
                    "text": "Gold and real yields are discussed together.",
                    "supported_passage": "Gold and real yields are discussed together.",
                    "score": 0.9,
                }
            ]
        },
    )

    result = provider.generate(_request(tool_results=(tool_result,)))

    assert calls == 2
    assert not result.success
    assert result.error_code == "provider_quota_exhausted"


def test_openai_compatible_provider_classifies_timeout_without_retry() -> None:
    calls = 0

    def transport(payload: dict[str, object]) -> dict[str, object]:
        del payload
        nonlocal calls
        calls += 1
        raise TimeoutError("timed out")

    provider = OpenAICompatibleModelProvider(
        provider_name="moonshot",
        api_key="test",
        model="kimi-k2.6",
        base_url="https://example.test/v1",
        serving_engine="kimi-api",
        max_attempts=3,
        retry_backoff_ms=0,
        transport=transport,
    )
    tool_result = ToolResult(
        call_id="retrieve-1",
        status="ok",
        output={
            "search": {"evidence_gate": {"decision": "supported"}},
            "results": [
                {
                    "evidence_item_id": 7,
                    "title": "Grounded source",
                    "source_type": "markdown",
                    "text": "A complete passage directly supports the question.",
                    "supported_passage": "A complete passage directly supports the question.",
                }
            ],
        },
    )

    result = provider.generate(_request(tool_results=(tool_result,)))

    assert calls == 1
    assert result.success is False
    assert result.error_code == "provider_timeout"
