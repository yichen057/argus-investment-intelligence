from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, Sequence


MARKET_DATA_PROVIDER_CODES: dict[str, str] = {
    "01": "robinhood",
    "02": "twelve_data",
    "03": "alpha_vantage",
    "04": "massive",
}
MARKET_DATA_PROVIDER_NAMES: dict[str, str] = {
    "01": "Robinhood Market Data",
    "02": "Twelve Data",
    "03": "Alpha Vantage",
    "04": "Massive",
}
_MARKET_DATA_PROVIDER_ALIASES = {
    **MARKET_DATA_PROVIDER_CODES,
    "robinhood": "robinhood",
    "twelvedata": "twelve_data",
    "twelve_data": "twelve_data",
    "alpha_vantage": "alpha_vantage",
    "alphavantage": "alpha_vantage",
    "massive": "massive",
}


def normalize_market_data_provider(value: str | None) -> tuple[str, str, str]:
    """Return stable code, semantic key, and display name for a configured provider."""

    normalized = (value or "01").strip().lower()
    provider_key = _MARKET_DATA_PROVIDER_ALIASES.get(normalized)
    if provider_key is None:
        choices = ", ".join(MARKET_DATA_PROVIDER_CODES)
        raise ValueError(
            f"Expected market-data provider code {choices}; received {normalized!r}."
        )
    provider_code = next(
        code
        for code, configured_key in MARKET_DATA_PROVIDER_CODES.items()
        if configured_key == provider_key
    )
    return (
        provider_code,
        provider_key,
        MARKET_DATA_PROVIDER_NAMES[provider_code],
    )


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    last_price: float | None
    previous_close: float | None
    previous_close_date: date | None
    percent_change: float | None
    volume: float | None
    dollar_volume: float | None
    volume_z_score: float | None
    observed_at: datetime | None
    status: str
    volume_activity: str = "Not enough history"
    volume_observation_date: date | None = None
    volume_reference_start: date | None = None
    volume_reference_end: date | None = None
    volume_reference_sessions: int = 0
    volume_observation_value: float | None = None
    volume_reference_median: float | None = None
    volume_reference_log_mad: float | None = None
    volume_method: str = "robust_log_mad_v1"
    volume_quality: str = "not_available"


@dataclass(frozen=True)
class MarketDataBatch:
    provider_code: str
    provider_key: str
    provider_name: str
    is_live: bool
    is_delayed: bool
    generated_at: datetime
    quotes: tuple[MarketQuote, ...]
    status: str
    message: str


class MarketDataSourceUnavailable(RuntimeError):
    """Raised when the selected source is not connected or cannot return data."""


class MarketDataSource(Protocol):
    provider_code: str
    provider_key: str
    provider_name: str

    def fetch_quotes(self, symbols: Sequence[str]) -> MarketDataBatch:
        ...
