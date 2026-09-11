from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "infra" / "k8s" / "overlays" / "kind"


def test_kind_overlay_is_local_single_node_and_has_no_committed_secret() -> None:
    rendered_sources = "\n".join(
        path.read_text() for path in sorted(OVERLAY.glob("*.yaml"))
    )

    assert "ARGUS_ENABLE_CLOUD_SERVICES: \"false\"" in rendered_sources
    assert "ARGUS_KAFKA_BOOTSTRAP_SERVERS: argus-kafka:9092" in rendered_sources
    assert "ARGUS_REDIS_URL: redis://argus-redis:6379/0" in rendered_sources
    assert "KIND_IMAGE_TAG" in rendered_sources
    assert "kind: Secret" not in rendered_sources


def test_kind_topic_bootstrap_waits_for_kafka_and_uses_one_replica() -> None:
    bootstrap = (OVERLAY / "kafka-topic-bootstrap.yaml").read_text()

    assert "name: wait-for-kafka" in bootstrap
    assert "--bootstrap-server argus-kafka:9092 --list" in bootstrap
    assert "- --replication-factor\n            - \"1\"" in bootstrap


def test_kind_script_guards_context_and_generates_runtime_secrets() -> None:
    script = (ROOT / "scripts" / "kind_local.sh").read_text()

    assert 'readonly CONTEXT_NAME="kind-${CLUSTER_NAME}"' in script
    assert "Refusing to continue: kubectl context" in script
    assert "openssl rand -hex 24" in script
    assert "ARGUS_KIND_SKIP_BUILD" in script
    assert "kubectl config use-context" in script
