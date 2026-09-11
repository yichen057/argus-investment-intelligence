from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4


def _is_redis_timeout(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    try:
        from redis.exceptions import TimeoutError as RedisTimeoutError
    except ImportError:
        return False
    return isinstance(exc, RedisTimeoutError)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class Job:
    job_type: str
    payload: dict[str, Any]
    job_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    attempt: int = 0


class JobQueue(Protocol):
    def enqueue(self, job: Job) -> None: ...

    def dequeue(self, *, timeout_seconds: int = 5) -> Job | None: ...

    def set_status(self, job_id: str, status: JobStatus, detail: str = "") -> None: ...

    def get_status(self, job_id: str) -> dict[str, str] | None: ...


class RedisJobQueue:
    def __init__(self, url: str, *, queue_name: str = "argus:jobs", client: Any = None):
        if client is None:
            from redis import Redis

            client = Redis.from_url(url, decode_responses=True)
        self._client = client
        self._queue_name = queue_name

    def enqueue(self, job: Job) -> None:
        self._client.lpush(self._queue_name, json.dumps(asdict(job), sort_keys=True))
        self.set_status(job.job_id, JobStatus.QUEUED)

    def dequeue(self, *, timeout_seconds: int = 5) -> Job | None:
        try:
            item = self._client.brpop(self._queue_name, timeout=timeout_seconds)
        except Exception as exc:
            if _is_redis_timeout(exc):
                return None
            raise
        if item is None:
            return None
        _, raw = item
        return Job(**json.loads(raw))

    def set_status(self, job_id: str, status: JobStatus, detail: str = "") -> None:
        key = f"argus:job:{job_id}"
        self._client.hset(key, mapping={"status": status.value, "detail": detail})
        self._client.expire(key, 86_400)

    def get_status(self, job_id: str) -> dict[str, str] | None:
        value = self._client.hgetall(f"argus:job:{job_id}")
        return value or None
