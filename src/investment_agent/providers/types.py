from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

from investment_agent.harness.types import ToolCall, ToolResult


class Deployment(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


@dataclass(frozen=True)
class ModelProfile:
    name: str
    deployment: Deployment
    allowed_sensitivity: frozenset[str]
    capabilities: frozenset[str]
    quality_score: float
    cost_score: float
    latency_score: float


@dataclass(frozen=True)
class ModelRequest:
    objective: str
    role: str
    sensitivity: str
    as_of_date: date | None
    document_id: int | None = None
    tool_results: tuple[ToolResult, ...] = ()
    iteration: int = 0
    style_context: str | None = None


@dataclass(frozen=True)
class ModelResponse:
    provider: str
    model: str
    deployment: Deployment
    content: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    tool_call: ToolCall | None = None
    serving_engine: str | None = None
    success: bool = True
    error_code: str | None = None
    input_cost_per_million_usd: float | None = None
    output_cost_per_million_usd: float | None = None


class ModelProvider(Protocol):
    provider_name: str
    model_name: str
    deployment: Deployment
    serving_engine: str | None
    input_cost_per_million_usd: float | None
    output_cost_per_million_usd: float | None

    def generate(self, request: ModelRequest) -> ModelResponse:
        ...
