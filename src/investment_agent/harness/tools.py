from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, replace
from time import sleep

from investment_agent.harness.types import ToolCall, ToolResult

ToolHandler = Callable[[ToolCall], ToolResult]


@dataclass(frozen=True)
class ToolExecutionPolicy:
    timeout_seconds: float = 10.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.1

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("Tool timeout must be positive")
        if self.max_attempts <= 0:
            raise ValueError("Tool max attempts must be positive")
        if self.retry_backoff_seconds < 0:
            raise ValueError("Tool retry backoff cannot be negative")


class ToolRegistry:
    def __init__(self, *, policy: ToolExecutionPolicy | None = None) -> None:
        self._handlers: dict[str, ToolHandler] = {}
        self._policy = policy or ToolExecutionPolicy()

    def register(self, name: str, handler: ToolHandler) -> None:
        if not name.strip():
            raise ValueError("Tool name cannot be empty")
        if name in self._handlers:
            raise ValueError(f"Tool already registered: {name}")
        self._handlers[name] = handler

    def dispatch(self, call: ToolCall) -> ToolResult:
        handler = self._handlers.get(call.name)
        if handler is None:
            return ToolResult(
                call_id=call.call_id,
                status="error",
                error_code="unknown_tool",
                retryable=False,
            )
        last_result: ToolResult | None = None
        for attempt in range(1, self._policy.max_attempts + 1):
            result = self._execute_once(handler, call)
            last_result = _with_execution_metadata(
                result,
                attempt=attempt,
                max_attempts=self._policy.max_attempts,
            )
            if result.status == "ok" or not result.retryable:
                return last_result
            if attempt < self._policy.max_attempts:
                sleep(self._policy.retry_backoff_seconds * attempt)

        assert last_result is not None
        return replace(last_result, retryable=False)

    def _execute_once(self, handler: ToolHandler, call: ToolCall) -> ToolResult:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="argus-tool")
        future = executor.submit(handler, call)
        try:
            return future.result(timeout=self._policy.timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            return ToolResult(
                call_id=call.call_id,
                status="error",
                error_code="tool_timeout",
                retryable=True,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call.call_id,
                status="error",
                output={"exception_type": type(exc).__name__},
                error_code="tool_execution_error",
                retryable=True,
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))


def _with_execution_metadata(
    result: ToolResult,
    *,
    attempt: int,
    max_attempts: int,
) -> ToolResult:
    output = dict(result.output)
    output["_execution"] = {
        "attempts": attempt,
        "max_attempts": max_attempts,
    }
    return replace(result, output=output)
