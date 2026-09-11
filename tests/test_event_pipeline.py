from __future__ import annotations

from datetime import UTC, datetime
import json

import pytest

from investment_agent.cloud import EventContractError, EventEnvelope
from investment_agent.event_consumer import (
    AuditMetricsHandler,
    KafkaAuditMetricsConsumer,
    KafkaMessageContext,
)
from investment_agent.repositories import EventAuditRepository
from investment_agent.storage import Base, make_session_factory
from sqlalchemy import create_engine


class FakeMessage:
    def __init__(
        self,
        value: bytes,
        *,
        topic: str = "agent.run.completed.v1",
        partition: int = 0,
        offset: int = 1,
    ) -> None:
        self._value = value
        self._topic = topic
        self._partition = partition
        self._offset = offset

    def error(self):
        return None

    def value(self) -> bytes:
        return self._value

    def topic(self) -> str:
        return self._topic

    def partition(self) -> int:
        return self._partition

    def offset(self) -> int:
        return self._offset


class FakeConsumer:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self.messages = messages
        self.topics: list[str] = []
        self.committed: list[FakeMessage] = []
        self.closed = False

    def subscribe(self, topics: list[str]) -> None:
        self.topics = topics

    def poll(self, timeout: float):
        assert timeout >= 0
        return self.messages.pop(0) if self.messages else None

    def commit(self, *, message: FakeMessage, asynchronous: bool):
        assert asynchronous is False
        self.committed.append(message)

    def close(self) -> None:
        self.closed = True


class FakeProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def produce(self, topic: str, *, key: str, value: str) -> None:
        self.messages.append((topic, key, value))

    def poll(self, timeout: float) -> None:
        assert timeout == 0

    def flush(self, timeout: float) -> int:
        assert timeout == 10
        return 0


class FlakyHandler:
    def __init__(self, delegate: AuditMetricsHandler, *, failures: int) -> None:
        self.delegate = delegate
        self.failures = failures
        self.calls = 0

    def handle(self, *args, **kwargs) -> bool:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("transient_database_error")
        return self.delegate.handle(*args, **kwargs)

    def record_dlq(self, **kwargs) -> None:
        self.delegate.record_dlq(**kwargs)

    def heartbeat(self, status: str, *, error_code: str | None = None) -> None:
        self.delegate.heartbeat(status, error_code=error_code)


def test_event_envelope_round_trip_and_validation() -> None:
    event = completed_event(event_id="event-1", run_id=42)

    restored = EventEnvelope.from_json(event.to_json())

    assert restored == event
    with pytest.raises(EventContractError, match="event_json_invalid"):
        EventEnvelope.from_json(b"not-json")
    with pytest.raises(EventContractError, match="event_envelope_fields_invalid"):
        EventEnvelope.from_json(
            json.dumps({**json.loads(event.to_json()), "unexpected": "field"})
        )
    with pytest.raises(EventContractError, match="event_envelope_too_large"):
        EventEnvelope.from_json(b"x" * (64 * 1024 + 1))


def test_consumer_records_one_event_and_deduplicates_replay(tmp_path) -> None:
    session_factory = sqlite_session_factory(tmp_path)
    event = completed_event(event_id="event-deduplicated", run_id=42)
    consumer = FakeConsumer(
        [
            FakeMessage(event.to_json().encode(), offset=10),
            FakeMessage(event.to_json().encode(), offset=11),
        ]
    )
    runtime = KafkaAuditMetricsConsumer(
        consumer=consumer,
        dlq_producer=FakeProducer(),
        handler=AuditMetricsHandler(
            session_factory,
            consumer_group="argus-audit-metrics-v1",
        ),
    )

    assert runtime.run_once(timeout_seconds=0) == "processed"
    assert runtime.run_once(timeout_seconds=0) == "duplicate"

    with session_factory() as session:
        repository = EventAuditRepository(session)
        totals = repository.totals()
        records = repository.list_recent()
        heartbeat = repository.get_heartbeat("argus-audit-metrics-v1")
    assert totals.processed_count == 1
    assert totals.duplicate_count == 1
    assert totals.dlq_count == 0
    assert len(records) == 1
    assert records[0].payload_summary_json == {
        "run_id": 42,
        "status": "complete",
        "total_tokens": 120,
        "total_estimated_cost_usd": 0.002,
    }
    assert heartbeat is not None
    assert heartbeat.status == "running"
    assert consumer.topics == ["agent.run.completed.v1", "agent.run.failed.v1"]
    assert len(consumer.committed) == 2


