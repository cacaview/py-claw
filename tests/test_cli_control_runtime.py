from __future__ import annotations

import base64
import json
import shlex
import sys
from io import StringIO

import pytest

from py_claw.cli.control import ControlRuntime
from py_claw.cli.main import main
from py_claw.cli.runtime import RuntimeState
from py_claw.query import QueryRuntime
from py_claw.cli.structured_io import StructuredIOError
from py_claw.permissions.engine import PermissionEngine
from py_claw.permissions.rules import (
    PermissionRule,
    matches_permission_rule,
    parse_permission_rule_value,
    permission_rule_value_to_string,
)
from py_claw.permissions.state import build_permission_context
from pydantic import BaseModel

from py_claw.schemas.control import (
    BuiltinToolUsage,
    SDKControlCancelAsyncMessageRequest,
    SDKControlElicitationRequest,
    SDKControlInitializeRequest,
    SDKControlInterruptRequest,
    SDKControlGetContextUsageRequest,
    SDKControlGetSettingsRequest,
    SDKControlMcpMessageRequest,
    SDKControlMcpReconnectRequest,
    SDKControlMcpSetServersRequest,
    SDKControlMcpStatusRequest,
    SDKControlMcpToggleRequest,
    SDKControlPermissionRequest,
    SDKControlReloadPluginsRequest,
    SDKControlResponseEnvelope,
    SDKControlRewindFilesRequest,
    SDKControlSeedReadStateRequest,
    SDKControlSetMaxThinkingTokensRequest,
    SDKControlStopTaskRequest,
)
from py_claw.tools.base import ToolDefinition, ToolPermissionTarget
from py_claw.tools.registry import ToolRegistry
from py_claw.tools.runtime import ToolRuntime


class _CustomWriteInput(BaseModel):
    path: str


