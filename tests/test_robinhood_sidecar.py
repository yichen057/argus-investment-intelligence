from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from investment_agent.integrations.robinhood import (
    ROBINHOOD_OBSERVED_TOOL_NAMES,
    ROBINHOOD_PHASE_ONE_TOOLS,
    ToolDeclaration,
    audit_tool_declarations,
)
from investment_agent.integrations.robinhood.sidecar import (
    RobinhoodReadOnlyService,
    create_sidecar_app,
)
from investment_agent.integrations.robinhood.contracts import (
    ProviderError,
    ProviderErrorCode,
)
from investment_agent.integrations.robinhood.mcp_transport import (
    RobinhoodMcpOAuthTransport,
)


def _declarations() -> list[ToolDeclaration]:
    return [
        ToolDeclaration(
            name=name,
            description=f"Live declaration for {name}",
            input_schema={"type": "object", "properties": {}},
        )
        for name in sorted(ROBINHOOD_OBSERVED_TOOL_NAMES)
    ]


class FakeMetadataAndReadTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_tools(self) -> list[ToolDeclaration]:
        return _declarations()

    def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        self.calls.append((name, arguments))
        if name == "get_accounts":
            return {
                "data": {
                    "accounts": [
                        {
                            "account_number": "sensitive-account",
                            "state": "active",
                            "is_default": True,
                            "agentic_allowed": False,
                            "deactivated": False,
                            "permanently_deactivated": False,
                        },
                        {
                            "account_number": "agentic-sensitive-account",
                            "state": "active",
                            "is_default": False,
                            "agentic_allowed": True,
                            "deactivated": False,
                            "permanently_deactivated": False,
                        },
                    ]
                }
            }
        return {
            "positions": [
                {
                    "symbol": "SPY",
                    "quantity": "1",
                    "account_number": "sensitive-account",
                }
            ]
        }


def test_live_directory_baseline_has_fifty_two_tools_and_three_phase_one_reads() -> None:
    audit = audit_tool_declarations(_declarations())

    assert len(ROBINHOOD_OBSERVED_TOOL_NAMES) == 52
    assert ROBINHOOD_PHASE_ONE_TOOLS == {
        "get_accounts",
        "get_equity_positions",
        "get_equity_quotes",
    }
    assert audit.ready_for_phase_one_reads
    assert audit.observed_count == 52
    assert not audit.added_tools
    assert not audit.missing_tools


def test_capability_drift_fails_closed_before_any_business_read() -> None:
    declarations = _declarations()
    declarations.append(
        ToolDeclaration(
            name="new_provider_tool",
            description="Unexpected",
            input_schema={"type": "object"},
        )
    )
    audit = audit_tool_declarations(declarations)

    assert not audit.ready_for_phase_one_reads
    assert audit.added_tools == ("new_provider_tool",)


def test_sidecar_requires_exact_manifest_and_exposes_only_typed_routes() -> None:
    transport = FakeMetadataAndReadTransport()
    audit = audit_tool_declarations(transport.list_tools())
    service = RobinhoodReadOnlyService(
        transport=transport,
        approved_manifest_fingerprint=audit.manifest_fingerprint,
    )
    client = TestClient(create_sidecar_app(service=service, bearer_token="local-test"))

    unauthorized = client.post(
        "/v1/positions", json={"account_scope": "investments"}
    )
    response = client.post(
        "/v1/positions",
        json={"account_scope": "investments"},
        headers={"Authorization": "Bearer local-test"},
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert transport.calls == [
        ("get_accounts", {}),
        ("get_equity_positions", {"account_number": "sensitive-account"}),
    ]
    assert response.json() == {"positions": [{"symbol": "SPY", "quantity": "1"}]}
    assert not hasattr(service, "call_tool")
    assert service.approved_manifest_fingerprint == audit.manifest_fingerprint


def test_sidecar_refuses_to_guess_between_multiple_accounts() -> None:
    class MultipleAccountTransport(FakeMetadataAndReadTransport):
        def call_tool(self, name: str, arguments: dict[str, object]) -> object:
            self.calls.append((name, arguments))
            if name == "get_accounts":
                return {
                    "accounts": [
                        {"account_number": "first-sensitive-account"},
                        {"account_number": "second-sensitive-account"},
                    ]
                }
            raise AssertionError("Positions must not be read after ambiguous discovery.")

    transport = MultipleAccountTransport()
    audit = audit_tool_declarations(transport.list_tools())
    service = RobinhoodReadOnlyService(
        transport=transport,
        approved_manifest_fingerprint=audit.manifest_fingerprint,
    )
    client = TestClient(create_sidecar_app(service=service, bearer_token="local-test"))

    response = client.post(
        "/v1/positions",
        json={"account_scope": "investments"},
        headers={"Authorization": "Bearer local-test"},
    )

    assert response.status_code == 409
    assert transport.calls == [("get_accounts", {})]


def test_historicals_remain_disabled_after_directory_approval() -> None:
    transport = FakeMetadataAndReadTransport()
    audit = audit_tool_declarations(transport.list_tools())
    service = RobinhoodReadOnlyService(
        transport=transport,
        approved_manifest_fingerprint=audit.manifest_fingerprint,
        enable_historicals=False,
    )

    client = TestClient(create_sidecar_app(service=service, bearer_token="local-test"))
    response = client.post(
        "/v1/historicals",
        json={
            "symbols": ["SPY"],
            "start_time": "2026-04-01T00:00:00Z",
            "interval": "day",
            "bounds": "regular",
            "adjustment_type": "split",
        },
        headers={"Authorization": "Bearer local-test"},
    )

    assert response.status_code == 409
    assert transport.calls == []


def test_historicals_use_the_pinned_read_only_input_contract() -> None:
    transport = FakeMetadataAndReadTransport()
    audit = audit_tool_declarations(transport.list_tools())
    service = RobinhoodReadOnlyService(
        transport=transport,
        approved_manifest_fingerprint=audit.manifest_fingerprint,
        enable_historicals=True,
    )

    client = TestClient(create_sidecar_app(service=service, bearer_token="local-test"))
    response = client.post(
        "/v1/historicals",
        json={
            "symbols": ["spy"],
            "start_time": "2026-04-01T00:00:00Z",
            "end_time": "2026-07-21T00:00:00Z",
            "interval": "day",
            "bounds": "regular",
            "adjustment_type": "split",
        },
        headers={"Authorization": "Bearer local-test"},
    )

    assert response.status_code == 200
    assert transport.calls == [
        (
            "get_equity_historicals",
            {
                "symbols": ["SPY"],
                "start_time": "2026-04-01T00:00:00Z",
                "end_time": "2026-07-21T00:00:00Z",
                "interval": "day",
                "bounds": "regular",
                "adjustment_type": "split",
            },
        )
    ]


def test_transport_rejects_order_tools_before_network_access() -> None:
    transport = RobinhoodMcpOAuthTransport(
        server_url="https://example.invalid/mcp",
        interactive_auth=False,
    )

    with pytest.raises(ProviderError) as exc_info:
        transport.call_tool("place_equity_order", {})

    assert exc_info.value.code == ProviderErrorCode.DENIED_TOOL
