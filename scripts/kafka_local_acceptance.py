#!/usr/bin/env python3
"""Exercise Argus's real Kafka consumer, dedupe, and DLQ path."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from typing import Any
from urllib.request import Request, urlopen
from uuid import uuid4

from confluent_kafka import Producer

from investment_agent.cloud import EventEnvelope
from investment_agent.cloud.events import kafka_auth_config
from investment_agent.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", default="localhost:29092")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--timeout-seconds", type=float, default=45)
    parser.add_argument(
        "--verify-api-publisher",
        action="store_true",
        help=(
            "Also create a local Research Run. Requires at least one indexed source "
            "and leaves that Run in the active database."
        ),
    )
    args = parser.parse_args()

    baseline = read_dashboard(args.api_base)
    event_id = f"kafka-acceptance-{uuid4()}"
    event = EventEnvelope(
        event_type="agent.run.completed.v1",
        aggregate_id="0",
        event_id=event_id,
        payload={
            "run_id": 0,
            "status": "acceptance_test",
            "total_tokens": 0,
            "total_estimated_cost_usd": 0.0,
        },
    )
    failed_event_id = f"kafka-failure-acceptance-{uuid4()}"
    failed_event = EventEnvelope(
        event_type="agent.run.failed.v1",
        aggregate_id="0",
        event_id=failed_event_id,
        payload={
            "run_id": 0,
            "status": "failed",
            "error_code": "provider_timeout",
            "failure_stage": "answer_model",
            "provider": "acceptance-test",
            "model": "synthetic-no-cost-model",
            "total_tokens": 0,
            "total_estimated_cost_usd": 0.0,
        },
    )
    settings = get_settings()
    producer = Producer(
        {
            "bootstrap.servers": args.bootstrap,
            "client.id": "argus-kafka-acceptance",
            "enable.idempotence": True,
            "acks": "all",
            **kafka_auth_config(
                security_protocol=settings.kafka_security_protocol,
                sasl_mechanism=settings.kafka_sasl_mechanism,
                aws_region=settings.aws_region,
            ),
        }
    )
    for _ in range(2):
        producer.produce(event.topic, key=event.aggregate_id, value=event.to_json())
    producer.produce(
        failed_event.topic,
        key=failed_event.aggregate_id,
        value=failed_event.to_json(),
    )
    producer.produce(
        event.topic,
        key="invalid-contract",
        value=f"invalid-kafka-acceptance-{uuid4()}",
    )
    remaining = producer.flush(10)
    if remaining:
        raise SystemExit(f"Kafka delivery timed out with {remaining} message(s) pending")

    deadline = time.monotonic() + args.timeout_seconds
    while time.monotonic() < deadline:
        current = read_dashboard(args.api_base)
        if acceptance_visible(
            baseline,
            current,
            event_ids={event_id, failed_event_id},
        ):
            accepted_events = [
                item
                for item in current.get("recent_events", [])
                if isinstance(item, dict)
                and item.get("event_id") in {event_id, failed_event_id}
            ]
            result = {
                "status": "passed",
                "event": asdict(event),
                "failed_event": asdict(failed_event),
                "consumer_status": current["consumer_status"],
                "offsets": [
                    {
                        "topic": item.get("topic"),
                        "partition": item.get("partition"),
                        "message_offset": item.get("message_offset"),
                    }
                    for item in accepted_events
                ],
                "processed_delta": (
                    current["processed_count"] - baseline["processed_count"]
                ),
                "duplicate_delta": (
                    current["duplicate_count"] - baseline["duplicate_count"]
                ),
                "dlq_delta": current["dlq_count"] - baseline["dlq_count"],
            }
            if args.verify_api_publisher:
                result["api_publisher"] = verify_api_publisher(
                    args.api_base,
                    timeout_seconds=args.timeout_seconds,
                )
            print(json.dumps(result, indent=2, sort_keys=True))
            return
        time.sleep(1)
    raise SystemExit(
        "Kafka acceptance timed out. Inspect `docker compose -f compose.yaml "
        "-f compose.v2.yaml logs event-consumer kafka backend`."
    )


def read_dashboard(api_base: str) -> dict[str, Any]:
    with urlopen(f"{api_base.rstrip('/')}/runs?limit=1", timeout=5) as response:
        dashboard = json.load(response)
    pipeline = dashboard.get("event_pipeline")
    if not isinstance(pipeline, dict):
        raise SystemExit("The API does not expose event_pipeline on /runs")
    return pipeline


def verify_api_publisher(api_base: str, *, timeout_seconds: float) -> dict[str, Any]:
    baseline = read_dashboard(api_base)
    request = Request(
        f"{api_base.rstrip('/')}/chat/query",
        data=json.dumps(
            {
                "query": "Why should a source-backed research claim include citations?",
                "evidence_scope": "indexed",
                "selection_mode": "auto",
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        query_result = json.load(response)
    run_id = query_result.get("run_id")
    if not isinstance(run_id, int):
        raise SystemExit("The chat acceptance request did not return a Run ID")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        current = read_dashboard(api_base)
        matching = [
            item
            for item in current.get("recent_events", [])
            if isinstance(item, dict) and item.get("aggregate_id") == str(run_id)
        ]
        if (
            current.get("processed_count", 0)
            >= baseline.get("processed_count", 0) + 1
            and matching
        ):
            return {
                "status": "passed",
                "run_id": run_id,
                "event_status": matching[0].get("status"),
            }
        time.sleep(1)
    raise SystemExit(
        f"Run {run_id} completed, but its Kafka audit event did not become visible"
    )


def acceptance_visible(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    event_ids: set[str],
) -> bool:
    recent_ids = {
        item.get("event_id")
        for item in current.get("recent_events", [])
        if isinstance(item, dict)
    }
    return bool(
        current.get("consumer_status") == "running"
        and current.get("processed_count", 0) >= baseline.get("processed_count", 0) + 2
        and current.get("completed_count", 0) >= baseline.get("completed_count", 0) + 1
        and current.get("failed_count", 0) >= baseline.get("failed_count", 0) + 1
        and current.get("duplicate_count", 0) >= baseline.get("duplicate_count", 0) + 1
        and current.get("dlq_count", 0) >= baseline.get("dlq_count", 0) + 1
        and event_ids.issubset(recent_ids)
    )


if __name__ == "__main__":
    main()