class _CustomWriteTool:
    definition = ToolDefinition(name="Write", input_model=_CustomWriteInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("path")
        return ToolPermissionTarget(tool_name="Write", content=str(value) if isinstance(value, str) else None)


def _runtime_with_custom_write_tool() -> ControlRuntime:
    registry = ToolRegistry()
    registry.register(_CustomWriteTool())
    return ControlRuntime(
        RuntimeState(
            tool_runtime=ToolRuntime(registry=registry),
            flag_settings={"permissions": {"allow": ["Write(allowed.txt)"]}},
        )
    )


def _python_print_json(payload: dict[str, object]) -> str:
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return (
        "python - <<'PY'\n"
        "import base64\n"
        f"print(base64.b64decode({encoded!r}).decode('utf-8'))\n"
        "PY"
    )


def _expected_commands(*skill_entries: dict[str, str]) -> list[dict[str, str]]:
    # Build a dict of skill overrides keyed by name
    skill_map = {entry["name"]: entry for entry in skill_entries}
    # All builtin user_invocable commands (alphabetical, excluding reset-limits and summary)
    builtin_names = [
        "add-dir", "advisor", "agents", "agents-platform", "ant-trace", "autofix-pr",
        "backfill-sessions", "branch", "break-cache", "bridge", "bridge-kick", "brief",
        "btw", "bughunter", "chrome", "clear", "color", "commit", "commit-push-pr",
        "compact", "config", "context", "copy", "cost", "ctx_viz", "debug-tool-call",
        "desktop", "diff", "doctor", "effort", "env", "exit", "export", "extra-usage",
        "fast", "feedback", "files", "heapdump", "help", "hooks", "ide", "init",
        "init-verifiers", "insights", "install", "install-github-app", "install-slack-app",
        "issue", "keybindings", "login", "logout", "mcp", "memory", "mobile",
        "mock-limits", "model", "notifications", "oauth-refresh", "onboarding",
        "output-style", "passes", "perf-issue", "permissions", "plan", "plugin",
        "pr-comments", "privacy-settings", "rate-limit-options", "release-notes",
        "reload-plugins", "remote-env", "remote-setup", "rename", "resume", "review",
        "rewind", "sandbox-toggle", "screenshot", "security-review", "session", "share",
        "skills", "stats", "status", "statusline", "stickers", "subscribe", "tag",
        "tasks", "team", "teleport", "terminal-setup", "test", "theme", "think-back",
        "thinkback-play", "tunnel", "ultraplan", "upgrade", "usage", "version", "vim",
        "voice", "watch", "web-setup", "workspace",
    ]
    builtin_descriptions = {
        "add-dir": "Add a directory to the allowed list for file operations",
        "advisor": "Configure the advisor model",
        "agents": "List and manage active agents",
        "agents-platform": "Manage agents platform",
        "ant-trace": "Trace Ant internal operations (internal)",
        "autofix-pr": "Automatically fix issues in a PR",
        "backfill-sessions": "Backfill session memory from historical data",
        "branch": "List, create, or switch git branches",
        "break-cache": "Clear cached data and refresh state",
        "bridge": "Remote Control bridge for connected clients",
        "bridge-kick": "Inject bridge fault state (internal)",
        "brief": "Toggle brief-only mode (KAIROS feature)",
        "btw": "Add a side note to prepend to your next message",
        "bughunter": "Find and analyze bugs in the codebase",
        "chrome": "Claude in Chrome (Beta) settings",
        "clear": "Clear session transcript and state",
        "color": "Set the prompt bar color for this session",
        "commit": "Create a git commit",
        "commit-push-pr": "Commit, push, and open a pull request",
        "compact": "Compact conversation history to free up context",
        "config": "Show or edit configuration settings",
        "context": "Manage conversation context",
        "copy": "Copy assistant response to clipboard",
        "cost": "Show token usage and cost estimates for this session",
        "ctx_viz": "Visualize context usage",
        "debug-tool-call": "Debug a specific tool invocation",
        "desktop": "Interact with desktop applications",
        "diff": "Show git diffs of staged and unstaged changes",
        "doctor": "Run system diagnostics and check configuration",
        "effort": "Set effort level for tasks",
        "env": "Show environment variables",
        "exit": "Exit Claude Code",
        "export": "Export conversation to a text file",
        "extra-usage": "Manage extra usage and subscription settings",
        "fast": "Toggle fast mode for premium speed",
        "feedback": "Send feedback about Claude Code",
        "files": "List files changed in this session",
        "heapdump": "Generate a heap dump for memory profiling",
        "help": "Show available slash commands",
        "hooks": "Inspect configured hooks",
        "ide": "IDE integration and auto-connect settings",
        "init": "Initialize CLAUDE.md file with codebase documentation",
        "init-verifiers": "Create verifier skill(s) for automated verification of code changes",
        "insights": "Show Claude Code usage statistics and insights",
        "install": "Install or update Claude Code",
        "install-github-app": "Set up Claude GitHub Actions for a repository",
        "install-slack-app": "Install the Claude Code Slack app",
        "issue": "Interact with issue tracking systems",
        "keybindings": "Show configured keyboard shortcuts",
        "login": "Log in to Claude Code",
        "logout": "Log out and clear credentials",
        "mcp": "Inspect MCP server status",
        "memory": "Inspect loaded memory state",
        "mobile": "Show QR code to download the Claude mobile app",
        "mock-limits": "Simulate rate limit errors for testing",
        "model": "Inspect or change the active model",
        "notifications": "Manage desktop notifications",
        "oauth-refresh": "Refresh OAuth tokens",
        "onboarding": "Show onboarding information",
        "output-style": "Configure output styling",
        "passes": "Share a free week of Claude Code with friends and earn extra usage",
        "perf-issue": "Diagnose performance problems",
        "permissions": "Inspect active permission mode",
        "plan": "Inspect plan-mode guidance",
        "plugin": "Manage plugins (list, install, uninstall, enable, disable, marketplace)",
        "pr-comments": "Get comments from a GitHub pull request",
        "privacy-settings": "Manage privacy and data settings",
        "rate-limit-options": "Show rate limit options (internal)",
        "release-notes": "Show Claude Code release notes and changelog",
        "reload-plugins": "Reload plugins and activate pending changes",
        "remote-env": "Configure default remote environment for teleport",
        "remote-setup": "Configure remote connections",
        "rename": "Rename the current session",
        "resume": "Resume a prior session",
        "review": "Review a pull request",
        "rewind": "Rewind the conversation by N messages",
        "sandbox-toggle": "Toggle sandbox mode for security",
        "screenshot": "Take a screenshot of the current screen",
        "security-review": "Run a security review on the codebase",
        "session": "Inspect current session state",
        "share": "Share current session or artifacts",
        "skills": "List and manage available skills",
        "stats": "Show session statistics and metrics",
        "status": "Show current runtime status",
        "statusline": "Set up Claude Code's status line UI",
        "stickers": "Order Claude Code stickers",
        "subscribe": "Subscribe to events and get notified",
        "tag": "List, create, or delete git tags",
        "tasks": "List tracked tasks",
        "team": "Manage agent teams and team members",
        "teleport": "Teleport to a remote environment",
        "terminal-setup": "Install Shift+Enter keybinding for newlines in terminals that don't support CSI u",
        "test": "Run tests in the project",
        "theme": "Show or change the color theme",
        "think-back": "Your Claude Code Year in Review",
        "thinkback-play": "Play back think-back history",
        "tunnel": "Create a tunnel for remote access",
        "ultraplan": "Use ultraplan mode for CCR sessions (ULTRAPLAN feature gate)",
        "upgrade": "Upgrade Claude Code to a newer version",
        "usage": "Show usage information and limits",
        "version": "Show version information",
        "vim": "Toggle between Vim and Normal editing modes",
        "voice": "Configure voice input and output",
        "watch": "Watch files for changes and run commands on change",
        "web-setup": "Setup Claude Code on the web (connect GitHub account)",
        "workspace": "Manage workspace configuration",
    }
    builtin_hints = {
        "add-dir": "<path>",
        "advisor": "[<model>|off]",
        "agents": "[list|stop|info] [agent-id]",
        "agents-platform": "[action]",
        "ant-trace": "",
        "autofix-pr": "[PR number]",
        "backfill-sessions": "[session-id]",
        "branch": "[branch-name]",
        "break-cache": "[all|tools|settings]",
        "bridge": "[start|stop|status|connect]",
        "bridge-kick": "",
        "brief": "",
        "btw": "<note>",
        "bughunter": "[pattern]",
        "chrome": "",
        "clear": "",
        "color": "<color|default>",
        "commit": "[commit message]",
        "commit-push-pr": "[PR description]",
        "compact": "",
        "config": "[key] [value]",
        "context": "[show|clear]",
        "copy": "[N]",
        "cost": "",
        "ctx_viz": "",
        "debug-tool-call": "<tool-name>",
        "desktop": "<action> [args...]",
        "diff": "[--cached]",
        "doctor": "",
        "effort": "[low|medium|high]",
        "env": "[name]",
        "exit": "",
        "export": "",
        "extra-usage": "",
        "fast": "",
        "feedback": "<message>",
        "files": "",
        "heapdump": "[output-path]",
        "help": "",
        "hooks": "",
        "ide": "[info|auto-connect|reset]",
        "init": "",
        "init-verifiers": "",
        "insights": "[open|json]",
        "install": "[stable|latest|version]",
        "install-github-app": "<repo> [--api-key <key>] [--workflow claude|claude-review|both]",
        "install-slack-app": "",
        "issue": "[list|show|create] [args...]",
        "keybindings": "[list|set|remove] [key] [command]",
        "login": "",
        "logout": "",
        "mcp": "",
        "memory": "",
        "mobile": "[ios|android]",
        "mock-limits": "<type> [duration]",
        "model": "[model]",
        "notifications": "[list|dismiss|clear]",
        "oauth-refresh": "[service]",
        "onboarding": "",
        "output-style": "[default|compact|detailed]",
        "passes": "",
        "perf-issue": "[area]",
        "permissions": "",
        "plan": "",
        "plugin": "[list|install|uninstall|enable|disable|marketplace] [args...]",
        "pr-comments": "[PR number]",
        "privacy-settings": "[show|reset]",
        "rate-limit-options": "",
        "release-notes": "",
        "reload-plugins": "",
        "remote-env": "[set <id>]",
        "remote-setup": "[action]",
        "rename": "[name]",
        "resume": "<session-id>",
        "review": "[PR number]",
        "rewind": "<count>",
        "sandbox-toggle": "[on|off|status]",
        "screenshot": "[output-path]",
        "security-review": "[path]",
        "session": "",
        "share": "[session|artifact] [id]",
        "skills": "[list|info] [skill-name]",
        "stats": "",
        "status": "",
        "statusline": "",
        "stickers": "",
        "subscribe": "<event-type> [filter]",
        "tag": "[tag-name] [-d]",
        "tasks": "",
        "team": "[list|create|delete|add|remove] [args...]",
        "teleport": "[session-id|host]",
        "terminal-setup": "",
        "test": "[pattern] [--verbose]",
        "theme": "[theme-name]",
        "think-back": "[play|edit|fix|regenerate]",
        "thinkback-play": "[session-id]",
        "tunnel": "[start|stop|status]",
        "ultraplan": "[seed_plan]",
        "upgrade": "[stable|latest|version]",
        "usage": "",
        "version": "",
        "vim": "",
        "voice": "[on|off|status|device]",
        "watch": "<command> [file-pattern]",
        "web-setup": "",
        "workspace": "[show|set|reset] [key=value]",
    }
    # Build merged list (skill overrides replace builtins alphabetically)
    result = []
    all_names = sorted(set(builtin_names) | set(skill_map.keys()))
    for name in all_names:
        if name in skill_map:
            result.append(skill_map[name])
        elif name in builtin_names:
            result.append({
                "name": name,
                "description": builtin_descriptions[name],
                "argumentHint": builtin_hints.get(name, ""),
            })
    return result


def test_cli_stream_json_applies_flag_settings_and_returns_settings() -> None:
    stdin = StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "control_request",
                        "request_id": "req-1",
                        "request": {
                            "subtype": "apply_flag_settings",
                            "settings": {
                                "model": "claude-opus-4-6",
                                "permissions": {"defaultMode": "plan"},
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "control_request",
                        "request_id": "req-2",
                        "request": {"subtype": "get_settings"},
                    }
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    assert main(["--input-format", "stream-json", "--output-format", "stream-json"], stdin=stdin, stdout=stdout) == 0

    responses = [SDKControlResponseEnvelope.model_validate_json(line) for line in stdout.getvalue().splitlines()]
    assert [response.response.request_id for response in responses] == ["req-1", "req-2"]
    assert responses[0].response.subtype == "success"
    assert responses[0].response.response == {}

    payload = responses[1].response.response
    assert responses[1].response.subtype == "success"
    assert payload is not None
    assert payload["effective"]["model"] == "claude-opus-4-6"
    assert payload["effective"]["permissions"]["defaultMode"] == "plan"
    assert payload["applied"]["model"] == "claude-opus-4-6"
    assert payload["sources"][-1] == {
        "source": "flagSettings",
        "settings": {
            "model": "claude-opus-4-6",
            "permissions": {"defaultMode": "plan"},
        },
    }
    assert any(source["source"] == "flagSettings" for source in payload["sources"])
    assert any(source["settings"].get("model") == "claude-opus-4-6" for source in payload["sources"])
    assert any(
        source["settings"].get("permissions", {}).get("defaultMode") == "plan"
        for source in payload["sources"]
    )

    flags = payload["sources"][-1]["settings"]
    assert flags["model"] == "claude-opus-4-6"
    assert flags["permissions"]["defaultMode"] == "plan"



def test_control_runtime_merges_settings_sources_in_priority_order(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)

    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"model": "user-model", "permissions": {"allow": ["Read"]}}),
        encoding="utf-8",
    )
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps({"model": "project-model", "env": {"PROJECT": "1"}}),
        encoding="utf-8",
    )
    (project_dir / ".claude" / "settings.local.json").write_text(
        json.dumps({"env": {"LOCAL": "1"}, "permissions": {"deny": ["Bash(rm:*)"]}}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(
        RuntimeState(
            cwd=str(project_dir),
            home_dir=str(home_dir),
            flag_settings={"model": "flag-model"},
        )
    )

    response = runtime.handle_request(SDKControlGetSettingsRequest.model_validate({"subtype": "get_settings"}))

    assert response is not None
    assert response["effective"]["model"] == "flag-model"
    assert response["effective"]["env"] == {"PROJECT": "1", "LOCAL": "1"}
    assert response["effective"]["permissions"] == {
        "allow": ["Read"],
        "deny": ["Bash(rm:*)"],
    }
    assert [source["source"] for source in response["sources"]] == [
        "userSettings",
        "projectSettings",
        "localSettings",
        "flagSettings",
    ]



def test_control_runtime_tracks_dynamic_mcp_servers() -> None:
    runtime = ControlRuntime(RuntimeState())

    set_response = runtime.handle_request(
        SDKControlMcpSetServersRequest.model_validate(
            {
                "subtype": "mcp_set_servers",
                "servers": {
                    "local": {"command": "python", "args": ["-m", "server"]},
                    "remote": {"type": "http", "url": "https://example.com/mcp"},
                },
            }
        )
    )
    status_response = runtime.handle_request(SDKControlMcpStatusRequest.model_validate({"subtype": "mcp_status"}))

    assert set_response == {"added": ["local", "remote"], "removed": [], "errors": {}}
    assert status_response is not None
    assert [server["name"] for server in status_response["mcpServers"]] == ["local", "remote"]
    assert all(server["status"] == "pending" for server in status_response["mcpServers"])



def test_control_runtime_get_context_usage_returns_schema_compatible_defaults() -> None:
    runtime = ControlRuntime(RuntimeState())

    response = runtime.handle_request(
        SDKControlGetContextUsageRequest.model_validate({"subtype": "get_context_usage"})
    )

    assert response is not None
    # deferredBuiltinTools now includes all built-in tool names
    expected_tools = [
        "Agent", "AskUserQuestion", "Bash", "Brief", "Config", "ConfigList", "ConfigSet",
        "CronCreate", "CronDelete", "CronList",
        "Edit", "EnterPlanMode", "EnterWorktree", "ExitPlanMode", "ExitWorktree",
        "Glob", "Grep", "LSP", "ListMCPTools", "ListMcpResources", "MCP", "Monitor", "NotebookEdit", "PowerShell", "Read",
        "ReadMcpResource", "ReviewArtifact", "SendMessage", "SendUserFile", "SendUserMessage",
        "Skill", "Sleep", "Snip", "StructuredOutput",
        "TaskCreate", "TaskGet", "TaskList", "TaskOutput", "TaskStop", "TaskUpdate",
        "TeamCreate", "TeamDelete", "TerminalCapture", "TodoWrite", "ToolSearch",
        "VerifyPlanExecution", "WebBrowser", "WebFetch", "WebSearch", "Workflow", "Write",
    ]
    assert response == {
        "categories": [],
        "totalTokens": 0,
        "maxTokens": 0,
        "rawMaxTokens": 0,
        "percentage": 0.0,
        "gridRows": [],
        "model": "default",
        "memoryFiles": [],
        "mcpTools": [],
        "deferredBuiltinTools": [{"name": name, "tokens": 0, "isLoaded": True} for name in expected_tools],
        "agents": [],
        "slashCommands": {"totalCommands": 106, "includedCommands": 106, "tokens": 0},
        "isAutoCompactEnabled": False,
    }



def test_control_runtime_initialize_and_context_usage_surface_settings_skills_and_agents(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "skills": ["review-pr", "commit", "review-pr", "  ", "commit"],
                "agents": {
                    "explore": {"description": "Explore codebase", "prompt": "Look around", "model": "sonnet"}
                },
            }
        ),
        encoding="utf-8",
    )
    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))

    initialize = runtime.handle_request(
        type(
            "InitializeRequestLike",
            (),
            {"subtype": "initialize", "agents": {"planner": {"description": "Plan work", "prompt": "Plan it"}}},
        )()
    )
    usage = runtime.handle_request(
        SDKControlGetContextUsageRequest.model_validate({"subtype": "get_context_usage"})
    )

    assert initialize is not None
    assert initialize["commands"] == _expected_commands(
        {"name": "commit", "description": "Invoke the commit skill", "argumentHint": ""},
        {"name": "review-pr", "description": "Invoke the review-pr skill", "argumentHint": ""},
    )
    assert usage["slashCommands"] == {"totalCommands": 107, "includedCommands": 107, "tokens": 0}
    assert initialize["agents"] == [
        {"name": "explore", "description": "Explore codebase", "model": "sonnet"},
        {"name": "planner", "description": "Plan work"},
    ]
    assert [model["value"] for model in initialize["models"]] == [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ]
    assert initialize["account"] == {}
    assert initialize["mcpServers"] == []
    assert usage is not None
    assert usage["agents"] == [
        {"agentType": "explore", "source": "settings", "tokens": 0},
        {"agentType": "planner", "source": "session", "tokens": 0},
    ]
    assert usage["skills"]["totalSkills"] == 2
    assert usage["skills"]["includedSkills"] == 2
    assert usage["skills"]["tokens"] == 0
    assert usage["skills"]["skillFrontmatter"] == [
        {
            "name": "commit",
            "source": "settings",
            "tokens": 0,
            "userInvocable": True,
            "disableModelInvocation": False,
        },
        {
            "name": "review-pr",
            "source": "settings",
            "tokens": 0,
            "userInvocable": True,
            "disableModelInvocation": False,
        },
    ]



