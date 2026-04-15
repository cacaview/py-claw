"""
Pure utility functions for MCP name normalization.

This file has no heavy dependencies to keep it lightweight for
consumers that only need string parsing (e.g., permissionValidation).

Mirrors: ClaudeCode-main/src/services/mcp/normalization.ts
"""
from __future__ import annotations

import re

# Claude.ai server names are prefixed with this string
CLAUDEAI_SERVER_PREFIX = "claude.ai "


def normalize_name_for_mcp(name: str) -> str:
    """
    Normalize server names to be compatible with the API pattern ^[a-zA-Z0-9_-]{1,64}$.

    Replaces any invalid characters (including dots and spaces) with underscores.

    For claude.ai servers (names starting with "claude.ai "), also collapses
    consecutive underscores and strips leading/trailing underscores to prevent
    interference with the __ delimiter used in MCP tool names.

    Args:
        name: The server name to normalize

    Returns:
        Normalized server name
    """
    normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    if name.startswith(CLAUDEAI_SERVER_PREFIX):
        normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def mcp_info_from_string(tool_string: str) -> dict[str, str] | None:
    """
    Extracts MCP server information from a tool name string.

    Expected format: "mcp__serverName__toolName"

    Args:
        tool_string: The string to parse

    Returns:
        Dict with 'serverName' and optional 'toolName', or None if not a valid MCP rule

    Note:
        Known limitation: If a server name contains "__", parsing will be incorrect.
        For example, "mcp__my__server__tool" would parse as server="my" and tool="server__tool"
        instead of server="my__server" and tool="tool". This is rare in practice since server
        names typically don't contain double underscores.
    """
    parts = tool_string.split("__")
    if len(parts) < 3 or parts[0] != "mcp" or not parts[1]:
        return None
    # Join all parts after server name to preserve double underscores in tool names
    server_name = parts[1]
    tool_name = "__".join(parts[2:]) if len(parts) > 2 else None
    result: dict[str, str] = {"serverName": server_name}
    if tool_name:
        result["toolName"] = tool_name
    return result


def get_mcp_prefix(server_name: str) -> str:
    """
    Generates the MCP tool/command name prefix for a given server.

    Args:
        server_name: Name of the MCP server

    Returns:
        The prefix string (e.g., "mcp__server__")
    """
    return f"mcp__{normalize_name_for_mcp(server_name)}__"


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """
    Builds a fully qualified MCP tool name from server and tool names.

    Inverse of mcp_info_from_string().

    Args:
        server_name: Name of the MCP server (unnormalized)
        tool_name: Name of the tool (unnormalized)

    Returns:
        The fully qualified name, e.g., "mcp__server__tool"
    """
    return f"{get_mcp_prefix(server_name)}{normalize_name_for_mcp(tool_name)}"


def get_mcp_display_name(full_name: str, server_name: str) -> str:
    """
    Extracts the display name from an MCP tool/command name.

    Args:
        full_name: The full MCP tool/command name (e.g., "mcp__server_name__tool_name")
        server_name: The server name to remove from the prefix

    Returns:
        The display name without the MCP prefix
    """
    prefix = f"mcp__{normalize_name_for_mcp(server_name)}__"
    return full_name.replace(prefix, "", 1)


def extract_mcp_tool_display_name(user_facing_name: str) -> str:
    """
    Extracts just the tool/command display name from a userFacingName.

    Args:
        user_facing_name: The full user-facing name (e.g., "github - Add comment to issue (MCP)")

    Returns:
        The display name without server prefix and (MCP) suffix
    """
    # First, remove the (MCP) suffix if present
    without_suffix = re.sub(r"\s*\(MCP\)\s*$", "", user_facing_name)
    without_suffix = without_suffix.strip()

    # Then, remove the server prefix (everything before " - ")
    dash_index = without_suffix.find(" - ")
    if dash_index != -1:
        display_name = without_suffix[ dash_index + 3 : ].strip()
        return display_name

    # If no dash found, return the string without (MCP)
    return without_suffix


def get_tool_name_for_permission_check(
    tool_name: str, mcp_info: dict[str, str] | None = None
) -> str:
    """
    Returns the name to use for permission rule matching.

    For MCP tools, uses the fully qualified mcp__server__tool name so that
    deny rules targeting builtins (e.g., "Write") don't match unprefixed MCP
    replacements that share the same display name.

    Args:
        tool_name: The tool name
        mcp_info: Optional MCP info dict with 'serverName' and 'toolName'

    Returns:
        The name to use for permission checking
    """
    if mcp_info:
        return build_mcp_tool_name(mcp_info["serverName"], mcp_info["toolName"])
    return tool_name
