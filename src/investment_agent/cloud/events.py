from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4


class EventContractError(ValueError):
    pass


MAX_EVENT_ENVELOPE_BYTES = 64 * 1024
EVENT_ENVELOPE_FIELDS = {
    "event_type",
    "aggregate_id",
    "payload",
    "event_id",
    "occurred_at",
    "schema_version",
}


@dataclass(frozen=True)
class EventEnvelope:
    event_type: str
    aggregate_id: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: int = 1

    @property
    def topic(self) -> str:
        return self.event_type

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, raw: bytes | str) -> EventEnvelope:
        raw_size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
        if raw_size > MAX_EVENT_ENVELOPE_BYTES:
            raise EventContractError("event_envelope_too_large")
        try:
            decoded = json.loads(raw)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EventContractError("event_json_invalid") from exc
        if not isinstance(decoded, dict):
            raise EventContractError("event_envelope_not_object")
        if set(decoded) != EVENT_ENVELOPE_FIELDS:
            raise EventContractError("event_envelope_fields_invalid")

        event_type = _bounded_string(decoded.get("event_type"), "event_type", 128)
        aggregate_id = _bounded_string(
            decoded.get("aggregate_id"), "aggregate_id", 128
        )
        event_id = _bounded_string(decoded.get("event_id"), "event_id", 128)
        occurred_at = _bounded_string(decoded.get("occurred_at"), "occurred_at", 64)
        try:
            parsed_occurred_at = datetime.fromisoformat(
                occurred_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise EventContractError("event_occurred_at_invalid") from exc
        if parsed_occurred_at.tzinfo is None:
            raise EventContractError("event_occurred_at_timezone_required")
        schema_version = decoded.get("schema_version")
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise EventContractError("event_schema_version_invalid")
        payload = decoded.get("payload")
        if not isinstance(payload, dict):
            raise EventContractError("event_payload_not_object")
        return cls(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
            event_id=event_id,
            occurred_at=occurred_at,
            schema_version=schema_version,
        )


class EventPublisher(Protocol):
    def publish(self, event: EventEnvelope) -> None: ...

    def close(self) -> None: ...


@dataclass
class InMemoryEventPublisher:
    events: list[EventEnvelope] = field(default_factory=list)

    def publish(self, event: EventEnvelope) -> None:
        self.events.append(event)

    def close(self) -> None:
        return None


class KafkaEventPublisher:
    def __init__(
        self,
        bootstrap_servers: str,
        *,
        client_id: str = "argus",
        security_protocol: str = "PLAINTEXT",
        sasl_mechanism: str | None = None,
        aws_region: str = "us-west-2",
        producer: Any | None = None,
    ) -> None:
        if producer is None:
            from confluent_kafka import Producer

            config: dict[str, Any] = {
                "bootstrap.servers": bootstrap_servers,
                "client.id": client_id,
                "enable.idempotence": True,
                "acks": "all",
                "security.protocol": security_protocol,
            }
            config.update(
                kafka_auth_config(
                    security_protocol=security_protocol,
                    sasl_mechanism=sasl_mechanism,
                    aws_region=aws_region,
                )
            )
            producer = Producer(config)
        self._producer = producer

    def publish(self, event: EventEnvelope) -> None:
        self._producer.produce(
            event.topic,
            key=event.aggregate_id,
            value=event.to_json(),
        )
        self._producer.poll(0)

    def close(self) -> None:
        self._producer.flush(10)


def make_event_publisher(
    bootstrap_servers: str | None,
    *,
    client_id: str = "argus",
    security_protocol: str = "PLAINTEXT",
    sasl_mechanism: str | None = None,
    aws_region: str = "us-west-2",
) -> EventPublisher:
    if bootstrap_servers:
        return KafkaEventPublisher(
            bootstrap_servers,
            client_id=client_id,
            security_protocol=security_protocol,
            sasl_mechanism=sasl_mechanism,
            aws_region=aws_region,
        )
    return InMemoryEventPublisher()


def kafka_auth_config(
    *,
    security_protocol: str,
    sasl_mechanism: str | None,
    aws_region: str,
) -> dict[str, Any]:
    config: dict[str, Any] = {"security.protocol": security_protocol}
    if sasl_mechanism:
        config["sasl.mechanism"] = sasl_mechanism
    if sasl_mechanism == "OAUTHBEARER":
        from aws_msk_iam_sasl_signer import MSKAuthTokenProvider

        def oauth_callback(_config):
            token, expiry_ms = MSKAuthTokenProvider.generate_auth_token(aws_region)
            return token, expiry_ms / 1000

        config["oauth_cb"] = oauth_callback
    return config


def _bounded_string(value: Any, field_name: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EventContractError(f"event_{field_name}_invalid")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise EventContractError(f"event_{field_name}_too_long")
    return normalized