def test_control_runtime_get_context_usage_exposes_richer_skill_frontmatter(tmp_path) -> None:
    project_dir = tmp_path / "project"
    skill_dir = project_dir / ".claude" / "skills" / "review-pr"
    skill_dir.mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps({"skills": ["review-pr"]}),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: Review a pull request\n"
        "argument-hint: <pr-number>\n"
        "when-to-use: Use when reviewing PR feedback\n"
        "version: 2\n"
        "model: sonnet\n"
        "allowed-tools:\n"
        "  - Read\n"
        "  - Grep\n"
        "effort: high\n"
        "user-invocable: false\n"
        "disable-model-invocation: true\n"
        "---\n"
        "Review the PR.\n",
        encoding="utf-8",
    )
    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir)))

    usage = runtime.handle_request(
        SDKControlGetContextUsageRequest.model_validate({"subtype": "get_context_usage"})
    )

    assert usage is not None
    frontmatter = usage["skills"]["skillFrontmatter"][0]
    assert frontmatter == {
        "name": "review-pr",
        "source": "projectSettings",
        "tokens": 0,
        "argumentHint": "<pr-number>",
        "whenToUse": "Use when reviewing PR feedback",
        "version": "2",
        "model": "sonnet",
        "allowedTools": ["Read", "Grep"],
        "effort": "high",
        "userInvocable": False,
        "disableModelInvocation": True,
    }


def test_control_runtime_initialize_prefers_disk_backed_skill_metadata(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    skill_dir = project_dir / ".claude" / "skills" / "commit"
    skill_dir.mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "skills": ["commit", "review-pr"],
                "agents": {
                    "explore": {"description": "Explore codebase", "prompt": "Look around", "model": "sonnet"}
                },
            }
        ),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: Create a commit\n"
        "argument-hint: <message>\n"
        "user-invocable: true\n"
        "---\n"
        "Commit changes.\n",
        encoding="utf-8",
    )
    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))

    initialize = runtime.handle_request(
        type(
            "InitializeRequestLike",
            (),
            {"subtype": "initialize", "agents": {"planner": {"description": "Plan work", "prompt": "Plan it"}}},
        )()
    )
    usage = runtime.handle_request(
        SDKControlGetContextUsageRequest.model_validate({"subtype": "get_context_usage"})
    )

    assert initialize is not None
    assert initialize["commands"] == _expected_commands(
        {"name": "commit", "description": "Create a commit", "argumentHint": "<message>"},
        {"name": "review-pr", "description": "Invoke the review-pr skill", "argumentHint": ""},
    )
    assert usage is not None
    assert usage["slashCommands"] == {"totalCommands": 107, "includedCommands": 107, "tokens": 0}
    assert usage["skills"]["totalSkills"] == 2
    assert usage["skills"]["includedSkills"] == 2
    assert usage["skills"]["tokens"] == 0
    assert usage["skills"]["skillFrontmatter"] == [
        {
            "name": "commit",
            "source": "projectSettings",
            "tokens": 0,
            "argumentHint": "<message>",
            "userInvocable": True,
            "disableModelInvocation": False,
        },
        {
            "name": "review-pr",
            "source": "settings",
            "tokens": 0,
            "userInvocable": True,
            "disableModelInvocation": False,
        },
    ]

































































































def test_control_runtime_initialize_surfaces_account_metadata_from_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    project_dir = tmp_path / "project"
    (project_dir / ".claude").mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps({"apiKeySource": "project", "apiProvider": "vertex"}),
        encoding="utf-8",
    )
    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir)))

    response = runtime.handle_request(SDKControlInitializeRequest.model_validate({"subtype": "initialize"}))

    assert response is not None
    assert response["account"] == {"apiKeySource": "project", "apiProvider": "vertex"}


@pytest.mark.parametrize(
    ("env_name", "env_value", "expected_provider"),
    [
        ("ANTHROPIC_API_KEY", "sk-ant", "firstParty"),
        ("AWS_REGION", "us-east-1", "bedrock"),
        ("VERTEX_PROJECT", "vertex-project", "vertex"),
        ("AZURE_OPENAI_API_KEY", "azure-key", "foundry"),
    ],
)
def test_control_runtime_initialize_detects_account_provider_from_environment(
    monkeypatch, env_name: str, env_value: str, expected_provider: str
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv(env_name, env_value)
    runtime = ControlRuntime(RuntimeState())

    response = runtime.handle_request(SDKControlInitializeRequest.model_validate({"subtype": "initialize"}))

    assert response is not None
    assert response["account"] == {"apiKeySource": "user", "apiProvider": expected_provider}



def test_control_runtime_initialize_prefers_configured_account_metadata_over_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    project_dir = tmp_path / "project"
    (project_dir / ".claude").mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps({"apiKeySource": "project", "apiProvider": "bedrock"}),
        encoding="utf-8",
    )
    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir)))

    response = runtime.handle_request(SDKControlInitializeRequest.model_validate({"subtype": "initialize"}))

    assert response is not None
    assert response["account"] == {"apiKeySource": "project", "apiProvider": "bedrock"}



def test_control_runtime_initialize_ignores_invalid_agent_definitions(tmp_path) -> None:
    project_dir = tmp_path / "project"
    (project_dir / ".claude").mkdir(parents=True)
    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir)))

    response = runtime.handle_request(
        type(
            "InitializeRequestLike",
            (),
            {"subtype": "initialize", "agents": {"broken": {"description": "Missing prompt"}}},
        )()
    )

    assert response is not None
    assert response["agents"] == []
    assert runtime.state.initialized_agents == {}



def test_control_runtime_initialize_overrides_settings_agents_with_request_agents(tmp_path) -> None:
    project_dir = tmp_path / "project"
    (project_dir / ".claude").mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps({"agents": {"explore": {"description": "From settings", "prompt": "Look", "model": "haiku"}}}),
        encoding="utf-8",
    )
    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir)))

    response = runtime.handle_request(
        type(
            "InitializeRequestLike",
            (),
            {
                "subtype": "initialize",
                "agents": {"explore": {"description": "From request", "prompt": "Plan", "model": "sonnet"}},
            },
        )()
    )

    assert response is not None
    assert response["agents"] == [{"name": "explore", "description": "From request", "model": "sonnet"}]



def test_control_runtime_initialize_stores_query_configuration_fields() -> None:
    runtime = ControlRuntime(RuntimeState())

    response = runtime.handle_request(
        SDKControlInitializeRequest.model_validate(
            {
                "subtype": "initialize",
                "systemPrompt": "System guidance",
                "appendSystemPrompt": "Append guidance",
                "jsonSchema": {"type": "object"},
                "sdkMcpServers": ["local", "remote"],
                "promptSuggestions": True,
                "agentProgressSummaries": True,
            }
        )
    )

    assert response is not None
    assert runtime.state.system_prompt == "System guidance"
    assert runtime.state.append_system_prompt == "Append guidance"
    assert runtime.state.json_schema == {"type": "object"}
    assert runtime.state.sdk_mcp_servers == ["local", "remote"]
    assert runtime.state.prompt_suggestions is True
    assert runtime.state.agent_progress_summaries is True



def test_control_runtime_context_usage_surfaces_initialized_system_prompt_sections() -> None:
    state = RuntimeState(
        system_prompt="System guidance",
        append_system_prompt="Append guidance",
        json_schema={"type": "object"},
    )
    runtime = ControlRuntime(state)

    response = runtime.handle_request(
        SDKControlGetContextUsageRequest.model_validate({"subtype": "get_context_usage"})
    )

    assert response is not None
    assert response["systemPromptSections"] == [
        {"name": "systemPrompt", "tokens": 0},
        {"name": "appendSystemPrompt", "tokens": 0},
        {"name": "jsonSchema", "tokens": 0},
    ]



def test_control_runtime_reload_plugins_returns_commands_and_agents_from_settings(tmp_path) -> None:
    project_dir = tmp_path / "project"
    (project_dir / ".claude").mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "skills": ["review-pr", "commit"],
                "agents": {"explore": {"description": "Explore codebase", "prompt": "Look around"}},
            }
        ),
        encoding="utf-8",
    )
    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir)))

    response = runtime.handle_request(
        SDKControlReloadPluginsRequest.model_validate({"subtype": "reload_plugins"})
    )

    assert response is not None
    assert response["commands"] == _expected_commands(
        {"name": "commit", "description": "Invoke the commit skill", "argumentHint": ""},
        {"name": "review-pr", "description": "Invoke the review-pr skill", "argumentHint": ""},
    )
    assert response["agents"] == [{"name": "explore", "description": "Explore codebase"}]
    assert response["plugins"] == []
    assert response["mcpServers"] == []
    assert response["error_count"] == 0



def test_control_runtime_reload_plugins_includes_initialized_agents_and_current_mcp_statuses(tmp_path) -> None:
    project_dir = tmp_path / "project"
    (project_dir / ".claude").mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps({"agents": {"explore": {"description": "Explore codebase", "prompt": "Look around"}}}),
        encoding="utf-8",
    )
    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir)))
    runtime.handle_request(
        type(
            "InitializeRequestLike",
            (),
            {"subtype": "initialize", "agents": {"planner": {"description": "Plan work", "prompt": "Plan it"}}},
        )()
    )
    runtime.handle_request(
        SDKControlMcpSetServersRequest.model_validate(
            {
                "subtype": "mcp_set_servers",
                "servers": {
                    "local": {"command": "python", "args": ["-m", "server"]},
                },
            }
        )
    )

    response = runtime.handle_request(
        SDKControlReloadPluginsRequest.model_validate({"subtype": "reload_plugins"})
    )

    assert response is not None
    assert response["commands"] == _expected_commands()
    assert response["agents"] == [
        {"name": "explore", "description": "Explore codebase"},
        {"name": "planner", "description": "Plan work"},
    ]
    assert response["plugins"] == []
    assert response["error_count"] == 0
    assert response["mcpServers"] == [
        {
            "name": "local",
            "status": "pending",
            "config": {"command": "python", "args": ["-m", "server"]},
            "scope": "local",
        }
    ]



