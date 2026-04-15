"""
Tests for MCP service utilities (normalization, env_expansion, config, channel_permissions).

Mirrors TypeScript tests in ClaudeCode-main/src/services/mcp/
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from py_claw.mcp import (
    normalize_name_for_mcp,
    mcp_info_from_string,
    get_mcp_prefix,
    build_mcp_tool_name,
    get_mcp_display_name,
    extract_mcp_tool_display_name,
    get_tool_name_for_permission_check,
    expand_env_vars_in_string,
    expand_env_vars_in_config,
    get_server_command_array,
    get_server_url,
    unwrap_ccr_proxy_url,
    get_mcp_server_signature,
    command_arrays_match,
    url_matches_pattern,
    short_request_id,
    dedup_plugin_mcp_servers,
    dedup_claude_ai_mcp_servers,
    is_mcp_server_denied,
    is_mcp_server_allowed,
    filter_mcp_servers_by_policy,
    parse_mcp_config,
    parse_mcp_config_from_file,
    is_mcp_server_disabled,
    PERMISSION_REPLY_RE,
    filter_permission_relay_clients,
    create_channel_permission_callbacks,
)


class TestNormalizeNameForMcp:
    """Tests for normalize_name_for_mcp."""

    def test_normalizes_spaces_and_dots(self):
        assert normalize_name_for_mcp("my server") == "my_server"
        assert normalize_name_for_mcp("my.server") == "my_server"
        assert normalize_name_for_mcp("my-server") == "my-server"

    def test_preserves_valid_characters(self):
        assert normalize_name_for_mcp("my_server-123") == "my_server-123"

    def test_claude_ai_prefix_collapse_underscores(self):
        assert normalize_name_for_mcp("claude.ai Slack") == "claude_ai_Slack"
        assert normalize_name_for_mcp("claude.ai  Slack") == "claude_ai_Slack"
        assert normalize_name_for_mcp("claude.ai Slack ") == "claude_ai_Slack"


class TestMcpInfoFromString:
    """Tests for mcp_info_from_string."""

    def test_parses_valid_mcp_tool_name(self):
        result = mcp_info_from_string("mcp__github__create_issue")
        assert result == {"serverName": "github", "toolName": "create_issue"}

    def test_parses_tool_name_with_underscores(self):
        result = mcp_info_from_string("mcp__my_server__my_tool")
        assert result == {"serverName": "my_server", "toolName": "my_tool"}

    def test_parses_server_only(self):
        result = mcp_info_from_string("mcp__github__")
        assert result == {"serverName": "github"}
        assert "toolName" not in result

    def test_returns_none_for_invalid_format(self):
        assert mcp_info_from_string("mcp__") is None
        assert mcp_info_from_string("github__create_issue") is None
        assert mcp_info_from_string("mcpgithub__create_issue") is None
        assert mcp_info_from_string("") is None


class TestBuildMcpToolName:
    """Tests for build_mcp_tool_name."""

    def test_builds_correct_tool_name(self):
        assert build_mcp_tool_name("github", "create_issue") == "mcp__github__create_issue"

    def test_normalizes_server_and_tool_names(self):
        assert build_mcp_tool_name("GitHub", "Create Issue") == "mcp__GitHub__Create_Issue"


class TestExpandEnvVarsInString:
    """Tests for expand_env_vars_in_string."""

    def test_expands_simple_variable(self):
        os.environ["TEST_VAR"] = "test_value"
        try:
            result = expand_env_vars_in_string("${TEST_VAR}")
            assert result["expanded"] == "test_value"
            assert result["missing_vars"] == []
        finally:
            del os.environ["TEST_VAR"]

    def test_expands_with_default(self):
        result = expand_env_vars_in_string("${NONEXISTENT:-default_value}")
        assert result["expanded"] == "default_value"
        assert result["missing_vars"] == []

    def test_expands_missing_variable(self):
        result = expand_env_vars_in_string("${NONEXISTENT}")
        assert result["expanded"] == "${NONEXISTENT}"
        assert result["missing_vars"] == ["NONEXISTENT"]

    def test_preserves_text_without_variables(self):
        result = expand_env_vars_in_string("plain text")
        assert result["expanded"] == "plain text"
        assert result["missing_vars"] == []


class TestExpandEnvVarsInConfig:
    """Tests for expand_env_vars_in_config."""

    def test_expands_nested_variables(self):
        os.environ["SERVER_CMD"] = "npx"
        try:
            config = {"type": "stdio", "command": "${SERVER_CMD}", "args": ["-y", "server"]}
            result = expand_env_vars_in_config(config)
            assert result["expanded"]["command"] == "npx"
        finally:
            del os.environ["SERVER_CMD"]

    def test_reports_missing_vars(self):
        config = {"type": "stdio", "command": "${MISSING_CMD}"}
        result = expand_env_vars_in_config(config)
        assert "MISSING_CMD" in result["missing_vars"]


class TestGetMcpServerSignature:
    """Tests for get_mcp_server_signature."""

    def test_stdio_signature(self):
        config = {"type": "stdio", "command": "npx", "args": ["-y", "server"]}
        sig = get_mcp_server_signature(config)
        assert sig is not None
        assert sig.startswith("stdio:")

    def test_url_signature(self):
        config = {"type": "http", "url": "https://example.com/mcp"}
        sig = get_mcp_server_signature(config)
        assert sig is not None
        assert sig.startswith("url:")

    def test_sdk_returns_none(self):
        config = {"type": "sdk", "name": "claude-vscode"}
        sig = get_mcp_server_signature(config)
        assert sig is None


class TestUnwrapCcrProxyUrl:
    """Tests for unwrap_ccr_proxy_url."""

    def test_passes_through_regular_urls(self):
        url = "https://api.example.com/mcp"
        assert unwrap_ccr_proxy_url(url) == url

    def test_extracts_original_url_from_proxy(self):
        proxy_url = "https://claude.ai/v2/session_ingress/shttp/mcp/?mcp_url=https://api.example.com/mcp"
        assert unwrap_ccr_proxy_url(proxy_url) == "https://api.example.com/mcp"


class TestUrlMatchesPattern:
    """Tests for url_matches_pattern."""

    def test_exact_match(self):
        assert url_matches_pattern("https://api.example.com/v1", "https://api.example.com/v1") is True
        assert url_matches_pattern("https://api.example.com/v2", "https://api.example.com/v1") is False

    def test_wildcard_match(self):
        assert url_matches_pattern("https://api.example.com/v1", "https://api.example.com/*") is True
        assert url_matches_pattern("https://api.example.com/v1", "https://*.example.com/*") is True
        assert url_matches_pattern("https://api.example.com:8080/v1", "https://api.example.com:*/*") is True


class TestShortRequestId:
    """Tests for short_request_id."""

    def test_returns_5_characters(self):
        result = short_request_id("toolu_abc123")
        assert len(result) == 5
        assert result.isalpha()

    def test_avoids_blocked_substrings(self):
        for i in range(20):
            result = short_request_id(f"toolu_test_{i}")
            for blocked in ["fuck", "shit", "cunt"]:
                assert blocked not in result.lower()


class TestDedupPluginMcpServers:
    """Tests for dedup_plugin_mcp_servers."""

    def test_plugin_duped_by_manual(self):
        plugin_servers = {"plugin:slack:slack_server": {"type": "http", "url": "https://slack.com/mcp"}}
        manual_servers = {"slack": {"type": "http", "url": "https://slack.com/mcp"}}
        result = dedup_plugin_mcp_servers(plugin_servers, manual_servers)
        assert "plugin:slack:slack_server" not in result["servers"]
        assert len(result["suppressed"]) == 1

    def test_first_plugin_wins(self):
        plugin_servers = {
            "plugin:slack:first": {"type": "http", "url": "https://slack.com/mcp"},
            "plugin:slack:second": {"type": "http", "url": "https://slack.com/mcp"},
        }
        manual_servers = {}
        result = dedup_plugin_mcp_servers(plugin_servers, manual_servers)
        assert "plugin:slack:first" in result["servers"]
        assert "plugin:slack:second" not in result["servers"]


class TestDedupClaudeAiMcpServers:
    """Tests for dedup_claude_ai_mcp_servers."""

    def test_connector_duped_by_manual(self):
        claudeai_servers = {"claude.ai Slack": {"type": "http", "url": "https://mcp.slack.com"}}
        manual_servers = {"slack": {"type": "http", "url": "https://mcp.slack.com"}}
        result = dedup_claude_ai_mcp_servers(claudeai_servers, manual_servers)
        assert "claude.ai Slack" not in result["servers"]


class TestFilterMcpServersByPolicy:
    """Tests for filter_mcp_servers_by_policy."""

    def test_allows_when_no_policy(self):
        configs = {"server1": {"type": "stdio", "command": "npx"}}
        result = filter_mcp_servers_by_policy(configs)
        assert "server1" in result["allowed"]

    def test_blocks_denied_server(self):
        configs = {"server1": {"type": "stdio", "command": "npx"}}
        denied_list = [{"type": "name", "serverName": "server1"}]
        result = filter_mcp_servers_by_policy(configs, denied_list=denied_list)
        assert "server1" in result["blocked"]

    def test_sdk_exempt_from_policy(self):
        configs = {"server1": {"type": "sdk", "name": "claude-vscode"}}
        denied_list = [{"type": "name", "serverName": "server1"}]
        result = filter_mcp_servers_by_policy(configs, denied_list=denied_list)
        assert "server1" in result["allowed"]


class TestParseMcpConfig:
    """Tests for parse_mcp_config."""

    def test_parses_valid_config(self):
        config = {"mcpServers": {"github": {"type": "http", "url": "https://api.github.com/mcp"}}}
        result = parse_mcp_config(config)
        assert result["config"] is not None
        assert "github" in result["config"]["mcpServers"]

    def test_reports_missing_env_vars(self):
        config = {"mcpServers": {"server1": {"type": "stdio", "command": "${MISSING_VAR}"}}}
        result = parse_mcp_config(config, expand_vars=True)
        assert len(result["errors"]) > 0
        assert "MISSING_VAR" in result["errors"][0]["message"]


class TestParseMcpConfigFromFile:
    """Tests for parse_mcp_config_from_file."""

    def test_parses_existing_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"mcpServers": {"test": {"type": "stdio", "command": "echo"}}}, f)
            temp_path = f.name
        try:
            result = parse_mcp_config_from_file(temp_path)
            assert result["config"] is not None
            assert "test" in result["config"]["mcpServers"]
        finally:
            os.unlink(temp_path)

    def test_missing_file_returns_error(self):
        result = parse_mcp_config_from_file("/nonexistent/path/.mcp.json")
        assert result["config"] is None
        assert len(result["errors"]) > 0


class TestIsMcpServerDisabled:
    """Tests for is_mcp_server_disabled."""

    def test_detects_disabled_server(self):
        assert is_mcp_server_disabled("server1", ["server1", "server2"]) is True
        assert is_mcp_server_disabled("server3", ["server1", "server2"]) is False

    def test_exact_match_required(self):
        assert is_mcp_server_disabled("server1", ["server1"]) is True


class TestPermissionReplyRe:
    """Tests for PERMISSION_REPLY_RE."""

    def test_matches_valid_yes_replies(self):
        assert PERMISSION_REPLY_RE.match("yes tbxkq") is not None
        assert PERMISSION_REPLY_RE.match("y tbxkq") is not None
        assert PERMISSION_REPLY_RE.match("YES TBXKQ") is not None
        assert PERMISSION_REPLY_RE.match("  yes   tbxkq  ") is not None

    def test_matches_no_replies(self):
        assert PERMISSION_REPLY_RE.match("no tbxkq") is not None
        assert PERMISSION_REPLY_RE.match("n tbxkq") is not None

    def test_rejects_invalid_replies(self):
        assert PERMISSION_REPLY_RE.match("yes") is None
        assert PERMISSION_REPLY_RE.match("tbxkq") is None


class TestFilterPermissionRelayClients:
    """Tests for filter_permission_relay_clients."""

    def test_filters_clients_with_capabilities(self):
        clients = [
            {
                "name": "telegram",
                "type": "connected",
                "capabilities": {"experimental": {"claude/channel": True, "claude/channel/permission": True}},
            },
            {"name": "slack", "type": "connected", "capabilities": {"experimental": {}}},
        ]

        def allowlist(name):
            return name in ["telegram"]

        result = filter_permission_relay_clients(clients, allowlist)
        assert len(result) == 1
        assert result[0]["name"] == "telegram"


class TestChannelPermissionCallbacks:
    """Tests for ChannelPermissionCallbacks."""

    def test_resolve_calls_handler(self):
        callbacks = create_channel_permission_callbacks()
        results = []
        callbacks.on_response("tbxkq", lambda r: results.append(r))
        resolved = callbacks.resolve("tbxkq", "allow", "plugin:telegram:tg")
        assert resolved is True
        assert len(results) == 1
        assert results[0]["behavior"] == "allow"
        assert results[0]["fromServer"] == "plugin:telegram:tg"

    def test_resolve_returns_false_for_unknown_id(self):
        callbacks = create_channel_permission_callbacks()
        resolved = callbacks.resolve("unknown", "allow", "plugin:telegram:tg")
        assert resolved is False

    def test_unsubscribe(self):
        """Verify unsubscribe stops delivery."""
        callbacks = create_channel_permission_callbacks()
        results = []
        unsubscribe = callbacks.on_response("tbxkq", lambda r: results.append(r))
        unsubscribe()
        # After unsubscribe removes entry, resolve returns False
        resolved = callbacks.resolve("tbxkq", "allow", "plugin:telegram:tg")
        assert resolved is False
        assert len(results) == 0
