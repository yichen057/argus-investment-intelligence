from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from statistics import fmean
from typing import Mapping, Sequence

from investment_agent.market_data.volume import (
    DailyVolume,
    calculate_volume_activity,
)


POLICY_NAME = "market-review-v1"
MINIMUM_SESSIONS = 60
MAX_DATA_AGE_DAYS = 7


@dataclass(frozen=True)
class AlertDecision:
    symbol: str
    direction: str
    severity: str
    score: int
    holding_quantity: float
    portfolio_weight: float
    latest_close: float
    market_as_of_date: date
    holdings_as_of_date: date
    reasons: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: Mapping[str, object]
    content_hash: str


def evaluate_market_alerts(
    positions: Sequence[object],
    histories: Mapping[str, Sequence[DailyVolume]],
    *,
    target_allocation: Mapping[str, float],
    rebalance_threshold: float,
    sensitivity: str,
) -> tuple[AlertDecision, ...]:
    total_value = sum(max(0.0, float(getattr(item, "market_value", 0.0))) for item in positions)
    if total_value <= 0:
        return ()
    class_values: dict[str, float] = {}
    for item in positions:
        key = _canonical(str(getattr(item, "asset_class", "")))
        class_values[key] = class_values.get(key, 0.0) + max(
            0.0, float(getattr(item, "market_value", 0.0))
        )
    targets = {_canonical(key): float(value) for key, value in target_allocation.items()}
    decisions: list[AlertDecision] = []
    for position in positions:
        symbol = str(getattr(position, "symbol", "")).strip().upper()
        observations = tuple(
            item for item in histories.get(symbol, ()) if item.close_price not in (None, 0.0)
        )
        if not symbol or len(observations) < MINIMUM_SESSIONS:
            continue
        ordered = sorted(observations, key=lambda item: item.session_date)
        holdings_as_of = getattr(position, "as_of_date", None)
        if not isinstance(holdings_as_of, date):
            continue
        if abs((holdings_as_of - ordered[-1].session_date).days) > MAX_DATA_AGE_DAYS:
            continue
        closes = [float(item.close_price) for item in ordered]
        latest = ordered[-1]
        latest_close = closes[-1]
        recent = closes[-60:]
        high_60 = max(recent)
        drawdown = (latest_close / high_60) - 1.0
        sma20 = fmean(closes[-20:])
        prior_sma20 = fmean(closes[-21:-1])
        recovered = closes[-2] < prior_sma20 and latest_close >= sma20
        deteriorating = latest_close < sma20 and sma20 < prior_sma20
        activity = calculate_volume_activity(ordered)
        weight = float(getattr(position, "market_value", 0.0)) / total_value
        class_key = _canonical(str(getattr(position, "asset_class", "")))
        class_weight = class_values.get(class_key, 0.0) / total_value
        target = targets.get(class_key)
        underweight = target is not None and class_weight < target - rebalance_threshold
        overweight = target is not None and class_weight > target + rebalance_threshold
        drawdown_limit, threshold = {
            "conservative": (-0.12, 5),
            "standard": (-0.08, 4),
            "active": (-0.05, 3),
        }.get(sensitivity, (-0.08, 4))

        buy_reasons: list[str] = []
        buy_counter: list[str] = []
        buy_score = 0
        if underweight:
            buy_score += 2
            buy_reasons.append(
                f"{getattr(position, 'asset_class', 'Asset class')} is below the saved target by "
                f"{(target - class_weight) * 100:.1f} percentage points."
            )
        if drawdown <= drawdown_limit:
            buy_score += 1
            buy_reasons.append(f"Latest completed close is {abs(drawdown) * 100:.1f}% below its 60-session high.")
        if recovered:
            buy_score += 1
            buy_reasons.append("Price recovered above the 20-session moving average after being below it.")
        elif latest_close < sma20:
            buy_counter.append("Price remains below the 20-session moving average.")
        if activity.z_score is not None and activity.z_score >= 1.0:
            buy_score += 1
            buy_reasons.append(f"Completed-session volume is elevated (robust Z {activity.z_score:.2f}).")
        if buy_score >= threshold and (underweight or recovered):
            decisions.append(
                _decision(
                    position,
                    direction="buy",
                    score=buy_score,
                    threshold=threshold,
                    weight=weight,
                    latest=latest,
                    latest_close=latest_close,
                    reasons=buy_reasons,
                    counter=buy_counter or ["No separate fundamental-event evidence is available in this preview."],
                    drawdown=drawdown,
                    sma20=sma20,
                    volume_z=activity.z_score,
                )
            )

        reduce_reasons: list[str] = []
        reduce_counter: list[str] = []
        reduce_score = 0
        if overweight:
            reduce_score += 2
            reduce_reasons.append(
                f"{getattr(position, 'asset_class', 'Asset class')} is above the saved target by "
                f"{(class_weight - target) * 100:.1f} percentage points."
            )
        if weight >= 0.25:
            reduce_score += 2
            reduce_reasons.append(f"Position is {weight * 100:.1f}% of the scoped portfolio.")
        if deteriorating:
            reduce_score += 1
            reduce_reasons.append("Price is below a declining 20-session moving average.")
        else:
            reduce_counter.append("The configured trend-deterioration condition is not confirmed.")
        if drawdown <= -0.15:
            reduce_score += 1
            reduce_reasons.append(f"Drawdown from the 60-session high reached {abs(drawdown) * 100:.1f}%.")
        if reduce_score >= threshold and (overweight or weight >= 0.25):
            decisions.append(
                _decision(
                    position,
                    direction="reduce",
                    score=reduce_score,
                    threshold=threshold,
                    weight=weight,
                    latest=latest,
                    latest_close=latest_close,
                    reasons=reduce_reasons,
                    counter=reduce_counter,
                    drawdown=drawdown,
                    sma20=sma20,
                    volume_z=activity.z_score,
                )
            )
    return tuple(decisions)


