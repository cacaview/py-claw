"""
MCPTool - Dynamic MCP tool wrapper.

Provides a generic tool interface for calling any MCP server's tools
by wrapping mcp/runtime.py's list_tools() and call_tool() methods.

This mirrors the TypeScript MCPTool pattern where a single generic tool
shell is specialized at runtime with actual MCP tool names, schemas, and
call implementations.
"""
from __future__ import annotations

from typing import Any

from pydantic import Field

from py_claw.schemas.common import McpToolInfo, PyClawBaseModel
from py_claw.settings.loader import get_settings_with_sources
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

from py_claw.tools.mcp_resource_tools import (
    _find_server,
    _format_server_summaries,
    _load_settings_for_state,
    _match_servers,
    _require_state,
    _status_summary,
)


class MCPToolInput(PyClawBaseModel):
    """Input for the generic MCP tool."""
    server: str = Field(description="Name of the MCP server")
    tool: str = Field(description="Name of the tool to call")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to pass to the tool (key-value pairs)",
    )


class MCPTool:
    """
    Generic MCP tool wrapper.

    This tool provides a passthrough interface for calling any MCP server's tools.
    It wraps the MCP runtime's call_tool() method, allowing dynamic tool
    invocation without requiring static tool registration.

    The tool name, description, and schema are determined at runtime by
    the MCP server's tools/list response.
    """

    definition = ToolDefinition(name="MCP", input_model=MCPToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        parts = []
        server = payload.get("server")
        if isinstance(server, str) and server:
            parts.append(f"server:{server}")
        tool = payload.get("tool")
        if isinstance(tool, str) and tool:
            parts.append(f"tool:{tool}")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=" | ".join(parts) if parts else None,
        )

    def execute(self, arguments: MCPToolInput, *, cwd: str) -> dict[str, object]:
        """
        Execute an MCP tool by name.

        Args:
            server: Name of the MCP server
            tool: Name of the tool to call
            arguments: Dict of arguments to pass to the tool

        Returns:
            Tool execution result with status and output
        """
        state = _require_state(self._state, self.definition.name)
        settings = _load_settings_for_state(state)

        # Verify server exists
        statuses = state.mcp_runtime.build_statuses(settings)
        status = _find_server(statuses, arguments.server)
        if status is None:
            available = ", ".join(s.name for s in statuses) or "none"
            raise ToolError(
                f'MCP server "{arguments.server}" not found. Available servers: {available}'
            )

        # Check server is connected
        if status.status != "connected":
            raise ToolError(
                f'MCP server "{arguments.server}" is not connected (status: {status.status}). '
                f"Make sure the server is running and try again."
            )

        # Call the tool
        try:
            result = state.mcp_runtime.call_tool(
                arguments.server,
                arguments.tool,
                arguments.arguments,
                settings,
            )
        except (KeyError, ValueError, NotImplementedError, RuntimeError) as exc:
            raise ToolError(f"Failed to call {arguments.tool} on {arguments.server}: {exc}") from exc

        return {
            "server": arguments.server,
            "tool": arguments.tool,
            "result": result,
            "message": f"Called {arguments.tool} on {arguments.server}.",
        }

    def __init__(self, state: Any = None) -> None:
        self._state = state


class ListMCPToolsInput(PyClawBaseModel):
    """Input for listing MCP tools."""
    server: str | None = Field(
        default=None,
        description="Optional: filter tools to a specific server",
    )


class ListMCPToolsTool:
    """
    List available tools from MCP servers.

    This tool queries the tools/list method on MCP servers and returns
    the available tool definitions including names, descriptions, and
    input schemas.
    """

    definition = ToolDefinition(name="ListMCPTools", input_model=ListMCPToolsInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        server = payload.get("server")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=server if isinstance(server, str) else None,
        )

    def execute(self, arguments: ListMCPToolsInput, *, cwd: str) -> dict[str, object]:
        """
        List available tools from MCP servers.

        Args:
            server: Optional server name to filter by

        Returns:
            List of MCP tools with names, descriptions, and schemas
        """
        state = _require_state(self._state, self.definition.name)
        settings = _load_settings_for_state(state)

        statuses = state.mcp_runtime.build_statuses(settings)
        matched = _match_servers(statuses, arguments.server)

        if not matched:
            if arguments.server is not None:
                raise ToolError(
                    f'MCP server "{arguments.server}" not found. Available servers: '
                    f"{_format_server_summaries(statuses)}"
                )
            return {
                "tools": [],
                "servers": [],
                "message": "No MCP servers are currently configured.",
            }

        all_tools: list[dict[str, Any]] = []
        server_tools: dict[str, list[dict[str, Any]]] = {}

        for server_status in matched:
            if server_status.status != "connected":
                continue
            try:
                tools = state.mcp_runtime.list_tools(server_status.name, settings)
                tool_defs = []
                for tool in tools:
                    if isinstance(tool, McpToolInfo):
                        tool_defs.append({
                            "name": tool.name,
                            "description": tool.description,
                            "annotations": tool.annotations.model_dump() if tool.annotations else None,
                        })
                    elif isinstance(tool, dict):
                        tool_defs.append({
                            "name": tool.get("name"),
                            "description": tool.get("description"),
                            "annotations": tool.get("annotations"),
                        })
                    else:
                        tool_defs.append({"name": str(tool)})
                all_tools.extend(tool_defs)
                server_tools[server_status.name] = tool_defs
            except (KeyError, ValueError, NotImplementedError, RuntimeError):
                # Server may not support tools/list
                pass

        return {
            "tools": all_tools,
            "server_tools": server_tools,
            "servers": [_status_summary(s) for s in matched],
            "message": (
                f"Found {len(all_tools)} tool(s) across {len(server_tools)} server(s). "
                f"Use the MCP tool to call them by server name and tool name."
            ),
        }

    def __init__(self, state: Any = None) -> None:
        self._state = state