def test_control_runtime_get_context_usage_surfaces_mcp_tool_usage_from_runtime_statuses() -> None:
    runtime = ControlRuntime(RuntimeState())
    runtime.state.mcp_runtime = type(
        "FakeMcpRuntime",
        (),
        {
            "build_statuses": lambda self, settings: [
                type(
                    "StatusLike",
                    (),
                    {
                        "name": "local",
                        "status": "pending",
                        "tools": [
                            type("ToolLike", (), {"name": "search"})(),
                            type("ToolLike", (), {"name": "read"})(),
                        ],
                    },
                )()
            ]
        },
    )()

    response = runtime.handle_request(
        SDKControlGetContextUsageRequest.model_validate({"subtype": "get_context_usage"})
    )

    assert response is not None
    assert response["mcpTools"] == [
        {"name": "search", "serverName": "local", "tokens": 0, "isLoaded": True},
        {"name": "read", "serverName": "local", "tokens": 0, "isLoaded": True},
    ]



def test_control_runtime_get_context_usage_marks_disabled_mcp_tools_unloaded() -> None:
    runtime = ControlRuntime(RuntimeState())
    runtime.state.mcp_runtime = type(
        "FakeMcpRuntime",
        (),
        {
            "build_statuses": lambda self, settings: [
                type(
                    "StatusLike",
                    (),
                    {
                        "name": "local",
                        "status": "disabled",
                        "tools": [type("ToolLike", (), {"name": "search"})()],
                    },
                )()
            ]
        },
    )()

    response = runtime.handle_request(
        SDKControlGetContextUsageRequest.model_validate({"subtype": "get_context_usage"})
    )

    assert response is not None
    assert response["mcpTools"] == [
        {"name": "search", "serverName": "local", "tokens": 0, "isLoaded": False}
    ]



def test_control_runtime_get_context_usage_uses_settings_model_and_auto_compact_threshold(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"model": "claude-sonnet-4-6", "autoCompactEnabled": True, "autoCompactThreshold": 12345}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))

    response = runtime.handle_request(
        SDKControlGetContextUsageRequest.model_validate({"subtype": "get_context_usage"})
    )

    assert response is not None
    assert response["model"] == "claude-sonnet-4-6"
    assert response["maxTokens"] == 200000
    assert response["rawMaxTokens"] == 200000
    assert response["autoCompactThreshold"] == 12345
    assert response["isAutoCompactEnabled"] is True



def test_control_runtime_interrupt_sets_shared_interrupt_event_without_query_runtime() -> None:
    state = RuntimeState()
    runtime = ControlRuntime(state)

    response = runtime.handle_request(SDKControlInterruptRequest.model_validate({"subtype": "interrupt"}))

    assert response == {}
    assert state.interrupt_event.is_set() is True



def test_control_runtime_interrupt_delegates_to_query_runtime() -> None:
    state = RuntimeState()
    query_runtime = QueryRuntime(state=state)
    runtime = ControlRuntime(state)

    response = runtime.handle_request(SDKControlInterruptRequest.model_validate({"subtype": "interrupt"}))

    assert response == {}
    assert state.query_runtime is query_runtime
    assert state.interrupt_event.is_set() is True



def test_control_runtime_cancel_async_message_returns_false_without_async_queue() -> None:
    runtime = ControlRuntime(RuntimeState())

    response = runtime.handle_request(
        SDKControlCancelAsyncMessageRequest.model_validate(
            {"subtype": "cancel_async_message", "message_uuid": "msg-1"}
        )
    )

    assert response == {"cancelled": False}



def test_control_runtime_cancel_async_message_delegates_to_query_runtime() -> None:
    state = RuntimeState()
    query_runtime = QueryRuntime(state=state)
    runtime = ControlRuntime(state)

    response = runtime.handle_request(
        SDKControlCancelAsyncMessageRequest.model_validate(
            {"subtype": "cancel_async_message", "message_uuid": "msg-1"}
        )
    )

    assert state.query_runtime is query_runtime
    assert response == {"cancelled": False}



def test_control_runtime_cancel_async_message_is_idempotent_for_unknown_message() -> None:
    state = RuntimeState()
    QueryRuntime(state=state)
    runtime = ControlRuntime(state)

    first = runtime.handle_request(
        SDKControlCancelAsyncMessageRequest.model_validate(
            {"subtype": "cancel_async_message", "message_uuid": "missing"}
        )
    )
    second = runtime.handle_request(
        SDKControlCancelAsyncMessageRequest.model_validate(
            {"subtype": "cancel_async_message", "message_uuid": "missing"}
        )
    )

    assert first == {"cancelled": False}
    assert second == {"cancelled": False}



def test_control_runtime_reload_plugins_returns_schema_compatible_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    runtime = ControlRuntime(RuntimeState())

    response = runtime.handle_request(
        SDKControlReloadPluginsRequest.model_validate({"subtype": "reload_plugins"})
    )

    assert response is not None
    assert response["commands"] == _expected_commands()
    assert response["agents"] == []
    assert response["plugins"] == []
    assert response["mcpServers"] == []
    assert response["error_count"] == 0



def test_control_runtime_initialize_response_includes_settings_skills_and_agents_via_stream_json(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    project_dir = tmp_path / "project"
    (project_dir / ".claude").mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "skills": ["review-pr", "commit"],
                "agents": {"explore": {"description": "Explore codebase", "prompt": "Look around"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    stdin = StringIO(
        '{"type":"control_request","request_id":"req-init","request":{"subtype":"initialize"}}\n'
    )
    stdout = StringIO()

    assert main(["--input-format", "stream-json", "--output-format", "stream-json"], stdin=stdin, stdout=stdout) == 0

    response = SDKControlResponseEnvelope.model_validate_json(stdout.getvalue().splitlines()[0])
    payload = response.response.response
    assert response.response.subtype == "success"
    assert payload is not None
    assert payload["commands"] == _expected_commands(
        {"name": "commit", "description": "Invoke the commit skill", "argumentHint": ""},
        {"name": "review-pr", "description": "Invoke the review-pr skill", "argumentHint": ""},
    )
    assert payload["agents"] == [{"name": "explore", "description": "Explore codebase"}]
    assert [model["value"] for model in payload["models"]] == [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ]
    assert payload["account"] == {}
    assert payload["mcpServers"] == []


def test_control_runtime_initialize_includes_current_mcp_statuses() -> None:
    runtime = ControlRuntime(RuntimeState())
    runtime.handle_request(
        SDKControlMcpSetServersRequest.model_validate(
            {
                "subtype": "mcp_set_servers",
                "servers": {
                    "local": {"command": "python", "args": ["-m", "server"]},
                },
            }
        )
    )

    response = runtime.handle_request(SDKControlInitializeRequest.model_validate({"subtype": "initialize"}))

    assert response is not None
    assert response["mcpServers"] == [
        {
            "name": "local",
            "status": "pending",
            "config": {"command": "python", "args": ["-m", "server"]},
            "scope": "local",
        }
    ]



def test_control_runtime_reload_plugins_includes_current_mcp_statuses() -> None:
    runtime = ControlRuntime(RuntimeState())
    runtime.handle_request(
        SDKControlMcpSetServersRequest.model_validate(
            {
                "subtype": "mcp_set_servers",
                "servers": {
                    "local": {"command": "python", "args": ["-m", "server"]},
                },
            }
        )
    )

    response = runtime.handle_request(
        SDKControlReloadPluginsRequest.model_validate({"subtype": "reload_plugins"})
    )

    assert response is not None
    assert response["commands"] == _expected_commands()
    assert response["agents"] == []
    assert response["plugins"] == []
    assert response["error_count"] == 0
    assert [server["name"] for server in response["mcpServers"]] == ["local"]
    assert response["mcpServers"][0]["status"] == "pending"



def test_control_runtime_mcp_toggle_updates_server_status() -> None:
    runtime = ControlRuntime(RuntimeState())
    runtime.handle_request(
        SDKControlMcpSetServersRequest.model_validate(
            {
                "subtype": "mcp_set_servers",
                "servers": {
                    "local": {"command": "python", "args": ["-m", "server"]},
                },
            }
        )
    )

    toggle_response = runtime.handle_request(
        SDKControlMcpToggleRequest.model_validate(
            {"subtype": "mcp_toggle", "serverName": "local", "enabled": False}
        )
    )
    status_response = runtime.handle_request(SDKControlMcpStatusRequest.model_validate({"subtype": "mcp_status"}))

    assert toggle_response == {}
    assert status_response is not None
    assert status_response["mcpServers"] == [
        {
            "name": "local",
            "status": "disabled",
            "config": {"command": "python", "args": ["-m", "server"]},
            "scope": "local",
        }
    ]



def test_control_runtime_mcp_reconnect_allows_enabled_server() -> None:
    runtime = ControlRuntime(RuntimeState())
    runtime.handle_request(
        SDKControlMcpSetServersRequest.model_validate(
            {
                "subtype": "mcp_set_servers",
                "servers": {
                    "local": {"command": "python", "args": ["-m", "server"]},
                },
            }
        )
    )

    response = runtime.handle_request(
        SDKControlMcpReconnectRequest.model_validate(
            {"subtype": "mcp_reconnect", "serverName": "local"}
        )
    )

    assert response == {}



def test_control_runtime_mcp_reconnect_raises_for_disabled_server() -> None:
    runtime = ControlRuntime(RuntimeState())
    runtime.handle_request(
        SDKControlMcpSetServersRequest.model_validate(
            {
                "subtype": "mcp_set_servers",
                "servers": {
                    "local": {"command": "python", "args": ["-m", "server"]},
                },
            }
        )
    )
    runtime.handle_request(
        SDKControlMcpToggleRequest.model_validate(
            {"subtype": "mcp_toggle", "serverName": "local", "enabled": False}
        )
    )

    with pytest.raises(StructuredIOError, match=r"Server is disabled: local"):
        runtime.handle_request(
            SDKControlMcpReconnectRequest.model_validate(
                {"subtype": "mcp_reconnect", "serverName": "local"}
            )
        )



def test_control_runtime_mcp_message_supports_stdio_transport(tmp_path) -> None:
    script = tmp_path / "stdio_mcp.py"
    script.write_text(
        "import json, sys\n"
        "message = json.loads(sys.stdin.read())\n"
        "print(json.dumps({\"jsonrpc\": \"2.0\", \"result\": {\"echo\": message}}))\n",
        encoding="utf-8",
    )
    runtime = ControlRuntime(
        RuntimeState(
            flag_settings={
                "mcp": {
                    "local": {"command": sys.executable, "args": [str(script)]},
                }
            }
        )
    )

    response = runtime.handle_request(
        SDKControlMcpMessageRequest.model_validate(
            {
                "subtype": "mcp_message",
                "server_name": "local",
                "message": {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            }
        )
    )

    assert response is not None
    assert response["result"]["echo"] == {"jsonrpc": "2.0", "id": 1, "method": "ping"}



def test_control_runtime_elicitation_defaults_to_cancel_without_hooks() -> None:
    runtime = ControlRuntime(RuntimeState())

    response = runtime.handle_request(
        SDKControlElicitationRequest.model_validate(
            {
                "subtype": "elicitation",
                "mcp_server_name": "local",
                "message": "Need approval",
                "mode": "form",
                "elicitation_id": "elic-1",
                "requested_schema": {"type": "object"},
            }
        )
    )

    assert response == {"action": "cancel", "content": None}



def test_control_runtime_elicitation_uses_hook_action_and_content() -> None:
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "Elicitation",
                "action": "accept",
                "content": {"answer": "yes"},
            }
        }
    )
    runtime = ControlRuntime(
        RuntimeState(
            flag_settings={
                "hooks": {
                    "Elicitation": [
                        {
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ]
                }
            }
        )
    )

    response = runtime.handle_request(
        SDKControlElicitationRequest.model_validate(
            {
                "subtype": "elicitation",
                "mcp_server_name": "local",
                "message": "Need approval",
                "mode": "form",
                "elicitation_id": "elic-1",
                "requested_schema": {"type": "object"},
            }
        )
    )

    assert response == {"action": "accept", "content": {"answer": "yes"}}



def test_control_runtime_elicitation_result_hook_can_override_action_and_content() -> None:
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "ElicitationResult",
                "action": "decline",
                "content": {"reason": "changed"},
            }
        }
    )
    runtime = ControlRuntime(
        RuntimeState(
            flag_settings={
                "hooks": {
                    "Elicitation": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": _python_print_json(
                                        {
                                            "hookSpecificOutput": {
                                                "hookEventName": "Elicitation",
                                                "action": "accept",
                                                "content": {"answer": "yes"},
                                            }
                                        }
                                    ),
                                }
                            ],
                        }
                    ],
                    "ElicitationResult": [
                        {
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ],
                }
            }
        )
    )

    response = runtime.handle_request(
        SDKControlElicitationRequest.model_validate(
            {
                "subtype": "elicitation",
                "mcp_server_name": "local",
                "message": "Need approval",
                "mode": "form",
                "elicitation_id": "elic-1",
                "requested_schema": {"type": "object"},
            }
        )
    )

    assert response == {"action": "decline", "content": {"reason": "changed"}}



