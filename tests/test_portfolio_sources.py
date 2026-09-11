import pytest

from investment_agent.integrations.robinhood import (
    ProviderError,
    ProviderErrorCode,
)
from investment_agent.portfolio import RobinhoodMcpSource


class FakeRobinhoodPortfolioClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def read_positions(self) -> object:
        self.calls.append("read_positions")
        return {
            "positions": [
                {
                    "symbol": "AAPL",
                    "name": "Apple",
                    "quantity": "2",
                    "last_price": "200",
                    "average_cost": "150",
                    "account_type": "Roth IRA",
                    "updated_at": "2026-07-21T15:00:00Z",
                }
            ]
        }


def test_robinhood_portfolio_source_normalizes_read_only_positions() -> None:
    client = FakeRobinhoodPortfolioClient()

    snapshot = RobinhoodMcpSource(client).load()

    assert client.calls == ["read_positions"]
    assert snapshot.source_key == "robinhood_mcp"
    assert snapshot.source_scope == "investments"
    assert snapshot.is_live
    assert len(snapshot.positions) == 1
    assert snapshot.positions[0].market_value == 400
    assert snapshot.positions[0].cost_basis == 300
    assert snapshot.positions[0].account == "Roth IRA"


def test_robinhood_partial_response_is_rejected_before_storage() -> None:
    class PartialClient:
        def read_positions(self) -> object:
            return {
                "positions": [
                    {"symbol": "AAPL", "quantity": "2", "last_price": "200"},
                    {"symbol": "MSFT", "quantity": "1"},
                ]
            }

    with pytest.raises(ProviderError) as exc_info:
        RobinhoodMcpSource(PartialClient()).load()

    assert exc_info.value.code == ProviderErrorCode.PARTIAL_RESPONSE


def test_robinhood_nested_positions_use_live_quotes_instead_of_average_cost() -> None:
    class LiveShapeClient:
        def read_positions(self) -> object:
            return {
                "data": {
                    "positions": [
                        {
                            "symbol": "AAPL",
                            "quantity": "2",
                            "average_buy_price": "150",
                            "type": "long",
                        }
                    ]
                }
            }

        def read_quotes(self, symbols) -> object:
            return {
                "data": {
                    "results": [
                        {
                            "quote": {
                                "symbol": symbols[0],
                                "last_trade_price": "200",
                                "previous_close": "198",
                            }
                        }
                    ]
                }
            }

    snapshot = RobinhoodMcpSource(LiveShapeClient()).load()

    assert snapshot.positions[0].price == 200
    assert snapshot.positions[0].market_value == 400
    assert snapshot.positions[0].cost_basis == 300
    assert snapshot.positions[0].asset_class == "Equity"
