"""Cloud-ready infrastructure adapters with in-memory local fallbacks."""

from investment_agent.cloud.artifacts import (
    ArtifactStore,
    LocalArtifactStore,
    S3ArtifactStore,
    make_artifact_store,
)
from investment_agent.cloud.cache import (
    CacheStore,
    InMemoryCacheStore,
    RedisCacheStore,
    make_cache_store,
)
from investment_agent.cloud.events import (
    EventContractError,
    EventEnvelope,
    EventPublisher,
    InMemoryEventPublisher,
    KafkaEventPublisher,
    make_event_publisher,
)
from investment_agent.cloud.jobs import Job, JobQueue, JobStatus, RedisJobQueue

__all__ = [
    "ArtifactStore",
    "CacheStore",
    "EventEnvelope",
    "EventContractError",
    "EventPublisher",
    "InMemoryCacheStore",
    "InMemoryEventPublisher",
    "Job",
    "JobQueue",
    "JobStatus",
    "KafkaEventPublisher",
    "LocalArtifactStore",
    "RedisCacheStore",
    "RedisJobQueue",
    "S3ArtifactStore",
    "make_artifact_store",
    "make_cache_store",
    "make_event_publisher",
]
