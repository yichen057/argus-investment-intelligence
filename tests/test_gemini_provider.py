from types import SimpleNamespace

import pytest

from investment_agent.harness.types import ToolResult
from investment_agent.providers.gemini import GeminiModelProvider
from investment_agent.providers.mock import NO_EVIDENCE_ANSWER
from investment_agent.providers.types import ModelRequest


class FakeModels:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, models: FakeModels) -> None:
        self.models = models


def request_with_results(
    results: list[dict],
    *,
    gate_decision: str | None = None,
) -> ModelRequest:
    decision = gate_decision or ("supported" if results else "refuse")
    return ModelRequest(
        objective="Why might gold benefit when real yields fall?",
        role="research",
        sensitivity="public",
        as_of_date=None,
        document_id=7,
        tool_results=(
            ToolResult(
                call_id="retrieve-1",
                status="ok",
                output={
                    "search": {"evidence_gate": {"decision": decision}},
                    "results": results,
                },
            ),
        ),
        iteration=1,
    )


def test_gemini_provider_plans_local_retrieval_before_api_call() -> None:
    models = FakeModels()
    provider = GeminiModelProvider(api_key="", client=FakeClient(models))

    response = provider.generate(
        ModelRequest(
            objective="What drives gold prices?",
            role="research",
            sensitivity="public",
            as_of_date=None,
            document_id=7,
        )
    )

    assert response.tool_call is not None
    assert response.tool_call.name == "retrieve_evidence"
    assert response.deployment == "local"
    assert models.calls == []


def test_gemini_provider_skips_api_when_retrieval_has_no_evidence() -> None:
    models = FakeModels()
    provider = GeminiModelProvider(api_key="", client=FakeClient(models))

    response = provider.generate(request_with_results([]))

    assert response.content == NO_EVIDENCE_ANSWER
    assert response.estimated_cost_usd == 0.0
    assert models.calls == []


def test_gemini_provider_skips_api_when_evidence_does_not_cover_year() -> None:
    models = FakeModels()
    provider = GeminiModelProvider(api_key="", client=FakeClient(models))
    request = request_with_results(
        [
            {
                "evidence_item_id": 3,
                "title": "Gold history",
                "source_type": "markdown",
                "text": "Gold demand rose in 2025.",
            }
        ],
        gate_decision="refuse",
    )
    request = ModelRequest(
        objective="What is the gold trend in 2027?",
        role=request.role,
        sensitivity=request.sensitivity,
        as_of_date=request.as_of_date,
        document_id=request.document_id,
        tool_results=request.tool_results,
        iteration=request.iteration,
    )

    response = provider.generate(request)

    assert response.content == NO_EVIDENCE_ANSWER
    assert response.estimated_cost_usd == 0.0
    assert models.calls == []


def test_gemini_provider_records_usage_and_estimated_cost() -> None:
    usage = SimpleNamespace(
        prompt_token_count=100,
        candidates_token_count=20,
        thoughts_token_count=5,
        total_token_count=125,
    )
    models = FakeModels(
        response=SimpleNamespace(
            text="Lower real yields reduce the opportunity cost of gold. [evidence:3]",
            usage_metadata=usage,
        )
    )
    provider = GeminiModelProvider(api_key="", client=FakeClient(models))

    response = provider.generate(
        request_with_results(
            [
                {
                    "evidence_item_id": 3,
                    "title": "Gold and real yields",
                    "source_type": "markdown",
                    "page_or_section": "full document",
                    "text": "Lower real yields can support gold demand.",
                    "supported_passage": "Lower real yields can support gold demand.",
                }
            ]
        )
    )

    assert response.prompt_tokens == 100
    assert response.completion_tokens == 25
    assert response.estimated_cost_usd == pytest.approx(0.0000625)
    assert "[evidence:3]" in response.content
    assert len(models.calls) == 1


def test_gemini_provider_returns_failed_response_on_api_error() -> None:
    models = FakeModels(error=TimeoutError("request timed out"))
    provider = GeminiModelProvider(api_key="", client=FakeClient(models))

    response = provider.generate(
        request_with_results(
            [
                {
                    "evidence_item_id": 3,
                    "title": "Gold and real yields",
                    "source_type": "markdown",
                    "text": "Lower real yields can support gold demand.",
                    "supported_passage": "Lower real yields can support gold demand.",
                }
            ]
        )
    )

    assert response.success is False
    assert response.error_code == "model_provider_error"
    assert response.content == ""


def test_gemini_provider_identifies_free_tier_quota_error() -> None:
    models = FakeModels(error=RuntimeError("429 RESOURCE_EXHAUSTED"))
    provider = GeminiModelProvider(api_key="", client=FakeClient(models))

    response = provider.generate(
        request_with_results(
            [
                {
                    "evidence_item_id": 3,
                    "title": "Gold and real yields",
                    "source_type": "markdown",
                    "text": "Lower real yields can support gold demand.",
                    "supported_passage": "Lower real yields can support gold demand.",
                }
            ]
        )
    )

    assert response.success is False
    assert response.error_code == "provider_quota_exhausted"