def test_control_runtime_set_max_thinking_tokens_updates_runtime_state() -> None:
    state = RuntimeState()
    runtime = ControlRuntime(state)

    response = runtime.handle_request(
        SDKControlSetMaxThinkingTokensRequest.model_validate(
            {"subtype": "set_max_thinking_tokens", "max_thinking_tokens": 4096}
        )
    )

    assert response == {}
    assert state.max_thinking_tokens == 4096



def test_control_runtime_set_max_thinking_tokens_allows_reset_to_none() -> None:
    state = RuntimeState(max_thinking_tokens=2048)
    runtime = ControlRuntime(state)

    response = runtime.handle_request(
        SDKControlSetMaxThinkingTokensRequest.model_validate(
            {"subtype": "set_max_thinking_tokens", "max_thinking_tokens": None}
        )
    )

    assert response == {}
    assert state.max_thinking_tokens is None



def test_control_runtime_seed_read_state_stores_normalized_snapshot(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("\ufeffalpha\r\nbeta\r\n", encoding="utf-8")
    runtime = ControlRuntime(RuntimeState(cwd=str(tmp_path)))

    response = runtime.handle_request(
        SDKControlSeedReadStateRequest.model_validate(
            {"subtype": "seed_read_state", "path": "sample.txt", "mtime": target.stat().st_mtime}
        )
    )

    assert response == {}
    seeded = runtime.state.tool_runtime.seeded_read_state[str(target.resolve())]
    assert seeded == {
        "content": "alpha\nbeta\n",
        "timestamp": target.stat().st_mtime,
        "offset": None,
        "limit": None,
    }



def test_control_runtime_seed_read_state_ignores_newer_disk_state(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("alpha\n", encoding="utf-8")
    runtime = ControlRuntime(RuntimeState(cwd=str(tmp_path)))

    response = runtime.handle_request(
        SDKControlSeedReadStateRequest.model_validate(
            {"subtype": "seed_read_state", "path": str(target), "mtime": target.stat().st_mtime - 1}
        )
    )

    assert response == {}
    assert runtime.state.tool_runtime.seeded_read_state == {}



def test_control_runtime_rewind_files_returns_dry_run_summary(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    state = RuntimeState(cwd=str(tmp_path))
    runtime = ControlRuntime(state)
    state.tool_runtime.execute(
        "Write",
        {"file_path": str(target), "content": "hello\nworld\n"},
        cwd=str(tmp_path),
    )
    state.tool_runtime.execute(
        "Edit",
        {"file_path": str(target), "old_string": "world", "new_string": "claude"},
        cwd=str(tmp_path),
    )

    response = runtime.handle_request(
        SDKControlRewindFilesRequest.model_validate(
            {"subtype": "rewind_files", "user_message_id": "msg-1", "dry_run": True}
        )
    )

    assert response == {
        "canRewind": True,
        "filesChanged": [str(target)],
        "insertions": 2,
        "deletions": 0,
    }
    assert target.read_text(encoding="utf-8") == "hello\nclaude\n"



def test_control_runtime_rewind_files_restores_previous_contents(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    state = RuntimeState(cwd=str(tmp_path))
    runtime = ControlRuntime(state)
    state.tool_runtime.execute(
        "Write",
        {"file_path": str(target), "content": "hello\nworld\n"},
        cwd=str(tmp_path),
    )
    state.tool_runtime.execute(
        "Edit",
        {"file_path": str(target), "old_string": "world", "new_string": "claude"},
        cwd=str(tmp_path),
    )

    response = runtime.handle_request(
        SDKControlRewindFilesRequest.model_validate(
            {"subtype": "rewind_files", "user_message_id": "msg-1", "dry_run": False}
        )
    )

    assert response == {
        "canRewind": True,
        "filesChanged": [str(target)],
        "insertions": 2,
        "deletions": 0,
    }
    assert not target.exists()
    assert state.tool_runtime.file_mutation_history == []



def test_control_runtime_rewind_files_raises_when_no_changes_exist() -> None:
    runtime = ControlRuntime(RuntimeState())

    with pytest.raises(StructuredIOError, match="No recorded file changes"):
        runtime.handle_request(
            SDKControlRewindFilesRequest.model_validate(
                {"subtype": "rewind_files", "user_message_id": "msg-1", "dry_run": False}
            )
        )



def test_control_runtime_rewind_files_dry_run_reports_no_changes_without_error() -> None:
    runtime = ControlRuntime(RuntimeState())

    response = runtime.handle_request(
        SDKControlRewindFilesRequest.model_validate(
            {"subtype": "rewind_files", "user_message_id": "msg-1", "dry_run": True}
        )
    )

    assert response == {
        "canRewind": False,
        "error": "No recorded file changes",
        "filesChanged": [],
    }



def test_control_runtime_stop_task_stops_running_background_task(tmp_path) -> None:
    state = RuntimeState(cwd=str(tmp_path))
    runtime = ControlRuntime(state)
    started = state.tool_runtime.execute(
        "Bash",
        {"command": f"{shlex.quote(sys.executable)} -c \"import time; time.sleep(30)\"", "run_in_background": True},
        cwd=str(tmp_path),
    )

    response = runtime.handle_request(
        SDKControlStopTaskRequest.model_validate({"subtype": "stop_task", "task_id": started.output["task_id"]})
    )

    assert response == {}
    task = state.task_runtime.get(started.output["task_id"])
    assert task.status == "completed"
    assert task.error == "Task stopped"



def test_control_runtime_stop_task_raises_structured_io_error_for_unknown_task() -> None:
    runtime = ControlRuntime(RuntimeState())

    with pytest.raises(StructuredIOError, match=r"Unknown task: missing"):
        runtime.handle_request(
            SDKControlStopTaskRequest.model_validate({"subtype": "stop_task", "task_id": "missing"})
        )



def test_control_runtime_stop_task_raises_structured_io_error_for_non_running_task() -> None:
    state = RuntimeState()
    runtime = ControlRuntime(state)
    created = state.task_runtime.create(subject="Only", description="Only task")

    with pytest.raises(StructuredIOError, match=rf"Task {created.id} is not running"):
        runtime.handle_request(
            SDKControlStopTaskRequest.model_validate({"subtype": "stop_task", "task_id": created.id})
        )



def test_runtime_state_shares_task_runtime_with_tool_runtime() -> None:
    state = RuntimeState()

    created = state.tool_runtime.execute(
        "TaskCreate",
        {"subject": "Shared", "description": "Shared task runtime"},
        cwd=state.cwd,
    )

    assert state.task_runtime.get(created.output["task"]["id"]).subject == "Shared"



def test_tool_runtime_maps_permission_targets_for_builtin_tools() -> None:
    runtime = ToolRuntime()

    assert runtime.permission_target_for("Read", {"file_path": "src/main.py"}).content == "src/main.py"
    assert runtime.permission_target_for("Glob", {"pattern": "src/**/*.py"}).content == "src/**/*.py"
    assert runtime.permission_target_for("Bash", {"command": "pytest -q"}).content == "pytest -q"



def test_control_runtime_uses_tool_owned_permission_target() -> None:
    runtime = _runtime_with_custom_write_tool()

    allow_response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Write",
                "input": {"path": "allowed.txt"},
                "tool_use_id": "tool-custom",
            }
        )
    )
    deny_response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Write",
                "input": {"path": "blocked.txt"},
                "tool_use_id": "tool-custom-deny",
            }
        )
    )

    assert allow_response == {"behavior": "allow", "updatedInput": {"path": "allowed.txt"}}
    assert deny_response == {
        "behavior": "deny",
        "message": "Write requires permission",
        "toolUseID": "tool-custom-deny",
    }



