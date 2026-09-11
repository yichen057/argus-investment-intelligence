from datetime import date, timedelta

import pytest

from investment_agent.market_data import (
    RobinhoodMarketDataSource,
    UploadedSnapshotMarketDataSource,
    normalize_market_data_provider,
)
from investment_agent.market_data.volume import (
    DailyVolume,
    calculate_volume_activity,
    extract_daily_volumes,
)
from investment_agent.cloud.cache import InMemoryCacheStore
from investment_agent.portfolio import HoldingRow


class FakeRobinhoodClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def read_quotes(self, symbols) -> object:
        self.calls.append(("read_quotes", {"symbols": list(symbols)}))
        return {
            "quotes": [
                {
                    "symbol": symbol,
                    "last_price": "110",
                    "previous_close": "100",
                    "volume": "2500",
                    "updated_at": "2026-07-21T15:00:00Z",
                }
                for symbol in symbols
            ]
        }


def test_market_data_provider_codes_normalize_to_semantic_keys() -> None:
    assert normalize_market_data_provider("01") == (
        "01",
        "robinhood",
        "Robinhood Market Data",
    )
    assert normalize_market_data_provider("TwelveData") == (
        "02",
        "twelve_data",
        "Twelve Data",
    )


def test_uploaded_snapshot_is_explicitly_not_live() -> None:
    position = HoldingRow(
        symbol="XLF",
        name="Financial Select Sector SPDR Fund",
        asset_class="ETF",
        quantity=2,
        price=50,
        market_value=100,
        cost_basis=None,
        account="Brokerage",
        as_of_date=date(2026, 7, 20),
    )

    batch = UploadedSnapshotMarketDataSource([position]).fetch_quotes(["XLF", "XLK"])

    assert batch.status == "not_live"
    assert not batch.is_live
    assert batch.quotes[0].last_price == 50
    assert batch.quotes[0].percent_change is None
    assert batch.quotes[1].status == "unavailable"


def test_robinhood_market_source_batches_read_only_quote_calls() -> None:
    client = FakeRobinhoodClient()
    source = RobinhoodMarketDataSource(client)
    symbols = [f"S{index:02d}" for index in range(21)]

    batch = source.fetch_quotes(symbols)

    assert len(client.calls) == 2
    assert {name for name, _ in client.calls} == {"read_quotes"}
    assert len(batch.quotes) == 21
    assert batch.quotes[0].percent_change == pytest.approx(10)
    assert batch.quotes[0].dollar_volume == 275_000


def test_robinhood_market_source_normalizes_live_nested_response() -> None:
    class NestedClient:
        def read_quotes(self, symbols) -> object:
            return {
                "data": {
                    "results": [
                        {
                            "quote": {
                                "symbol": symbols[0],
                                "last_trade_price": "123.45",
                                "previous_close": "120",
                                "venue_last_trade_time": "2026-07-21T15:00:00Z",
                            },
                            "close": {
                                "symbol": symbols[0],
                                "price": "120",
                                "date": "2026-07-20",
                            },
                        }
                    ]
                }
            }

    batch = RobinhoodMarketDataSource(NestedClient()).fetch_quotes(["AAPL"])

    assert batch.quotes[0].symbol == "AAPL"
    assert batch.quotes[0].last_price == pytest.approx(123.45)
    assert batch.quotes[0].previous_close == pytest.approx(120)
    assert batch.quotes[0].status == "live"


def test_robust_volume_activity_uses_completed_session_and_prior_reference() -> None:
    start = date(2026, 4, 1)
    observations = [
        DailyVolume(
            symbol="XLK",
            session_date=start + timedelta(days=index),
            volume=1_000_000 + (index % 7) * 75_000,
        )
        for index in range(60)
    ]
    observations.append(
        DailyVolume(
            symbol="XLK",
            session_date=start + timedelta(days=60),
            volume=4_000_000,
        )
    )

    activity = calculate_volume_activity(observations)

    assert activity.quality == "supported"
    assert activity.reference_sessions == 60
    assert activity.observation_date == start + timedelta(days=60)
    assert activity.observation_volume == 4_000_000
    assert activity.reference_median_volume is not None
    assert activity.reference_log_mad is not None
    assert activity.z_score is not None
    assert activity.z_score > 2
    assert activity.label in {"High", "Unusual"}


