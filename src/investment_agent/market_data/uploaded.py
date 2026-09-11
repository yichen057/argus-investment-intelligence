from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timezone
from typing import Sequence

from investment_agent.market_data.base import MarketDataBatch, MarketQuote


class UploadedSnapshotMarketDataSource:
    """Expose uploaded holdings prices without presenting them as live market data."""

    provider_code = "upload"
    provider_key = "file_upload"
    provider_name = "Uploaded holdings snapshot"

    def __init__(self, positions: Sequence[object]) -> None:
        self._positions = positions

    def fetch_quotes(self, symbols: Sequence[str]) -> MarketDataBatch:
        requested = {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        quantities: dict[str, float] = defaultdict(float)
        market_values: dict[str, float] = defaultdict(float)
        observed_dates: dict[str, date] = {}
        prices: dict[str, float] = {}

        for position in self._positions:
            symbol = str(getattr(position, "symbol", "")).strip().upper()
            if symbol not in requested:
                continue
            quantity = float(getattr(position, "quantity", 0.0) or 0.0)
            market_value = float(getattr(position, "market_value", 0.0) or 0.0)
            price = float(getattr(position, "price", 0.0) or 0.0)
            quantities[symbol] += quantity
            market_values[symbol] += market_value
            if price > 0:
                prices[symbol] = price
            observed_date = getattr(position, "as_of_date", None)
            if isinstance(observed_date, date):
                observed_dates[symbol] = observed_date

        quotes: list[MarketQuote] = []
        for symbol in sorted(requested):
            price = prices.get(symbol)
            total_quantity = quantities.get(symbol, 0.0)
            if total_quantity > 0 and market_values.get(symbol, 0.0) > 0:
                price = market_values[symbol] / total_quantity
            observed_at = None
            observed_date = observed_dates.get(symbol)
            if observed_date is not None:
                observed_at = datetime.combine(
                    observed_date,
                    time.min,
                    tzinfo=timezone.utc,
                )
            quotes.append(
                MarketQuote(
                    symbol=symbol,
                    last_price=price,
                    previous_close=None,
                    previous_close_date=None,
                    percent_change=None,
                    volume=None,
                    dollar_volume=None,
                    volume_z_score=None,
                    observed_at=observed_at,
                    status="uploaded_snapshot" if price is not None else "unavailable",
                )
            )

        now = datetime.now(timezone.utc)
        return MarketDataBatch(
            provider_code=self.provider_code,
            provider_key=self.provider_key,
            provider_name=self.provider_name,
            is_live=False,
            is_delayed=False,
            generated_at=now,
            quotes=tuple(quotes),
            status="not_live",
            message=(
                "External market data is unavailable or disabled. Uploaded prices are "
                "shown only as a dated portfolio snapshot; daily change, turnover, and "
                "volume Z-score are not available."
            ),
        )