def test_permission_engine_respects_rule_priority_and_modes(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)

    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read(src/*.py)"], "ask": ["Bash(pytest:*)"]}}),
        encoding="utf-8",
    )
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"deny": ["Read(src/secret.py)"]}}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))
    settings_response = runtime.handle_request(SDKControlGetSettingsRequest.model_validate({"subtype": "get_settings"}))

    assert settings_response is not None
    context = build_permission_context(
        type("SettingsLike", (), {"effective": settings_response["effective"], "sources": settings_response["sources"]})(),
        mode="default",
    )
    engine = PermissionEngine(context)

    assert engine.evaluate("Read", "src/main.py").behavior == "allow"
    assert engine.evaluate("Read", "src/secret.py").behavior == "deny"
    assert engine.evaluate("Bash", "pytest tests").behavior == "ask"
    assert engine.evaluate("Write", "src/main.py").behavior == "ask"



def test_permission_rule_helpers_match_bash_prefix_and_mcp_server_scope() -> None:
    bash_rule = PermissionRule(
        source="userSettings",
        rule_behavior="allow",
        rule_value=parse_permission_rule_value("Bash(pytest:*)"),
    )
    mcp_rule = PermissionRule(
        source="projectSettings",
        rule_behavior="allow",
        rule_value=parse_permission_rule_value("mcp__local__*"),
    )

    assert matches_permission_rule(bash_rule, type("Target", (), {"tool_name": "Bash", "content": "pytest -q"})())
    assert not matches_permission_rule(bash_rule, type("Target", (), {"tool_name": "Bash", "content": "python -m pytest"})())
    assert matches_permission_rule(mcp_rule, type("Target", (), {"tool_name": "mcp__local__search", "content": None})())
    assert not matches_permission_rule(mcp_rule, type("Target", (), {"tool_name": "mcp__remote__search", "content": None})())



def test_control_runtime_can_use_tool_returns_allow_and_deny_results(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)

    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read(src/*.py)"]}}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir), permission_mode="dontAsk"))

    allow_response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Read",
                "input": {"file_path": "src/main.py"},
                "tool_use_id": "tool-1",
            }
        )
    )
    deny_response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Write",
                "input": {"file_path": "src/main.py", "content": "x"},
                "tool_use_id": "tool-2",
            }
        )
    )

    assert allow_response == {"behavior": "allow", "updatedInput": {"file_path": "src/main.py"}}
    assert deny_response == {
        "behavior": "deny",
        "message": "Current permission mode (dontAsk) denies Write",
        "toolUseID": "tool-2",
    }



def test_control_runtime_can_use_tool_uses_request_description_for_promptable_actions() -> None:
    runtime = ControlRuntime(RuntimeState())

    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Bash",
                "input": {"command": "pytest"},
                "tool_use_id": "tool-3",
                "description": "Run tests",
            }
        )
    )

    assert response == {
        "behavior": "deny",
        "message": "Run tests",
        "toolUseID": "tool-3",
    }



def test_permission_context_honors_managed_only_policy() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"allowManagedPermissionRulesOnly": True},
            "sources": [
                {"source": "userSettings", "settings": {"permissions": {"allow": ["Read(src/*.py)"]}}},
                {"source": "policySettings", "settings": {"permissions": {"deny": ["Read(secret.txt)"]}}},
            ],
        },
    )()

    context = build_permission_context(settings, mode="default")
    engine = PermissionEngine(context)

    assert context.allow_managed_permission_rules_only is True
    assert engine.evaluate("Read", "src/main.py").behavior == "ask"
    assert engine.evaluate("Read", "secret.txt").behavior == "deny"



def test_permission_context_disables_bypass_mode_when_settings_forbid_it() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"disableBypassPermissionsMode": "disable", "allow": ["Read"]}},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read"]}}}],
        },
    )()

    context = build_permission_context(settings, mode="bypassPermissions")

    assert context.mode == "default"
    assert context.disable_bypass_permissions_mode is True



def test_permission_context_uses_default_mode_from_settings() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"defaultMode": "plan", "additionalDirectories": ["/tmp", 1]}},
            "sources": [],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert context.mode == "plan"
    assert context.additional_directories == ["/tmp"]



def test_permission_rule_round_trip_serialization() -> None:
    rule = parse_permission_rule_value(r"Read(path\(with\).txt)")

    assert rule.toolName == "Read"
    assert rule.ruleContent == r"path\(with\).txt"
    assert permission_rule_value_to_string(rule) == r"Read(path\(with\).txt)"



def test_permission_engine_bypass_mode_still_respects_explicit_ask_and_deny() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"ask": ["Bash(pytest:*)"], "deny": ["Bash(rm:*)"]}},
            "sources": [
                {"source": "userSettings", "settings": {"permissions": {"ask": ["Bash(pytest:*)"], "deny": ["Bash(rm:*)"]}}}
            ],
        },
    )()

    engine = PermissionEngine.from_settings(settings, mode="bypassPermissions")

    assert engine.evaluate("Bash", "rm -rf tmp").behavior == "deny"
    assert engine.evaluate("Bash", "pytest tests").behavior == "ask"
    assert engine.evaluate("Read", "README.md").behavior == "allow"



def test_permission_engine_dont_ask_denies_by_mode() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": []})()
    engine = PermissionEngine.from_settings(settings, mode="dontAsk")

    result = engine.evaluate("Read", "README.md")

    assert result.behavior == "deny"
    assert result.reason == "mode"



def test_permission_engine_prefers_earlier_source_order_within_behavior() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [
                {"source": "userSettings", "settings": {"permissions": {"allow": ["Read(user.txt)"]}}},
                {"source": "projectSettings", "settings": {"permissions": {"allow": ["Read(project.txt)"]}}},
            ],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Read", "user.txt").matched_rule is not None
    assert engine.evaluate("Read", "user.txt").matched_rule.source == "userSettings"
    assert engine.evaluate("Read", "project.txt").matched_rule is not None
    assert engine.evaluate("Read", "project.txt").matched_rule.source == "projectSettings"



def test_permission_engine_matches_tool_level_rule_without_content() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Read", None).behavior == "allow"
    assert engine.evaluate("Read", "anything.txt").behavior == "allow"
    assert engine.evaluate("Write", "anything.txt").behavior == "ask"



def test_permission_engine_ask_rule_takes_precedence_over_allow_rule() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Bash"], "ask": ["Bash(pytest:*)"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Bash", "pytest tests").behavior == "ask"
    assert engine.evaluate("Bash", "echo hi").behavior == "allow"



def test_permission_engine_deny_rule_takes_precedence_over_allow_rule() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read"], "deny": ["Read(secret.txt)"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Read", "secret.txt").behavior == "deny"
    assert engine.evaluate("Read", "other.txt").behavior == "allow"



def test_permission_context_collects_rules_by_source() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [
                {"source": "userSettings", "settings": {"permissions": {"allow": ["Read"]}}},
                {"source": "projectSettings", "settings": {"permissions": {"deny": ["Write"]}}},
                {"source": "flagSettings", "settings": {"permissions": {"ask": ["Bash(pytest:*)"]}}},
            ],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert [rule.source for rule in context.rules_for_behavior("allow")] == ["userSettings"]
    assert [rule.source for rule in context.rules_for_behavior("deny")] == ["projectSettings"]
    assert [rule.source for rule in context.rules_for_behavior("ask")] == ["flagSettings"]



def test_permission_rule_parser_supports_tool_without_pattern() -> None:
    rule = parse_permission_rule_value("Read")

    assert rule.toolName == "Read"
    assert rule.ruleContent is None
    assert permission_rule_value_to_string(rule) == "Read"



def test_permission_rule_parser_supports_mcp_server_rule() -> None:
    rule = parse_permission_rule_value("mcp__docs")

    assert rule.toolName == "mcp__docs"
    assert rule.ruleContent is None
    assert permission_rule_value_to_string(rule) == "mcp__docs"



def test_permission_engine_matches_mcp_server_rule() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["mcp__docs"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("mcp__docs__search", None).behavior == "allow"
    assert engine.evaluate("mcp__other__search", None).behavior == "ask"



def test_permission_engine_matches_glob_patterns_for_file_tools() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read(src/**/*.py)"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Read", "src/pkg/main.py").behavior == "allow"
    assert engine.evaluate("Read", "tests/test_main.py").behavior == "ask"



def test_permission_engine_returns_default_ask_without_rules() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": []})()
    engine = PermissionEngine.from_settings(settings, mode="default")

    result = engine.evaluate("Read", "README.md")

    assert result.behavior == "ask"
    assert result.reason == "default"



def test_permission_context_ignores_unknown_source_entries() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [
                {"source": "unknown", "settings": {"permissions": {"allow": ["Read"]}}},
                {"source": "userSettings", "settings": {"permissions": {"allow": ["Write"]}}},
            ],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert [rule.rule_value.toolName for rule in context.rules_for_behavior("allow")] == ["Write"]



def test_permission_context_ignores_non_string_rules() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read", 1, None]}}}],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert [rule.rule_value.toolName for rule in context.rules_for_behavior("allow")] == ["Read"]



def test_permission_context_ignores_invalid_additional_directories_values() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"additionalDirectories": ["/tmp", None, 1, "/var/tmp"]}},
            "sources": [],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert context.additional_directories == ["/tmp", "/var/tmp"]



def test_permission_engine_uses_default_mode_when_bypass_not_disabled() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"defaultMode": "bypassPermissions"}},
            "sources": [],
        },
    )()

    context = build_permission_context(settings, mode="default")
    engine = PermissionEngine(context)

    assert context.mode == "bypassPermissions"
    assert engine.evaluate("Write", "x").behavior == "allow"



def test_permission_engine_preserves_matched_rule_details() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read(README.md)"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    result = engine.evaluate("Read", "README.md")

    assert result.matched_rule is not None
    assert result.matched_rule.source == "userSettings"
    assert result.matched_rule.rule_value.toolName == "Read"
    assert result.matched_rule.rule_value.ruleContent == "README.md"