def test_consumer_records_sanitized_model_failure_event(tmp_path) -> None:
    session_factory = sqlite_session_factory(tmp_path)
    event = failed_event(event_id="event-provider-timeout", run_id=95)
    consumer = FakeConsumer(
        [
            FakeMessage(
                event.to_json().encode(),
                topic="agent.run.failed.v1",
                offset=15,
            )
        ]
    )
    runtime = KafkaAuditMetricsConsumer(
        consumer=consumer,
        dlq_producer=FakeProducer(),
        handler=AuditMetricsHandler(
            session_factory,
            consumer_group="argus-audit-metrics-v1",
        ),
    )

    assert runtime.run_once(timeout_seconds=0) == "processed"
    with session_factory() as session:
        repository = EventAuditRepository(session)
        record = repository.list_recent()[0]
        totals = repository.totals()
    assert record.event_type == "agent.run.failed.v1"
    assert record.payload_summary_json == {
        "run_id": 95,
        "status": "failed",
        "error_code": "provider_timeout",
        "failure_stage": "answer_model",
        "provider": "moonshot",
        "model": "kimi-k2.6",
        "total_tokens": 0,
        "total_estimated_cost_usd": 0.0,
    }
    assert totals.completed_count == 0
    assert totals.failed_count == 1
    assert "message" not in record.payload_summary_json


def test_consumer_records_answer_outcome_without_storing_answer_text(tmp_path) -> None:
    session_factory = sqlite_session_factory(tmp_path)
    event = completed_event(event_id="event-safe-stop", run_id=92)
    event = EventEnvelope(
        event_type=event.event_type,
        aggregate_id=event.aggregate_id,
        event_id=event.event_id,
        occurred_at=event.occurred_at,
        payload={
            **event.payload,
            "execution_outcome": "web_skipped_no_supported_evidence",
            "answer_generated": False,
        },
    )
    consumer = FakeConsumer([FakeMessage(event.to_json().encode())])
    runtime = KafkaAuditMetricsConsumer(
        consumer=consumer,
        dlq_producer=FakeProducer(),
        handler=AuditMetricsHandler(
            session_factory,
            consumer_group="argus-audit-metrics-v1",
        ),
    )

    assert runtime.run_once(timeout_seconds=0) == "processed"
    with session_factory() as session:
        record = EventAuditRepository(session).list_recent()[0]
    assert record.payload_summary_json == {
        "run_id": 92,
        "status": "complete",
        "total_tokens": 120,
        "total_estimated_cost_usd": 0.002,
        "execution_outcome": "web_skipped_no_supported_evidence",
        "answer_generated": False,
    }
    assert "answer" not in record.payload_summary_json


def test_invalid_event_is_hashed_sent_to_dlq_and_committed(tmp_path) -> None:
    session_factory = sqlite_session_factory(tmp_path)
    consumer = FakeConsumer([FakeMessage(b"not-json", offset=12)])
    producer = FakeProducer()
    runtime = KafkaAuditMetricsConsumer(
        consumer=consumer,
        dlq_producer=producer,
        handler=AuditMetricsHandler(
            session_factory,
            consumer_group="argus-audit-metrics-v1",
        ),
    )

    assert runtime.run_once(timeout_seconds=0) == "dlq"

    assert producer.messages[0][0] == "agent.run.completed.v1.dlq"
    assert producer.messages[0][1].startswith("invalid:")
    with session_factory() as session:
        records = EventAuditRepository(session).list_recent()
    assert len(records) == 1
    assert records[0].status == "dlq"
    assert records[0].error_code == "event_json_invalid"
    assert set(records[0].payload_summary_json) == {"raw_sha256"}
    assert len(consumer.committed) == 1


def test_unknown_model_failure_code_is_sent_to_failed_topic_dlq(tmp_path) -> None:
    session_factory = sqlite_session_factory(tmp_path)
    valid = failed_event(event_id="event-invalid-failure-code", run_id=96)
    invalid = EventEnvelope(
        event_type=valid.event_type,
        aggregate_id=valid.aggregate_id,
        event_id=valid.event_id,
        occurred_at=valid.occurred_at,
        payload={**valid.payload, "error_code": "raw_secret_provider_message"},
    )
    consumer = FakeConsumer(
        [FakeMessage(invalid.to_json().encode(), topic="agent.run.failed.v1")]
    )
    producer = FakeProducer()
    runtime = KafkaAuditMetricsConsumer(
        consumer=consumer,
        dlq_producer=producer,
        handler=AuditMetricsHandler(
            session_factory,
            consumer_group="argus-audit-metrics-v1",
        ),
    )

    assert runtime.run_once(timeout_seconds=0) == "dlq"
    assert producer.messages[0][0] == "agent.run.failed.v1.dlq"
    with session_factory() as session:
        record = EventAuditRepository(session).list_recent()[0]
    assert record.status == "dlq"
    assert record.error_code == "event_failure_code_invalid"
    assert set(record.payload_summary_json) == {"raw_sha256"}


