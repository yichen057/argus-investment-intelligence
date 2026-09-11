from __future__ import annotations

import argparse
import hmac
import json
import os
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Mapping, Protocol, Sequence

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from investment_agent.integrations.robinhood.capabilities import (
    CapabilityAudit,
    ToolDeclaration,
    audit_tool_declarations,
)
from investment_agent.integrations.robinhood.mcp_transport import (
    RobinhoodMcpOAuthTransport,
)

ROBINHOOD_MCP_URL = "https://agent.robinhood.com/mcp/trading"


class _McpTransport(Protocol):
    def list_tools(self) -> list[ToolDeclaration]:
        ...

    def call_tool(self, name: str, arguments: Mapping[str, object]) -> object:
        ...


class QuoteRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=50)


class PositionRequest(BaseModel):
    account_scope: str = Field(pattern="^investments$")


class HistoricalRequest(QuoteRequest):
    symbols: list[str] = Field(min_length=1, max_length=10)
    start_time: str = Field(min_length=20, max_length=40)
    end_time: str | None = Field(default=None, min_length=20, max_length=40)
    interval: str | None = Field(default="day", min_length=1, max_length=32)
    bounds: str = Field(default="regular", pattern="^(regular|extended|trading|24_5|24_7|hyper_trading)$")
    adjustment_type: str = Field(default="split", pattern="^(none|split|all)$")


class RobinhoodReadOnlyService:
    def __init__(
        self,
        *,
        transport: _McpTransport,
        approved_manifest_fingerprint: str,
        enable_historicals: bool = False,
    ) -> None:
        self._transport = transport
        self._approved_manifest_fingerprint = approved_manifest_fingerprint
        self._enable_historicals = enable_historicals
        self._audit: CapabilityAudit | None = None

    @property
    def approved_manifest_fingerprint(self) -> str:
        return self._approved_manifest_fingerprint

    def capability_audit(self, *, refresh: bool = False) -> CapabilityAudit:
        if self._audit is None or refresh:
            self._audit = audit_tool_declarations(self._transport.list_tools())
        return self._audit

    def read_positions(self, *, account_scope: str = "investments") -> object:
        self._require_approved("get_accounts")
        self._require_approved("get_equity_positions")
        account_payload = self._timed_call("get_accounts", {})
        account_number = _selected_account_number(
            account_payload,
            account_scope=account_scope,
        )
        positions = self._timed_call(
            "get_equity_positions",
            {"account_number": account_number},
        )
        return _without_account_identifiers(positions)

    def read_quotes(self, symbols: Sequence[str]) -> object:
        self._require_approved("get_equity_quotes")
        normalized = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
        return self._timed_call("get_equity_quotes", {"symbols": normalized})

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
        if not self._enable_historicals:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Robinhood OHLCV is disabled pending explicit Schema review.",
            )
        self._require_approved("get_equity_historicals", pending_allowed=True)
        arguments: dict[str, object] = {
            "symbols": sorted(
                {symbol.strip().upper() for symbol in symbols if symbol.strip()}
            ),
            "start_time": start_time,
            "bounds": bounds,
            "adjustment_type": adjustment_type,
        }
        if end_time is not None:
            arguments["end_time"] = end_time
        if interval is not None:
            arguments["interval"] = interval
        return self._timed_call("get_equity_historicals", arguments)

    def _require_approved(self, name: str, *, pending_allowed: bool = False) -> None:
        audit = self.capability_audit()
        if not audit.ready_for_phase_one_reads:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Robinhood capability directory changed; reads are fail-closed.",
            )
        if not self._approved_manifest_fingerprint or not hmac.compare_digest(
            audit.manifest_fingerprint,
            self._approved_manifest_fingerprint,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Robinhood Schema manifest has not been approved for this Sidecar.",
            )
        allowed = set(audit.phase_one_schema_fingerprints)
        if pending_allowed:
            allowed.update(audit.pending_review_schema_fingerprints)
        if name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The requested Robinhood capability is not read-only allowlisted.",
            )

    def _timed_call(self, name: str, arguments: Mapping[str, object]) -> object:
        started = perf_counter()
        try:
            return self._transport.call_tool(name, arguments)
        finally:
            # Intentionally record no symbols, accounts, quantities, result bodies,
            # OAuth material, or tool arguments.
            duration_ms = round((perf_counter() - started) * 1000)
            print(json.dumps({"event": "robinhood_read", "tool": name, "duration_ms": duration_ms}))


def _account_records(payload: object) -> list[Mapping[str, object]]:
    if isinstance(payload, list):
        return [record for record in payload if isinstance(record, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("accounts", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [record for record in value if isinstance(record, Mapping)]
        if isinstance(value, Mapping):
            nested = _account_records(value)
            if nested:
                return nested
    if payload.get("account_number"):
        return [payload]
    return []


def _selected_account_number(payload: object, *, account_scope: str) -> str:
    records = _account_records(payload)
    if account_scope != "investments":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only the explicitly approved investments account scope is supported.",
        )
    # The user explicitly selected the original investments account. Robinhood's
    # live directory identifies it as the unique active, default, non-Agentic
    # account. Never fall through to the newly created Agentic account.
    selected = [
        record
        for record in records
        if record.get("is_default") is True
        and record.get("agentic_allowed") is False
        and record.get("deactivated") is not True
        and record.get("permanently_deactivated") is not True
        and str(record.get("state") or "").strip().lower() == "active"
    ]
    numbers = {
        str(record.get("account_number") or "").strip()
        for record in selected
        if str(record.get("account_number") or "").strip()
    }
    if len(numbers) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Robinhood did not return exactly one active default non-Agentic "
                "investments account. Argus will not guess an account number."
            ),
        )
    return next(iter(numbers))


