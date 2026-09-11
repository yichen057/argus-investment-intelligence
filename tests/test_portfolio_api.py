from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from investment_agent.api import portfolio as portfolio_api
from investment_agent.app import create_app
from investment_agent.config import Settings
from investment_agent.market_data import MarketDataBatch, MarketQuote
from investment_agent.storage import (
    AgentRun,
    Base,
    ModelCall,
    PortfolioPosition,
    ToolCallRecord,
    UserProfile,
)


def test_portfolio_upload_summary_and_profile_scenarios(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text(
        "\n".join(
            [
                "symbol,name,asset_class,quantity,price,market_value,cost_basis,account",
                "AAPL,Apple Inc,Equity,10,200,2000,1500,Taxable",
                "BND,Vanguard Bond ETF,Bond,20,50,1000,950,IRA",
                "CASH,Cash Sweep,Cash,1,500,500,500,Taxable",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    profile_response = client.post(
        "/profile",
        json={
            "risk_tolerance": "conservative",
            "life_stage": "early career",
            "investment_horizon": "10+ years",
            "income_stability": "stable",
            "liquidity_needs": "medium",
            "preferred_style": "macro",
            "target_allocation": {"Equity": 0.5, "Bond": 0.5},
        },
    )
    upload_response = client.post("/portfolio/upload", json={"path": str(source)})
    summary_response = client.get("/portfolio/summary")
    saved_profile_response = client.get("/profile")

    assert profile_response.status_code == 201
    assert upload_response.status_code == 201
    assert summary_response.status_code == 200
    assert saved_profile_response.status_code == 200
    upload_payload = upload_response.json()
    summary_payload = summary_response.json()
    assert upload_payload["positions_count"] == 3
    assert upload_payload["summary"]["total_value"] == 3500
    assert summary_payload["total_value"] == 3500
    assert summary_payload["positions"][0]["symbol"] == "AAPL"
    assert summary_payload["positions"][0]["weight"] == 2000 / 3500
    assert summary_payload["allocation"][0]["asset_class"] == "Equity"
    assert summary_payload["concentration_flags"][0]["code"] == (
        "single_position_concentration"
    )
    assert summary_payload["concentration_flags"][0]["threshold"] == 0.25
    assert summary_payload["concentration_flags"][0][
        "excess_percentage_points"
    ] == pytest.approx((2000 / 3000 - 0.25) * 100)
    assert {scenario["scenario"] for scenario in summary_payload["scenarios"]} >= {
        "Reduce concentration",
        "Rebalance toward target allocation",
    }
    assert [
        scenario["code"] for scenario in summary_payload["rebalance_scenarios"]
    ] == ["maintain", "new_contributions", "partial_sell_reallocate"]
    assert all(
        action["reference_kind"] == "policy_target"
        for action in summary_payload["rebalance_actions"]
    )
    assert summary_payload["recommendation_context"]["analysis_method"] == (
        "deterministic_portfolio_rules"
    )
    assert len(summary_payload["sector_candidates"]) == 41
    assert all(
        candidate["candidate_category"] in {"sector_research", "industry_research"}
        and candidate["dca_eligible"] is False
        for candidate in summary_payload["sector_candidates"]
    )
    xsd = next(
        candidate
        for candidate in summary_payload["sector_candidates"]
        if candidate["symbol"] == "XSD"
    )
    assert xsd["source_link_kind"] == "issuer_directory"
    assert xsd["source_checked_at"] == "2026-07-20"
    assert saved_profile_response.json()["risk_tolerance"] == "conservative"

    with client.app.state.session_factory() as session:
        positions = session.query(PortfolioPosition).all()
        profiles = session.query(UserProfile).all()

    assert len(positions) == 3
    assert len(profiles) == 1
    assert profiles[0].is_active


def test_portfolio_upload_maps_invalid_csv_to_422(tmp_path) -> None:
    source = tmp_path / "holdings.csv"
    source.write_text("symbol,market_value\nAAPL,2000\n", encoding="utf-8")
    client = client_for_tmp_db(tmp_path)

    response = client.post("/portfolio/upload", json={"path": str(source)})

    assert response.status_code == 422


def test_portfolio_browser_upload_accepts_xlsx(tmp_path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(
        [
            "symbol",
            "name",
            "asset_class",
            "quantity",
            "price",
            "market_value",
            "cost_basis",
            "account",
        ]
    )
    worksheet.append(["MSFT", "Microsoft", "Equity", 4, 500, 2000, 1200, "Taxable"])
    worksheet.append(["CASH", "Cash", "Cash", 1, 250, 250, 250, "Brokerage"])
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/portfolio/upload-file",
        files={
            "file": (
                "holdings.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["positions_count"] == 2
    assert payload["summary"]["total_value"] == 2250
    assert payload["summary"]["positions"][0]["symbol"] == "MSFT"


def test_portfolio_browser_upload_accepts_csv(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/portfolio/upload-file",
        files={
            "file": (
                "holdings.csv",
                "\n".join(
                    [
                        "symbol,name,asset_class,quantity,price,market_value,cost_basis,account",
                        "AAPL,Apple Inc,Equity,10,200,2000,1500,Taxable",
                    ]
                ).encode(),
                "text/csv",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["positions_count"] == 1


def test_market_map_uses_uploaded_snapshot_when_external_data_is_off(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    client.post(
        "/portfolio/upload-file",
        data={"as_of_date": "2026-07-20"},
        files={
            "file": (
                "holdings.csv",
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,account\n"
                    "XLF,Financial Select Sector SPDR Fund,ETF,2,50,100,80,Taxable\n"
                    "JPM,JPMorgan Chase,Equity,1,300,300,250,Taxable"
                ).encode(),
                "text/csv",
            )
        },
    )

    response = client.get("/portfolio/market-map")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "external_disabled"
    assert payload["is_live"] is False
    assert payload["configured_provider_code"] == "01"
    assert payload["heatmap_enabled"] is False
    xlf = next(tile for tile in payload["tiles"] if tile["symbol"] == "XLF")
    assert xlf["latest_price"] == 50
    assert xlf["quote_status"] == "uploaded_snapshot"
    assert xlf["directly_held"] is True
    assert xlf["related_holdings"] == ["JPM"]
    assert xlf["volume_activity"] == "Not enough history"


def test_market_map_uses_only_explicitly_configured_source(tmp_path) -> None:
    client = client_for_tmp_db(
        tmp_path,
        enable_external_market_data=True,
        enable_robinhood=True,
        enable_market_heatmap=True,
        enable_unified_etf_universe=True,
    )
    profile_response = client.post(
        "/profile",
        json={
            "risk_tolerance": "moderate",
            "target_allocation": {"Equity": 0.5, "Bond": 0.5},
            "monthly_contribution": 500,
        },
    )
    upload_response = client.post(
        "/portfolio/upload-file",
        data={"as_of_date": "2026-07-21"},
        files={
            "file": (
                "holdings.csv",
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,account\n"
                    "AAPL,Apple Inc,Equity,10,200,2000,1500,Taxable"
                ).encode(),
                "text/csv",
            )
        },
    )
    assert profile_response.status_code == 201
    assert upload_response.status_code == 201

    class FakeMarketSource:
        provider_code = "01"
        provider_key = "robinhood"
        provider_name = "Robinhood Market Data"

        def fetch_quotes(self, symbols):
            assert "XLK" in symbols
            assert "BND" in symbols
            return MarketDataBatch(
                provider_code=self.provider_code,
                provider_key=self.provider_key,
                provider_name=self.provider_name,
                is_live=True,
                is_delayed=False,
                generated_at=datetime(2026, 7, 21, 18, tzinfo=timezone.utc),
                quotes=(
                    MarketQuote(
                        symbol="XLK",
                        last_price=300,
                        previous_close=294,
                        previous_close_date=date(2026, 7, 18),
                        percent_change=2.04,
                        volume=1_000_000,
                        dollar_volume=300_000_000,
                        volume_z_score=1.5,
                        observed_at=datetime(
                            2026, 7, 21, 18, tzinfo=timezone.utc
                        ),
                        status="live",
                    ),
                    MarketQuote(
                        symbol="BND",
                        last_price=100,
                        previous_close=99,
                        previous_close_date=date(2026, 7, 18),
                        percent_change=1.01,
                        volume=2_000_000,
                        dollar_volume=200_000_000,
                        volume_z_score=None,
                        observed_at=datetime(
                            2026, 7, 21, 18, tzinfo=timezone.utc
                        ),
                        status="live",
                    ),
                ),
                status="live",
                message="Connected read-only quotes.",
            )

    client.app.state.market_data_source = FakeMarketSource()

    response = client.get("/portfolio/market-map")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "live"
    assert payload["provider_code"] == "01"
    assert payload["heatmap_enabled"] is True
    assert payload["unified_universe_enabled"] is True
    xlk = next(tile for tile in payload["tiles"] if tile["symbol"] == "XLK")
    assert xlk["group"] == "Technology & AI"
    assert xlk["percent_change"] == 2.04
    assert xlk["previous_close_date"] == "2026-07-18"
    assert xlk["volume_z_score"] == 1.5
    bnd_buy = next(
        action
        for action in payload["portfolio_summary"]["rebalance_actions"]
        if action["symbol"] == "BND"
    )
    assert bnd_buy["reference_price"] == 100
    assert bnd_buy["estimated_shares"] == 10
    assert bnd_buy["warnings"] == []
    assert payload["portfolio_summary"]["recommendation_context"][
        "price_source"
    ] == "position_snapshot_with_live_candidate_quotes"


def test_robinhood_sync_requires_connection_and_uses_read_only_positions(tmp_path) -> None:
    client = client_for_tmp_db(
        tmp_path,
        enable_external_market_data=True,
        enable_robinhood=True,
    )

    missing_response = client.post("/portfolio/sync-robinhood")

    class FakeRobinhoodClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def read_positions(self):
            self.calls.append("read_positions")
            return {
                "positions": [
                    {
                        "symbol": "AAPL",
                        "quantity": "2",
                        "last_price": "200",
                        "average_cost": "150",
                        "account_type": "Brokerage",
                        "updated_at": "2026-07-21T15:00:00Z",
                    }
                ]
            }

    fake_client = FakeRobinhoodClient()
    client.app.state.robinhood_gateway = fake_client
    sync_response = client.post("/portfolio/sync-robinhood")

    assert missing_response.status_code == 409
    assert sync_response.status_code == 201
    assert sync_response.json()["as_of_date_source"] == "robinhood_mcp"
    assert sync_response.json()["positions_count"] == 1
    assert (
        sync_response.json()["summary"]["recommendation_context"]["price_source"]
        == "robinhood_mcp_snapshot"
    )
    assert not sync_response.json()["summary"]["recommendation_context"][
        "live_market_data"
    ]
    assert "active Robinhood holdings snapshot" in sync_response.json()["summary"][
        "recommendation_context"
    ]["analysis_method_description"]
    assert fake_client.calls == ["read_positions"]


def test_robinhood_partial_refresh_preserves_last_complete_snapshot(tmp_path) -> None:
    client = client_for_tmp_db(
        tmp_path,
        enable_external_market_data=True,
        enable_robinhood=True,
    )

    class CompleteThenPartialClient:
        def __init__(self) -> None:
            self.partial = False

        def read_positions(self):
            if self.partial:
                return {
                    "positions": [
                        {"symbol": "AAPL", "quantity": "2", "last_price": "200"},
                        {"symbol": "MSFT", "quantity": "1"},
                    ]
                }
            return {
                "positions": [
                    {
                        "symbol": "AAPL",
                        "quantity": "2",
                        "last_price": "200",
                        "account_type": "Brokerage",
                    }
                ]
            }

    fake_client = CompleteThenPartialClient()
    client.app.state.robinhood_gateway = fake_client

    first = client.post("/portfolio/sync-robinhood")
    fake_client.partial = True
    rejected = client.post("/portfolio/sync-robinhood")
    retained = client.get("/portfolio/summary")

    assert first.status_code == 201
    assert rejected.status_code == 502
    assert [item["symbol"] for item in retained.json()["positions"]] == ["AAPL"]
    assert retained.json()["positions"][0]["source_key"] == "robinhood_mcp"


def test_file_and_robinhood_sources_coexist_without_cross_source_erasure(tmp_path) -> None:
    client = client_for_tmp_db(
        tmp_path,
        enable_external_market_data=True,
        enable_robinhood=True,
    )
    uploaded = client.post(
        "/portfolio/upload-file",
        data={"as_of_date": "2026-07-20"},
        files={
            "file": (
                "holdings.csv",
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,account\n"
                    "CD1,Bank CD,Cash,1,5000,5000,5000,Bank"
                ).encode(),
                "text/csv",
            )
        },
    )

    class RobinhoodClient:
        def read_positions(self):
            return {
                "positions": [
                    {
                        "symbol": "AAPL",
                        "quantity": "2",
                        "last_price": "200",
                        "account_type": "Brokerage",
                    }
                ]
            }

    client.app.state.robinhood_gateway = RobinhoodClient()
    synced = client.post("/portfolio/sync-robinhood")
    summary = client.get("/portfolio/summary").json()

    assert uploaded.status_code == 201
    assert synced.status_code == 201
    assert {(item["symbol"], item["source_key"]) for item in summary["positions"]} == {
        ("AAPL", "robinhood_mcp"),
        ("CD1", "file_upload"),
    }
    assert (
        summary["recommendation_context"]["price_source"]
        == "mixed_position_snapshots"
    )


def test_robinhood_wins_for_an_overlapping_ticker(tmp_path) -> None:
    client = client_for_tmp_db(
        tmp_path,
        enable_external_market_data=True,
        enable_robinhood=True,
    )
    client.post(
        "/portfolio/upload-file",
        data={"as_of_date": "2026-07-20"},
        files={
            "file": (
                "holdings.csv",
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,account\n"
                    "AAPL,Apple,Equity,1,100,100,90,Manual brokerage"
                ).encode(),
                "text/csv",
            )
        },
    )

    class RobinhoodClient:
        def read_positions(self):
            return {
                "positions": [
                    {
                        "symbol": "AAPL",
                        "quantity": "2",
                        "last_price": "200",
                        "account_type": "Robinhood Investments",
                    }
                ]
            }

    client.app.state.robinhood_gateway = RobinhoodClient()
    client.post("/portfolio/sync-robinhood")
    positions = client.get("/portfolio/summary").json()["positions"]

    assert len(positions) == 1
    assert positions[0]["source_key"] == "robinhood_mcp"
    assert positions[0]["quantity"] == 2


def test_market_analysis_is_explicit_sourced_and_separate(
    tmp_path, monkeypatch
) -> None:
    client = client_for_tmp_db(
        tmp_path,
        enable_cloud_services=True,
        gemini_api_key="test",
        exa_api_key="test-exa",
    )
    client.post(
        "/portfolio/upload-file",
        data={"as_of_date": "2026-07-15"},
        files={
            "file": (
                "holdings.csv",
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,account\n"
                    "VTI,Vanguard Total Market,Equity,10,100,1000,900,IRA"
                ).encode(),
                "text/csv",
            )
        },
    )
    generated_at = datetime(2026, 7, 15, 18, tzinfo=timezone.utc)

    class FakeService:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def analyze(
            self,
            prompt: str,
            *,
            search_query: str,
            evidence_gate_query: str,
        ):
            assert '"portfolio_weight": 1.0' in prompt
            assert "1000" not in prompt
            assert "VTI" in search_query
            assert evidence_gate_query == "market risk drivers"
            return SimpleNamespace(
                provider="google",
                model="gemini-3.1-flash-lite",
                generated_at=generated_at,
                content="Sourced current context. [source:W1]",
                sources=(
                    SimpleNamespace(
                        citation_id="W1",
                        title="Federal Reserve",
                        url="https://www.federalreserve.gov/monetarypolicy.htm",
                        retrieved_at=generated_at,
                    ),
                ),
                prompt_tokens=100,
                completion_tokens=50,
                estimated_cost_usd=0.0071,
                source_method="Exa Search + Argus Evidence Gate + Gemini synthesis",
                search_provider="exa",
                search_calls=1,
                search_estimated_cost_usd=0.007,
                answer_model_estimated_cost_usd=0.0001,
                answer_model_calls=1,
                source_count=1,
                domain_count=1,
                limitations=(),
                retrieved_result_count=3,
                retrieved_domain_count=2,
                gate_rejected_result_count=2,
                evidence_snapshot_id="snapshot-test-001",
                candidate_parse_status="valid",
                raw_candidate_count=2,
                candidate_audit=(
                    SimpleNamespace(
                        index=0,
                        symbol="XLV",
                        requested_mode="new_exposure",
                        expected_mode="new_exposure",
                        supplied_citation_ids=("W1",),
                        accepted_citation_ids=("W1",),
                        present_fields=(
                            "rationale",
                            "counter_evidence",
                            "invalidation_signal",
                            "overlap_risk",
                            "dca_guidance",
                        ),
                        accepted=True,
                        validation_codes=("accepted",),
                    ),
                    SimpleNamespace(
                        index=1,
                        symbol="XLE",
                        requested_mode="new_exposure",
                        expected_mode="new_exposure",
                        supplied_citation_ids=("W9",),
                        accepted_citation_ids=(),
                        present_fields=("rationale",),
                        accepted=False,
                        validation_codes=("no_accepted_citation",),
                    ),
                ),
                watchlist=(
                    SimpleNamespace(
                        symbol="XLV",
                        name="Health Care Select Sector SPDR Fund",
                        category="sector_research",
                        rationale="Defensive earnings merit current research.",
                        counter_evidence="Valuations may already price in defensiveness.",
                        invalidation_signal="Relative earnings revisions turn negative.",
                        overlap_risk="VTI already contains health-care exposure.",
                        dca_guidance="Suitable only as a small satellite.",
                        dca_suitable=True,
                        citation_ids=("W1",),
                        recommendation_mode="new_exposure",
                    ),
                ),
            )

    monkeypatch.setattr(
        portfolio_api,
        "IndependentSearchMarketAnalysisService",
        FakeService,
    )
    monkeypatch.setattr(
        portfolio_api,
        "_market_answer_provider",
        lambda settings, requested_model: SimpleNamespace(provider_name="google"),
    )
    response = client.post(
        "/portfolio/market-analysis",
        json={"requested_model": "google/gemini-3.1-flash-lite"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == "Sourced current context. [source:W1]"
    assert payload["sources"][0]["url"].startswith("https://")
    assert payload["sources"][0]["citation_id"] == "W1"
    assert payload["search_provider"] == "exa"
    assert payload["search_estimated_cost_usd"] == 0.007
    assert payload["generated_at"] == "2026-07-15T18:00:00Z"
    assert payload["watchlist"][0]["symbol"] == "XLV"
    assert payload["watchlist"][0]["dca_suitable"] is True
    assert payload["watchlist"][0]["dca_monthly_amount"] == 0
    assert payload["watchlist"][0]["recommendation_mode"] == "new_exposure"
    assert payload["run_id"] > 0
    assert payload["evidence_snapshot_id"] == "snapshot-test-001"
    assert payload["candidate_audit"][1]["accepted"] is False
    assert payload["candidate_audit"][1]["validation_codes"] == ["no_accepted_citation"]

    detail = client.get(f"/runs/{payload['run_id']}").json()
    trace = detail["decision_trace"]
    assert trace["evidence_snapshot_id"] == "snapshot-test-001"
    assert trace["accepted_candidate_symbols"] == ["XLV"]
    assert trace["rejected_candidate_count"] == 1
    assert trace["privacy"] == {
        "raw_prompt_stored": False,
        "raw_model_response_stored": False,
        "full_web_pages_stored": False,
        "account_names_stored": False,
        "holding_dollar_values_stored": False,
        "api_keys_stored": False,
    }
    assert trace["retention"]["role_limit"] == 50
    assert trace["retention"]["max_age_days"] == 30

    with client.app.state.session_factory() as session:
        assert session.query(AgentRun).filter_by(id=payload["run_id"]).count() == 1
        assert session.query(ModelCall).filter_by(run_id=payload["run_id"]).count() == 1
        assert (
            session.query(ToolCallRecord).filter_by(run_id=payload["run_id"]).count()
            == 1
        )


def test_market_analysis_rejects_unconfigured_model(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    client.post(
        "/portfolio/upload-file",
        files={
            "file": (
                "holdings.csv",
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,account\n"
                    "VTI,Vanguard Total Market,Equity,10,100,1000,900,IRA"
                ).encode(),
                "text/csv",
            )
        },
    )

    response = client.post(
        "/portfolio/market-analysis",
        json={"requested_model": "deepseek/deepseek-v4-flash"},
    )

    assert response.status_code == 422
    assert "requires cloud services and an Exa API key" in response.text


def test_market_analysis_accepts_deepseek_as_exa_synthesis_model(
    tmp_path, monkeypatch
) -> None:
    client = client_for_tmp_db(
        tmp_path,
        enable_cloud_services=True,
        deepseek_api_key="test-deepseek",
        exa_api_key="test-exa",
    )
    client.post(
        "/portfolio/upload-file",
        files={
            "file": (
                "holdings.csv",
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,account\n"
                    "VTI,Vanguard Total Market,Equity,10,100,1000,900,IRA"
                ).encode(),
                "text/csv",
            )
        },
    )
    generated_at = datetime(2026, 7, 17, 18, tzinfo=timezone.utc)

    class FakeService:
        def __init__(self, **kwargs) -> None:
            assert kwargs["answer_provider"].provider_name == "deepseek"

        def analyze(
            self,
            prompt: str,
            *,
            search_query: str,
            evidence_gate_query: str,
        ):
            assert "supplied Exa evidence" in prompt
            assert "VTI" in search_query
            assert evidence_gate_query == "market risk drivers"
            return SimpleNamespace(
                provider="deepseek",
                model="deepseek-v4-flash",
                generated_at=generated_at,
                content="Current context. [source:W1]",
                sources=(
                    SimpleNamespace(
                        citation_id="W1",
                        title="Issuer source",
                        url="https://example.com/source",
                        retrieved_at=generated_at,
                    ),
                ),
                prompt_tokens=10,
                completion_tokens=10,
                estimated_cost_usd=0.00701,
                source_method=(
                    "Exa Search + Argus Evidence Gate + deepseek-v4-flash synthesis"
                ),
                search_provider="exa",
                search_calls=1,
                search_estimated_cost_usd=0.007,
                answer_model_estimated_cost_usd=0.00001,
            )

    monkeypatch.setattr(
        portfolio_api,
        "IndependentSearchMarketAnalysisService",
        FakeService,
    )
    response = client.post(
        "/portfolio/market-analysis",
        json={"requested_model": "deepseek/deepseek-v4-flash"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "deepseek"


def test_kimi_market_analysis_reports_zero_balance_without_gemini_copy(
    tmp_path, monkeypatch
) -> None:
    client = client_for_tmp_db(
        tmp_path,
        enable_cloud_services=True,
        kimi_api_key="test-kimi-key",
        exa_api_key="test-exa",
    )
    client.post(
        "/portfolio/upload-file",
        files={
            "file": (
                "holdings.csv",
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,account\n"
                    "VTI,Vanguard Total Market,Equity,10,100,1000,900,IRA"
                ).encode(),
                "text/csv",
            )
        },
    )

    class FakeService:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def analyze(
            self,
            prompt: str,
            *,
            search_query: str,
            evidence_gate_query: str,
        ):
            del prompt, search_query, evidence_gate_query
            raise portfolio_api.MarketAnalysisError(
                "provider_balance_exhausted",
                "Kimi request rejected.",
            )

    monkeypatch.setattr(
        portfolio_api,
        "IndependentSearchMarketAnalysisService",
        FakeService,
    )
    response = client.post(
        "/portfolio/market-analysis",
        json={"requested_model": "moonshot/kimi-k2.6"},
    )

    assert response.status_code == 429
    message = response.json()["detail"]["message"]
    assert "no available cash or voucher balance" in message
    assert "Gemini" not in message

    dashboard = client.get("/runs").json()
    failed_run = dashboard["recent_runs"][0]
    assert failed_run["role"] == "portfolio_market_analysis"
    assert failed_run["status"] == "failed"
    detail = client.get(f"/runs/{failed_run['id']}").json()
    assert detail["decision_trace"]["failure_code"] == "provider_balance_exhausted"
    assert detail["decision_trace"]["candidate_outcomes"] == []


def test_portfolio_upload_stores_and_returns_as_of_date(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/portfolio/upload-file",
        data={"as_of_date": "2026-07-10"},
        files={
            "file": (
                "holdings.csv",
                "\n".join(
                    [
                        "symbol,name,asset_class,quantity,price,market_value,cost_basis,account",
                        "VOO,Vanguard S&P 500 ETF,Equity,5,600,3000,2500,IRA",
                    ]
                ).encode(),
                "text/csv",
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["as_of_date"] == "2026-07-10"
    assert payload["as_of_date_source"] == "upload_form"
    assert payload["summary"]["as_of_date"] == "2026-07-10"
    assert payload["summary"]["positions"][0]["as_of_date"] == "2026-07-10"


def test_portfolio_upload_rejects_conflicting_dates(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/portfolio/upload-file",
        data={"as_of_date": "2026-07-10"},
        files={
            "file": (
                "holdings.csv",
                "\n".join(
                    [
                        (
                            "symbol,name,asset_class,quantity,price,market_value,"
                            "cost_basis,account,as_of_date"
                        ),
                        "VOO,Vanguard S&P 500 ETF,Equity,5,600,3000,2500,IRA,2026-07-11",
                    ]
                ).encode(),
                "text/csv",
            )
        },
    )

    assert response.status_code == 422
    assert "does not match" in response.json()["detail"]


def test_profile_requires_targets_to_sum_to_one(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/profile",
        json={
            "risk_tolerance": "moderate",
            "target_allocation": {"Equity": 0.6, "Bond": 0.2},
        },
    )

    assert response.status_code == 422
    assert "add up to 100%" in response.text


def test_profile_keeps_cash_outside_investment_targets(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/profile",
        json={
            "risk_tolerance": "moderate",
            "target_allocation": {"Equity": 0.9, "Cash": 0.1},
        },
    )

    assert response.status_code == 422
    assert "Cash is planned through cash goals" in response.text


def test_profile_guidance_applies_inputs_without_saving_profile(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/profile/guidance",
        json={
            "risk_tolerance": "moderate",
            "life_stage": "Student",
            "investment_horizon": "10+ years",
            "income_stability": "Low",
            "liquidity_needs": "High",
            "preferred_style": "Broad index / passive",
            "monthly_net_income": 0,
            "monthly_contribution": 300,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert sum(payload["target_allocation"].values()) == pytest.approx(1.0)
    assert payload["target_allocation"]["Alternatives"] == 0
    assert payload["method"] == "deterministic_profile_guidance_v1"
    assert "Argus applies its own" in payload["method_summary"]
    assert any(
        reference["institution"] == "FINRA" for reference in payload["references"]
    )
    assert client.get("/profile").status_code == 404


def test_profile_persists_income_and_cash_goals(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/profile",
        json={
            "risk_tolerance": "moderate",
            "investing_experience": "3-7 years",
            "target_allocation": {"Equity": 0.6, "Bond": 0.4},
            "monthly_net_income": 4200.50,
            "monthly_contribution": 500,
            "monthly_sector_satellite_budget": 100,
            "monthly_total_expenses": 3000,
            "primary_financial_priority": "family flexibility",
            "current_age": 35,
            "planned_retirement_age": 65,
            "retirement_planning_age": 100,
            "retirement_monthly_spending": 5000,
            "retirement_monthly_income": 2000,
            "retirement_current_savings": 25000,
            "retirement_income_taxable": True,
            "retirement_inflation_rate": 0.025,
            "retirement_current_tax_rate": 0.22,
            "retirement_tax_rate": 0.15,
            "retirement_annual_return": 0.05,
            "retirement_account_type": "traditional_401k",
            "retirement_adjust_contributions_for_inflation": True,
            "monthly_essential_expenses": 2500,
            "current_cash_savings": 6000,
            "emergency_fund_months": 6,
            "emergency_fund_build_months": 12,
            "education_plan": "private",
            "education_target_year": 2035,
            "education_target_amount": 50000,
            "cash_goals": [
                {
                    "goal_type": "medical_care",
                    "target_amount": 1200,
                    "months_until_needed": 6,
                    "priority": "urgent",
                },
                {
                    "goal_type": "travel",
                    "target_amount": 2400,
                    "months_until_needed": 12,
                    "priority": "flexible",
                },
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["monthly_net_income"] == 4200.50
    saved = client.get("/profile").json()
    assert saved["monthly_net_income"] == 4200.50
    assert saved["investing_experience"] == "3-7 years"
    assert saved["education_plan"] == "private"
    assert saved["planned_retirement_age"] == 65
    assert saved["calculated_retirement_cash_target"] is None
    assert saved["retirement_planning_age"] == 100
    assert saved["retirement_monthly_spending"] == 5000
    assert saved["retirement_monthly_income"] == 2000
    assert saved["retirement_current_savings"] == 25000
    assert saved["retirement_income_taxable"] is True
    assert saved["retirement_inflation_rate"] == 0.025
    assert saved["retirement_current_tax_rate"] == 0.22
    assert saved["retirement_tax_rate"] == 0.15
    assert saved["retirement_annual_return"] == 0.05
    assert saved["retirement_account_type"] == "traditional_401k"
    assert saved["retirement_adjust_contributions_for_inflation"] is True
    assert saved["monthly_sector_satellite_budget"] == 100
    assert saved["primary_financial_priority"] == "family flexibility"
    assert [goal["goal_type"] for goal in saved["cash_goals"]] == [
        "medical_care",
        "travel",
    ]

    holdings_response = client.post(
        "/portfolio/upload-file",
        data={"as_of_date": "2026-07-15"},
        files={
            "file": (
                "holdings.csv",
                (
                    "symbol,name,asset_class,quantity,price,market_value,cost_basis,account\n"
                    "VTI,Vanguard Total Market,Equity,10,100,1000,900,IRA"
                ).encode(),
                "text/csv",
            )
        },
    )
    cash_plan = holdings_response.json()["summary"]["cash_plan"]
    assert cash_plan["status"] == "ready"
    assert {goal["code"] for goal in cash_plan["goals"]} == {
        "emergency_fund",
        "planned_medical_care",
        "planned_travel",
        "education",
    }
    assert cash_plan["feasibility_status"] == "shortfall"
    assert cash_plan["primary_financial_priority"] == "family flexibility"
    assert cash_plan["monthly_shortfall"] > 0
    retirement_plan = holdings_response.json()["summary"]["retirement_plan"]
    assert retirement_plan["monthly_reliable_income_after_tax"] == 1700
    assert retirement_plan["monthly_spending_gap"] == 3300
    assert retirement_plan["years_to_retirement"] == 30
    assert retirement_plan["target_assets_at_retirement"] > 0
    assert retirement_plan["current_retirement_savings"] == 25000
    assert retirement_plan["account_type"] == "traditional_401k"
    assert (
        sum(
            item["monthly_amount"]
            for item in holdings_response.json()["summary"]["dca_suggestions"]
        )
        == 400
    )


def test_profile_rejects_sector_budget_above_total_monthly_investment(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    response = client.post(
        "/profile",
        json={
            "risk_tolerance": "moderate",
            "target_allocation": {"Equity": 1.0},
            "monthly_contribution": 100,
            "monthly_sector_satellite_budget": 150,
        },
    )

    assert response.status_code == 422
    assert "satellite budget cannot exceed" in response.text


def test_profile_persists_mixed_retirement_account_share(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    missing_share = client.post(
        "/profile",
        json={
            "risk_tolerance": "moderate",
            "target_allocation": {"Equity": 1.0},
            "retirement_account_type": "mixed",
        },
    )
    assert missing_share.status_code == 422

    response = client.post(
        "/profile",
        json={
            "risk_tolerance": "moderate",
            "target_allocation": {"Equity": 1.0},
            "retirement_account_type": "mixed",
            "retirement_taxable_withdrawal_share": 0.65,
        },
    )

    assert response.status_code == 201
    assert response.json()["retirement_account_type"] == "mixed"
    assert response.json()["retirement_taxable_withdrawal_share"] == 0.65


def test_portfolio_browser_upload_rejects_unsupported_file(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/portfolio/upload-file",
        files={"file": ("holdings.pdf", b"not a spreadsheet", "application/pdf")},
    )

    assert response.status_code == 422
    assert "must use one of" in response.json()["detail"]


def test_portfolio_browser_upload_rejects_corrupt_xlsx(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/portfolio/upload-file",
        files={
            "file": (
                "holdings.xlsx",
                b"not an Excel workbook",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 422
    assert "could not be read" in response.json()["detail"]


def test_portfolio_browser_upload_enforces_size_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(portfolio_api, "MAX_PORTFOLIO_UPLOAD_BYTES", 4)
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/portfolio/upload-file",
        files={"file": ("holdings.csv", b"12345", "text/csv")},
    )

    assert response.status_code == 413
    assert "10 MB upload limit" in response.json()["detail"]


def test_get_profile_returns_404_before_profile_is_saved(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.get("/profile")

    assert response.status_code == 404


def test_clear_profile_deactivates_saved_profile_and_is_idempotent(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    saved_response = client.post(
        "/profile",
        json={
            "risk_tolerance": "aggressive",
            "investment_horizon": "10+ years",
            "target_allocation": {"Equity": 0.8, "Bond": 0.2},
        },
    )

    first_clear_response = client.delete("/profile")
    missing_response = client.get("/profile")
    second_clear_response = client.delete("/profile")

    assert saved_response.status_code == 201
    assert first_clear_response.status_code == 204
    assert missing_response.status_code == 404
    assert second_clear_response.status_code == 204

    with client.app.state.session_factory() as session:
        profiles = session.query(UserProfile).all()

    assert len(profiles) == 1
    assert profiles[0].is_active is False


def client_for_tmp_db(
    tmp_path,
    *,
    enable_cloud_services: bool = False,
    gemini_api_key: str | None = None,
    deepseek_api_key: str | None = None,
    kimi_api_key: str | None = None,
    exa_api_key: str | None = None,
    enable_external_market_data: bool = False,
    enable_robinhood: bool = False,
    enable_market_heatmap: bool = False,
    enable_unified_etf_universe: bool = False,
) -> TestClient:
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'portfolio_api.db'}",
        enable_cloud_services=enable_cloud_services,
        enable_gmail=False,
        enable_robinhood=enable_robinhood,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        enable_external_market_data=enable_external_market_data,
        enable_market_heatmap=enable_market_heatmap,
        enable_unified_etf_universe=enable_unified_etf_universe,
        gemini_api_key=gemini_api_key,
        deepseek_api_key=deepseek_api_key,
        kimi_api_key=kimi_api_key,
        exa_api_key=exa_api_key,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)
