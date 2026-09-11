from __future__ import annotations

import hashlib
import json
import logging
import signal
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from investment_agent.cloud.events import (
    EventContractError,
    EventEnvelope,
    kafka_auth_config,
)
from investment_agent.config import Settings, get_settings
from investment_agent.repositories import (
    EventAuditConflictError,
    EventAuditCreate,
    EventAuditRepository,
)
from investment_agent.storage import make_engine, make_session_factory, session_scope

logger = logging.getLogger(__name__)

RUN_COMPLETED_EVENT_TYPE = "agent.run.completed.v1"
RUN_FAILED_EVENT_TYPE = "agent.run.failed.v1"
AUDIT_EVENT_TYPE = RUN_COMPLETED_EVENT_TYPE  # backwards-compatible import
AUDIT_TOPICS = (RUN_COMPLETED_EVENT_TYPE, RUN_FAILED_EVENT_TYPE)
MODEL_FAILURE_CODES = frozenset(
    {
        "provider_timeout",
        "provider_authentication_failed",
        "provider_quota_exhausted",
        "model_provider_error",
    }
)


@dataclass(frozen=True)
class KafkaMessageContext:
    topic: str
    partition: int | None
    offset: int | None


class ConsumerClient(Protocol):
    def subscribe(self, topics: list[str]) -> None: ...

    def poll(self, timeout: float) -> Any: ...

    def commit(self, *, message: Any, asynchronous: bool) -> Any: ...

    def close(self) -> None: ...


class ProducerClient(Protocol):
    def produce(self, topic: str, *, key: str, value: str) -> None: ...

    def poll(self, timeout: float) -> Any: ...

    def flush(self, timeout: float) -> Any: ...


class AuditMetricsHandler:
    def __init__(
        self,
        session_factory,
        *,
        consumer_group: str,
        retention_count: int = 5_000,
        retention_days: int = 30,
    ) -> None:
        self._session_factory = session_factory
        self._consumer_group = consumer_group
        self._retention_count = max(1, retention_count)
        self._retention_days = max(1, retention_days)

    def handle(
        self,
        envelope: EventEnvelope,
        context: KafkaMessageContext,
        *,
        attempt_count: int,
    ) -> bool:
        summary = validate_agent_run_event(envelope)
        occurred_at = datetime.fromisoformat(
            envelope.occurred_at.replace("Z", "+00:00")
        )
        with session_scope(self._session_factory) as session:
            repository = EventAuditRepository(session)
            _, duplicate = repository.record(
                EventAuditCreate(
                    event_id=envelope.event_id,
                    event_type=envelope.event_type,
                    aggregate_id=envelope.aggregate_id,
                    schema_version=envelope.schema_version,
                    status="processed",
                    consumer_group=self._consumer_group,
                    topic=context.topic,
                    partition=context.partition,
                    message_offset=context.offset,
                    attempt_count=attempt_count,
                    occurred_at=occurred_at,
                    payload_summary=summary,
                )
            )
            repository.prune(
                keep_latest=self._retention_count,
                max_age_days=self._retention_days,
            )
        return duplicate

    def record_dlq(
        self,
        *,
        event_id: str,
        envelope: EventEnvelope | None,
        context: KafkaMessageContext,
        attempt_count: int,
        error_code: str,
        raw_sha256: str,
    ) -> None:
        safe_summary: dict[str, Any] = {"raw_sha256": raw_sha256}
        occurred_at = None
        event_type = "invalid"
        aggregate_id = "invalid"
        schema_version = 0
        if envelope is not None:
            event_type = envelope.event_type
            aggregate_id = envelope.aggregate_id
            schema_version = envelope.schema_version
            try:
                safe_summary.update(validate_agent_run_event(envelope))
            except EventContractError:
                pass
            occurred_at = datetime.fromisoformat(
                envelope.occurred_at.replace("Z", "+00:00")
            )
        with session_scope(self._session_factory) as session:
            repository = EventAuditRepository(session)
            record_payload = EventAuditCreate(
                event_id=event_id,
                event_type=event_type,
                aggregate_id=aggregate_id,
                schema_version=schema_version,
                status="dlq",
                consumer_group=self._consumer_group,
                topic=context.topic,
                partition=context.partition,
                message_offset=context.offset,
                attempt_count=attempt_count,
                occurred_at=occurred_at,
                payload_summary=safe_summary,
                error_code=error_code[:128],
            )
            try:
                repository.record(record_payload)
            except EventAuditConflictError:
                repository.record(
                    EventAuditCreate(
                        **{
                            **asdict(record_payload),
                            "event_id": f"conflict:{raw_sha256}",
                        }
                    )
                )
            repository.prune(
                keep_latest=self._retention_count,
                max_age_days=self._retention_days,
            )

    def heartbeat(self, status: str, *, error_code: str | None = None) -> None:
        with session_scope(self._session_factory) as session:
            EventAuditRepository(session).update_heartbeat(
                consumer_group=self._consumer_group,
                status=status,
                topics=AUDIT_TOPICS,
                error_code=error_code,
            )