_ACCOUNT_IDENTIFIER_KEYS = frozenset(
    {
        "account",
        "account_id",
        "account_number",
        "account_url",
        "brokerage_account_number",
    }
)


def _without_account_identifiers(payload: object) -> object:
    if isinstance(payload, Mapping):
        return {
            str(key): _without_account_identifiers(value)
            for key, value in payload.items()
            if str(key).strip().lower() not in _ACCOUNT_IDENTIFIER_KEYS
        }
    if isinstance(payload, list):
        return [_without_account_identifiers(value) for value in payload]
    return payload


def create_sidecar_app(
    *,
    service: RobinhoodReadOnlyService,
    bearer_token: str,
) -> FastAPI:
    app = FastAPI(title="Argus Robinhood read-only Sidecar", version="0.1.0")

    def authorize(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {bearer_token}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="Invalid Sidecar bearer token.")

    @app.get("/health", dependencies=[Depends(authorize)])
    def health() -> dict[str, object]:
        audit = service.capability_audit()
        return {
            "status": "ready" if audit.ready_for_phase_one_reads else "capability_drift",
            "observed_tool_count": audit.observed_count,
            "manifest_fingerprint": audit.manifest_fingerprint,
            "business_reads_enabled": bool(
                audit.ready_for_phase_one_reads
                and service.approved_manifest_fingerprint
                and hmac.compare_digest(
                    audit.manifest_fingerprint,
                    service.approved_manifest_fingerprint,
                )
            ),
        }

    @app.get("/v1/capabilities", dependencies=[Depends(authorize)])
    def capabilities(refresh: bool = False) -> dict[str, object]:
        return asdict(service.capability_audit(refresh=refresh))

    @app.post("/v1/positions", dependencies=[Depends(authorize)])
    def positions(request: PositionRequest) -> object:
        return service.read_positions(account_scope=request.account_scope)

    @app.post("/v1/quotes", dependencies=[Depends(authorize)])
    def quotes(request: QuoteRequest) -> object:
        return service.read_quotes(request.symbols)

    @app.post("/v1/historicals", dependencies=[Depends(authorize)])
    def historicals(request: HistoricalRequest) -> object:
        return service.read_historicals(
            request.symbols,
            start_time=request.start_time,
            end_time=request.end_time,
            interval=request.interval,
            bounds=request.bounds,
            adjustment_type=request.adjustment_type,
        )

    return app


def _transport(*, interactive_auth: bool) -> RobinhoodMcpOAuthTransport:
    return RobinhoodMcpOAuthTransport(
        server_url=os.getenv("ARGUS_ROBINHOOD_MCP_URL", ROBINHOOD_MCP_URL),
        interactive_auth=interactive_auth,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Argus read-only Robinhood Sidecar")
    parser.add_argument("command", choices=("authorize", "serve", "disconnect"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--audit-output",
        default="artifacts/robinhood-capability-audit.json",
    )
    args = parser.parse_args()
    if args.command == "disconnect":
        _transport(interactive_auth=False).clear_credentials()
        print("Argus Robinhood OAuth material was removed from macOS Keychain.")
        return
    if args.command == "authorize":
        declarations = _transport(interactive_auth=True).list_tools()
        audit = audit_tool_declarations(declarations)
        output = Path(args.audit_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        sanitized = {
            "audit": asdict(audit),
            "tools": [
                {
                    "name": declaration.name,
                    "description": declaration.description,
                    "input_schema": declaration.input_schema,
                    "schema_fingerprint": declaration.schema_fingerprint,
                }
                for declaration in declarations
            ],
        }
        output.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
        print(f"Sanitized capability audit written to {output}.")
        print("Review it, then set this local Sidecar fingerprint:")
        print(f"ARGUS_ROBINHOOD_APPROVED_MANIFEST={audit.manifest_fingerprint}")
        return

    token = os.getenv("ARGUS_ROBINHOOD_SIDECAR_TOKEN", "")
    approved = os.getenv("ARGUS_ROBINHOOD_APPROVED_MANIFEST", "")
    if not token:
        raise SystemExit("ARGUS_ROBINHOOD_SIDECAR_TOKEN is required.")
    service = RobinhoodReadOnlyService(
        transport=_transport(interactive_auth=False),
        approved_manifest_fingerprint=approved,
        enable_historicals=os.getenv(
            "ARGUS_ROBINHOOD_ENABLE_HISTORICALS", "false"
        ).lower()
        in {"1", "true", "yes", "on"},
    )
    import uvicorn

    uvicorn.run(
        create_sidecar_app(service=service, bearer_token=token),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
