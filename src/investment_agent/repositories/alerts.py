from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from investment_agent.storage import MarketAlertSettings, MarketAlertSnapshot

if TYPE_CHECKING:
    from investment_agent.portfolio.alerts import AlertDecision


class MarketAlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def settings(self) -> MarketAlertSettings:
        value = self._session.scalar(
            select(MarketAlertSettings).order_by(MarketAlertSettings.id.desc())
        )
        if value is None:
            value = MarketAlertSettings()
            self._session.add(value)
            self._session.flush()
        return value

    def save_settings(self, **values: object) -> MarketAlertSettings:
        settings = self.settings()
        changed = any(getattr(settings, key) != value for key, value in values.items())
        for key, value in values.items():
            setattr(settings, key, value)
        if changed:
            settings.policy_version += 1
        self._session.flush()
        return settings

    def list_snapshots(self, *, limit: int = 50) -> list[MarketAlertSnapshot]:
        return list(
            self._session.scalars(
                select(MarketAlertSnapshot)
                .order_by(MarketAlertSnapshot.created_at.desc())
                .limit(limit)
            )
        )

    def add_decision(
        self, decision: AlertDecision, *, policy_version: int
    ) -> MarketAlertSnapshot | None:
        now = datetime.now(timezone.utc)
        feedback_suppression = self._session.scalar(
            select(MarketAlertSnapshot)
            .where(
                MarketAlertSnapshot.symbol == decision.symbol,
                MarketAlertSnapshot.direction == decision.direction,
                MarketAlertSnapshot.feedback.in_(("noise", "incorrect")),
                MarketAlertSnapshot.feedback_at >= now - timedelta(days=7),
            )
            .order_by(MarketAlertSnapshot.feedback_at.desc())
        )
        if feedback_suppression is not None:
            return None
        prior = self._session.scalar(
            select(MarketAlertSnapshot)
            .where(
                MarketAlertSnapshot.symbol == decision.symbol,
                MarketAlertSnapshot.direction == decision.direction,
                MarketAlertSnapshot.created_at >= now - timedelta(hours=24),
            )
            .order_by(MarketAlertSnapshot.created_at.desc())
        )
        if prior is not None:
            return None
        deduplication_key = (
            f"{decision.symbol}:{decision.direction}:{policy_version}:"
            f"{decision.market_as_of_date.isoformat()}:{decision.content_hash[:16]}"
        )
        snapshot = MarketAlertSnapshot(
            symbol=decision.symbol,
            direction=decision.direction,
            severity=decision.severity,
            score=decision.score,
            policy_version=policy_version,
            holding_quantity=decision.holding_quantity,
            portfolio_weight=decision.portfolio_weight,
            latest_close=decision.latest_close,
            market_as_of_date=decision.market_as_of_date,
            holdings_as_of_date=decision.holdings_as_of_date,
            reasons_json=list(decision.reasons),
            counter_evidence_json=list(decision.counter_evidence),
            invalidation_conditions_json=list(decision.invalidation_conditions),
            warnings_json=list(decision.warnings),
            metrics_json=dict(decision.metrics),
            content_hash=decision.content_hash,
            deduplication_key=deduplication_key,
        )
        self._session.add(snapshot)
        self._session.flush()
        return snapshot

    def feedback(self, snapshot_id: int, value: str) -> MarketAlertSnapshot | None:
        snapshot = self._session.get(MarketAlertSnapshot, snapshot_id)
        if snapshot is None:
            return None
        actions = {
            "useful": "Similar previews remain enabled.",
            "noise": f"Similar {snapshot.symbol} {snapshot.direction} previews are suppressed for 7 days.",
            "too_late": "Timing was recorded for latency review; policy thresholds were not changed.",
            "incorrect": (
                "This preview is flagged for rule review and similar previews are suppressed "
                "for 7 days; policy thresholds were not changed automatically."
            ),
        }
        snapshot.feedback = value
        snapshot.feedback_action = actions[value]
        snapshot.feedback_at = datetime.now(timezone.utc)
        snapshot.status = "rule_review" if value == "incorrect" else "reviewed"
        self._session.flush()
        return snapshot
