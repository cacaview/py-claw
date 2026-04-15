"""
VSCode SDK MCP integration.

Handles MCP server authentication for VSCode MCP SDK,
including the needs-auth state and McpAuthTool creation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from py_claw.services.mcp_auth.service import (
    McpAuthService,
    get_mcp_auth_service,
)
from py_claw.services.mcp_auth.types import (
    McpAuthResult,
    McpOAuthSettings,
)

logger = logging.getLogger(__name__)


# ─── VSCode SDK Auth Tool ───────────────────────────────────────────────────────


@dataclass
class McpAuthToolResult:
    """Result from calling the MCP auth tool."""
    status: str  # 'auth_url' | 'unsupported' | 'error'
    message: str
    auth_url: str | None = None


@dataclass
class McpAuthTool:
    """Pseudo-tool for authenticating to an MCP server that requires OAuth.

    This tool is surfaced when an MCP server is installed but not authenticated,
    allowing the model to trigger the OAuth flow on the user's behalf.
    """

    server_name: str
    server_url: str
    transport_type: str  # 'stdio' | 'sse' | 'http'
    oauth_settings: McpOAuthSettings

    @property
    def name(self) -> str:
        """Tool name in format mcp__serverName__authenticate."""
        return f"mcp__{self.server_name}__authenticate"

    @property
    def description(self) -> str:
        """Human-readable description of the tool."""
        location = f"{self.transport_type} at {self.server_url}" if self.server_url else self.transport_type
        return (
            f"The `{self.server_name}` MCP server ({location}) is installed but requires authentication. "
            f"Call this tool to start the OAuth flow — you'll receive an authorization URL to share with the user. "
            f"Once the user completes authorization in their browser, the server's real tools will become available automatically."
        )

    async def call(self, context: Any | None = None) -> McpAuthToolResult:
        """Execute the auth tool.

        Starts the OAuth flow and returns the authorization URL.

        Args:
            context: Optional tool execution context

        Returns:
            McpAuthToolResult with auth URL or error
        """
        service = get_mcp_auth_service()

        # Only SSE/HTTP transports support OAuth from this tool
        if self.transport_type not in ("sse", "http"):
            return McpAuthToolResult(
                status="unsupported",
                message=f"Server '{self.server_name}' uses {self.transport_type} transport which does not support OAuth from this tool. "
                        f"Use /mcp to authenticate manually.",
            )

        def on_auth_url(url: str) -> None:
            logger.debug("OAuth authorization URL: %s", url)

        result = await service.perform_oauth_flow(
            server_name=self.server_name,
            server_url=self.server_url,
            oauth_settings=self.oauth_settings,
            on_auth_url=on_auth_url,
            skip_browser_open=True,  # Return URL to user instead
        )

        if result.success:
            return McpAuthToolResult(
                status="auth_url",
                message=f"Open this URL in your browser to authorize the {self.server_name} MCP server:\n\n{result.auth_url or ''}\n\n"
                        f"Once complete, the server's tools will be available.",
                auth_url=result.auth_url,
            )
        else:
            return McpAuthToolResult(
                status="error",
                message=f"Failed to start OAuth flow for {self.server_name}: {result.message}. "
                        f"Use /mcp to authenticate manually.",
            )


# ─── VSCode SDK Helper Functions ───────────────────────────────────────────────


def create_auth_tool_for_server(
    server_name: str,
    server_url: str | None,
    transport_type: str,
    oauth_settings: McpOAuthSettings,
) -> McpAuthTool | None:
    """Create an auth tool for a server that needs authentication.

    Args:
        server_name: Name of the MCP server
        server_url: URL of the server (if HTTP-based)
        transport_type: Transport type (stdio, sse, http)
        oauth_settings: OAuth settings for the server

    Returns:
        McpAuthTool if OAuth is needed, None otherwise
    """
    if not oauth_settings.enabled:
        return None

    return McpAuthTool(
        server_name=server_name,
        server_url=server_url or "",
        transport_type=transport_type,
        oauth_settings=oauth_settings,
    )


def get_needs_auth_servers(
    server_configs: list[dict[str, Any]],
) -> list[tuple[str, McpOAuthSettings]]:
    """Identify servers that need authentication.

    Args:
        server_configs: List of MCP server configuration dicts

    Returns:
        List of (server_name, oauth_settings) tuples for servers needing auth
    """
    needs_auth = []
    service = get_mcp_auth_service()

    for config in server_configs:
        server_name = config.get("name", "")
        server_url = config.get("url", "")
        oauth = config.get("oauth")

        if not oauth:
            continue

        oauth_settings = McpOAuthSettings(
            enabled=True,
            client_id=oauth.get("clientId"),
            scope=oauth.get("scope"),
        )

        server_key = service.get_server_key(server_name, server_url)
        tokens = service.get_stored_tokens(server_key)

        if tokens is None:
            needs_auth.append((server_name, oauth_settings))

    return needs_auth
