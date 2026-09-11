from __future__ import annotations

from pathlib import Path

import pytest

from investment_agent.event_consumer import _touch_health_file
from investment_agent.kafka_topic_bootstrap import topic_specs
from investment_agent.migration_check import verify_migration_heads
from scripts.aws_sync_runtime_secret import _build_runtime_values


def test_topic_bootstrap_defines_event_retry_and_dlq_topics() -> None:
    specs = topic_specs(
        partitions=1,
        replication_factor=3,
        event_retention_ms=604_800_000,
        retry_retention_ms=86_400_000,
        dlq_retention_ms=604_800_000,
    )

    assert {spec.name for spec in specs} == {
        "agent.run.completed.v1",
        "agent.run.completed.v1.retry",
        "agent.run.completed.v1.dlq",
        "agent.run.failed.v1",
        "agent.run.failed.v1.retry",
        "agent.run.failed.v1.dlq",
    }
    assert all(spec.partitions == 1 for spec in specs)
    assert all(spec.replication_factor == 3 for spec in specs)
    assert {
        spec.retention_ms for spec in specs if spec.name.endswith(".retry")
    } == {86_400_000}


def test_migration_check_requires_database_and_image_heads_to_match() -> None:
    verify_migration_heads(("20260722_0022",), ("20260722_0022",))

    with pytest.raises(RuntimeError, match="do not match"):
        verify_migration_heads(("20260721_0021",), ("20260722_0022",))


def test_runtime_secret_sync_keeps_only_authorized_provider_keys() -> None:
    current = {
        "ARGUS_DATABASE_URL": "database",
        "ARGUS_REDIS_URL": "redis",
        "ARGUS_S3_BUCKET": "bucket",
        "ARGUS_KAFKA_BOOTSTRAP_SERVERS": "broker",
        "ARGUS_KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
        "ARGUS_KAFKA_SASL_MECHANISM": "OAUTHBEARER",
        "ARGUS_DEEPSEEK_API_KEY": "must-not-survive",
    }
    env_values = {
        "ARGUS_GEMINI_API_KEY": "gemini",
        "ARGUS_EXA_API_KEY": "exa",
        "ARGUS_OPENAI_API_KEY": "must-not-sync",
    }

    result = _build_runtime_values(current, env_values)

    assert result["ARGUS_GEMINI_API_KEY"] == "gemini"
    assert result["ARGUS_EXA_API_KEY"] == "exa"
    assert "ARGUS_DEEPSEEK_API_KEY" not in result
    assert "ARGUS_OPENAI_API_KEY" not in result


def test_runtime_secret_sync_requires_exa_for_cloud_smoke() -> None:
    current = {
        "ARGUS_DATABASE_URL": "database",
        "ARGUS_REDIS_URL": "redis",
        "ARGUS_S3_BUCKET": "bucket",
        "ARGUS_KAFKA_BOOTSTRAP_SERVERS": "broker",
        "ARGUS_KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
        "ARGUS_KAFKA_SASL_MECHANISM": "OAUTHBEARER",
    }

    with pytest.raises(RuntimeError, match="ARGUS_EXA_API_KEY"):
        _build_runtime_values(current, {"ARGUS_GEMINI_API_KEY": "gemini"})


def test_event_consumer_health_file_is_touchable(tmp_path: Path) -> None:
    health_file = tmp_path / "consumer.live"

    _touch_health_file(health_file)

    assert health_file.is_file()