def test_permission_engine_ask_rule_without_content_matches_entire_tool() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"ask": ["Bash"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Bash", "echo hi").behavior == "ask"



def test_permission_engine_deny_rule_without_content_matches_entire_tool() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"deny": ["Write"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Write", "file.txt").behavior == "deny"



def test_permission_context_mode_can_be_overridden_explicitly() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"defaultMode": "plan"}},
            "sources": [],
        },
    )()

    context = build_permission_context(settings, mode="acceptEdits")

    assert context.mode == "acceptEdits"



def test_permission_engine_default_mode_applies_when_explicit_mode_default() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"defaultMode": "dontAsk"}},
            "sources": [],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Read", "README.md").behavior == "deny"
    assert engine.evaluate("Read", "README.md").mode == "dontAsk"



def test_permission_context_keeps_empty_rule_maps_when_no_permissions() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": [{"source": "userSettings", "settings": {}}]})()

    context = build_permission_context(settings, mode="default")

    assert context.allow_rules == {}
    assert context.deny_rules == {}
    assert context.ask_rules == {}



def test_permission_engine_ask_rule_matches_before_mode_allow() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"ask": ["Read(secret.txt)"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="bypassPermissions")

    assert engine.evaluate("Read", "secret.txt").behavior == "ask"



def test_permission_engine_deny_rule_matches_before_mode_allow() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"deny": ["Read(secret.txt)"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="bypassPermissions")

    assert engine.evaluate("Read", "secret.txt").behavior == "deny"



def test_permission_context_filters_non_dict_source_settings() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [
                {"source": "userSettings", "settings": None},
                {"source": "projectSettings", "settings": {"permissions": {"allow": ["Read"]}}},
            ],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert [rule.source for rule in context.rules_for_behavior("allow")] == ["projectSettings"]



def test_permission_rule_parser_preserves_parentheses_content() -> None:
    rule = parse_permission_rule_value(r"Bash(python -c \"print(1)\")")

    assert rule.toolName == "Bash"
    assert rule.ruleContent == r"python -c \"print(1)\""
    assert permission_rule_value_to_string(rule) == r"Bash(python -c \"print(1)\")"



def test_permission_engine_handles_missing_content_for_pattern_rule() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read(README.md)"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Read", None).behavior == "ask"



def test_permission_context_managed_only_keeps_policy_ask_rules() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"allowManagedPermissionRulesOnly": True},
            "sources": [
                {"source": "policySettings", "settings": {"permissions": {"ask": ["Bash"]}}},
                {"source": "userSettings", "settings": {"permissions": {"allow": ["Bash"]}}},
            ],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Bash", "echo hi").behavior == "ask"



def test_control_runtime_can_use_tool_returns_tool_use_id_on_allow_absence() -> None:
    runtime = ControlRuntime(RuntimeState())

    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Read",
                "input": {"file_path": "README.md"},
                "tool_use_id": "tool-4",
            }
        )
    )

    assert response == {
        "behavior": "deny",
        "message": "Read requires permission",
        "toolUseID": "tool-4",
    }



def test_control_runtime_can_use_tool_handles_bash_command_content_matching(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(pytest:*)"]}}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))
    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Bash",
                "input": {"command": "pytest -q"},
                "tool_use_id": "tool-5",
            }
        )
    )

    assert response == {"behavior": "allow", "updatedInput": {"command": "pytest -q"}}



def test_control_runtime_can_use_tool_handles_glob_pattern_matching(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read(src/**/*.py)"]}}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))
    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Read",
                "input": {"file_path": "src/pkg/main.py"},
                "tool_use_id": "tool-6",
            }
        )
    )

    assert response == {"behavior": "allow", "updatedInput": {"file_path": "src/pkg/main.py"}}



def test_control_runtime_can_use_tool_deny_rule_beats_allow_rule(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read"], "deny": ["Read(secret.txt)"]}}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))
    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Read",
                "input": {"file_path": "secret.txt"},
                "tool_use_id": "tool-7",
            }
        )
    )

    assert response == {
        "behavior": "deny",
        "message": "Read requires permission",
        "toolUseID": "tool-7",
    }



def test_control_runtime_can_use_tool_ask_rule_returns_deny_payload_shape(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"ask": ["Bash(pytest:*)"]}}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))
    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Bash",
                "input": {"command": "pytest -q"},
                "tool_use_id": "tool-8",
                "description": "Run pytest",
            }
        )
    )

    assert response == {
        "behavior": "deny",
        "message": "Run pytest",
        "toolUseID": "tool-8",
    }



def test_control_runtime_can_use_tool_supports_grep_pattern_extraction() -> None:
    runtime = ControlRuntime(RuntimeState())
    request = SDKControlPermissionRequest.model_validate(
        {
            "subtype": "can_use_tool",
            "tool_name": "Grep",
            "input": {"pattern": "foo", "path": "."},
            "tool_use_id": "tool-9",
        }
    )

    assert runtime.state.tool_runtime.permission_target_for(request.tool_name, request.input).content == "foo"



def test_control_runtime_can_use_tool_supports_unknown_tool_without_content() -> None:
    runtime = ControlRuntime(RuntimeState())
    request = SDKControlPermissionRequest.model_validate(
        {
            "subtype": "can_use_tool",
            "tool_name": "CustomTool",
            "input": {"value": 1},
            "tool_use_id": "tool-10",
        }
    )

    target = runtime.state.tool_runtime.permission_target_for(request.tool_name, request.input)
    assert target.tool_name == "CustomTool"
    assert target.content is None



def test_permission_rule_matches_exact_tool_name_first() -> None:
    rule = PermissionRule(
        source="userSettings",
        rule_behavior="allow",
        rule_value=parse_permission_rule_value("Read"),
    )

    assert matches_permission_rule(rule, type("Target", (), {"tool_name": "Read", "content": None})())
    assert not matches_permission_rule(rule, type("Target", (), {"tool_name": "Write", "content": None})())



def test_permission_rule_matches_mcp_server_without_wildcard() -> None:
    rule = PermissionRule(
        source="userSettings",
        rule_behavior="allow",
        rule_value=parse_permission_rule_value("mcp__docs"),
    )

    assert matches_permission_rule(rule, type("Target", (), {"tool_name": "mcp__docs__search", "content": None})())
    assert not matches_permission_rule(rule, type("Target", (), {"tool_name": "mcp__other__search", "content": None})())



def test_permission_rule_with_content_requires_target_content() -> None:
    rule = PermissionRule(
        source="userSettings",
        rule_behavior="allow",
        rule_value=parse_permission_rule_value("Read(README.md)"),
    )

    assert not matches_permission_rule(rule, type("Target", (), {"tool_name": "Read", "content": None})())



def test_permission_context_managed_only_returns_policy_rules_only() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"allowManagedPermissionRulesOnly": True},
            "sources": [
                {"source": "policySettings", "settings": {"permissions": {"allow": ["Read"]}}},
                {"source": "userSettings", "settings": {"permissions": {"allow": ["Write"]}}},
            ],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert [rule.rule_value.toolName for rule in context.rules_for_behavior("allow")] == ["Read"]



def test_permission_engine_uses_ask_before_default_mode_allow() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"defaultMode": "bypassPermissions", "ask": ["Read(secret.txt)"]}},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"ask": ["Read(secret.txt)"]}}}],
        },
    )()

    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Read", "secret.txt").behavior == "ask"



def test_permission_engine_uses_deny_before_default_mode_allow() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"defaultMode": "bypassPermissions", "deny": ["Read(secret.txt)"]}},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"deny": ["Read(secret.txt)"]}}}],
        },
    )()

    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Read", "secret.txt").behavior == "deny"



def test_control_runtime_can_use_tool_with_default_bypass_mode_allows_when_no_rule(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "bypassPermissions"}}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))
    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Write",
                "input": {"file_path": "x.txt", "content": "hi"},
                "tool_use_id": "tool-11",
            }
        )
    )

    assert response == {"behavior": "allow", "updatedInput": {"file_path": "x.txt", "content": "hi"}}



def test_control_runtime_can_use_tool_with_disabled_bypass_default_mode_prompts(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "bypassPermissions", "disableBypassPermissionsMode": "disable"}}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))
    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Write",
                "input": {"file_path": "x.txt", "content": "hi"},
                "tool_use_id": "tool-12",
            }
        )
    )

    assert response == {
        "behavior": "deny",
        "message": "Write requires permission",
        "toolUseID": "tool-12",
    }



def test_permission_engine_with_policy_only_and_default_bypass_can_still_allow_by_mode() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"allowManagedPermissionRulesOnly": True, "permissions": {"defaultMode": "bypassPermissions"}},
            "sources": [],
        },
    )()

    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Write", "x.txt").behavior == "allow"



def test_permission_engine_policy_only_with_policy_ask_overrides_bypass() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"allowManagedPermissionRulesOnly": True, "permissions": {"defaultMode": "bypassPermissions"}},
            "sources": [{"source": "policySettings", "settings": {"permissions": {"ask": ["Write"]}}}],
        },
    )()

    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Write", "x.txt").behavior == "ask"



def test_permission_engine_policy_only_with_policy_deny_overrides_bypass() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"allowManagedPermissionRulesOnly": True, "permissions": {"defaultMode": "bypassPermissions"}},
            "sources": [{"source": "policySettings", "settings": {"permissions": {"deny": ["Write"]}}}],
        },
    )()

    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Write", "x.txt").behavior == "deny"



def test_control_runtime_can_use_tool_prefers_description_even_in_dont_ask() -> None:
    runtime = ControlRuntime(RuntimeState(permission_mode="dontAsk"))

    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Write",
                "input": {"file_path": "x.txt", "content": "hi"},
                "tool_use_id": "tool-13",
                "description": "Edit file",
            }
        )
    )

    assert response == {
        "behavior": "deny",
        "message": "Edit file",
        "toolUseID": "tool-13",
    }



def test_permission_engine_returns_mode_in_result() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": []})()
    result = PermissionEngine.from_settings(settings, mode="plan").evaluate("Read", "README.md")

    assert result.mode == "plan"



def test_permission_context_rule_order_includes_session_after_disk_sources() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [
                {"source": "userSettings", "settings": {"permissions": {"allow": ["Read(user.txt)"]}}},
                {"source": "flagSettings", "settings": {"permissions": {"allow": ["Read(flag.txt)"]}}},
            ],
        },
    )()
    context = build_permission_context(settings, mode="default")
    context.allow_rules["session"] = [
        PermissionRule(source="session", rule_behavior="allow", rule_value=parse_permission_rule_value("Read(session.txt)"))
    ]

    assert [rule.source for rule in context.rules_for_behavior("allow")] == ["userSettings", "flagSettings", "session"]



