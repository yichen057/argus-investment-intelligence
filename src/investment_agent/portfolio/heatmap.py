from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

from investment_agent.market_data import MarketDataBatch
from investment_agent.portfolio.summary import InvestmentCandidate


@dataclass(frozen=True)
class HeatmapTile:
    symbol: str
    name: str
    group: str
    exposure_key: str
    latest_price: float | None
    previous_close: float | None
    previous_close_date: date | None
    percent_change: float | None
    volume: float | None
    dollar_volume: float | None
    volume_z_score: float | None
    volume_activity: str
    volume_observation_date: date | None
    volume_reference_start: date | None
    volume_reference_end: date | None
    volume_reference_sessions: int
    volume_observation_value: float | None
    volume_reference_median: float | None
    volume_reference_log_mad: float | None
    volume_method: str
    volume_quality: str
    quote_observed_at: datetime | None
    quote_status: str
    directly_held: bool
    related_holdings: tuple[str, ...]


@dataclass(frozen=True)
class HeatmapSnapshot:
    provider_code: str
    provider_key: str
    provider_name: str
    configured_provider_code: str
    configured_provider_key: str
    configured_provider_name: str
    external_data_enabled: bool
    is_live: bool
    is_delayed: bool
    status: str
    message: str
    generated_at: datetime
    tiles: tuple[HeatmapTile, ...]


def build_heatmap_snapshot(
    *,
    candidates: Sequence[InvestmentCandidate],
    positions: Sequence[object],
    market_data: MarketDataBatch,
    configured_provider_code: str,
    configured_provider_key: str,
    configured_provider_name: str,
    external_data_enabled: bool,
) -> HeatmapSnapshot:
    """Join the controlled ETF universe, holdings, and provider-neutral quotes."""

    held_symbols = {
        str(getattr(position, "symbol", "")).strip().upper()
        for position in positions
    }
    quotes = {quote.symbol.upper(): quote for quote in market_data.quotes}
    tiles = []
    for candidate in candidates:
        quote = quotes.get(candidate.symbol.upper())
        tiles.append(
            HeatmapTile(
                symbol=candidate.symbol,
                name=candidate.name,
                group=_heatmap_group(candidate.exposure_key),
                exposure_key=candidate.exposure_key,
                latest_price=quote.last_price if quote else None,
                previous_close=quote.previous_close if quote else None,
                previous_close_date=quote.previous_close_date if quote else None,
                percent_change=quote.percent_change if quote else None,
                volume=quote.volume if quote else None,
                dollar_volume=quote.dollar_volume if quote else None,
                volume_z_score=quote.volume_z_score if quote else None,
                volume_activity=(
                    quote.volume_activity if quote else "Not enough history"
                ),
                volume_observation_date=(
                    quote.volume_observation_date if quote else None
                ),
                volume_reference_start=(
                    quote.volume_reference_start if quote else None
                ),
                volume_reference_end=quote.volume_reference_end if quote else None,
                volume_reference_sessions=(
                    quote.volume_reference_sessions if quote else 0
                ),
                volume_observation_value=(
                    quote.volume_observation_value if quote else None
                ),
                volume_reference_median=(
                    quote.volume_reference_median if quote else None
                ),
                volume_reference_log_mad=(
                    quote.volume_reference_log_mad if quote else None
                ),
                volume_method=quote.volume_method if quote else "robust_log_mad_v1",
                volume_quality=quote.volume_quality if quote else "not_available",
                quote_observed_at=quote.observed_at if quote else None,
                quote_status=quote.status if quote else "unavailable",
                directly_held=candidate.symbol.upper() in held_symbols,
                related_holdings=candidate.related_holdings,
            )
        )
    return HeatmapSnapshot(
        provider_code=market_data.provider_code,
        provider_key=market_data.provider_key,
        provider_name=market_data.provider_name,
        configured_provider_code=configured_provider_code,
        configured_provider_key=configured_provider_key,
        configured_provider_name=configured_provider_name,
        external_data_enabled=external_data_enabled,
        is_live=market_data.is_live,
        is_delayed=market_data.is_delayed,
        status=market_data.status,
        message=market_data.message,
        generated_at=market_data.generated_at,
        tiles=tuple(tiles),
    )


def _heatmap_group(exposure_key: str) -> str:
    key = exposure_key.lower()
    if any(term in key for term in ("technology", "semiconductor", "software")):
        return "Technology & AI"
    if any(term in key for term in ("energy", "oil & gas")):
        return "Energy"
    if any(term in key for term in ("financial", "bank", "insurance", "capital market")):
        return "Financials"
    if any(term in key for term in ("consumer", "retail", "homebuilder")):
        return "Consumer"
    if any(term in key for term in ("health care", "biotech", "pharmaceutical")):
        return "Health Care"
    if any(term in key for term in ("industrial", "aerospace", "transportation")):
        return "Industrials"
    if any(term in key for term in ("material", "metals & mining")):
        return "Materials"
    if "real estate" in key:
        return "Real Estate"
    if "utilities" in key:
        return "Utilities"
    if any(term in key for term in ("communication", "telecom")):
        return "Communication Services"
    return "Other"
