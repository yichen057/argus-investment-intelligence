from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    retryable: bool = False


@dataclass(frozen=True)
class WorkRequest:
    request_id: str
    run_id: str
    role: str
    objective: str
    as_of_date: date
    sensitivity: str
    required_capabilities: frozenset[str]
    input_evidence_ids: tuple[str, ...] = ()
    deadline: datetime | None = None


@dataclass(frozen=True)
class WorkResult:
    request_id: str
    status: str
    claims: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    counter_evidence_ids: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    tokens: int = 0
    cost_usd: float = 0.0
