from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from investment_agent.app import create_app
from investment_agent.api import chat as chat_api
from investment_agent.config import Settings
from investment_agent.providers.mock import NO_EVIDENCE_ANSWER
from investment_agent.providers.openai_compatible import OpenAICompatibleModelProvider
from investment_agent.providers.types import Deployment, ModelResponse
from investment_agent.search import (
    WebEvidence,
    WebSearchError,
    WebSearchResponse,
)
from investment_agent.storage import AgentRun, Base, Claim, ModelCall, ToolCallRecord


def test_chat_query_retrieves_evidence_after_document_ingest(tmp_path) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold demand strengthened as real yields fell and central banks bought.",
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    query_response = client.post(
        "/chat/query",
        json={
            "query": "Why might gold benefit when real yields fall?",
            "as_of_date": "2026-01-01",
        },
    )

    assert ingest_response.status_code == 201
    assert query_response.status_code == 200
    payload = query_response.json()
    assert payload["status"] == "complete"
    assert "Gold demand strengthened" in payload["answer"]
    assert "[evidence:" not in payload["answer"]
    assert payload["evidence_ids"]
    assert payload["sources"][0]["display_name"] == "gold.md"
    assert payload["sources"][0]["evidence_id"] == payload["evidence_ids"][0]
    assert len(payload["claims"]) == 1
    assert payload["claims"][0]["evidence_ids"] == payload["evidence_ids"]
    assert payload["claims"][0]["relations"] == {
        str(payload["evidence_ids"][0]): "supports"
    }
    assert payload["critic"]["status"] == "passed"
    assert payload["critic"]["findings"] == []
    assert payload["iterations"] == 2
    assert payload["total_tokens"] > 0
    assert payload["deployment"] == "local"
    assert payload["execution_outcome"] == "local_completed"
    assert "without calling a paid model API" in payload["execution_message"]
    assert payload["total_estimated_cost_usd"] == 0

    with client.app.state.session_factory() as session:
        run = session.get(AgentRun, payload["run_id"])
        model_calls = list(
            session.scalars(
                select(ModelCall).where(ModelCall.run_id == payload["run_id"])
            )
        )
        tool_calls = list(
            session.scalars(
                select(ToolCallRecord).where(ToolCallRecord.run_id == payload["run_id"])
            )
        )
        claims = list(
            session.scalars(select(Claim).where(Claim.run_id == payload["run_id"]))
        )

    assert run is not None
    assert run.status == "complete"
    assert len(model_calls) == 2
    assert len(tool_calls) == 1
    assert len(claims) == 1
    assert claims[0].evidence_ids_json == payload["evidence_ids"]
    assert tool_calls[0].status == "ok"


