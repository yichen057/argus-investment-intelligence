from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping, Sequence


VOLUME_REFERENCE_SESSIONS = 60
VOLUME_MINIMUM_SESSIONS = 20
VOLUME_METHOD = "robust_log_mad_v1"


@dataclass(frozen=True)
class DailyVolume:
    symbol: str
    session_date: date
    volume: float
    close_price: float | None = None


@dataclass(frozen=True)
class VolumeActivity:
    z_score: float | None
    label: str
    observation_date: date | None
    reference_start: date | None
    reference_end: date | None
    reference_sessions: int
    observation_volume: float | None
    reference_median_volume: float | None
    reference_log_mad: float | None
    method: str
    quality: str


def extract_daily_volumes(
    payload: object,
    *,
    requested_symbols: Sequence[str],
    exclude_on_or_after: date,
) -> dict[str, tuple[DailyVolume, ...]]:
    """Project a provider response into complete, non-interpolated daily volumes.

    Robinhood publishes an input Schema through ``list_tools`` but does not pin an
    output Schema there. This narrow projector accepts common wrapper shapes while
    discarding every field except symbol, session date, volume, and interpolation
    status. Unknown shapes fail to an empty result rather than being guessed.
    """

    expected = {
        symbol.strip().upper()
        for symbol in requested_symbols
        if symbol.strip()
    }
    collected: dict[str, dict[date, DailyVolume]] = {
        symbol: {} for symbol in expected
    }
    _walk_historical_payload(
        payload,
        expected=expected,
        collected=collected,
        exclude_on_or_after=exclude_on_or_after,
    )
    return {
        symbol: tuple(sorted(records.values(), key=lambda item: item.session_date))
        for symbol, records in collected.items()
    }


def calculate_volume_activity(
    observations: Sequence[DailyVolume],
    *,
    reference_sessions: int = VOLUME_REFERENCE_SESSIONS,
    minimum_sessions: int = VOLUME_MINIMUM_SESSIONS,
) -> VolumeActivity:
    ordered = sorted(observations, key=lambda item: item.session_date)
    if not ordered:
        return _unavailable_activity("no_complete_sessions")

    current = ordered[-1]
    reference = ordered[:-1][-reference_sessions:]
    if len(reference) < minimum_sessions:
        return VolumeActivity(
            z_score=None,
            label="Not enough history",
            observation_date=current.session_date,
            reference_start=reference[0].session_date if reference else None,
            reference_end=reference[-1].session_date if reference else None,
            reference_sessions=len(reference),
            observation_volume=current.volume,
            reference_median_volume=(
                statistics.median(item.volume for item in reference)
                if reference
                else None
            ),
            reference_log_mad=None,
            method=VOLUME_METHOD,
            quality="insufficient_sessions",
        )

    logged = [math.log1p(item.volume) for item in reference]
    center = statistics.median(logged)
    mad = statistics.median(abs(value - center) for value in logged)
    if mad <= 1e-12:
        return VolumeActivity(
            z_score=None,
            label="Not enough variation",
            observation_date=current.session_date,
            reference_start=reference[0].session_date,
            reference_end=reference[-1].session_date,
            reference_sessions=len(reference),
            observation_volume=current.volume,
            reference_median_volume=math.expm1(center),
            reference_log_mad=mad,
            method=VOLUME_METHOD,
            quality="insufficient_variation",
        )

    raw_score = (math.log1p(current.volume) - center) / (1.4826 * mad)
    score = round(max(-9.99, min(9.99, raw_score)), 2)
    return VolumeActivity(
        z_score=score,
        label=_activity_label(score),
        observation_date=current.session_date,
        reference_start=reference[0].session_date,
        reference_end=reference[-1].session_date,
        reference_sessions=len(reference),
        observation_volume=current.volume,
        reference_median_volume=statistics.median(
            item.volume for item in reference
        ),
        reference_log_mad=mad,
        method=VOLUME_METHOD,
        quality="supported",
    )


def serialize_daily_volumes(observations: Sequence[DailyVolume]) -> list[dict[str, object]]:
    return [
        {
            "symbol": observation.symbol,
            "session_date": observation.session_date.isoformat(),
            "volume": observation.volume,
            "close_price": observation.close_price,
        }
        for observation in observations
    ]


def deserialize_daily_volumes(value: object) -> tuple[DailyVolume, ...]:
    if not isinstance(value, list):
        return ()
    observations: list[DailyVolume] = []
    for record in value:
        if not isinstance(record, Mapping):
            continue
        symbol = str(record.get("symbol") or "").strip().upper()
        session_date = _optional_date(record.get("session_date"))
        volume = _optional_float(record.get("volume"))
        close_price = _optional_float(record.get("close_price"))
        if symbol and session_date is not None and volume is not None and volume > 0:
            observations.append(
                DailyVolume(
                    symbol=symbol,
                    session_date=session_date,
                    volume=volume,
                    close_price=close_price,
                )
            )
    return tuple(sorted(observations, key=lambda item: item.session_date))


def _walk_historical_payload(
    node: object,
    *,
    expected: set[str],
    collected: dict[str, dict[date, DailyVolume]],
    exclude_on_or_after: date,
    inherited_symbol: str | None = None,
) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_historical_payload(
                item,
                expected=expected,
                collected=collected,
                exclude_on_or_after=exclude_on_or_after,
                inherited_symbol=inherited_symbol,
            )
        return
    if not isinstance(node, Mapping):
        return

    symbol = str(node.get("symbol") or node.get("ticker") or inherited_symbol or "")
    symbol = symbol.strip().upper()
    if symbol in expected:
        observation = _daily_volume_from_record(node, symbol=symbol)
        if (
            observation is not None
            and observation.session_date < exclude_on_or_after
            and not _truthy(node.get("interpolated"))
        ):
            collected[symbol][observation.session_date] = observation

    for key, value in node.items():
        child_symbol = symbol if symbol in expected else inherited_symbol
        normalized_key = str(key).strip().upper()
        if normalized_key in expected and isinstance(value, (list, Mapping)):
            child_symbol = normalized_key
        if isinstance(value, (list, Mapping)):
            _walk_historical_payload(
                value,
                expected=expected,
                collected=collected,
                exclude_on_or_after=exclude_on_or_after,
                inherited_symbol=child_symbol,
            )


def _daily_volume_from_record(
    record: Mapping[object, object],
    *,
    symbol: str,
) -> DailyVolume | None:
    volume = _optional_float(
        record.get("volume")
        or record.get("day_volume")
        or record.get("total_volume")
    )
    close_price = _optional_float(
        record.get("close_price")
        or record.get("close")
    )
    session_date = _optional_date(
        record.get("begins_at")
        or record.get("starts_at")
        or record.get("start_time")
        or record.get("timestamp")
        or record.get("date")
    )
    if volume is None or volume <= 0 or session_date is None:
        return None
    return DailyVolume(
        symbol=symbol,
        session_date=session_date,
        volume=volume,
        close_price=close_price,
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
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(normalized[:10])
        except ValueError:
            return None


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _activity_label(score: float) -> str:
    if score >= 3:
        return "Unusual"
    if score >= 2:
        return "High"
    if score >= 1:
        return "Elevated"
    if score <= -1.5:
        return "Quiet"
    return "Normal"


def _unavailable_activity(quality: str) -> VolumeActivity:
    return VolumeActivity(
        z_score=None,
        label="Not enough history",
        observation_date=None,
        reference_start=None,
        reference_end=None,
        reference_sessions=0,
        observation_volume=None,
        reference_median_volume=None,
        reference_log_mad=None,
        method=VOLUME_METHOD,
        quality=quality,
    )
