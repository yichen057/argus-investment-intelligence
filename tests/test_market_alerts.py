from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from investment_agent.app import create_app
from investment_agent.config import Settings
from investment_agent.market_data.volume import DailyVolume
from investment_agent.portfolio.alerts import evaluate_market_alerts
from investment_agent.storage import Base, PortfolioPosition


def _history(symbol: str, closes: list[float]) -> tuple[DailyVolume, ...]:
    start = date(2026, 1, 1)
    return tuple(
        DailyVolume(
            symbol=symbol,
            session_date=start + timedelta(days=index),
            volume=1_000_000 + (index % 5) * 50_000,
            close_price=close,
        )
        for index, close in enumerate(closes)
    )


def test_buy_review_requires_portfolio_relevance_and_multiple_market_signals() -> None:
    closes = [100.0] * 40 + [110.0] * 18 + [95.0, 101.0]
    position = SimpleNamespace(
        symbol="VXUS",
        asset_class="International Equity",
        quantity=10,
        market_value=1_000,
        as_of_date=date(2026, 3, 1),
    )
    core = SimpleNamespace(
        symbol="VTI",
        asset_class="US Equity",
        quantity=10,
        market_value=9_000,
        as_of_date=date(2026, 3, 1),
    )

    decisions = evaluate_market_alerts(
        [position, core],
        {"VXUS": _history("VXUS", closes), "VTI": _history("VTI", [100.0] * 60)},
        target_allocation={"International Equity": 0.25, "US Equity": 0.75},
        rebalance_threshold=0.05,
        sensitivity="standard",
    )

    buy = next(item for item in decisions if item.symbol == "VXUS" and item.direction == "buy")
    assert buy.score >= 4
    assert any("saved target" in reason for reason in buy.reasons)
    assert buy.metrics["fundamental_event_check"] == "unavailable_in_preview_v1"
    assert "placed no order" in buy.warnings[-1]


def test_reduce_review_uses_concentration_and_deteriorating_trend() -> None:
    closes = [120.0] * 38 + [120.0 - index for index in range(22)]
    concentrated = SimpleNamespace(
        symbol="AAPL",
        asset_class="US Equity",
        quantity=100,
        market_value=8_000,
        as_of_date=date(2026, 3, 1),
    )
    diversifier = SimpleNamespace(
        symbol="BND",
        asset_class="Bond",
        quantity=20,
        market_value=2_000,
        as_of_date=date(2026, 3, 1),
    )

    decisions = evaluate_market_alerts(
        [concentrated, diversifier],
        {"AAPL": _history("AAPL", closes), "BND": _history("BND", [50.0] * 60)},
        target_allocation={"US Equity": 0.60, "Bond": 0.40},
        rebalance_threshold=0.05,
        sensitivity="standard",
    )

    reduce = next(
        item for item in decisions if item.symbol == "AAPL" and item.direction == "reduce"
    )
    assert reduce.score >= 4
    assert any("scoped portfolio" in reason for reason in reduce.reasons)


def test_insufficient_history_fails_closed() -> None:
    position = SimpleNamespace(
        symbol="AAPL",
        asset_class="US Equity",
        quantity=10,
        market_value=1_000,
        as_of_date=date(2026, 3, 1),
    )
    assert (
        evaluate_market_alerts(
            [position],
            {"AAPL": _history("AAPL", [100.0] * 30)},
            target_allocation={"US Equity": 1.0},
            rebalance_threshold=0.05,
            sensitivity="active",
        )
        == ()
    )


def test_stale_history_fails_closed() -> None:
    position = SimpleNamespace(
        symbol="AAPL",
        asset_class="US Equity",
        quantity=10,
        market_value=1_000,
        as_of_date=date(2026, 4, 1),
    )
    assert (
        evaluate_market_alerts(
            [position],
            {"AAPL": _history("AAPL", [120.0] * 40 + [100.0] * 20)},
            target_allocation={"US Equity": 0.5},
            rebalance_threshold=0.05,
            sensitivity="active",
        )
        == ()
    )


def test_alert_api_is_preview_only_and_feedback_is_auditable(tmp_path) -> None:
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'alerts.db'}",
        enable_cloud_services=False,
        enable_gmail=False,
        enable_robinhood=True,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
        enable_external_market_data=True,
        robinhood_enable_historicals=True,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)

    class Gateway:
        def read_historicals(self, symbols, **_kwargs):
            closes = [100.0] * 40 + [110.0] * 18 + [95.0, 101.0]
            return {
                "results": [
                    {
                        "symbol": symbol,
                        "bars": [
                            {
                                "begins_at": (
                                    date.today() - timedelta(days=61 - index)
                                ).isoformat(),
                                "volume": 8_000_000 if index == len(closes) - 1 else 1_000_000 + index * 1_000,
                                "close_price": close,
                                "interpolated": False,
                            }
                            for index, close in enumerate(closes)
                        ],
                    }
                    for symbol in symbols
                ]
            }

    app.state.robinhood_gateway = Gateway()
    with app.state.session_factory() as session:
        session.add_all(
            [
                PortfolioPosition(
                    source_key="robinhood",
                    source_scope="investments",
                    symbol="VXUS",
                    name="VXUS",
                    asset_class="International Equity",
                    quantity=10,
                    price=100,
                    market_value=1_000,
                    cost_basis=900,
                    account=None,
                    import_id="test",
                    as_of_date=date.today(),
                ),
                PortfolioPosition(
                    source_key="robinhood",
                    source_scope="investments",
                    symbol="VTI",
                    name="VTI",
                    asset_class="US Equity",
                    quantity=10,
                    price=900,
                    market_value=9_000,
                    cost_basis=8_000,
                    account=None,
                    import_id="test",
                    as_of_date=date.today(),
                ),
            ]
        )
        session.commit()
    client = TestClient(app)
    client.post(
        "/profile",
        json={
            "risk_tolerance": "moderate",
            "target_allocation": {
                "International Equity": 0.30,
                "US Equity": 0.70,
            },
        },
    )
    saved = client.put(
        "/portfolio/alerts/settings",
        json={
            "enabled": True,
            "delivery_mode": "preview_only",
            "scope": "holdings",
            "sensitivity": "active",
            "timezone": "America/Los_Angeles",
            "quiet_hours_start": "21:00",
            "quiet_hours_end": "07:00",
        },
    )
    evaluated = client.post("/portfolio/alerts/evaluate")

    assert saved.status_code == 200
    assert saved.json()["telegram_available"] is False
    assert evaluated.status_code == 200
    assert evaluated.json()["created_count"] >= 1
    preview = evaluated.json()["alerts"][0]
    feedback = client.post(
        f"/portfolio/alerts/{preview['id']}/feedback",
        json={"feedback": "incorrect"},
    )
    assert feedback.status_code == 200
    assert feedback.json()["status"] == "rule_review"
    assert "not changed automatically" in feedback.json()["feedback_action"]
    assert "suppressed for 7 days" in feedback.json()["feedback_action"]