def test_chat_query_returns_clear_answer_when_no_documents_exist(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post("/chat/query", json={"query": "Find evidence"})

    assert response.status_code == 422
    assert "No research sources are indexed" in response.json()["detail"]


def test_web_research_works_without_uploaded_documents_and_generates_report(
    tmp_path,
    monkeypatch,
) -> None:
    generated_at = datetime(2026, 7, 15, 20, tzinfo=timezone.utc)

    class FakeSearchProvider:
        provider_name = "exa"

        def __init__(self, **kwargs) -> None:
            del kwargs

        def search(self, query, *, as_of_date=None) -> WebSearchResponse:
            del as_of_date
            return WebSearchResponse(
                provider="exa",
                query=query,
                request_id="exa-test-1",
                search_type="auto",
                results=(
                    WebEvidence(
                        evidence_key="web-fed-test",
                        title="Federal Reserve monetary policy",
                        url="https://www.federalreserve.gov/monetarypolicy.htm",
                        author="Federal Reserve",
                        published_at=generated_at,
                        retrieved_at=generated_at,
                        text=(
                            "Current downside risks for gold include firmer real rates, "
                            "which raise opportunity cost, and lower geopolitical risk, "
                            "which can reduce safe-haven demand for gold."
                        ),
                        highlights=(
                            "Current downside risks for gold include firmer real rates, "
                            "which raise opportunity cost, and lower geopolitical risk, "
                            "which can reduce safe-haven demand for gold.",
                        ),
                        highlight_scores=(0.93,),
                    ),
                ),
                estimated_cost_usd=0.007,
            )

    class FakeAnswerProvider:
        provider_name = "moonshot"
        model_name = "kimi-k2.6"
        deployment = Deployment.CLOUD
        serving_engine = "kimi-api"

        def generate(self, request) -> ModelResponse:
            assert "Evidence scope: web" in request.objective
            assert '"style_id": "general_research"' in request.objective
            assert '"portfolio_priorities": []' in request.objective
            assert '"product_preferences": []' in request.objective
            assert '"composition": "base framework AND bounded expert method panel' in (
                request.objective
            )
            assert "Review downside risk and counter-evidence" in request.objective
            return ModelResponse(
                provider=self.provider_name,
                model=self.model_name,
                deployment=self.deployment,
                serving_engine=self.serving_engine,
                content=(
                    "## Direct answer\nGold downside risks include firmer real rates and "
                    "lower geopolitical risk [source:W1].\n"
                    "## Mechanism and drivers\n- Higher real yields raise gold's "
                    "opportunity cost [source:W1].\n"
                    "## Supporting evidence\n- Firmer real rates raise opportunity cost "
                    "for gold [source:W1].\n"
                    "## Risks and uncertainties\n- Lower geopolitical risk can reduce "
                    "safe-haven gold demand [source:W1].\n"
                    "## Counter-evidence and gaps\n- Gold demand may still respond differently "
                    "from the stated rate and geopolitical channels [source:W1].\n"
                    "## Falsification conditions\n- Reassess the rate channel if firmer real "
                    "rates stop raising opportunity cost [source:W1].\n"
                    "## Investment implications\n- Firmer rates and lower geopolitical risk "
                    "are contextual downside drivers [source:W1].\n"
                    "## What to verify next\n- Verify real rates and geopolitical risk "
                    "before relying on the conclusion [source:W1]."
                ),
                prompt_tokens=120,
                completion_tokens=60,
                estimated_cost_usd=0.0054,
            )

    monkeypatch.setattr(chat_api, "ExaSearchProvider", FakeSearchProvider)
    monkeypatch.setattr(
        chat_api.LocalResearchWorkflow,
        "model_provider",
        lambda *args, **kwargs: FakeAnswerProvider(),
    )
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'web_chat.db'}",
        enable_cloud_services=True,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        kimi_api_key="test",
        exa_api_key="test",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    method_upload = client.post(
        "/styles/method-documents/upload",
        files={
            "file": (
                "risk-method.txt",
                b"Review downside risk and counter-evidence before drawing a conclusion.",
                "text/plain",
            )
        },
    )
    assert method_upload.status_code == 201

    response = client.post(
        "/chat/query",
        json={
            "query": "What are the current downside risks for gold?",
            "sensitivity": "public",
            "selection_mode": "manual",
            "requested_model": "moonshot/kimi-k2.6",
            "evidence_scope": "web",
            "method_document_id": method_upload.json()["id"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence_scope"] == "web"
    assert payload["sources"] == []
    assert payload["web_sources"][0]["url"].startswith("https://")
    assert payload["web_sources"][0]["citation_id"] == "W1"
    assert payload["critic"]["status"] == "web_evidence_validated"
    assert payload["style_pack_name"] == "General evidence-first research"
    assert payload["method_document_name"] == "risk-method"
    assert payload["search_provider"] == "exa"
    assert payload["search_calls"] == 1
    assert payload["search_estimated_cost_usd"] == 0.007
    assert payload["answer_model_estimated_cost_usd"] == 0.0054
    assert payload["total_estimated_cost_usd"] == 0.0124

    report = client.post(
        "/reports/generate",
        json={
            "topic": "Gold downside risk",
            "question": "What are the current downside risks for gold?",
            "source_run_id": payload["run_id"],
        },
    )
    assert report.status_code == 201
    assert report.json()["report_type"] == "web_research_brief"
    assert report.json()["report_json"]["style_pack"]["id"] == "general_research"
    assert report.json()["report_json"]["metrics"] == {
        "iterations": 2,
        "source_ask_tokens": 180,
        "source_ask_estimated_cost_usd": 0.0124,
        "report_generation_provider_tokens": 0,
        "report_generation_estimated_cost_usd": 0.0,
        "total_tokens": 180,
        "total_estimated_cost_usd": 0.0124,
    }
    html = client.get(report.json()["html_url"]).text
    assert "Argus-validated Web Evidence" in html
    assert "federalreserve.gov" in html
    assert "Source Ask Cost and Report Cost" in html
    assert "HTML report generation: 0 provider tokens" in html
    assert "Higher real yields raise gold&#x27;s opportunity cost" in html


def test_web_research_rejects_non_search_model(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/chat/query",
        json={
            "query": "Search current markets",
            "sensitivity": "public",
            "selection_mode": "manual",
            "requested_model": "local/deterministic-mock-researcher",
            "evidence_scope": "web",
        },
    )

    assert response.status_code == 422
    assert "ARGUS_EXA_API_KEY" in response.json()["detail"]


def test_web_research_provider_failure_returns_run_id(tmp_path, monkeypatch) -> None:
    def fail_after_evidence(self, **kwargs):
        del self, kwargs
        raise chat_api.WebResearchError(
            "provider_timeout",
            "The selected answer model timed out after Argus collected evidence; "
            "no fallback model was used.",
            run_id=95,
        )

    monkeypatch.setattr(chat_api.WebResearchWorkflow, "run", fail_after_evidence)
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'web_failure.db'}",
        enable_cloud_services=True,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        kimi_api_key="test",
        exa_api_key="test",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)

    response = client.post(
        "/chat/query",
        json={
            "query": "Summarize current evidence.",
            "sensitivity": "public",
            "selection_mode": "manual",
            "requested_model": "moonshot/kimi-k2.6",
            "evidence_scope": "web",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "provider_timeout",
        "message": (
            "The selected answer model timed out after Argus collected evidence; "
            "no fallback model was used."
        ),
        "run_id": 95,
    }
    failed_events = [
        event
        for event in app.state.event_publisher.events
        if event.event_type == "agent.run.failed.v1"
    ]
    assert failed_events[-1].aggregate_id == "95"
    assert failed_events[-1].payload == {
        "run_id": 95,
        "status": "failed",
        "error_code": "provider_timeout",
        "failure_stage": "answer_model",
        "provider": "moonshot",
        "model": "kimi-k2.6",
        "total_tokens": 0,
        "total_estimated_cost_usd": 0.0,
    }


def test_failed_web_research_persists_provider_cost_audit(
    tmp_path,
    monkeypatch,
) -> None:
    class FailingSearchProvider:
        provider_name = "exa"

        def __init__(self, **kwargs) -> None:
            del kwargs

        def search(self, query, *, as_of_date=None) -> WebSearchResponse:
            del query, as_of_date
            raise WebSearchError(
                "web_search_rate_limited",
                "Exa rate limited the request.",
                status_code=429,
                estimated_cost_usd=0.007,
            )

    monkeypatch.setattr(chat_api, "ExaSearchProvider", FailingSearchProvider)
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'failed_web_chat.db'}",
        enable_cloud_services=True,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        kimi_api_key="test",
        exa_api_key="test",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)

    response = client.post(
        "/chat/query",
        json={
            "query": "Search current gold evidence",
            "sensitivity": "public",
            "selection_mode": "manual",
            "requested_model": "moonshot/kimi-k2.6",
            "evidence_scope": "web",
        },
    )
    runs = client.get("/runs").json()

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "web_search_rate_limited"
    assert runs["failed_runs"] == 1
    assert runs["recent_runs"][0]["status"] == "failed"
    assert runs["recent_runs"][0]["total_tokens"] == 0
    assert runs["recent_runs"][0]["total_estimated_cost_usd"] == 0.007


