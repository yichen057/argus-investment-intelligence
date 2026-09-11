from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class ProviderBalanceError(RuntimeError):
    """A sanitized failure from an official provider balance endpoint."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProviderBalance:
    provider: str
    billing_status: str
    currency: str
    available_balance: Decimal
    paid_balance: Decimal
    promotional_balance: Decimal
    source_reference: str
    metadata: dict[str, Any] = field(default_factory=dict)


BalanceTransport = Callable[[str, str, float], dict[str, Any]]


def fetch_deepseek_balance(
    *,
    api_key: str,
    base_url: str,
    timeout_seconds: float,
    transport: BalanceTransport | None = None,
) -> ProviderBalance:
    endpoint = f"{base_url.rstrip('/')}/user/balance"
    payload = (transport or _get_json)(endpoint, api_key, timeout_seconds)
    infos = payload.get("balance_infos")
    if not isinstance(infos, list) or not infos:
        raise ProviderBalanceError(
            "provider_response_invalid",
            "DeepSeek returned no usable balance information.",
        )
    parsed = [_deepseek_balance_info(item) for item in infos]
    primary = next((item for item in parsed if item[1] > 0), parsed[0])
    currency, total, topped_up, granted = primary
    return ProviderBalance(
        provider="deepseek",
        billing_status="active" if payload.get("is_available") is True else "insufficient_balance",
        currency=currency,
        available_balance=total,
        paid_balance=topped_up,
        promotional_balance=granted,
        source_reference=endpoint,
        metadata={
            "import_kind": "official_balance_api",
            "available_for_api_calls": payload.get("is_available") is True,
            "reported_currencies": [item[0] for item in parsed],
        },
    )


def fetch_kimi_balance(
    *,
    api_key: str,
    base_url: str,
    timeout_seconds: float,
    transport: BalanceTransport | None = None,
) -> ProviderBalance:
    endpoint = f"{base_url.rstrip('/')}/users/me/balance"
    payload = (transport or _get_json)(endpoint, api_key, timeout_seconds)
    data = payload.get("data")
    if payload.get("status") is not True or not isinstance(data, dict):
        raise ProviderBalanceError(
            "provider_response_invalid",
            "Kimi returned no usable balance information.",
        )
    available = _decimal(data.get("available_balance"), "available_balance")
    cash = _decimal(data.get("cash_balance"), "cash_balance")
    voucher = _decimal(data.get("voucher_balance"), "voucher_balance")
    hostname = (urlparse(endpoint).hostname or "").lower()
    currency = "CNY" if hostname.endswith("moonshot.cn") else "USD"
    return ProviderBalance(
        provider="moonshot",
        billing_status="active" if available > 0 else "insufficient_balance",
        currency=currency,
        available_balance=max(Decimal("0"), available),
        paid_balance=cash,
        promotional_balance=max(Decimal("0"), voucher),
        source_reference=endpoint,
        metadata={
            "import_kind": "official_balance_api",
            "available_for_api_calls": available > 0,
            "platform": "domestic" if currency == "CNY" else "international",
        },
    )


def _deepseek_balance_info(value: object) -> tuple[str, Decimal, Decimal, Decimal]:
    if not isinstance(value, dict):
        raise ProviderBalanceError(
            "provider_response_invalid",
            "DeepSeek returned an invalid balance row.",
        )
    currency = value.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        raise ProviderBalanceError(
            "provider_response_invalid",
            "DeepSeek returned a balance without a currency.",
        )
    return (
        currency.upper(),
        _decimal(value.get("total_balance"), "total_balance"),
        _decimal(value.get("topped_up_balance"), "topped_up_balance"),
        _decimal(value.get("granted_balance"), "granted_balance"),
    )


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProviderBalanceError(
            "provider_response_invalid",
            f"The provider returned an invalid {field_name}.",
        ) from exc
    if not number.is_finite():
        raise ProviderBalanceError(
            "provider_response_invalid",
            f"The provider returned an invalid {field_name}.",
        )
    return number


def _get_json(endpoint: str, api_key: str, timeout_seconds: float) -> dict[str, Any]:
    request = Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "argus-investment-agent/0.1",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=max(1.0, timeout_seconds)) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        code = (
            "provider_authentication_failed"
            if exc.code in {401, 403}
            else "provider_rate_limited"
            if exc.code == 429
            else "provider_http_error"
        )
        raise ProviderBalanceError(
            code,
            f"The provider balance API returned HTTP {exc.code}.",
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise ProviderBalanceError(
            "provider_unavailable",
            "The provider balance API could not be reached.",
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderBalanceError(
            "provider_response_invalid",
            "The provider balance API returned invalid JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderBalanceError(
            "provider_response_invalid",
            "The provider balance API returned an invalid response.",
        )
    return payload
