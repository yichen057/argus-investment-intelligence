from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping, Protocol, Sequence


class SourceStatus(StrEnum):
    DISABLED = "disabled"
    DISCONNECTED = "disconnected"
    AUTH_REQUIRED = "auth_required"
    READY = "ready"
    STALE = "stale"
    DEGRADED = "degraded"
    FAILED = "failed"


class ProviderErrorCode(StrEnum):
    DISABLED = "disabled"
    AUTH_REQUIRED = "auth_required"
    AUTH_EXPIRED = "auth_expired"
    CAPABILITY_DRIFT = "capability_drift"
    DENIED_TOOL = "denied_tool"
    INVALID_RESPONSE = "invalid_response"
    PARTIAL_RESPONSE = "partial_response"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


class ProviderError(RuntimeError):
    def __init__(self, code: ProviderErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class HistoricalBar:
    symbol: str
    begins_at: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    session: str | None = None


@dataclass(frozen=True)
class SyncResult:
    source_key: str
    source_scope: str
    observed_at: datetime
    status: SourceStatus
    record_count: int
    snapshot_key: str | None = None
    message: str = ""


class RobinhoodReadOnlyGateway(Protocol):
    """Narrow business boundary: dangerous MCP tool names are unrepresentable."""

    def read_positions(self) -> object:
        ...

    def read_quotes(self, symbols: Sequence[str]) -> object:
        ...

    def read_historicals(
        self,
        symbols: Sequence[str],
        *,
        start_time: str,
        end_time: str | None = None,
        interval: str | None = None,
        bounds: str,
        adjustment_type: str = "split",
    ) -> object:
        ...

    def source_status(self) -> Mapping[str, object]:
        ...
