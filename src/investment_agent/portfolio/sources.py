from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol

from investment_agent.integrations.robinhood import (
    ProviderError,
    ProviderErrorCode,
    RobinhoodReadOnlyGateway,
)
from investment_agent.market_data.robinhood import RobinhoodMarketDataSource
from investment_agent.portfolio.csv_parser import (
    HoldingRow,
    parse_holdings_bytes,
    parse_holdings_csv,
)


@dataclass(frozen=True)
class PortfolioSourceSnapshot:
    source_key: str
    source_name: str
    source_scope: str
    observed_at: datetime
    positions: tuple[HoldingRow, ...]
    is_live: bool


class PortfolioSource(Protocol):
    source_key: str
    source_name: str

    def load(self) -> PortfolioSourceSnapshot:
        ...


class FileUploadSource:
    source_key = "file_upload"
    source_name = "Uploaded portfolio file"

    def __init__(
        self,
        *,
        filename: str | None = None,
        raw_content: bytes | None = None,
        path: Path | None = None,
    ) -> None:
        self._filename = filename
        self._raw_content = raw_content
        self._path = path

    def load(self) -> PortfolioSourceSnapshot:
        if self._path is not None:
            positions = parse_holdings_csv(self._path)
        elif self._filename is not None and self._raw_content is not None:
            positions = parse_holdings_bytes(
                filename=self._filename,
                raw_content=self._raw_content,
            )
        else:
            raise ValueError("FileUploadSource requires a path or uploaded bytes.")
        return PortfolioSourceSnapshot(
            source_key=self.source_key,
            source_name=self.source_name,
            source_scope="manual",
            observed_at=datetime.now(timezone.utc),
            positions=tuple(positions),
            is_live=False,
        )


class RobinhoodMcpSource:
    source_key = "robinhood_mcp"
    source_name = "Robinhood Trading MCP"

    def __init__(self, gateway: RobinhoodReadOnlyGateway) -> None:
        self._gateway = gateway

    def load(self) -> PortfolioSourceSnapshot:
        payload = self._gateway.read_positions()
        observed_at = datetime.now(timezone.utc)
        records = _position_records(payload)
        quote_by_symbol = {}
        missing_price_symbols = sorted(
            {
                str(record.get("symbol") or record.get("ticker") or "")
                .strip()
                .upper()
                for record in records
                if not _record_has_price(record)
                and str(record.get("symbol") or record.get("ticker") or "").strip()
            }
        )
        if missing_price_symbols and hasattr(self._gateway, "read_quotes"):
            quote_batch = RobinhoodMarketDataSource(self._gateway).fetch_quotes(
                missing_price_symbols
            )
            quote_by_symbol = {
                quote.symbol: quote
                for quote in quote_batch.quotes
                if quote.symbol and quote.last_price is not None
            }
        normalized = tuple(
            _normalize_position(
                record,
                live_price=(
                    quote_by_symbol.get(
                        str(record.get("symbol") or record.get("ticker") or "")
                        .strip()
                        .upper()
                    ).last_price
                    if quote_by_symbol.get(
                        str(record.get("symbol") or record.get("ticker") or "")
                        .strip()
                        .upper()
                    )
                    else None
                ),
                observed_at=observed_at,
            )
            for record in records
        )
        if any(row is None for row in normalized):
            raise ProviderError(
                ProviderErrorCode.PARTIAL_RESPONSE,
                (
                    "Robinhood returned one or more incomplete position records. "
                    "Argus kept the previous snapshot instead of partially replacing it."
                ),
            )
        rows = tuple(row for row in normalized if row is not None)
        return PortfolioSourceSnapshot(
            source_key=self.source_key,
            source_name=self.source_name,
            source_scope="investments",
            observed_at=observed_at,
            positions=rows,
            is_live=True,
        )


def _position_records(payload: object) -> list[Mapping[str, object]]:
    if isinstance(payload, list):
        return [record for record in payload if isinstance(record, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("positions", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [record for record in value if isinstance(record, Mapping)]
        if isinstance(value, Mapping):
            nested = _position_records(value)
            if nested:
                return nested
    return []


def _record_has_price(record: Mapping[str, object]) -> bool:
    return any(
        record.get(key) not in (None, "")
        for key in ("price", "last_price", "current_price", "mark_price", "market_value")
    )


def _normalize_position(
    record: Mapping[str, object],
    *,
    live_price: float | None = None,
    observed_at: datetime | None = None,
) -> HoldingRow | None:
    symbol = str(record.get("symbol") or record.get("ticker") or "").strip().upper()
    quantity = _optional_float(record.get("quantity") or record.get("shares"))
    price = _optional_float(
        record.get("price")
        or record.get("last_price")
        or record.get("current_price")
        or record.get("mark_price")
    ) or live_price
    market_value = _optional_float(record.get("market_value") or record.get("value"))
    if not symbol or quantity is None:
        return None
    if price is None and market_value is not None and quantity != 0:
        price = market_value / quantity
    if market_value is None and price is not None:
        market_value = quantity * price
    if price is None or market_value is None:
        return None

    cost_basis = _optional_float(record.get("cost_basis"))
    average_cost = _optional_float(
        record.get("average_cost") or record.get("average_buy_price")
    )
    if cost_basis is None and average_cost is not None:
        cost_basis = average_cost * quantity
    account_label = str(
        record.get("account_type") or record.get("account_label") or "Robinhood"
    ).strip()
    observed_date = _optional_date(
        record.get("as_of_date")
        or record.get("updated_at")
        or record.get("timestamp")
    ) or (observed_at.date() if observed_at else date.today())
    return HoldingRow(
        symbol=symbol,
        name=str(record.get("name") or record.get("instrument_name") or symbol).strip(),
        # Robinhood's position ``type`` describes the position direction (for
        # example ``long``), not an allocation asset class.  Treat the
        # equity-positions endpoint as Equity unless the provider supplies a
        # dedicated asset_class field.  Symbol-level portfolio rules can then
        # identify controlled exceptions such as GLD or VXUS.
        asset_class=str(record.get("asset_class") or "Equity").strip(),
        quantity=quantity,
        price=price,
        market_value=market_value,
        cost_basis=cost_basis,
        account=account_label or "Robinhood",
        as_of_date=observed_date,
    )


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None
