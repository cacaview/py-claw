"""
Utility functions for MCP server management.

Mirrors: ClaudeCode-main/src/services/mcp/utils.ts
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from py_claw.mcp.normalization import normalize_name_for_mcp, mcp_info_from_string


def filter_tools_by_server(tools: list[dict[str, Any]], server_name: str) -> list[dict[str, Any]]:
    """
    Filters tools by MCP server name.

    Args:
        tools: Array of tools to filter
        server_name: Name of the MCP server

    Returns:
        Tools belonging to the specified server
    """
    prefix = f"mcp__{normalize_name_for_mcp(server_name)}__"
    return [t for t in tools if isinstance(t.get("name"), str) and t["name"].startswith(prefix)]


def filter_commands_by_server(commands: list[dict[str, Any]], server_name: str) -> list[dict[str, Any]]:
    """
    Filters commands by MCP server name.

    Args:
        commands: Array of commands to filter
        server_name: Name of the MCP server

    Returns:
        Commands belonging to the specified server
    """
    return [c for c in commands if command_belongs_to_server(c, server_name)]


def command_belongs_to_server(command: dict[str, Any], server_name: str) -> bool:
    """
    True when a command belongs to the given MCP server.

    MCP **prompts** are named `mcp__<server>__<prompt>` (wire-format constraint);
    MCP **skills** are named `<server>:<skill>` (matching plugin/nested-dir skill
    naming). Both live in `mcp.commands`, so cleanup and filtering must match
    either shape.
    """
    normalized = normalize_name_for_mcp(server_name)
    name = command.get("name")
    if not name:
        return False
    return name.startswith(f"mcp__{normalized}__") or name.startswith(f"{normalized}:")


def filter_mcp_prompts_by_server(commands: list[dict[str, Any]], server_name: str) -> list[dict[str, Any]]:
    """
    Filters MCP **prompts** (not skills) by server.

    The distinguisher is `loadedFrom === 'mcp'`: MCP skills set it, MCP
    prompts don't (they use `isMcp: True` instead).
    """
    return [
        c
        for c in commands
        if command_belongs_to_server(c, server_name)
        and not (c.get("type") == "prompt" and c.get("loadedFrom") == "mcp")
    ]


def filter_resources_by_server(resources: list[dict[str, Any]], server_name: str) -> list[dict[str, Any]]:
    """
    Filters resources by MCP server name.

    Args:
        resources: Array of resources to filter
        server_name: Name of the MCP server

    Returns:
        Resources belonging to the specified server
    """
    return [r for r in resources if r.get("server") == server_name]


def exclude_tools_by_server(tools: list[dict[str, Any]], server_name: str) -> list[dict[str, Any]]:
    """
    Removes tools belonging to a specific MCP server.

    Args:
        tools: Array of tools
        server_name: Name of the MCP server to exclude

    Returns:
        Tools not belonging to the specified server
    """
    prefix = f"mcp__{normalize_name_for_mcp(server_name)}__"
    return [t for t in tools if not (isinstance(t.get("name"), str) and t["name"].startswith(prefix))]


def exclude_commands_by_server(commands: list[dict[str, Any]], server_name: str) -> list[dict[str, Any]]:
    """
    Removes commands belonging to a specific MCP server.

    Args:
        commands: Array of commands
        server_name: Name of the MCP server to exclude

    Returns:
        Commands not belonging to the specified server
    """
    return [c for c in commands if not command_belongs_to_server(c, server_name)]


def exclude_resources_by_server(
    resources: dict[str, list[dict[str, Any]]], server_name: str
) -> dict[str, list[dict[str, Any]]]:
    """
    Removes resources belonging to a specific MCP server.

    Args:
        resources: Map of server resources
        server_name: Name of the MCP server to exclude

    Returns:
        Resources map without the specified server
    """
    result = dict(resources)
    result.pop(server_name, None)
    return result


def hash_mcp_config(config: dict[str, Any]) -> str:
    """
    Stable hash of an MCP server config for change detection on /reload-plugins.

    Excludes `scope` (provenance, not content — moving a server from .mcp.json
    to settings.json shouldn't reconnect it). Keys sorted so `{a:1,b:2}` and
    `{b:2,a:1}` hash the same.
    """
    # Remove scope from config
    rest = {k: v for k, v in config.items() if k != "scope"}

    def sort_keys(obj: Any) -> Any:
        if isinstance(obj, dict) and not isinstance(obj, list):
            return {k: sort_keys(obj[k]) for k in sorted(obj.keys())}
        elif isinstance(obj, list):
            return [sort_keys(item) for item in obj]
        return obj

    stable = json.dumps(sort_keys(rest), sort_keys=True)
    return hashlib.sha256(stable.encode()).hexdigest()[:16]


def is_tool_from_mcp_server(tool_name: str, server_name: str) -> bool:
    """
    Checks if a tool name belongs to a specific MCP server.

    Args:
        tool_name: The tool name to check
        server_name: The server name to match against

    Returns:
        True if the tool belongs to the specified server
    """
    info = mcp_info_from_string(tool_name)
    return info is not None and info.get("serverName") == server_name


def is_mcp_tool(tool: dict[str, Any]) -> bool:
    """
    Checks if a tool is from an MCP server.

    Args:
        tool: The tool to check

    Returns:
        True if the tool is from an MCP server
    """
    name = tool.get("name")
    return isinstance(name, str) and (name.startswith("mcp__") or tool.get("isMcp") is True)


def is_mcp_command(command: dict[str, Any]) -> bool:
    """
    Checks if a command is from an MCP server.

    Args:
        command: The command to check

    Returns:
        True if the command is from an MCP server
    """
    name = command.get("name")
    return isinstance(name, str) and (name.startswith("mcp__") or command.get("isMcp") is True)


def parse_headers(header_array: list[str]) -> dict[str, str]:
    """
    Parse headers from array of "Header-Name: value" strings.

    Args:
        header_array: Array of header strings

    Returns:
        Dict of header key-value pairs

    Raises:
        ValueError: If header format is invalid
    """
    headers: dict[str, str] = {}

    for header in header_array:
        colon_index = header.find(":")
        if colon_index == -1:
            raise ValueError(f'Invalid header format: "{header}". Expected format: "Header-Name: value"')

        key = header[:colon_index].strip()
        value = header[colon_index + 1 :].strip()

        if not key:
            raise ValueError(f'Invalid header: "{header}". Header name cannot be empty.')

        headers[key] = value

    return headers


def get_scope_label(scope: str) -> str:
    """
    Get human-readable label for a config scope.

    Args:
        scope: The config scope

    Returns:
        Human-readable label
    """
    labels = {
        "local": "Local config (private to you in this project)",
        "project": "Project config (shared via .mcp.json)",
        "user": "User config (available in all your projects)",
        "dynamic": "Dynamic config (from command line)",
        "enterprise": "Enterprise config (managed by your organization)",
        "claudeai": "claude.ai config",
        "managed": "Managed config",
    }
    return labels.get(scope, scope)


def ensure_config_scope(scope: str | None) -> str:
    """
    Ensure scope is a valid ConfigScope value.

    Args:
        scope: The scope to validate

    Returns:
        Valid ConfigScope value

    Raises:
        ValueError: If scope is invalid
    """
    valid_scopes = ["local", "user", "project", "dynamic", "enterprise", "claudeai", "managed"]
    if not scope:
        return "local"
    if scope not in valid_scopes:
        raise ValueError(f"Invalid scope: {scope}. Must be one of: {', '.join(valid_scopes)}")
    return scope


def ensure_transport(transport_type: str | None) -> str:
    """
    Ensure transport type is valid.

    Args:
        transport_type: The transport type to validate

    Returns:
        Valid transport type

    Raises:
        ValueError: If transport type is invalid
    """
    valid_types = ["stdio", "sse", "http"]
    if not transport_type:
        return "stdio"
    if transport_type not in valid_types:
        raise ValueError(f"Invalid transport type: {transport_type}. Must be one of: {', '.join(valid_types)}")
    return transport_type


def get_logging_safe_mcp_base_url(config: dict[str, Any]) -> str | None:
    """
    Extracts the MCP server base URL (without query string) for analytics logging.

    Query strings are stripped because they can contain access tokens.
    Trailing slashes are also removed for normalization.
    Returns None for stdio/sdk servers or if URL parsing fails.

    Args:
        config: MCP server config

    Returns:
        Base URL without query string, or None
    """
    if "url" not in config or not isinstance(config["url"], str):
        return None

    try:
        from urllib.parse import urlparse

        parsed = urlparse(config["url"])
        # Reconstruct URL without query string
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        # Remove trailing slash
        return base_url.rstrip("/")
    except Exception:
        return None