def test_historical_projector_rejects_current_and_interpolated_bars() -> None:
    payload = {
        "data": {
            "results": [
                {
                    "symbol": "XLK",
                    "bars": [
                    {
                        "begins_at": "2026-07-18T00:00:00Z",
                        "volume": "1000",
                        "close_price": "101.25",
                        "interpolated": False,
                    },
                    {
                        "begins_at": "2026-07-19T00:00:00Z",
                        "volume": "2000",
                        "interpolated": True,
                    },
                    {
                        "begins_at": "2026-07-21T00:00:00Z",
                        "volume": "3000",
                        "interpolated": False,
                    },
                    ],
                }
            ]
        },
        "guide": "Provider metadata is ignored by the bounded projector.",
    }

    projected = extract_daily_volumes(
        payload,
        requested_symbols=["XLK"],
        exclude_on_or_after=date(2026, 7, 21),
    )

    assert [(row.session_date, row.volume) for row in projected["XLK"]] == [
        (date(2026, 7, 18), 1000)
    ]
    assert projected["XLK"][0].close_price == pytest.approx(101.25)


def test_historicals_correct_post_close_session_move() -> None:
    today = date.today()

    class PostCloseClient(FakeRobinhoodClient):
        def read_quotes(self, symbols) -> object:
            return {
                "quotes": [
                    {
                        "symbol": symbols[0],
                        "last_price": "110",
                        # Providers may roll this field to the just-completed session,
                        # which would incorrectly display a 0% move after the close.
                        "previous_close": "110",
                        "previous_close_date": today.isoformat(),
                        "updated_at": f"{today.isoformat()}T20:00:00Z",
                    }
                ]
            }

        def read_historicals(
            self,
            symbols,
            *,
            start_time,
            end_time,
            interval,
            bounds,
            adjustment_type,
        ) -> object:
            return {
                "results": [
                    {
                        "symbol": symbols[0],
                        "bars": [
                            {
                                "begins_at": (today - timedelta(days=25 - index)).isoformat(),
                                "volume": 1_000_000 + index,
                                "close_price": "100",
                                "interpolated": False,
                            }
                            for index in range(25)
                        ],
                    }
                ]
            }

    source = RobinhoodMarketDataSource(
        PostCloseClient(),
        cache_store=InMemoryCacheStore(),
        enable_historicals=True,
    )

    quote = source.fetch_quotes(["XLC"]).quotes[0]

    assert quote.previous_close == pytest.approx(100)
    assert quote.previous_close_date == today - timedelta(days=1)
    assert quote.percent_change == pytest.approx(10)


def test_robinhood_historical_volume_is_bounded_and_cached() -> None:
    class HistoricalClient(FakeRobinhoodClient):
        def read_historicals(
            self,
            symbols,
            *,
            start_time,
            end_time,
            interval,
            bounds,
            adjustment_type,
        ) -> object:
            self.calls.append(
                (
                    "read_historicals",
                    {
                        "symbols": list(symbols),
                        "start_time": start_time,
                        "end_time": end_time,
                        "interval": interval,
                        "bounds": bounds,
                        "adjustment_type": adjustment_type,
                    },
                )
            )
            today = date.today()
            return {
                "results": [
                    {
                        "symbol": symbol,
                        "historicals": [
                            {
                                "begins_at": (today - timedelta(days=70 - index)).isoformat(),
                                "volume": (
                                    4_000_000
                                    if index == 69
                                    else 1_000_000 + (index % 7) * 75_000
                                ),
                                "interpolated": False,
                            }
                            for index in range(70)
                        ],
                    }
                    for symbol in symbols
                ]
            }

    client = HistoricalClient()
    source = RobinhoodMarketDataSource(
        client,
        cache_store=InMemoryCacheStore(),
        enable_historicals=True,
    )

    first = source.fetch_quotes(["XLK"])
    second = source.fetch_quotes(["XLK"])

    historical_calls = [call for call in client.calls if call[0] == "read_historicals"]
    assert len(historical_calls) == 1
    assert first.quotes[0].volume_reference_sessions == 60
    assert first.quotes[0].volume_z_score is not None
    assert second.quotes[0].volume_z_score == first.quotes[0].volume_z_score
