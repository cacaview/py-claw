"""
Tests for the MCP tool wrapper.
"""
from __future__ import annotations

import pytest

from py_claw.tools.mcp_tool import MCPTool, ListMCPToolsTool, MCPToolInput, ListMCPToolsInput


class TestMCPTool:
    """Tests for MCPTool."""

    def test_tool_definition(self) -> None:
        tool = MCPTool()
        assert tool.definition.name == "MCP"
        assert tool.definition.input_model == MCPToolInput

    def test_input_validation(self) -> None:
        inp = MCPToolInput(server="github", tool="search", arguments={"query": "test"})
        assert inp.server == "github"
        assert inp.tool == "search"
        assert inp.arguments == {"query": "test"}

    def test_input_validation_defaults(self) -> None:
        inp = MCPToolInput(server="github", tool="search")
        assert inp.arguments == {}

    def test_permission_target(self) -> None:
        tool = MCPTool()
        target = tool.permission_target({"server": "github", "tool": "search"})
        assert target.tool_name == "MCP"
        assert target.content == "server:github | tool:search"

    def test_permission_target_partial(self) -> None:
        tool = MCPTool()
        target = tool.permission_target({"server": "github"})
        assert target.tool_name == "MCP"
        assert target.content == "server:github"


class TestListMCPToolsTool:
    """Tests for ListMCPToolsTool."""

    def test_tool_definition(self) -> None:
        tool = ListMCPToolsTool()
        assert tool.definition.name == "ListMCPTools"
        assert tool.definition.input_model == ListMCPToolsInput

    def test_input_validation(self) -> None:
        inp = ListMCPToolsInput(server="github")
        assert inp.server == "github"

    def test_input_validation_optional(self) -> None:
        inp = ListMCPToolsInput()
        assert inp.server is None

    def test_permission_target(self) -> None:
        tool = ListMCPToolsTool()
        target = tool.permission_target({"server": "github"})
        assert target.tool_name == "ListMCPTools"
        assert target.content == "github"

    def test_permission_target_none(self) -> None:
        tool = ListMCPToolsTool()
        target = tool.permission_target({})
        assert target.tool_name == "ListMCPTools"
        assert target.content is None