class KafkaAuditMetricsConsumer:
    def __init__(
        self,
        *,
        consumer: ConsumerClient,
        dlq_producer: ProducerClient,
        handler: AuditMetricsHandler,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.1,
    ) -> None:
        self._consumer = consumer
        self._dlq_producer = dlq_producer
        self._handler = handler
        self._max_attempts = max(1, max_attempts)
        self._retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._consumer.subscribe(list(AUDIT_TOPICS))

    def run_once(self, *, timeout_seconds: float = 1.0) -> str:
        self._handler.heartbeat("running")
        message = self._consumer.poll(timeout_seconds)
        if message is None:
            return "idle"
        if message.error():
            kafka_error = message.error()
            error_code = f"kafka_consume_{kafka_error.code()}"
            if _is_retriable_kafka_error(kafka_error):
                self._handler.heartbeat("waiting", error_code=error_code)
                return "retrying"
            self._handler.heartbeat("error", error_code=error_code)
            raise RuntimeError(error_code)

        context = KafkaMessageContext(
            topic=str(message.topic()),
            partition=_optional_int(message.partition()),
            offset=_optional_int(message.offset()),
        )
        raw_value = message.value()
        if isinstance(raw_value, str):
            raw = raw_value.encode("utf-8")
        elif isinstance(raw_value, bytes):
            raw = raw_value
        else:
            raw = b""
        raw_sha256 = hashlib.sha256(raw).hexdigest()
        envelope: EventEnvelope | None = None
        try:
            envelope = EventEnvelope.from_json(raw)
            validate_agent_run_event(envelope)
        except EventContractError as exc:
            event_id = envelope.event_id if envelope else f"invalid:{raw_sha256}"
            self._send_to_dlq(
                event_id=event_id,
                envelope=envelope,
                context=context,
                attempt_count=1,
                error_code=str(exc),
                raw_sha256=raw_sha256,
            )
            self._consumer.commit(message=message, asynchronous=False)
            return "dlq"

        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                duplicate = self._handler.handle(
                    envelope,
                    context,
                    attempt_count=attempt,
                )
            except Exception as exc:  # retries are intentionally bounded here
                last_error = exc
                if attempt < self._max_attempts:
                    time.sleep(self._retry_backoff_seconds * attempt)
                continue
            self._consumer.commit(message=message, asynchronous=False)
            return "duplicate" if duplicate else "processed"

        error_code = type(last_error).__name__ if last_error else "handler_failed"
        self._send_to_dlq(
            event_id=envelope.event_id,
            envelope=envelope,
            context=context,
            attempt_count=self._max_attempts,
            error_code=error_code,
            raw_sha256=raw_sha256,
        )
        self._consumer.commit(message=message, asynchronous=False)
        return "dlq"

    def close(self) -> None:
        self._handler.heartbeat("stopped")
        self._consumer.close()
        self._dlq_producer.flush(10)

    def _send_to_dlq(
        self,
        *,
        event_id: str,
        envelope: EventEnvelope | None,
        context: KafkaMessageContext,
        attempt_count: int,
        error_code: str,
        raw_sha256: str,
    ) -> None:
        dlq_message = {
            "event_id": event_id,
            "source_topic": context.topic,
            "source_partition": context.partition,
            "source_offset": context.offset,
            "error_code": error_code[:128],
            "attempt_count": attempt_count,
            "raw_sha256": raw_sha256,
        }
        if envelope is not None:
            try:
                dlq_message["safe_event"] = {
                    **asdict(envelope),
                    "payload": validate_agent_run_event(envelope),
                }
            except EventContractError:
                pass
        self._dlq_producer.produce(
            f"{context.topic}.dlq",
            key=event_id,
            value=json.dumps(dlq_message, sort_keys=True),
        )
        self._dlq_producer.poll(0)
        remaining = self._dlq_producer.flush(10)
        if isinstance(remaining, int) and remaining > 0:
            raise RuntimeError("kafka_dlq_delivery_timeout")
        self._handler.record_dlq(
            event_id=event_id,
            envelope=envelope,
            context=context,
            attempt_count=attempt_count,
            error_code=error_code,
            raw_sha256=raw_sha256,
        )


