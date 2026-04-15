"""
Tests for the MCP Auth tool.
"""
from __future__ import annotations

import pytest

from py_claw.tools.mcp_auth_tool import (
    McpAuthTool,
    McpAuthInput,
    McpAuthToolFactory,
    build_mcp_auth_tool_name,
    is_mcp_auth_tool_name,
)


class TestMcpAuthTool:
    """Tests for McpAuthTool."""

    def test_tool_definition(self) -> None:
        tool = McpAuthTool()
        assert tool.definition.name == "McpAuth"

    def test_input_validation(self) -> None:
        inp = McpAuthInput(server_name="github")
        assert inp.server_name == "github"

    def test_input_validation_empty(self) -> None:
        with pytest.raises(ValueError):
            McpAuthInput(server_name="")

    def test_permission_target(self) -> None:
        tool = McpAuthTool()
        target = tool.permission_target({"server_name": "github"})
        assert target == "server:github"

    def test_execute_not_authenticated(self) -> None:
        tool = McpAuthTool()
        inp = McpAuthInput(server_name="github")
        result = tool.execute(inp, cwd="/tmp")
        assert result["status"] == "error"
        assert "Not authenticated" in result["message"]


class TestMcpAuthToolFactory:
    """Tests for McpAuthToolFactory."""

    def test_create_auth_tool(self) -> None:
        tool = McpAuthToolFactory.create_auth_tool("github", {"type": "sse"})
        assert isinstance(tool, McpAuthTool)


class TestToolNameHelpers:
    """Tests for tool name helper functions."""

    def test_build_mcp_auth_tool_name(self) -> None:
        assert build_mcp_auth_tool_name("github") == "mcp__github__authenticate"
        assert build_mcp_auth_tool_name("slack") == "mcp__slack__authenticate"

    def test_is_mcp_auth_tool_name_valid(self) -> None:
        is_auth, server = is_mcp_auth_tool_name("mcp__github__authenticate")
        assert is_auth is True
        assert server == "github"

    def test_is_mcp_auth_tool_name_invalid(self) -> None:
        is_auth, server = is_mcp_auth_tool_name("McpAuth")
        assert is_auth is False
        assert server is None

    def test_is_mcp_auth_tool_name_partial(self) -> None:
        is_auth, server = is_mcp_auth_tool_name("mcp__github")
        assert is_auth is False
        assert server is None
