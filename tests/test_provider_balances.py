from __future__ import annotations

from decimal import Decimal

from investment_agent.billing import fetch_deepseek_balance, fetch_kimi_balance


def test_deepseek_balance_adapter_normalizes_official_response() -> None:
    result = fetch_deepseek_balance(
        api_key="secret",
        base_url="https://api.deepseek.com",
        timeout_seconds=5,
        transport=lambda _url, _key, _timeout: {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "CNY",
                    "total_balance": "10.50",
                    "topped_up_balance": "8.00",
                    "granted_balance": "2.50",
                }
            ],
        },
    )

    assert result.provider == "deepseek"
    assert result.billing_status == "active"
    assert result.available_balance == Decimal("10.50")
    assert result.paid_balance == Decimal("8.00")
    assert result.promotional_balance == Decimal("2.50")


def test_kimi_balance_adapter_uses_configured_platform_currency() -> None:
    result = fetch_kimi_balance(
        api_key="secret",
        base_url="https://api.moonshot.cn/v1",
        timeout_seconds=5,
        transport=lambda _url, _key, _timeout: {
            "status": True,
            "data": {
                "available_balance": 65.25,
                "cash_balance": 50.0,
                "voucher_balance": 15.25,
            },
        },
    )

    assert result.provider == "moonshot"
    assert result.currency == "CNY"
    assert result.available_balance == Decimal("65.25")
    assert result.metadata["platform"] == "domestic"
