from __future__ import annotations

import json
from pathlib import Path

import pytest

from investment_agent.cloud import (
    EventEnvelope,
    InMemoryCacheStore,
    InMemoryEventPublisher,
    Job,
    JobStatus,
    KafkaEventPublisher,
    LocalArtifactStore,
    RedisCacheStore,
    RedisJobQueue,
    S3ArtifactStore,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values = {}
        self.lists = {}
        self.hashes = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        del ttl
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)

    def ping(self):
        return True

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def brpop(self, key, timeout):
        del timeout
        values = self.lists.get(key, [])
        return (key, values.pop()) if values else None

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    def expire(self, key, ttl):
        del key, ttl

    def hgetall(self, key):
        return self.hashes.get(key, {})


def test_cache_stores_have_matching_json_contract() -> None:
    stores = [
        InMemoryCacheStore(),
        RedisCacheStore("redis://unused", client=FakeRedis()),
    ]

    for store in stores:
        store.set_json("key", {"value": 7}, ttl_seconds=60)
        assert store.get_json("key") == {"value": 7}
        assert store.ping()
        store.delete("key")
        assert store.get_json("key") is None


def test_redis_job_queue_tracks_transitions() -> None:
    queue = RedisJobQueue("redis://unused", client=FakeRedis())
    job = Job(job_type="healthcheck.v1", payload={})

    queue.enqueue(job)
    assert queue.get_status(job.job_id) == {"status": "queued", "detail": ""}
    assert queue.dequeue(timeout_seconds=0) == job
    queue.set_status(job.job_id, JobStatus.COMPLETE, "ok")
    assert queue.get_status(job.job_id) == {"status": "complete", "detail": "ok"}


def test_redis_job_queue_treats_blocking_read_timeout_as_empty_queue() -> None:
    class TimeoutRedis(FakeRedis):
        def brpop(self, key, timeout):
            del key, timeout
            raise TimeoutError("blocking read elapsed")

    queue = RedisJobQueue("redis://unused", client=TimeoutRedis())

    assert queue.dequeue(timeout_seconds=5) is None


def test_event_envelope_and_publishers_use_versioned_contract() -> None:
    event = EventEnvelope(
        event_type="agent.run.completed.v1",
        aggregate_id="42",
        payload={"status": "complete"},
    )
    memory = InMemoryEventPublisher()
    memory.publish(event)

    assert event.topic == "agent.run.completed.v1"
    assert event.schema_version == 1
    assert memory.events == [event]

    class FakeProducer:
        def __init__(self):
            self.messages = []

        def produce(self, topic, key, value):
            self.messages.append((topic, key, json.loads(value)))

        def poll(self, timeout):
            assert timeout == 0

        def flush(self, timeout):
            assert timeout == 10

    producer = FakeProducer()
    publisher = KafkaEventPublisher("unused", producer=producer)
    publisher.publish(event)
    publisher.close()
    assert producer.messages[0][0:2] == ("agent.run.completed.v1", "42")
    assert producer.messages[0][2]["event_id"] == event.event_id


def test_local_artifact_store_puts_and_deletes_inside_root(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")

    uri = store.put_bytes("raw/source.md", b"evidence", content_type="text/markdown")

    assert Path(uri.removeprefix("file://")).read_bytes() == b"evidence"
    store.delete("raw/source.md")
    assert not (tmp_path / "artifacts" / "raw" / "source.md").exists()


def test_local_artifact_store_streams_from_file(tmp_path) -> None:
    source = tmp_path / "source.md"
    source.write_bytes(b"streamed evidence")
    store = LocalArtifactStore(tmp_path / "artifacts")

    uri = store.put_file("raw/source.md", source, content_type="text/markdown")

    assert Path(uri.removeprefix("file://")).read_bytes() == b"streamed evidence"


def test_local_artifact_store_rejects_path_traversal(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")

    with pytest.raises(ValueError, match="inside the artifact root"):
        store.put_bytes("../escape.md", b"nope", content_type="text/markdown")


def test_s3_artifact_store_enforces_encryption_and_deletes() -> None:
    class FakeS3:
        def __init__(self):
            self.request = None
            self.delete_request = None

        def put_object(self, **kwargs):
            self.request = kwargs

        def delete_object(self, **kwargs):
            self.delete_request = kwargs

    client = FakeS3()
    store = S3ArtifactStore("argus-bucket", prefix="prod", client=client)

    uri = store.put_bytes("raw/source.md", b"evidence", content_type="text/markdown")

    assert uri == "s3://argus-bucket/prod/raw/source.md"
    assert client.request["ServerSideEncryption"] == "AES256"
    store.delete("raw/source.md")
    assert client.delete_request == {
        "Bucket": "argus-bucket",
        "Key": "prod/raw/source.md",
    }
