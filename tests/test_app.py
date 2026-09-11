from fastapi.testclient import TestClient

from investment_agent.app import create_app


def test_health_endpoint_returns_service_status(monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_ENV", "test")

    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "argus-api",
        "version": "0.1.0",
        "mode": "test",
        "etf_selection_engine": "deterministic",
        "external_market_data_enabled": False,
        "market_heatmap_enabled": False,
        "unified_etf_universe_enabled": False,
        "robinhood_enabled": False,
        "robinhood_sidecar_configured": False,
        "market_data_provider_code": "01",
        "market_data_provider": "Robinhood Market Data",
    }