def _decision(
    position: object,
    *,
    direction: str,
    score: int,
    threshold: int,
    weight: float,
    latest: DailyVolume,
    latest_close: float,
    reasons: Sequence[str],
    counter: Sequence[str],
    drawdown: float,
    sma20: float,
    volume_z: float | None,
) -> AlertDecision:
    metrics = {
        "policy": POLICY_NAME,
        "score_threshold": threshold,
        "drawdown_60": round(drawdown, 6),
        "sma20": round(sma20, 4),
        "volume_z_score": volume_z,
        "fundamental_event_check": "unavailable_in_preview_v1",
    }
    content = {
        "symbol": str(getattr(position, "symbol", "")).upper(),
        "direction": direction,
        "market_as_of": latest.session_date.isoformat(),
        "reasons": list(reasons),
        "counter": list(counter),
        "metrics": metrics,
    }
    content_hash = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return AlertDecision(
        symbol=content["symbol"],
        direction=direction,
        severity="review",
        score=score,
        holding_quantity=float(getattr(position, "quantity", 0.0)),
        portfolio_weight=weight,
        latest_close=latest_close,
        market_as_of_date=latest.session_date,
        holdings_as_of_date=getattr(position, "as_of_date"),
        reasons=tuple(reasons),
        counter_evidence=tuple(counter),
        invalidation_conditions=(
            "Suppress if holdings or completed-session history becomes stale.",
            "Re-evaluate if the saved target allocation changes.",
            "Do not act if current quotes materially differ from this completed-session close.",
        ),
        warnings=(
            "Fundamental-event validation is not implemented in preview v1.",
            "This is a review prompt, not a trade instruction. Argus placed no order.",
        ),
        metrics=metrics,
        content_hash=content_hash,
    )


def _canonical(value: str) -> str:
    return " ".join(value.lower().replace("/", " ").replace("_", " ").split())
