from __future__ import annotations

import json
from typing import Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from investment_agent.integrations.robinhood.contracts import (
    ProviderError,
    ProviderErrorCode,
)


class RobinhoodSidecarHttpClient:
    """Typed local HTTP client; it exposes no generic MCP call surface."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self._timeout_seconds = timeout_seconds

    def read_positions(self) -> object:
        return self._post("/v1/positions", {"account_scope": "investments"})

    def read_quotes(self, symbols: Sequence[str]) -> object:
        return self._post("/v1/quotes", {"symbols": list(symbols)})

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
        payload: dict[str, object] = {
            "symbols": list(symbols),
            "start_time": start_time,
            "bounds": bounds,
            "adjustment_type": adjustment_type,
        }
        if end_time is not None:
            payload["end_time"] = end_time
        if interval is not None:
            payload["interval"] = interval
        return self._post(
            "/v1/historicals",
            payload,
        )

    def source_status(self) -> Mapping[str, object]:
        payload = self._request("GET", "/health", None)
        if not isinstance(payload, Mapping):
            raise ProviderError(
                ProviderErrorCode.INVALID_RESPONSE,
                "Robinhood sidecar health response was not an object.",
            )
        return payload

    def _post(self, path: str, payload: Mapping[str, object]) -> object:
        return self._request("POST", path, payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None,
    ) -> object:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self._base_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._bearer_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            code = {
                401: ProviderErrorCode.AUTH_REQUIRED,
                409: ProviderErrorCode.CAPABILITY_DRIFT,
                429: ProviderErrorCode.RATE_LIMITED,
            }.get(exc.code, ProviderErrorCode.UNAVAILABLE)
            raise ProviderError(code, f"Robinhood sidecar returned HTTP {exc.code}.") from exc
        except TimeoutError as exc:
            raise ProviderError(
                ProviderErrorCode.TIMEOUT,
                "Robinhood sidecar request timed out.",
            ) from exc
        except (URLError, json.JSONDecodeError) as exc:
            raise ProviderError(
                ProviderErrorCode.UNAVAILABLE,
                "Robinhood sidecar is unavailable or returned invalid JSON.",
            ) from exc
