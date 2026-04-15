"""
MCP Auth Tool.

Provides OAuth authentication for MCP servers that require it.
This is a simplified implementation based on the TS McpAuthTool.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import Field, model_validator

from py_claw.schemas.common import PyClawBaseModel
from py_claw.services.oauth.service import get_oauth_service, OAuthService
from py_claw.tools.base import ToolDefinition, ToolError


class McpAuthInput(PyClawBaseModel):
    """Input for MCP Auth tool."""
    server_name: str = Field(description="Name of the MCP server requiring authentication")

    @model_validator(mode="after")
    def validate_fields(self) -> McpAuthInput:
        if not self.server_name.strip():
            raise ValueError("server_name must not be empty")
        return self


@dataclass
class McpAuthResult:
    """Result of MCP auth operation."""
    status: str  # 'auth_url', 'unsupported', 'error'
    message: str
    auth_url: str | None = None


class McpAuthTool:
    """Tool for authenticating with MCP servers that require OAuth."""

    definition = ToolDefinition(
        name="McpAuth",
        input_model=McpAuthInput,
    )

    def __init__(self) -> None:
        pass

    def permission_target(self, payload: dict[str, object]) -> Any:
        server_name = payload.get("server_name")
        if isinstance(server_name, str):
            return f"server:{server_name}"
        return None

    def execute(self, arguments: McpAuthInput, *, cwd: str) -> dict[str, object]:
        """
        Start OAuth flow for an MCP server.

        For claude.ai connectors, authentication must be done via /mcp command.
        For other servers, this attempts to start the OAuth flow.
        """
        server_name = arguments.server_name.strip()

        oauth_service = get_oauth_service()

        # Check if authenticated
        if not oauth_service.is_authenticated():
            return {
                "status": "error",
                "message": (
                    f"Not authenticated with claude.ai. "
                    f"Run /login first, then try authenticating with {server_name}."
                ),
            }

        # In a full implementation, we would:
        # 1. Check if the server requires OAuth (from MCP config)
        # 2. Call performMCPOAuthFlow with skipBrowserOpen
        # 3. Return the authorization URL

        # Simplified: Check if we have OAuth tokens and return info
        tokens = oauth_service.get_tokens()
        profile = oauth_service.get_profile()

        if not tokens or not tokens.access_token:
            return {
                "status": "error",
                "message": (
                    f"OAuth authentication required for {server_name}. "
                    f"Run /login to authenticate with claude.ai."
                ),
            }

        # For now, return that auth is needed - a full implementation
        # would initiate the actual OAuth flow for the specific MCP server
        return {
            "status": "unsupported",
            "message": (
                f"MCP server '{server_name}' requires OAuth authentication. "
                f"Use /mcp command to configure and authenticate MCP servers. "
                f"The /mcp command provides the full interface for MCP server management."
            ),
        }


class McpAuthToolFactory:
    """
    Factory for creating MCP auth tools for specific servers.

    This creates a pseudo-tool that appears in place of the server's real tools
    when the server is installed but not authenticated.
    """

    @staticmethod
    def create_auth_tool(server_name: str, server_config: dict[str, Any]) -> McpAuthTool:
        """
        Create an MCP auth tool for a specific server.

        Args:
            server_name: Name of the MCP server
            server_config: Server configuration dict

        Returns:
            McpAuthTool instance configured for this server
        """
        return McpAuthTool()


def build_mcp_auth_tool_name(server_name: str) -> str:
    """
    Build the tool name for MCP server authentication.

    Args:
        server_name: Name of the MCP server

        Returns:
            Tool name in format mcp__server_name__authenticate
        """
    return f"mcp__{server_name}__authenticate"


def is_mcp_auth_tool_name(tool_name: str) -> tuple[bool, str | None]:
    """
    Check if a tool name is an MCP auth tool name.

    Args:
        tool_name: Tool name to check

        Returns:
            Tuple of (is_auth_tool, server_name or None)
    """
    if tool_name.startswith("mcp__") and tool_name.endswith("__authenticate"):
        parts = tool_name.split("__")
        if len(parts) >= 3:
            return True, parts[1]
    return False, None
