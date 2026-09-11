from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


class CacheStore(Protocol):
    def get_json(self, key: str) -> dict[str, Any] | None: ...

    def set_json(self, key: str, value: dict[str, Any], *, ttl_seconds: int) -> None: ...

    def delete(self, key: str) -> None: ...

    def ping(self) -> bool: ...


@dataclass
class InMemoryCacheStore:
    values: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get_json(self, key: str) -> dict[str, Any] | None:
        value = self.values.get(key)
        return dict(value) if value is not None else None

    def set_json(self, key: str, value: dict[str, Any], *, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Cache TTL must be positive")
        self.values[key] = dict(value)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def ping(self) -> bool:
        return True


class RedisCacheStore:
    def __init__(self, url: str, *, client: Any | None = None) -> None:
        if client is None:
            from redis import Redis

            client = Redis.from_url(url, decode_responses=True)
        self._client = client

    def get_json(self, key: str) -> dict[str, Any] | None:
        raw = self._client.get(key)
        if raw is None:
            return None
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Cached JSON value must be an object")
        return value

    def set_json(self, key: str, value: dict[str, Any], *, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Cache TTL must be positive")
        self._client.setex(key, ttl_seconds, json.dumps(value, sort_keys=True))

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def ping(self) -> bool:
        return bool(self._client.ping())


def make_cache_store(url: str | None) -> CacheStore:
    if url:
        return RedisCacheStore(url)
    return InMemoryCacheStore()
