from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from investment_agent.app import create_app
from investment_agent.billing import ProviderBalance
from investment_agent.config import Settings
from investment_agent.repositories import (
    AgentRunCreate,
    AgentRunRepository,
    EventAuditCreate,
    EventAuditRepository,
    ModelCallCreate,
)
from investment_agent.storage import AgentRun, Base


def test_runs_dashboard_returns_zero_state(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.get("/runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_runs"] == 0
    assert payload["total_tokens"] == 0
    assert payload["total_estimated_cost_usd"] == 0
    assert payload["recent_runs"] == []
    assert payload["model_breakdown"] == []
    assert payload["retained_run_usage"]["total_tokens"] == 0
    assert payload["historical_api_usage"]["total_tokens"] == 0
    assert payload["historical_model_breakdown"] == []
    assert payload["provider_billing_snapshots"] == []
    assert payload["provider_account_snapshots"] == []
    assert payload["event_pipeline"]["configured"] is False
    assert payload["event_pipeline"]["consumer_status"] == "disabled"
    assert payload["event_pipeline"]["processed_count"] == 0
    assert payload["event_pipeline"]["completed_count"] == 0
    assert payload["event_pipeline"]["answer_generated_count"] == 0
    assert payload["event_pipeline"]["safe_stop_count"] == 0
    assert payload["event_pipeline"]["failed_count"] == 0
    assert payload["event_pipeline"]["duplicate_count"] == 0
    assert payload["event_pipeline"]["dlq_count"] == 0
    assert payload["event_pipeline"]["recent_events"] == []
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert payload["has_more"] is False


def test_runs_dashboard_separates_model_failure_from_consumer_error(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    with client.app.state.session_factory() as session:
        EventAuditRepository(session).record(
            EventAuditCreate(
                event_id="event-provider-timeout",
                event_type="agent.run.failed.v1",
                aggregate_id="95",
                schema_version=1,
                status="processed",
                consumer_group="argus-audit-metrics-v1",
                topic="agent.run.failed.v1",
                payload_summary={
                    "run_id": 95,
                    "status": "failed",
                    "error_code": "provider_timeout",
                    "failure_stage": "answer_model",
                    "provider": "moonshot",
                    "model": "kimi-k2.6",
                    "total_tokens": 0,
                    "total_estimated_cost_usd": 0.0,
                },
            )
        )
        session.commit()

    event = client.get("/runs").json()["event_pipeline"]["recent_events"][0]

    assert event["error_code"] is None
    assert event["failure_code"] == "provider_timeout"
    assert event["provider"] == "moonshot"
    assert event["model"] == "kimi-k2.6"


def test_runs_dashboard_and_detail_after_chat_query(tmp_path) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold demand strengthened as real yields fell and central banks bought.",
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    query_response = client.post(
        "/chat/query",
        json={"query": "Why might gold benefit when real yields fall?"},
    )
    dashboard_response = client.get("/runs")

    assert ingest_response.status_code == 201
    assert query_response.status_code == 200
    assert dashboard_response.status_code == 200
    query_payload = query_response.json()
    dashboard = dashboard_response.json()
    assert dashboard["total_runs"] == 1
    assert dashboard["total_tokens"] == query_payload["total_tokens"]
    assert dashboard["model_call_count"] == 2
    assert dashboard["retained_run_usage"]["call_count"] == 0
    assert dashboard["retained_run_usage"]["total_tokens"] == 0
    assert dashboard["historical_api_usage"]["call_count"] == 0
    assert dashboard["historical_api_usage"]["total_tokens"] == 0
    assert dashboard["tool_call_count"] == 1
    assert dashboard["model_breakdown"] == []
    assert dashboard["historical_model_breakdown"] == []
    assert dashboard["recent_runs"][0]["id"] == query_payload["run_id"]
    assert dashboard["recent_runs"][0]["model_call_count"] == 2
    assert dashboard["recent_runs"][0]["tool_call_count"] == 1
    assert "Auto selected" in dashboard["recent_runs"][0]["selection_reason"]
    completed_events = [
        event
        for event in client.app.state.event_publisher.events
        if event.event_type == "agent.run.completed.v1"
    ]
    assert len(completed_events) == 1
    assert completed_events[0].aggregate_id == str(query_payload["run_id"])
    assert completed_events[0].payload["status"] == "complete"

    detail_response = client.get(f"/runs/{query_payload['run_id']}")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["run"]["id"] == query_payload["run_id"]
    assert len(detail["model_calls"]) == 2
    assert detail["model_calls"][0]["total_tokens"] > 0
    assert len(detail["tool_calls"]) == 1
    assert detail["tool_calls"][0]["tool_name"] == "retrieve_evidence"
    assert detail["tool_calls"][0]["arguments"]["query"] == (
        "Why might gold benefit when real yields fall?"
    )
    assert detail["evidence_ledger_queries"]
    assert detail["evidence_ledger_links"]
    assert detail["decision_trace"] is None


def test_runs_dashboard_supports_bounded_pagination(tmp_path) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold demand strengthened as real yields fell and central banks bought.",
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)
    assert (
        client.post("/documents/ingest", json={"path": str(source)}).status_code == 201
    )
    for query in (
        "Why might gold benefit when real yields fall?",
        "How can central-bank demand affect gold?",
    ):
        assert client.post("/chat/query", json={"query": query}).status_code == 200

    first_page = client.get("/runs?limit=1&offset=0").json()
    second_page = client.get("/runs?limit=1&offset=1").json()

    assert first_page["total_runs"] == 2
    assert len(first_page["recent_runs"]) == 1
    assert first_page["has_more"] is True
    assert second_page["offset"] == 1
    assert len(second_page["recent_runs"]) == 1
    assert second_page["has_more"] is False


def test_run_detail_returns_404_for_missing_run(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.get("/runs/404")

    assert response.status_code == 404


def test_portfolio_trace_retention_is_bounded_by_age_and_count(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    with client.app.state.session_factory() as session:
        repository = AgentRunRepository(session)
        market_runs = []
        for index in range(4):
            market_run = repository.create_run(
                AgentRunCreate(
                    run_key=f"market-{index}",
                    role="portfolio_market_analysis",
                    objective="Bounded audit trace",
                    status="complete",
                    sensitivity="internal",
                    as_of_date=date(2026, 7, 20),
                )
            )
            market_runs.append(market_run)
            repository.record_model_call(
                ModelCallCreate(
                    run_id=market_run.id,
                    provider="test-provider",
                    model="test-model",
                    deployment="cloud",
                    prompt_tokens=10,
                    completion_tokens=5,
                    estimated_cost_usd=0.001,
                    input_cost_per_million_usd=1.0,
                    output_cost_per_million_usd=2.0,
                )
            )
        unrelated = repository.create_run(
            AgentRunCreate(
                run_key="chat-kept",
                role="research",
                objective="Unrelated run",
                status="complete",
                sensitivity="internal",
                as_of_date=date(2026, 7, 20),
            )
        )
        market_runs[0].created_at = datetime.now(timezone.utc) - timedelta(days=31)
        session.flush()

        assert (
            repository.prune_runs_by_role(
                role="portfolio_market_analysis",
                keep_latest=10,
                max_age_days=30,
            )
            == 1
        )
        assert (
            repository.prune_runs_by_role(
                role="portfolio_market_analysis",
                keep_latest=2,
                max_age_days=30,
            )
            == 1
        )
        session.commit()

        remaining_market = (
            session.query(AgentRun).filter_by(role="portfolio_market_analysis").all()
        )
        assert len(remaining_market) == 2
        assert session.get(AgentRun, unrelated.id) is not None
        assert repository.retained_model_usage_totals().call_count == 2
        assert repository.api_usage_totals().call_count == 4
        assert repository.api_usage_totals().prompt_tokens == 40


def test_provider_billing_snapshot_is_separate_from_estimates(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/runs/provider-billing-snapshots",
        json={
            "provider": "DeepSeek",
            "period_start": "2026-06-22",
            "period_end": "2026-07-21",
            "currency": "CNY",
            "actual_cost": 0.11,
            "total_tokens": 91528,
            "request_count": 32,
            "source_reference": "provider usage export",
        },
    )

    assert response.status_code == 201
    snapshot = response.json()
    assert snapshot["provider"] == "deepseek"
    assert snapshot["currency"] == "CNY"
    dashboard = client.get("/runs").json()
    assert dashboard["historical_api_usage"]["total_tokens"] == 0
    assert dashboard["provider_billing_snapshots"][0]["total_tokens"] == 91528
    assert dashboard["provider_billing_snapshots"][0]["actual_cost"] == 0.11


def test_provider_billing_snapshot_rejects_reverse_period(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/runs/provider-billing-snapshots",
        json={
            "provider": "provider",
            "period_start": "2026-07-21",
            "period_end": "2026-06-22",
            "currency": "USD",
            "actual_cost": 1.0,
        },
    )

    assert response.status_code == 422


def test_deepseek_export_import_is_exact_redacted_and_idempotent(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    archive = _deepseek_export_zip()

    first = client.post(
        "/runs/provider-billing-snapshots/import/deepseek",
        content=archive,
        headers={"X-Argus-Filename": "usage_data.zip"},
    )
    second = client.post(
        "/runs/provider-billing-snapshots/import/deepseek",
        content=archive,
        headers={"X-Argus-Filename": "usage_data.zip"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    snapshot = first.json()
    assert snapshot["period_start"] == "2026-06-22"
    assert snapshot["period_end"] == "2026-07-21"
    assert snapshot["actual_cost"] == 0.11910752
    assert snapshot["total_tokens"] == 91528
    assert snapshot["request_count"] == 32
    serialized = str(snapshot["metadata"])
    assert "Google-user" not in serialized
    assert "sk-secret" not in serialized
    assert snapshot["metadata"]["model_breakdown"][0]["model"] == (
        "deepseek-v4-flash"
    )
    assert len(client.get("/runs").json()["provider_billing_snapshots"]) == 1


def test_provider_account_snapshot_is_not_counted_as_spend(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/runs/provider-account-snapshots",
        json={
            "provider": "Kimi",
            "billing_tier": "paid",
            "billing_status": "active",
            "currency": "CNY",
            "available_balance": 63.27922,
            "paid_balance": 50,
            "promotional_balance": 13.27922,
            "source_reference": "official balance API",
        },
    )

    assert response.status_code == 201
    dashboard = client.get("/runs").json()
    assert dashboard["provider_billing_snapshots"] == []
    assert dashboard["historical_api_usage"]["total_estimated_cost_usd"] == 0
    account = dashboard["provider_account_snapshots"][0]
    assert account["provider"] == "kimi"
    assert account["available_balance"] == 63.27922


def test_provider_balance_refresh_updates_supported_accounts(
    tmp_path,
    monkeypatch,
) -> None:
    client = client_for_tmp_db(
        tmp_path,
        enable_cloud_services=True,
        deepseek_api_key="deepseek-secret",
        kimi_api_key="kimi-secret",
    )
    monkeypatch.setattr(
        "investment_agent.api.runs.fetch_deepseek_balance",
        lambda **_kwargs: ProviderBalance(
            provider="deepseek",
            billing_status="active",
            currency="CNY",
            available_balance=Decimal("9.50"),
            paid_balance=Decimal("7.00"),
            promotional_balance=Decimal("2.50"),
            source_reference="https://api.deepseek.com/user/balance",
        ),
    )
    monkeypatch.setattr(
        "investment_agent.api.runs.fetch_kimi_balance",
        lambda **_kwargs: ProviderBalance(
            provider="moonshot",
            billing_status="active",
            currency="CNY",
            available_balance=Decimal("65.00"),
            paid_balance=Decimal("50.00"),
            promotional_balance=Decimal("15.00"),
            source_reference="https://api.moonshot.cn/v1/users/me/balance",
        ),
    )

    response = client.post("/runs/provider-account-snapshots/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated_count"] == 2
    assert {item["status"] for item in payload["results"]} == {"updated"}
    accounts = client.get("/runs").json()["provider_account_snapshots"]
    assert {account["provider"] for account in accounts} == {"deepseek", "moonshot"}
    assert all(account["billing_status"] == "active" for account in accounts)


def test_deepseek_export_rejects_oversized_request_before_parsing(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/runs/provider-billing-snapshots/import/deepseek",
        content=b"x" * (5 * 1024 * 1024 + 1),
        headers={"X-Argus-Filename": "usage_data.zip"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == (
        "The DeepSeek export exceeds the 5 MB import limit."
    )


def _deepseek_export_zip() -> bytes:
    cost_csv = """user_id,utc_date,model,wallet_type,cost,currency
Google-user,20260716,deepseek-v4-flash,Paid,0.10570052,CNY
Google-user,20260718,deepseek-v4-pro,Paid,0.013407,CNY
"""
    amount_csv = """user_id,utc_date,model,api_key_name,api_key,type,price,amount
Google-user,20260716,deepseek-v4-flash,Argus,sk-secret,input_cache_hit_tokens,0,5376
Google-user,20260716,deepseek-v4-flash,Argus,sk-secret,input_cache_miss_tokens,0,59997
Google-user,20260716,deepseek-v4-flash,Argus,sk-secret,output_tokens,0,22798
Google-user,20260716,deepseek-v4-flash,Argus,sk-secret,request_count,,26
Google-user,20260718,deepseek-v4-pro,Argus,sk-secret,input_cache_miss_tokens,0,2245
Google-user,20260718,deepseek-v4-pro,Argus,sk-secret,output_tokens,0,1112
Google-user,20260718,deepseek-v4-pro,Argus,sk-secret,request_count,,6
"""
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as bundle:
        bundle.writestr("cost-2026-06-22_2026-07-22.csv", cost_csv)
        bundle.writestr("amount-2026-06-22_2026-07-22.csv", amount_csv)
    return output.getvalue()


def client_for_tmp_db(
    tmp_path,
    *,
    enable_cloud_services: bool = False,
    deepseek_api_key: str | None = None,
    kimi_api_key: str | None = None,
) -> TestClient:
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'runs_api.db'}",
        enable_cloud_services=enable_cloud_services,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        deepseek_api_key=deepseek_api_key,
        kimi_api_key=kimi_api_key,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)