def validate_agent_run_event(envelope: EventEnvelope) -> dict[str, Any]:
    if envelope.event_type == RUN_COMPLETED_EVENT_TYPE:
        return validate_agent_run_completed(envelope)
    if envelope.event_type == RUN_FAILED_EVENT_TYPE:
        return validate_agent_run_failed(envelope)
    raise EventContractError("event_type_not_supported")


def validate_agent_run_completed(envelope: EventEnvelope) -> dict[str, Any]:
    if envelope.event_type != RUN_COMPLETED_EVENT_TYPE:
        raise EventContractError("event_type_not_supported")
    if envelope.schema_version != 1:
        raise EventContractError("event_schema_version_not_supported")
    payload = envelope.payload
    required_fields = {
        "run_id",
        "status",
        "total_tokens",
        "total_estimated_cost_usd",
    }
    optional_fields = {"execution_outcome", "answer_generated"}
    if not required_fields.issubset(payload) or not set(payload).issubset(
        required_fields | optional_fields
    ):
        raise EventContractError("event_payload_fields_invalid")
    run_id = payload.get("run_id")
    total_tokens = payload.get("total_tokens")
    cost = payload.get("total_estimated_cost_usd")
    status = payload.get("status")
    execution_outcome = payload.get("execution_outcome")
    answer_generated = payload.get("answer_generated")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 0:
        raise EventContractError("event_run_id_invalid")
    if str(run_id) != envelope.aggregate_id:
        raise EventContractError("event_aggregate_id_mismatch")
    if not isinstance(status, str) or not status.strip() or len(status) > 32:
        raise EventContractError("event_run_status_invalid")
    if (
        isinstance(total_tokens, bool)
        or not isinstance(total_tokens, int)
        or total_tokens < 0
    ):
        raise EventContractError("event_total_tokens_invalid")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
        raise EventContractError("event_cost_invalid")
    if execution_outcome is not None and (
        not isinstance(execution_outcome, str)
        or not execution_outcome.strip()
        or len(execution_outcome) > 64
    ):
        raise EventContractError("event_execution_outcome_invalid")
    if answer_generated is not None and not isinstance(answer_generated, bool):
        raise EventContractError("event_answer_generated_invalid")
    summary = {
        "run_id": run_id,
        "status": status.strip(),
        "total_tokens": total_tokens,
        "total_estimated_cost_usd": round(float(cost), 6),
    }
    if execution_outcome is not None:
        summary["execution_outcome"] = execution_outcome.strip()
    if answer_generated is not None:
        summary["answer_generated"] = answer_generated
    return summary


