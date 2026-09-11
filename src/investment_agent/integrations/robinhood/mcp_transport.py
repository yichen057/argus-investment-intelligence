from __future__ import annotations

import asyncio
import json
import webbrowser
from typing import Mapping
from urllib.parse import parse_qs, urlparse

from investment_agent.integrations.robinhood.capabilities import (
    ROBINHOOD_PENDING_REVIEW_TOOLS,
    ROBINHOOD_PHASE_ONE_TOOLS,
    ToolDeclaration,
)
from investment_agent.integrations.robinhood.contracts import (
    ProviderError,
    ProviderErrorCode,
)


class RobinhoodMcpOAuthTransport:
    """Internal MCP transport. Business code never receives call_tool()."""

    def __init__(
        self,
        *,
        server_url: str,
        interactive_auth: bool,
        keyring_service: str = "argus-robinhood-mcp",
    ) -> None:
        self._server_url = server_url
        self._interactive_auth = interactive_auth
        self._keyring_service = keyring_service

    def list_tools(self) -> list[ToolDeclaration]:
        return asyncio.run(self._list_tools())

    def call_tool(self, name: str, arguments: Mapping[str, object]) -> object:
        if name not in ROBINHOOD_PHASE_ONE_TOOLS | ROBINHOOD_PENDING_REVIEW_TOOLS:
            raise ProviderError(
                ProviderErrorCode.DENIED_TOOL,
                "The requested Robinhood capability is not transport-allowlisted.",
            )
        return asyncio.run(self._call_tool(name, arguments))

    def clear_credentials(self) -> None:
        _KeyringTokenStorage(self._keyring_service).clear()

    async def _list_tools(self) -> list[ToolDeclaration]:
        async with self._session() as session:
            response = await session.list_tools()
            return [
                ToolDeclaration(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=(
                        getattr(tool, "inputSchema", None)
                        or getattr(tool, "input_schema", None)
                        or {}
                    ),
                )
                for tool in response.tools
            ]

    async def _call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
    ) -> object:
        async with self._session() as session:
            result = await session.call_tool(name, arguments=dict(arguments))
            if result.isError:
                raise RuntimeError(f"Robinhood MCP tool {name} returned an error.")
            structured = getattr(result, "structuredContent", None)
            if structured is not None:
                return structured
            for item in result.content:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {"text": text}
            return {}

    def _session(self):  # type annotations require optional MCP dependencies
        try:
            import httpx
            from mcp import ClientSession
            from mcp.client.auth import OAuthClientProvider
            from mcp.client.streamable_http import streamable_http_client
            from mcp.shared.auth import OAuthClientMetadata
            from pydantic import AnyUrl
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError(
                "Install Argus with the robinhood extra before starting the sidecar."
            ) from exc

        storage = _KeyringTokenStorage(self._keyring_service)

        async def handle_redirect(auth_url: str) -> None:
            if not self._interactive_auth:
                raise RuntimeError(
                    "Robinhood authorization is required. Stop the Sidecar and run "
                    "`argus-robinhood-sidecar authorize` in a terminal."
                )
            print("Open this Robinhood authorization URL in your browser:")
            print(auth_url)
            webbrowser.open(auth_url)

        async def handle_callback() -> tuple[str, str | None]:
            if not self._interactive_auth:
                raise RuntimeError("Interactive Robinhood authorization is disabled.")
            callback_url = input(
                "After Robinhood redirects, paste the full localhost callback URL: "
            ).strip()
            params = parse_qs(urlparse(callback_url).query)
            if not params.get("code"):
                raise RuntimeError("The callback URL did not contain an OAuth code.")
            return params["code"][0], params.get("state", [None])[0]

        oauth = OAuthClientProvider(
            server_url=self._server_url,
            client_metadata=OAuthClientMetadata(
                client_name="Argus read-only Robinhood Sidecar",
                redirect_uris=[AnyUrl("http://127.0.0.1:8766/callback")],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
            ),
            storage=storage,
            redirect_handler=handle_redirect,
            callback_handler=handle_callback,
        )

        class _SessionContext:
            def __init__(self) -> None:
                self._http_context = None
                self._transport_context = None
                self._session_context = None

            async def __aenter__(inner_self):
                inner_self._http_context = httpx.AsyncClient(
                    auth=oauth,
                    follow_redirects=True,
                )
                client = await inner_self._http_context.__aenter__()
                inner_self._transport_context = streamable_http_client(
                    self._server_url,
                    http_client=client,
                )
                read, write, _ = await inner_self._transport_context.__aenter__()
                inner_self._session_context = ClientSession(read, write)
                session = await inner_self._session_context.__aenter__()
                await session.initialize()
                return session

            async def __aexit__(inner_self, exc_type, exc, tb):
                if inner_self._session_context is not None:
                    await inner_self._session_context.__aexit__(exc_type, exc, tb)
                if inner_self._transport_context is not None:
                    await inner_self._transport_context.__aexit__(exc_type, exc, tb)
                if inner_self._http_context is not None:
                    await inner_self._http_context.__aexit__(exc_type, exc, tb)

        return _SessionContext()


class _KeyringTokenStorage:
    def __init__(self, service_name: str) -> None:
        self._service_name = service_name

    async def get_tokens(self):
        return self._load("oauth_tokens", "OAuthToken")

    async def set_tokens(self, tokens) -> None:
        self._store("oauth_tokens", tokens)

    async def get_client_info(self):
        return self._load("oauth_client_info", "OAuthClientInformationFull")

    async def set_client_info(self, client_info) -> None:
        self._store("oauth_client_info", client_info)

    def _load(self, username: str, model_name: str):
        try:
            import keyring
            from mcp.shared import auth as auth_types
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError(
                "Install Argus with the robinhood extra for Keychain token storage."
            ) from exc
        payload = keyring.get_password(self._service_name, username)
        if not payload:
            return None
        model = getattr(auth_types, model_name)
        return model.model_validate_json(payload)

    def _store(self, username: str, value) -> None:
        try:
            import keyring
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError(
                "Install Argus with the robinhood extra for Keychain token storage."
            ) from exc
        keyring.set_password(
            self._service_name,
            username,
            value.model_dump_json(by_alias=True),
        )

    def clear(self) -> None:
        try:
            import keyring
            from keyring.errors import PasswordDeleteError
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError(
                "Install Argus with the robinhood extra for Keychain token storage."
            ) from exc
        for username in ("oauth_tokens", "oauth_client_info"):
            try:
                keyring.delete_password(self._service_name, username)
            except PasswordDeleteError:
                continue
