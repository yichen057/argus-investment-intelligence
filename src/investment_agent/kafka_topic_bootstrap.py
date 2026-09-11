from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Protocol

from investment_agent.cloud.events import kafka_auth_config
from investment_agent.config import get_settings
from investment_agent.event_consumer import AUDIT_TOPICS


@dataclass(frozen=True)
class TopicSpec:
    name: str
    partitions: int
    replication_factor: int
    retention_ms: int


class AdminClientProtocol(Protocol):
    def create_topics(
        self,
        topics: list[Any],
        *,
        request_timeout: float,
    ) -> dict[str, Any]: ...

    def list_topics(self, topic: str, *, timeout: float) -> Any: ...

    def describe_configs(
        self,
        resources: list[Any],
        *,
        request_timeout: float,
    ) -> dict[Any, Any]: ...


def topic_specs(
    *,
    partitions: int,
    replication_factor: int,
    event_retention_ms: int,
    retry_retention_ms: int,
    dlq_retention_ms: int,
) -> tuple[TopicSpec, ...]:
    specs: list[TopicSpec] = []
    for topic in AUDIT_TOPICS:
        specs.extend(
            (
                TopicSpec(
                    name=topic,
                    partitions=partitions,
                    replication_factor=replication_factor,
                    retention_ms=event_retention_ms,
                ),
                TopicSpec(
                    name=f"{topic}.retry",
                    partitions=partitions,
                    replication_factor=replication_factor,
                    retention_ms=retry_retention_ms,
                ),
                TopicSpec(
                    name=f"{topic}.dlq",
                    partitions=partitions,
                    replication_factor=replication_factor,
                    retention_ms=dlq_retention_ms,
                ),
            )
        )
    return tuple(specs)


def bootstrap_topics(
    admin: AdminClientProtocol,
    specs: tuple[TopicSpec, ...],
    *,
    timeout_seconds: float,
) -> list[str]:
    from confluent_kafka import KafkaError, KafkaException
    from confluent_kafka.admin import ConfigResource, NewTopic, ResourceType

    requests = [
        NewTopic(
            spec.name,
            num_partitions=spec.partitions,
            replication_factor=spec.replication_factor,
            config={
                "cleanup.policy": "delete",
                "retention.ms": str(spec.retention_ms),
            },
        )
        for spec in specs
    ]
    futures = admin.create_topics(requests, request_timeout=timeout_seconds)
    outcomes: list[str] = []
    for spec in specs:
        try:
            futures[spec.name].result(timeout=timeout_seconds)
            outcomes.append(f"{spec.name}:created")
        except KafkaException as exc:
            error = exc.args[0] if exc.args else None
            if getattr(error, "code", lambda: None)() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise
            outcomes.append(f"{spec.name}:existing")

    config_resources = [
        ConfigResource(ResourceType.TOPIC, spec.name) for spec in specs
    ]
    config_futures = admin.describe_configs(
        config_resources,
        request_timeout=timeout_seconds,
    )
    for spec, resource in zip(specs, config_resources, strict=True):
        metadata = admin.list_topics(spec.name, timeout=timeout_seconds)
        topic_metadata = metadata.topics.get(spec.name)
        if topic_metadata is None or topic_metadata.error is not None:
            raise RuntimeError(f"Kafka topic {spec.name} is not available")
        actual_partitions = len(topic_metadata.partitions)
        if actual_partitions != spec.partitions:
            raise RuntimeError(
                f"Kafka topic {spec.name} has {actual_partitions} partitions; "
                f"expected {spec.partitions}"
            )
        config = config_futures[resource].result(timeout=timeout_seconds)
        actual_retention = config["retention.ms"].value
        if actual_retention != str(spec.retention_ms):
            raise RuntimeError(
                f"Kafka topic {spec.name} retention.ms is {actual_retention}; "
                f"expected {spec.retention_ms}"
            )
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Idempotently create and verify Argus Kafka topics."
    )
    parser.add_argument("--partitions", type=int, default=1)
    parser.add_argument("--replication-factor", type=int, default=3)
    parser.add_argument("--event-retention-ms", type=int, default=604_800_000)
    parser.add_argument("--retry-retention-ms", type=int, default=86_400_000)
    parser.add_argument("--dlq-retention-ms", type=int, default=604_800_000)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    args = parser.parse_args()
    for name in (
        "partitions",
        "replication_factor",
        "event_retention_ms",
        "retry_retention_ms",
        "dlq_retention_ms",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be greater than zero")

    settings = get_settings()
    if not settings.kafka_bootstrap_servers:
        raise RuntimeError("ARGUS_KAFKA_BOOTSTRAP_SERVERS is required")
    from confluent_kafka.admin import AdminClient

    admin = AdminClient(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "client.id": f"{settings.kafka_client_id}-topic-bootstrap",
            **kafka_auth_config(
                security_protocol=settings.kafka_security_protocol,
                sasl_mechanism=settings.kafka_sasl_mechanism,
                aws_region=settings.aws_region,
            ),
        }
    )
    specs = topic_specs(
        partitions=args.partitions,
        replication_factor=args.replication_factor,
        event_retention_ms=args.event_retention_ms,
        retry_retention_ms=args.retry_retention_ms,
        dlq_retention_ms=args.dlq_retention_ms,
    )
    outcomes = bootstrap_topics(
        admin,
        specs,
        timeout_seconds=args.timeout_seconds,
    )
    for outcome in outcomes:
        print(outcome)
    print(f"Verified {len(specs)} Kafka topics.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
