from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from investment_agent.integrations.robinhood import RobinhoodReadOnlyGateway
from investment_agent.market_data.base import MarketDataBatch, MarketQuote
from investment_agent.market_data.volume import (
    DailyVolume,
    VOLUME_REFERENCE_SESSIONS,
    VolumeActivity,
    calculate_volume_activity,
    deserialize_daily_volumes,
    extract_daily_volumes,
    serialize_daily_volumes,
)


_QUOTE_BATCH_SIZE = 20
_HISTORICAL_BATCH_SIZE = 10
_HISTORICAL_CALENDAR_DAYS = 180
_HISTORICAL_CACHE_TTL_SECONDS = 6 * 60 * 60


class _JsonCache(Protocol):
    def get_json(self, key: str) -> dict[str, object] | None: ...

    def set_json(
        self,
        key: str,
        value: dict[str, object],
        *,
        ttl_seconds: int,
    ) -> None: ...


class RobinhoodMarketDataSource:
    provider_code = "01"
    provider_key = "robinhood"
    provider_name = "Robinhood Market Data"

    def __init__(
        self,
        gateway: RobinhoodReadOnlyGateway,
        *,
        cache_store: _JsonCache | None = None,
        enable_historicals: bool = False,
    ) -> None:
        self._gateway = gateway
        self._cache_store = cache_store
        self._enable_historicals = enable_historicals

    def fetch_quotes(
        self,
        symbols: Sequence[str],
        *,
        refresh_historicals: bool = False,
    ) -> MarketDataBatch:
        normalized = sorted(
            {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        )
        records: list[Mapping[str, object]] = []
        for offset in range(0, len(normalized), _QUOTE_BATCH_SIZE):
            chunk = normalized[offset : offset + _QUOTE_BATCH_SIZE]
            payload = self._gateway.read_quotes(chunk)
            records.extend(_quote_records(payload))

        quotes = tuple(_normalize_quote(record) for record in records)
        activities: dict[str, VolumeActivity] = {}
        observations_by_symbol = {}
        if self._enable_historicals:
            observations_by_symbol = self._historical_observations(
                normalized,
                refresh=refresh_historicals,
            )
            activities = {
                symbol: calculate_volume_activity(observations)
                for symbol, observations in observations_by_symbol.items()
            }
            quotes = tuple(
                _quote_with_historical_context(
                    quote,
                    observations_by_symbol.get(quote.symbol, ()),
                    activities.get(quote.symbol),
                )
                for quote in quotes
            )
        supported_activity_count = sum(
            activity.z_score is not None for activity in activities.values()
        )
        if not self._enable_historicals:
            message = (
                "Robinhood returned structured live quotes. Historical volume "
                "analysis is off, so Volume activity is not shown."
            )
        elif supported_activity_count:
            message = (
                "Robinhood returned structured live quotes and complete daily-volume "
                f"history for {supported_activity_count} symbol(s)."
            )
        else:
            message = (
                "Robinhood returned structured live quotes, but no symbol passed the "
                "historical-volume quality gate. Open a tile for the exact limitation."
            )
        return MarketDataBatch(
            provider_code=self.provider_code,
            provider_key=self.provider_key,
            provider_name=self.provider_name,
            is_live=True,
            is_delayed=False,
            generated_at=datetime.now(timezone.utc),
            quotes=quotes,
            status="live",
            message=message,
        )

    def _historical_observations(
        self,
        symbols: Sequence[str],
        *,
        refresh: bool,
    ) -> dict[str, tuple[DailyVolume, ...]]:
        observations_by_symbol = {}
        missing = []
        for symbol in symbols:
            cached = None if refresh else self._cached_daily_volumes(symbol)
            if cached:
                observations_by_symbol[symbol] = cached
            else:
                missing.append(symbol)

        now = datetime.now(timezone.utc)
        start_time = (now - timedelta(days=_HISTORICAL_CALENDAR_DAYS)).isoformat()
        end_time = now.isoformat()
        current_eastern_date = datetime.now(ZoneInfo("America/New_York")).date()
        for offset in range(0, len(missing), _HISTORICAL_BATCH_SIZE):
            chunk = missing[offset : offset + _HISTORICAL_BATCH_SIZE]
            try:
                payload = self._gateway.read_historicals(
                    chunk,
                    start_time=start_time,
                    end_time=end_time,
                    interval="day",
                    bounds="regular",
                    adjustment_type="split",
                )
            except Exception:
                continue
            extracted = extract_daily_volumes(
                payload,
                requested_symbols=chunk,
                exclude_on_or_after=current_eastern_date,
            )
            for symbol in chunk:
                observations = extracted.get(symbol, ())[-(VOLUME_REFERENCE_SESSIONS + 1) :]
                observations_by_symbol[symbol] = observations
                self._cache_daily_volumes(symbol, observations)

        return observations_by_symbol

    def _cached_daily_volumes(self, symbol: str):
        if self._cache_store is None:
            return ()
        cached = self._cache_store.get_json(_historical_cache_key(symbol))
        if not cached:
            return ()
        return deserialize_daily_volumes(cached.get("observations"))

    def _cache_daily_volumes(self, symbol: str, observations) -> None:
        if self._cache_store is None or not observations:
            return
        self._cache_store.set_json(
            _historical_cache_key(symbol),
            {"observations": serialize_daily_volumes(observations)},
            ttl_seconds=_HISTORICAL_CACHE_TTL_SECONDS,
        )


def _historical_cache_key(symbol: str) -> str:
    # v2 also retains the bounded daily close needed to calculate a true
    # session-over-session move after Robinhood rolls previous_close forward.
    return f"argus:market-data:robinhood:daily-volume:v2:{symbol}"


def _quote_with_historical_context(
    quote: MarketQuote,
    observations: Sequence[DailyVolume],
    activity: VolumeActivity | None,
) -> MarketQuote:
    values: dict[str, object] = {}
    previous_session = _previous_completed_session(quote, observations)
    if previous_session is not None and quote.last_price is not None:
        values.update(
            previous_close=previous_session.close_price,
            previous_close_date=previous_session.session_date,
            percent_change=(
                (quote.last_price - previous_session.close_price)
                / previous_session.close_price
                * 100
            ),
        )
    if activity is not None:
        values.update(
            volume_z_score=activity.z_score,
            volume_activity=activity.label,
            volume_observation_date=activity.observation_date,
            volume_reference_start=activity.reference_start,
            volume_reference_end=activity.reference_end,
            volume_reference_sessions=activity.reference_sessions,
            volume_observation_value=activity.observation_volume,
            volume_reference_median=activity.reference_median_volume,
            volume_reference_log_mad=activity.reference_log_mad,
            volume_method=activity.method,
            volume_quality=activity.quality,
        )
    return replace(quote, **values) if values else quote


def _previous_completed_session(
    quote: MarketQuote,
    observations: Sequence[DailyVolume],
) -> DailyVolume | None:
    if quote.observed_at is None:
        session_date = None
    else:
        session_date = quote.observed_at.astimezone(
            ZoneInfo("America/New_York")
        ).date()
    candidates = [
        observation
        for observation in observations
        if observation.close_price not in (None, 0.0)
        and (session_date is None or observation.session_date < session_date)
    ]
    return candidates[-1] if candidates else None


def _quote_records(payload: object) -> list[Mapping[str, object]]:
    if isinstance(payload, list):
        return [
            _flatten_quote_record(record)
            for record in payload
            if isinstance(record, Mapping)
        ]
    if not isinstance(payload, Mapping):
        return []
    if isinstance(payload.get("quote"), Mapping):
        return [_flatten_quote_record(payload)]
    for key in ("quotes", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [
                _flatten_quote_record(record)
                for record in value
                if isinstance(record, Mapping)
            ]
        if isinstance(value, Mapping):
            nested = _quote_records(value)
            if nested:
                return nested
    if payload.get("symbol"):
        return [payload]
    return []


def _flatten_quote_record(record: Mapping[str, object]) -> Mapping[str, object]:
    quote = record.get("quote")
    if not isinstance(quote, Mapping):
        return record
    flattened = dict(quote)
    close = record.get("close")
    if isinstance(close, Mapping):
        flattened.setdefault("close_price", close.get("price"))
        flattened.setdefault("close_date", close.get("date"))
    return flattened


def _normalize_quote(record: Mapping[str, object]) -> MarketQuote:
    symbol = str(record.get("symbol") or "").strip().upper()
    last_price = _optional_float(
        record.get("last_price")
        or record.get("price")
        or record.get("last_trade_price")
        or record.get("mark_price")
    )
    previous_close = _optional_float(
        record.get("previous_close") or record.get("previous_close_price")
    )
    previous_close_date = _optional_date(record.get("previous_close_date"))
    percent_change = _optional_float(
        record.get("percent_change") or record.get("change_percent")
    )
    if (
        percent_change is None
        and last_price is not None
        and previous_close not in (None, 0.0)
    ):
        percent_change = ((last_price - previous_close) / previous_close) * 100
    volume = _optional_float(record.get("volume") or record.get("day_volume"))
    dollar_volume = (
        last_price * volume
        if last_price is not None and volume is not None
        else None
    )
    return MarketQuote(
        symbol=symbol,
        last_price=last_price,
        previous_close=previous_close,
        previous_close_date=previous_close_date,
        percent_change=percent_change,
        volume=volume,
        dollar_volume=dollar_volume,
        volume_z_score=_optional_float(record.get("volume_z_score")),
        observed_at=_optional_datetime(
            record.get("observed_at")
            or record.get("updated_at")
            or record.get("timestamp")
            or record.get("venue_last_trade_time")
        ),
        status="live" if last_price is not None else "unavailable",
    )


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _optional_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None