def test_reused_event_id_with_different_content_is_sent_to_dlq(tmp_path) -> None:
    session_factory = sqlite_session_factory(tmp_path)
    first = completed_event(event_id="event-collision", run_id=42)
    conflicting = completed_event(event_id="event-collision", run_id=43)
    consumer = FakeConsumer(
        [
            FakeMessage(first.to_json().encode(), offset=20),
            FakeMessage(conflicting.to_json().encode(), offset=21),
        ]
    )
    producer = FakeProducer()
    runtime = KafkaAuditMetricsConsumer(
        consumer=consumer,
        dlq_producer=producer,
        handler=AuditMetricsHandler(
            session_factory,
            consumer_group="argus-audit-metrics-v1",
        ),
        retry_backoff_seconds=0,
    )

    assert runtime.run_once(timeout_seconds=0) == "processed"
    assert runtime.run_once(timeout_seconds=0) == "dlq"
    with session_factory() as session:
        totals = EventAuditRepository(session).totals()
        records = EventAuditRepository(session).list_recent()
    assert totals.processed_count == 1
    assert totals.dlq_count == 1
    assert len(records) == 2
    assert any(record.event_id.startswith("conflict:") for record in records)
    assert len(consumer.committed) == 2


def test_transient_handler_failure_retries_before_committing(tmp_path) -> None:
    session_factory = sqlite_session_factory(tmp_path)
    consumer = FakeConsumer(
        [FakeMessage(completed_event(event_id="event-retry", run_id=43).to_json().encode())]
    )
    handler = FlakyHandler(
        AuditMetricsHandler(
            session_factory,
            consumer_group="argus-audit-metrics-v1",
        ),
        failures=2,
    )
    runtime = KafkaAuditMetricsConsumer(
        consumer=consumer,
        dlq_producer=FakeProducer(),
        handler=handler,
        max_attempts=3,
        retry_backoff_seconds=0,
    )

    assert runtime.run_once(timeout_seconds=0) == "processed"
    assert handler.calls == 3
    assert len(consumer.committed) == 1
    with session_factory() as session:
        records = EventAuditRepository(session).list_recent()
    assert records[0].attempt_count == 3


def test_sanitized_projection_retention_is_bounded(tmp_path) -> None:
    session_factory = sqlite_session_factory(tmp_path)
    handler = AuditMetricsHandler(
        session_factory,
        consumer_group="argus-audit-metrics-v1",
        retention_count=2,
        retention_days=365,
    )
    context = KafkaMessageContext(
        topic="agent.run.completed.v1",
        partition=0,
        offset=1,
    )
    for run_id in (1, 2, 3):
        handler.handle(
            completed_event(event_id=f"bounded-{run_id}", run_id=run_id),
            context,
            attempt_count=1,
        )

    with session_factory() as session:
        records = EventAuditRepository(session).list_recent(limit=10)
    assert [record.aggregate_id for record in records] == ["3", "2"]


def completed_event(*, event_id: str, run_id: int) -> EventEnvelope:
    return EventEnvelope(
        event_type="agent.run.completed.v1",
        aggregate_id=str(run_id),
        event_id=event_id,
        occurred_at=datetime.now(UTC).isoformat(),
        payload={
            "run_id": run_id,
            "status": "complete",
            "total_tokens": 120,
            "total_estimated_cost_usd": 0.002,
        },
    )


def failed_event(*, event_id: str, run_id: int) -> EventEnvelope:
    return EventEnvelope(
        event_type="agent.run.failed.v1",
        aggregate_id=str(run_id),
        event_id=event_id,
        occurred_at=datetime.now(UTC).isoformat(),
        payload={
            "run_id": run_id,
            "status": "failed",
            "error_code": "provider_timeout",
            "failure_stage": "answer_model",
            "provider": "moonshot",
            "model": "kimi-k2.6",
            "total_tokens": 0,
            "total_estimated_cost_usd": 0.0,
        },
    )


def sqlite_session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'event-pipeline.db'}")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)