def validate_agent_run_failed(envelope: EventEnvelope) -> dict[str, Any]:
    if envelope.event_type != RUN_FAILED_EVENT_TYPE:
        raise EventContractError("event_type_not_supported")
    if envelope.schema_version != 1:
        raise EventContractError("event_schema_version_not_supported")
    payload = envelope.payload
    required_fields = {
        "run_id",
        "status",
        "error_code",
        "failure_stage",
        "provider",
        "model",
        "total_tokens",
        "total_estimated_cost_usd",
    }
    if set(payload) != required_fields:
        raise EventContractError("event_payload_fields_invalid")
    run_id = _validated_run_id(payload.get("run_id"), envelope.aggregate_id)
    status = _validated_bounded_string(
        payload.get("status"),
        code="event_run_status_invalid",
        maximum=32,
    )
    if status != "failed":
        raise EventContractError("event_run_status_invalid")
    error_code = _validated_bounded_string(
        payload.get("error_code"),
        code="event_failure_code_invalid",
        maximum=64,
    )
    if error_code not in MODEL_FAILURE_CODES:
        raise EventContractError("event_failure_code_invalid")
    failure_stage = _validated_bounded_string(
        payload.get("failure_stage"),
        code="event_failure_stage_invalid",
        maximum=64,
    )
    if failure_stage != "answer_model":
        raise EventContractError("event_failure_stage_invalid")
    provider = _validated_bounded_string(
        payload.get("provider"),
        code="event_provider_invalid",
        maximum=64,
    )
    model = _validated_bounded_string(
        payload.get("model"),
        code="event_model_invalid",
        maximum=128,
    )
    total_tokens = _validated_total_tokens(payload.get("total_tokens"))
    cost = _validated_cost(payload.get("total_estimated_cost_usd"))
    return {
        "run_id": run_id,
        "status": status,
        "error_code": error_code,
        "failure_stage": failure_stage,
        "provider": provider,
        "model": model,
        "total_tokens": total_tokens,
        "total_estimated_cost_usd": round(cost, 6),
    }


def _validated_run_id(value: Any, aggregate_id: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EventContractError("event_run_id_invalid")
    if str(value) != aggregate_id:
        raise EventContractError("event_aggregate_id_mismatch")
    return value


def _validated_total_tokens(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EventContractError("event_total_tokens_invalid")
    return value


def _validated_cost(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise EventContractError("event_cost_invalid")
    return float(value)


def _validated_bounded_string(value: Any, *, code: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise EventContractError(code)
    return value.strip()


def build_consumer(settings: Settings) -> KafkaAuditMetricsConsumer:
    if not settings.kafka_bootstrap_servers:
        raise RuntimeError("ARGUS_KAFKA_BOOTSTRAP_SERVERS is required")
    from confluent_kafka import Consumer, Producer

    auth = kafka_auth_config(
        security_protocol=settings.kafka_security_protocol,
        sasl_mechanism=settings.kafka_sasl_mechanism,
        aws_region=settings.aws_region,
    )
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "client.id": f"{settings.kafka_client_id}-audit-consumer",
            "group.id": settings.kafka_consumer_group,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
            # Local Kafka auto-creates a newly versioned topic on first publish.
            # Refresh quickly enough that the already-running consumer discovers it
            # within the bounded acceptance window rather than the 5-minute default.
            "topic.metadata.refresh.interval.ms": 10_000,
            **auth,
        }
    )
    producer = Producer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "client.id": f"{settings.kafka_client_id}-dlq-producer",
            "enable.idempotence": True,
            "acks": "all",
            **auth,
        }
    )
    session_factory = make_session_factory(make_engine(settings))
    return KafkaAuditMetricsConsumer(
        consumer=consumer,
        dlq_producer=producer,
        handler=AuditMetricsHandler(
            session_factory,
            consumer_group=settings.kafka_consumer_group,
            retention_count=settings.kafka_audit_retention_count,
            retention_days=settings.kafka_audit_retention_days,
        ),
        max_attempts=settings.kafka_consumer_max_attempts,
        retry_backoff_seconds=settings.kafka_consumer_retry_backoff_ms / 1000,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    runtime = build_consumer(settings)
    health_file = Path(settings.event_consumer_health_file)
    _touch_health_file(health_file)
    stopping = False

    def stop(*_args) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logger.info("Argus Kafka audit/metrics consumer started")
    try:
        while not stopping:
            try:
                runtime.run_once(
                    timeout_seconds=settings.kafka_consumer_poll_timeout_ms / 1000
                )
            except Exception:
                logger.exception("Kafka audit/metrics consumer iteration failed")
                time.sleep(1)
            finally:
                _touch_health_file(health_file)
    finally:
        runtime.close()


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _touch_health_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def _is_retriable_kafka_error(error: Any) -> bool:
    retriable = getattr(error, "retriable", None)
    if callable(retriable) and retriable():
        return True
    # librdkafka code 3 is UNKNOWN_TOPIC_OR_PARTITION. During a clean local
    # startup, the subscriber can see it briefly before the first producer
    # auto-creates the versioned event topic.
    return getattr(error, "code", lambda: None)() == 3


if __name__ == "__main__":
    main()