def test_permission_engine_matches_command_source_rules_when_injected() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": []})()
    context = build_permission_context(settings, mode="default")
    context.ask_rules["command"] = [
        PermissionRule(source="command", rule_behavior="ask", rule_value=parse_permission_rule_value("Bash(npm publish:*)"))
    ]
    engine = PermissionEngine(context)

    assert engine.evaluate("Bash", "npm publish --tag next").behavior == "ask"



def test_permission_rule_to_string_preserves_bash_prefix_rule() -> None:
    rule = parse_permission_rule_value("Bash(pytest:*)")

    assert permission_rule_value_to_string(rule) == "Bash(pytest:*)"



def test_permission_context_default_mode_ignores_invalid_mode_string() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"defaultMode": "auto"}},
            "sources": [],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert context.mode == "default"



def test_permission_context_collects_multiple_rules_per_source() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read", "Write"]}}}],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert [rule.rule_value.toolName for rule in context.rules_for_behavior("allow")] == ["Read", "Write"]



def test_permission_engine_uses_exact_match_for_non_glob_pattern() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read(README.md)"]}}}],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Read", "README.md").behavior == "allow"
    assert engine.evaluate("Read", "docs/README.md").behavior == "ask"



def test_permission_rule_matches_mcp_specific_tool_name() -> None:
    rule = PermissionRule(
        source="policySettings",
        rule_behavior="allow",
        rule_value=parse_permission_rule_value("mcp__docs__search"),
    )

    assert matches_permission_rule(rule, type("Target", (), {"tool_name": "mcp__docs__search", "content": None})())
    assert not matches_permission_rule(rule, type("Target", (), {"tool_name": "mcp__docs__read", "content": None})())



def test_permission_engine_preserves_reason_for_rule_matches() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read"]}}}],
        },
    )()
    result = PermissionEngine.from_settings(settings, mode="default").evaluate("Read", "README.md")

    assert result.reason == "allow_rule"



def test_permission_engine_preserves_reason_for_default() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": []})()
    result = PermissionEngine.from_settings(settings, mode="default").evaluate("Read", "README.md")

    assert result.reason == "default"



def test_permission_engine_preserves_reason_for_deny_rule() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"deny": ["Read"]}}}],
        },
    )()
    result = PermissionEngine.from_settings(settings, mode="default").evaluate("Read", "README.md")

    assert result.reason == "deny_rule"



def test_permission_engine_preserves_reason_for_ask_rule() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"ask": ["Read"]}}}],
        },
    )()
    result = PermissionEngine.from_settings(settings, mode="default").evaluate("Read", "README.md")

    assert result.reason == "ask_rule"



def test_permission_context_mode_stays_default_without_permissions_block() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": []})()

    context = build_permission_context(settings, mode="default")

    assert context.mode == "default"



def test_control_runtime_permission_message_defaults_for_unknown_reason() -> None:
    runtime = ControlRuntime(RuntimeState())

    assert runtime._build_permission_message("Read", "default") == "Read requires permission"



def test_permission_rule_mcp_wildcard_requires_server_prefix() -> None:
    rule = PermissionRule(
        source="policySettings",
        rule_behavior="allow",
        rule_value=parse_permission_rule_value("mcp__docs__*"),
    )

    assert not matches_permission_rule(rule, type("Target", (), {"tool_name": "Read", "content": None})())



def test_control_runtime_permission_content_uses_file_path_for_write() -> None:
    runtime = ControlRuntime(RuntimeState())
    request = SDKControlPermissionRequest.model_validate(
        {
            "subtype": "can_use_tool",
            "tool_name": "Write",
            "input": {"file_path": "x.txt", "content": "hi"},
            "tool_use_id": "tool-14",
        }
    )

    assert runtime.state.tool_runtime.permission_target_for(request.tool_name, request.input).content == "x.txt"



def test_control_runtime_permission_content_uses_pattern_for_glob() -> None:
    runtime = ControlRuntime(RuntimeState())
    request = SDKControlPermissionRequest.model_validate(
        {
            "subtype": "can_use_tool",
            "tool_name": "Glob",
            "input": {"pattern": "src/**/*.py", "path": "."},
            "tool_use_id": "tool-15",
        }
    )

    assert runtime.state.tool_runtime.permission_target_for(request.tool_name, request.input).content == "src/**/*.py"



def test_permission_engine_allow_rule_without_content_beats_default_ask() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Write"]}}}],
        },
    )()

    assert PermissionEngine.from_settings(settings, mode="default").evaluate("Write", "x.txt").behavior == "allow"



def test_permission_context_managed_only_with_no_policy_rules_returns_empty() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"allowManagedPermissionRulesOnly": True},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read"]}}}],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert context.rules_for_behavior("allow") == []



def test_permission_rule_string_with_nested_parentheses_round_trips() -> None:
    original = r"Bash(python -c \"print(func(1))\")"
    rule = parse_permission_rule_value(original)

    assert permission_rule_value_to_string(rule) == original



def test_permission_engine_handles_flag_settings_source() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "flagSettings", "settings": {"permissions": {"allow": ["Read"]}}}],
        },
    )()

    assert PermissionEngine.from_settings(settings, mode="default").evaluate("Read", "x").behavior == "allow"



def test_permission_context_returns_empty_for_unknown_behavior_map_request() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": []})()
    context = build_permission_context(settings, mode="default")

    assert context.rules_for_behavior("ask") == []



def test_permission_context_filters_sources_when_managed_only_enabled() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"allowManagedPermissionRulesOnly": True},
            "sources": [
                {"source": "flagSettings", "settings": {"permissions": {"allow": ["Read"]}}},
                {"source": "policySettings", "settings": {"permissions": {"allow": ["Write"]}}},
            ],
        },
    )()

    context = build_permission_context(settings, mode="default")

    assert [rule.rule_value.toolName for rule in context.rules_for_behavior("allow")] == ["Write"]



def test_permission_engine_ignores_allow_rules_when_policy_only_enabled_without_policy_allow() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"allowManagedPermissionRulesOnly": True},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["Read"]}}}],
        },
    )()

    assert PermissionEngine.from_settings(settings, mode="default").evaluate("Read", "x").behavior == "ask"



def test_control_runtime_can_use_tool_allows_with_tool_level_read_rule(tmp_path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude").mkdir(parents=True)
    (home_dir / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read"]}}),
        encoding="utf-8",
    )

    runtime = ControlRuntime(RuntimeState(cwd=str(project_dir), home_dir=str(home_dir)))
    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Read",
                "input": {"file_path": "any.txt"},
                "tool_use_id": "tool-16",
            }
        )
    )

    assert response == {"behavior": "allow", "updatedInput": {"file_path": "any.txt"}}



def test_permission_engine_handles_session_source_in_rule_lookup() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": []})()
    context = build_permission_context(settings, mode="default")
    context.deny_rules["session"] = [
        PermissionRule(source="session", rule_behavior="deny", rule_value=parse_permission_rule_value("Read(secret.txt)"))
    ]
    engine = PermissionEngine(context)

    assert engine.evaluate("Read", "secret.txt").behavior == "deny"



def test_permission_engine_handles_cli_arg_source_in_rule_lookup() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": []})()
    context = build_permission_context(settings, mode="default")
    context.allow_rules["cliArg"] = [
        PermissionRule(source="cliArg", rule_behavior="allow", rule_value=parse_permission_rule_value("Write") )
    ]
    engine = PermissionEngine(context)

    assert engine.evaluate("Write", "x.txt").behavior == "allow"



def test_permission_engine_handles_policy_source_priority_with_managed_only() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"allowManagedPermissionRulesOnly": True},
            "sources": [
                {"source": "policySettings", "settings": {"permissions": {"allow": ["Read(policy.txt)"]}}},
                {"source": "userSettings", "settings": {"permissions": {"allow": ["Read(user.txt)"]}}},
            ],
        },
    )()
    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("Read", "policy.txt").behavior == "allow"
    assert engine.evaluate("Read", "user.txt").behavior == "ask"



def test_permission_context_allows_empty_permissions_dict() -> None:
    settings = type("SettingsLike", (), {"effective": {"permissions": {}}, "sources": []})()

    context = build_permission_context(settings, mode="default")

    assert context.mode == "default"
    assert context.additional_directories == []



def test_permission_engine_allow_rule_for_mcp_specific_tool() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "policySettings", "settings": {"permissions": {"allow": ["mcp__docs__search"]}}}],
        },
    )()

    engine = PermissionEngine.from_settings(settings, mode="default")

    assert engine.evaluate("mcp__docs__search", None).behavior == "allow"
    assert engine.evaluate("mcp__docs__read", None).behavior == "ask"



def test_permission_rule_parser_handles_plain_parenthesis_content() -> None:
    rule = parse_permission_rule_value("Read(file(name).txt)")

    assert rule.toolName == "Read"
    assert rule.ruleContent == "file(name).txt"



def test_permission_engine_ask_rule_for_unknown_tool_level() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"ask": ["CustomTool"]}}}],
        },
    )()

    assert PermissionEngine.from_settings(settings, mode="default").evaluate("CustomTool", None).behavior == "ask"



def test_permission_engine_deny_rule_for_unknown_tool_level() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"deny": ["CustomTool"]}}}],
        },
    )()

    assert PermissionEngine.from_settings(settings, mode="default").evaluate("CustomTool", None).behavior == "deny"



def test_permission_engine_allow_rule_for_unknown_tool_level() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {},
            "sources": [{"source": "userSettings", "settings": {"permissions": {"allow": ["CustomTool"]}}}],
        },
    )()

    assert PermissionEngine.from_settings(settings, mode="default").evaluate("CustomTool", None).behavior == "allow"



def test_permission_context_default_mode_prefers_explicit_non_default_mode() -> None:
    settings = type(
        "SettingsLike",
        (),
        {
            "effective": {"permissions": {"defaultMode": "plan"}},
            "sources": [],
        },
    )()

    assert build_permission_context(settings, mode="dontAsk").mode == "dontAsk"



def test_permission_engine_reason_mode_for_bypass() -> None:
    settings = type("SettingsLike", (), {"effective": {}, "sources": []})()
    result = PermissionEngine.from_settings(settings, mode="bypassPermissions").evaluate("Write", "x")

    assert result.reason == "mode"