def test_web_research_stops_after_one_targeted_follow_up_without_model_call(
    tmp_path,
    monkeypatch,
) -> None:
    search_queries: list[str] = []
    model_calls: list[object] = []
    retrieved_at = datetime(2026, 7, 15, 20, tzinfo=timezone.utc)

    class UnrelatedSearchProvider:
        provider_name = "exa"

        def __init__(self, **kwargs) -> None:
            del kwargs

        def search(self, query, *, as_of_date=None) -> WebSearchResponse:
            del as_of_date
            search_queries.append(query)
            index = len(search_queries)
            return WebSearchResponse(
                provider="exa",
                query=query,
                request_id=f"exa-gap-{index}",
                search_type="auto",
                results=(
                    WebEvidence(
                        evidence_key=f"unrelated-{index}",
                        title="Unrelated semiconductor note",
                        url=f"https://example.com/unrelated-{index}",
                        author=None,
                        published_at=retrieved_at,
                        retrieved_at=retrieved_at,
                        text="Semiconductor factory capacity expanded during the quarter.",
                        highlights=(
                            "Semiconductor factory capacity expanded during the quarter.",
                        ),
                        highlight_scores=(0.9,),
                    ),
                ),
                estimated_cost_usd=0.007,
            )

    class MustNotRunAnswerProvider:
        provider_name = "moonshot"
        model_name = "kimi-k2.6"
        deployment = Deployment.CLOUD
        serving_engine = "kimi-api"

        def generate(self, request) -> ModelResponse:
            model_calls.append(request)
            raise AssertionError("Answer model must not run without accepted evidence")

    monkeypatch.setattr(chat_api, "ExaSearchProvider", UnrelatedSearchProvider)
    monkeypatch.setattr(
        chat_api.LocalResearchWorkflow,
        "model_provider",
        lambda *args, **kwargs: MustNotRunAnswerProvider(),
    )
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'web_gap.db'}",
        enable_cloud_services=True,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        kimi_api_key="test",
        exa_api_key="test",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)

    response = client.post(
        "/chat/query",
        json={
            "query": "How do real yields affect gold?",
            "sensitivity": "public",
            "selection_mode": "manual",
            "requested_model": "moonshot/kimi-k2.6",
            "evidence_scope": "web",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(search_queries) == 2
    assert model_calls == []
    assert payload["execution_outcome"] == "web_skipped_no_supported_evidence"
    assert payload["search_calls"] == 2
    assert payload["search"]["agent_search_triggered"] is True
    assert payload["search"]["evidence_gate"]["decision"] == "refuse"
    assert payload["provider_tokens"] == 0
    assert payload["search_estimated_cost_usd"] == 0.014
    assert payload["total_estimated_cost_usd"] == 0.014
    assert payload["web_sources"] == []


def test_hybrid_chinese_summary_uses_uploaded_document_without_required_framework(
    tmp_path,
    monkeypatch,
) -> None:
    generated_at = datetime(2026, 7, 22, 20, tzinfo=timezone.utc)
    model_calls: list[object] = []

    class UnrelatedSearchProvider:
        provider_name = "exa"

        def __init__(self, **kwargs) -> None:
            del kwargs

        def search(self, query, *, as_of_date=None) -> WebSearchResponse:
            del as_of_date
            return WebSearchResponse(
                provider="exa",
                query=query,
                request_id="exa-summary-test",
                search_type="auto",
                results=(
                    WebEvidence(
                        evidence_key="unrelated-web-result",
                        title="Unrelated market article",
                        url="https://example.com/unrelated-market-article",
                        author=None,
                        published_at=generated_at,
                        retrieved_at=generated_at,
                        text="Semiconductor factory capacity expanded during the quarter.",
                        highlights=(
                            "Semiconductor factory capacity expanded during the quarter.",
                        ),
                        highlight_scores=(0.8,),
                    ),
                ),
                estimated_cost_usd=0.007,
            )

    class SummaryAnswerProvider:
        provider_name = "moonshot"
        model_name = "kimi-k2.6"
        deployment = Deployment.CLOUD
        serving_engine = "kimi-api"

        def generate(self, request) -> ModelResponse:
            model_calls.append(request)
            assert "## Executive summary" in request.objective
            assert '"style_id": "general_research"' in request.objective
            rows = request.tool_results[0].output["results"]
            assert rows
            assert all(row["source_type"] == "markdown" for row in rows)
            return ModelResponse(
                provider=self.provider_name,
                model=self.model_name,
                deployment=self.deployment,
                serving_engine=self.serving_engine,
                content=(
                    "## Executive summary\nThe uploaded document argues that unclear "
                    "ownership slows infrastructure decisions [source:L1].\n"
                    "## Key points\n- It recommends explicit decision rights and "
                    "accountable leaders [source:L1].\n"
                    "## Supporting passages\n- Ownership and operating discipline are "
                    "the central themes [source:L1].\n"
                    "## Important caveats or missing context\n- This summary uses only "
                    "the uploaded document [source:L1]."
                ),
                prompt_tokens=90,
                completion_tokens=50,
                estimated_cost_usd=0.001,
            )

    monkeypatch.setattr(chat_api, "ExaSearchProvider", UnrelatedSearchProvider)
    monkeypatch.setattr(
        chat_api.LocalResearchWorkflow,
        "model_provider",
        lambda *args, **kwargs: SummaryAnswerProvider(),
    )
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'hybrid_summary.db'}",
        enable_cloud_services=True,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        kimi_api_key="test",
        exa_api_key="test",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    source = tmp_path / "meta_culture_reset.md"
    source.write_text(
        (
            "Meta's infrastructure organization needs a culture reset because unclear "
            "ownership slows decisions. The document recommends explicit decision rights, "
            "measurable operating goals, and accountable leaders."
        ),
        encoding="utf-8",
    )
    document_id = client.post(
        "/documents/ingest",
        json={"path": str(source)},
    ).json()["document_id"]

    response = client.post(
        "/chat/query",
        json={
            "query": "总结上传这篇 Meta 文档，总结文档要点",
            "document_id": document_id,
            "sensitivity": "public",
            "selection_mode": "manual",
            "requested_model": "moonshot/kimi-k2.6",
            "evidence_scope": "hybrid",
            "style_pack_id": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(model_calls) == 1
    assert payload["answer_generated"] is True
    assert payload["execution_outcome"] == "hybrid_evidence_completed"
    assert payload["style_pack_id"] == "general_research"
    assert payload["web_sources"] == []
    assert payload["sources"][0]["display_name"] == "meta_culture_reset.md"
    events = [
        event
        for event in app.state.event_publisher.events
        if event.event_type == "agent.run.completed.v1"
    ]
    assert events[-1].payload["answer_generated"] is True
    assert events[-1].payload["execution_outcome"] == "hybrid_evidence_completed"


def test_chat_query_does_not_reuse_unrelated_source(tmp_path) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold demand strengthened as real yields fell and central banks bought.",
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    client.post("/documents/ingest", json={"path": str(source)})
    response = client.post(
        "/chat/query",
        json={"query": "What does ACME revenue say about software margins?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    assert (
        payload["answer"]
        == "I could not find relevant local evidence for this question."
    )
    assert payload["evidence_ids"] == []
    assert payload["sources"] == []
    assert payload["claims"] == []
    assert payload["critic"]["status"] == "warning"
    assert payload["critic"]["findings"][0]["code"] == "no_evidence_retrieved"


def test_chat_query_uses_selected_document_context(tmp_path) -> None:
    old_source = tmp_path / "old_macro.md"
    selected_source = tmp_path / "gold_outlook_zh.md"
    old_source.write_text(
        "Supplier capacity normalized and ACME backlog declined.",
        encoding="utf-8",
    )
    selected_source.write_text(
        "黄金展望指出，2026 年金价可能受到央行购金、实际利率变化和投资需求影响。",
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    client.post("/documents/ingest", json={"path": str(old_source)})
    selected_ingest = client.post(
        "/documents/ingest",
        json={"path": str(selected_source)},
    )
    response = client.post(
        "/chat/query",
        json={
            "query": "Can I invest gold in 2026?",
            "document_id": selected_ingest.json()["document_id"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    assert "黄金展望" in payload["answer"]
    assert payload["sources"][0]["display_name"] == "gold_outlook_zh.md"
    assert payload["claims"]


def test_chat_query_focuses_csv_answer_on_question_keywords(tmp_path) -> None:
    source = tmp_path / "gold_macro_indicators.csv"
    source.write_text(
        "\n".join(
            [
                "year,gold_return_pct,real_yield_pct,etf_flows_b,"
                "central_bank_demand_share_pct",
                "2021,-4,-1.1,-9,14",
                "2022,1,1.6,-3,17",
                "2023,13,1.8,-1,21",
                "2024,27,1.5,2,22",
                "2025,19,0.8,3,23",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    document_id = ingest_response.json()["document_id"]
    gold_response = client.post(
        "/chat/query",
        json={
            "query": "What is the gold return trend?",
            "document_id": document_id,
        },
    )
    flows_response = client.post(
        "/chat/query",
        json={
            "query": "What is the ETF flows trend?",
            "document_id": document_id,
        },
    )

    assert ingest_response.status_code == 201
    assert gold_response.status_code == 200
    assert flows_response.status_code == 200
    gold_payload = gold_response.json()
    flows_payload = flows_response.json()
    assert gold_payload["answer"] != flows_payload["answer"]
    assert "Gold Return rose from -4% in 2021 to 19% in 2025" in gold_payload["answer"]
    assert "ETF Flows" not in gold_payload["answer"]
    assert "ETF Flows rose from -$9B in 2021 to $3B in 2025" in flows_payload["answer"]
    assert "Gold Return" not in flows_payload["answer"]
    assert gold_payload["sources"][0]["display_name"] == "gold_macro_indicators.csv"
    assert flows_payload["sources"][0]["display_name"] == "gold_macro_indicators.csv"
    assert gold_payload["claims"]
    assert flows_payload["claims"]


def test_chat_query_answers_factor_question_from_factor_columns(tmp_path) -> None:
    source = tmp_path / "gold_macro_indicators.csv"
    source.write_text(
        "\n".join(
            [
                "year,gold_return_pct,real_yield_pct,etf_flows_b,"
                "central_bank_demand_share_pct",
                "2021,-4,-1.1,-9,14",
                "2022,1,1.6,-3,17",
                "2023,13,1.8,-1,21",
                "2024,27,1.5,2,22",
                "2025,19,0.8,3,23",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    response = client.post(
        "/chat/query",
        json={
            "query": "What's the factor can influence gold price?",
            "document_id": ingest_response.json()["document_id"],
        },
    )

    assert ingest_response.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert "possible gold-price factors" in payload["answer"]
    assert "Real Yield rose from -1.1% in 2021 to 0.8% in 2025" in payload["answer"]
    assert "ETF Flows rose from -$9B in 2021 to $3B in 2025" in payload["answer"]
    assert "Gold Return" not in payload["answer"]
    assert payload["sources"][0]["display_name"] == "gold_macro_indicators.csv"
    assert payload["claims"]
    assert (
        "ETF Flows rose from -$9B in 2021 to $3B in 2025"
        in payload["claims"][0]["claim_text"]
    )


def test_chat_query_clears_citations_when_selected_csv_has_no_matching_metric(
    tmp_path,
) -> None:
    source = tmp_path / "gold_macro_indicators.csv"
    source.write_text(
        "\n".join(
            [
                "year,gold_return_pct,real_yield_pct",
                "2021,-4,-1.1",
                "2022,1,1.6",
                "2023,13,1.8",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    response = client.post(
        "/chat/query",
        json={
            "query": "What is the semiconductor margin trend?",
            "document_id": ingest_response.json()["document_id"],
        },
    )

    assert ingest_response.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["answer"]
        == "I could not find relevant local evidence for this question."
    )
    assert payload["evidence_ids"] == []
    assert payload["sources"] == []
    assert payload["claims"] == []


def test_chat_query_does_not_answer_investment_advice_from_csv_metric(
    tmp_path,
) -> None:
    source = tmp_path / "gold_macro_indicators.csv"
    source.write_text(
        "\n".join(
            [
                "year,gold_return_pct,real_yield_pct",
                "2021,-4,-1.1",
                "2022,1,1.6",
                "2023,13,1.8",
                "2024,27,1.5",
                "2025,19,0.8",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    response = client.post(
        "/chat/query",
        json={
            "query": "Can I invest gold in 2026?",
            "document_id": ingest_response.json()["document_id"],
        },
    )

    assert ingest_response.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["answer"]
        == "I could not find relevant local evidence for this question."
    )
    assert payload["evidence_ids"] == []
    assert payload["sources"] == []
    assert payload["claims"] == []


def test_chat_query_does_not_answer_future_year_from_historical_csv(
    tmp_path,
) -> None:
    source = tmp_path / "gold_macro_indicators.csv"
    source.write_text(
        "\n".join(
            [
                "year,gold_return_pct,real_yield_pct",
                "2021,-4,-1.1",
                "2022,1,1.6",
                "2023,13,1.8",
                "2024,27,1.5",
                "2025,19,0.8",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    response = client.post(
        "/chat/query",
        json={
            "query": "What's the gold trend in 2027?",
            "document_id": ingest_response.json()["document_id"],
        },
    )

    assert ingest_response.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["answer"]
        == "I could not find relevant local evidence for this question."
    )
    assert payload["evidence_ids"] == []
    assert payload["sources"] == []
    assert payload["claims"] == []


def test_chat_query_rejects_blank_query(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post("/chat/query", json={"query": ""})

    assert response.status_code == 422


def test_chat_lists_manual_model_options(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.get("/chat/models")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 4
    assert payload[0]["id"] == "local/deterministic-mock-researcher"
    assert payload[0]["available"] is True
    assert payload[1]["deployment"] == "cloud"
    assert payload[1]["available"] is False
    assert payload[2]["id"].startswith("deepseek/")
    assert payload[2]["input_cost_per_million"] == 0.14
    assert payload[3]["id"].startswith("moonshot/")
    assert payload[3]["supports_market_search"] is False
    assert payload[3]["supports_independent_web_search"] is False


def test_exa_enables_independent_web_search_for_all_configured_answer_models(
    tmp_path,
) -> None:
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'model_options.db'}",
        enable_cloud_services=True,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        gemini_api_key="test",
        deepseek_api_key="test",
        kimi_api_key="test",
        exa_api_key="test",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    payload = TestClient(app).get("/chat/models").json()

    assert payload[0]["supports_independent_web_search"] is False
    assert all(
        option["supports_independent_web_search"] is True for option in payload[1:]
    )
    assert all(option["supports_market_search"] is True for option in payload[1:])


def test_chat_query_enforces_manual_model_selection(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    source = tmp_path / "source.md"
    source.write_text("Gold is discussed in this source.", encoding="utf-8")
    client.post("/documents/ingest", json={"path": str(source)})

    response = client.post(
        "/chat/query",
        json={
            "query": "Find evidence",
            "selection_mode": "manual",
            "requested_model": "google/not-configured",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "routing_failed"
    assert payload["error_code"] == "model_not_available"


def test_indexed_provider_timeout_publishes_failed_event_only(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold benefited when real yields fell because its opportunity cost declined.",
        encoding="utf-8",
    )

    def timeout_after_retrieval(
        self: OpenAICompatibleModelProvider,
        payload: dict[str, object],
    ) -> dict[str, object]:
        del self, payload
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(
        OpenAICompatibleModelProvider,
        "_post_json",
        timeout_after_retrieval,
    )
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'indexed_timeout.db'}",
        enable_cloud_services=True,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        kimi_api_key="test",
        model_max_attempts=1,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    document_id = client.post(
        "/documents/ingest",
        json={"path": str(source)},
    ).json()["document_id"]

    response = client.post(
        "/chat/query",
        json={
            "query": "Why might gold benefit when real yields fall?",
            "document_id": document_id,
            "sensitivity": "public",
            "selection_mode": "manual",
            "requested_model": "moonshot/kimi-k2.6",
            "evidence_scope": "indexed",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error_code"] == "provider_timeout"
    assert payload["execution_outcome"] == "cloud_provider_failed"
    terminal_events = [
        event
        for event in app.state.event_publisher.events
        if event.aggregate_id == str(payload["run_id"])
    ]
    assert [event.event_type for event in terminal_events] == ["agent.run.failed.v1"]
    assert terminal_events[0].payload["error_code"] == "provider_timeout"
    assert terminal_events[0].payload["provider"] == "moonshot"
    assert terminal_events[0].payload["model"] == "kimi-k2.6"


def test_cloud_decline_reports_billed_provider_tokens(tmp_path, monkeypatch) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold benefited when real yields fell.",
        encoding="utf-8",
    )

    def fake_post_json(
        self: OpenAICompatibleModelProvider,
        payload: dict[str, object],
    ) -> dict[str, object]:
        del self, payload
        return {
            "choices": [{"message": {"content": NO_EVIDENCE_ANSWER}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }

    monkeypatch.setattr(OpenAICompatibleModelProvider, "_post_json", fake_post_json)
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'cloud_chat_api.db'}",
        enable_cloud_services=True,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        deepseek_api_key="test",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    document_id = client.post("/documents/ingest", json={"path": str(source)}).json()[
        "document_id"
    ]

    response = client.post(
        "/chat/query",
        json={
            "query": "Why might gold benefit when real yields fall?",
            "document_id": document_id,
            "sensitivity": "public",
            "selection_mode": "manual",
            "requested_model": "deepseek/deepseek-v4-flash",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_outcome"] == "cloud_declined_unsupported"
    assert payload["provider_tokens"] == 120
    assert payload["prompt_tokens"] == 100
    assert payload["completion_tokens"] == 20
    assert payload["total_tokens"] > payload["provider_tokens"]
    assert "provider tokens were billed" in payload["execution_message"]


def client_for_tmp_db(tmp_path) -> TestClient:
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'chat_api.db'}",
        enable_cloud_services=False,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)
