from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from investment_agent.storage import EventAuditRecord, EventConsumerHeartbeat


class EventAuditConflictError(RuntimeError):
    """The same event ID was reused for different business content."""


@dataclass(frozen=True)
class EventAuditCreate:
    event_id: str
    event_type: str
    aggregate_id: str
    schema_version: int
    status: str
    consumer_group: str
    topic: str
    partition: int | None = None
    message_offset: int | None = None
    attempt_count: int = 1
    occurred_at: datetime | None = None
    payload_summary: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None


@dataclass(frozen=True)
class EventPipelineTotals:
    processed_count: int
    completed_count: int
    answer_generated_count: int
    safe_stop_count: int
    failed_count: int
    dlq_count: int
    duplicate_count: int


class EventAuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, payload: EventAuditCreate) -> tuple[EventAuditRecord, bool]:
        existing = self._session.scalar(
            select(EventAuditRecord).where(
                EventAuditRecord.event_id == payload.event_id
            )
        )
        if existing is not None:
            expected_summary = payload.payload_summary
            if (
                existing.event_type != payload.event_type
                or existing.aggregate_id != payload.aggregate_id
                or existing.schema_version != payload.schema_version
                or existing.payload_summary_json != expected_summary
            ):
                raise EventAuditConflictError("event_id_content_conflict")
            existing.duplicate_count += 1
            existing.attempt_count = max(existing.attempt_count, payload.attempt_count)
            self._session.flush()
            return existing, True

        record = EventAuditRecord(
            event_id=payload.event_id,
            event_type=payload.event_type,
            aggregate_id=payload.aggregate_id,
            schema_version=payload.schema_version,
            status=payload.status,
            consumer_group=payload.consumer_group,
            topic=payload.topic,
            partition=payload.partition,
            message_offset=payload.message_offset,
            attempt_count=max(1, payload.attempt_count),
            duplicate_count=0,
            occurred_at=payload.occurred_at,
            payload_summary_json=payload.payload_summary,
            error_code=payload.error_code,
        )
        self._session.add(record)
        self._session.flush()
        return record, False

    def update_heartbeat(
        self,
        *,
        consumer_group: str,
        status: str,
        topics: tuple[str, ...],
        error_code: str | None = None,
    ) -> EventConsumerHeartbeat:
        heartbeat = self._session.scalar(
            select(EventConsumerHeartbeat).where(
                EventConsumerHeartbeat.consumer_group == consumer_group
            )
        )
        now = datetime.now(timezone.utc)
        if heartbeat is None:
            heartbeat = EventConsumerHeartbeat(
                consumer_group=consumer_group,
                status=status,
                topics_json=list(topics),
                last_seen_at=now,
                last_error_code=error_code,
            )
            self._session.add(heartbeat)
        else:
            heartbeat.status = status
            heartbeat.topics_json = list(topics)
            heartbeat.last_seen_at = now
            heartbeat.last_error_code = error_code
        self._session.flush()
        return heartbeat

    def get_heartbeat(self, consumer_group: str) -> EventConsumerHeartbeat | None:
        return self._session.scalar(
            select(EventConsumerHeartbeat).where(
                EventConsumerHeartbeat.consumer_group == consumer_group
            )
        )

    def totals(self) -> EventPipelineTotals:
        processed_records = list(
            self._session.execute(
                select(
                    EventAuditRecord.event_type,
                    EventAuditRecord.payload_summary_json,
                ).where(EventAuditRecord.status == "processed")
            )
        )
        processed = len(processed_records)
        completed = sum(
            1
            for event_type, _summary in processed_records
            if event_type == "agent.run.completed.v1"
        )
        failed = sum(
            1
            for event_type, _summary in processed_records
            if event_type == "agent.run.failed.v1"
        )
        answer_generated = sum(
            1
            for event_type, summary in processed_records
            if event_type == "agent.run.completed.v1"
            and isinstance(summary, dict)
            and summary.get("answer_generated") is True
        )
        safe_stops = sum(
            1
            for event_type, summary in processed_records
            if event_type == "agent.run.completed.v1"
            and isinstance(summary, dict)
            and summary.get("answer_generated") is False
        )
        dlq = int(
            self._session.scalar(
                select(func.count(EventAuditRecord.id)).where(
                    EventAuditRecord.status == "dlq"
                )
            )
            or 0
        )
        duplicates = int(
            self._session.scalar(
                select(func.coalesce(func.sum(EventAuditRecord.duplicate_count), 0))
            )
            or 0
        )
        return EventPipelineTotals(
            processed_count=processed,
            completed_count=completed,
            answer_generated_count=answer_generated,
            safe_stop_count=safe_stops,
            failed_count=failed,
            dlq_count=dlq,
            duplicate_count=duplicates,
        )

    def list_recent(self, *, limit: int = 10) -> list[EventAuditRecord]:
        return list(
            self._session.scalars(
                select(EventAuditRecord)
                .order_by(
                    EventAuditRecord.updated_at.desc(),
                    EventAuditRecord.id.desc(),
                )
                .limit(max(1, min(limit, 100)))
            )
        )

    def prune(self, *, keep_latest: int, max_age_days: int) -> int:
        """Bound the sanitized projection without changing Kafka or Run history."""

        keep = max(1, keep_latest)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, max_age_days))
        obsolete_ids = set(
            self._session.scalars(
                select(EventAuditRecord.id)
                .order_by(
                    EventAuditRecord.updated_at.desc(),
                    EventAuditRecord.id.desc(),
                )
                .offset(keep)
            )
        )
        obsolete_ids.update(
            self._session.scalars(
                select(EventAuditRecord.id).where(
                    EventAuditRecord.updated_at < cutoff
                )
            )
        )
        if not obsolete_ids:
            return 0
        self._session.execute(
            delete(EventAuditRecord).where(EventAuditRecord.id.in_(obsolete_ids))
        )
        self._session.flush()
        return len(obsolete_ids)
