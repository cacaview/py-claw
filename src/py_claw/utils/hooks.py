"""
Hooks utility functions.

This module provides utility functions for working with hooks in Claude Code,
including pattern matching, timeout management, and hook input/output processing.
"""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Generator,
    Literal,
    Protocol,
    TypedDict,
)
from .hooks_types import (
    HookEvent,
    HookResult,
    HookInput,
    HookJSONOutput,
    PermissionBehavior,
    MatchedHook,
    PreToolUseHookInput,
    PostToolUseHookInput,
    PostToolUseFailureHookInput,
    PermissionDeniedHookInput,
    SessionStartHookInput,
    SessionEndHookInput,
    SetupHookInput,
    StopHookInput,
    StopFailureHookInput,
    NotificationHookInput,
    PreCompactHookInput,
    PostCompactHookInput,
    SubagentStartHookInput,
    SubagentStopHookInput,
    TeammateIdleHookInput,
    TaskCreatedHookInput,
    TaskCompletedHookInput,
    ConfigChangeHookInput,
    CwdChangedHookInput,
    FileChangedHookInput,
    InstructionsLoadedHookInput,
    ElicitationHookInput,
    ElicitationResultHookInput,
)

# Default timeout for tool hook execution (10 minutes)
TOOL_HOOK_EXECUTION_TIMEOUT_MS = 10 * 60 * 1000

# Default timeout for session end hooks (1.5 seconds)
SESSION_END_HOOK_TIMEOUT_MS_DEFAULT = 1500


class HookBlockingError(Exception):
    """Exception raised when a hook blocks an operation."""

    def __init__(self, message: str, command: str | None = None) -> None:
        super().__init__(message)
        self.command = command


@dataclass
class BaseHookInput:
    """Base class for hook input data."""

    hook_event_name: str
    session_id: str


@dataclass
class HookMatchResult:
    """Result of matching a pattern against a value."""

    matched: bool
    pattern: str
    value: str


def get_session_end_hook_timeout_ms() -> int:
    """
    Get the timeout for session end hooks in milliseconds.

    Can be overridden via CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS env var.

    Returns:
        Timeout in milliseconds
    """
    raw = os.environ.get("CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS")
    if raw:
        try:
            parsed = int(raw, 10)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return SESSION_END_HOOK_TIMEOUT_MS_DEFAULT


def get_tool_hook_timeout_ms() -> int:
    """
    Get the timeout for tool hook execution in milliseconds.

    Returns:
        Timeout in milliseconds (default 10 minutes)
    """
    return TOOL_HOOK_EXECUTION_TIMEOUT_MS


def matches_pattern(value: str, pattern: str) -> bool:
    """
    Check if a value matches a glob or regex pattern.

    Args:
        value: The value to check
        pattern: The pattern to match against (glob or regex)

    Returns:
        True if the value matches the pattern
    """
    if not pattern:
        return True

    # Check if it's a regex pattern (starts with ^ or contains common regex chars)
    if _is_regex_pattern(pattern):
        try:
            return bool(re.search(pattern, value))
        except re.error:
            # If regex is invalid, fall back to glob
            pass

    # Use glob matching
    return fnmatch.fnmatch(value, pattern)


def _is_regex_pattern(pattern: str) -> bool:
    """Check if a pattern looks like a regex."""
    # Common regex metacharacters that indicate a regex pattern
    regex_indicators = ["^", "$", "+", "?", "{", "}", "[", "]", "(", ")"]
    return any(ind in pattern for ind in regex_indicators)


def get_hook_display_text(hook_name: str) -> str:
    """
    Get the display text for a hook name.

    Args:
        hook_name: The hook name (e.g., 'PreToolUse')

    Returns:
        Human-readable display text
    """
    hook_display_names = {
        "PreToolUse": "Pre-Tool Use",
        "PostToolUse": "Post-Tool Use",
        "PostToolUseFailure": "Post-Tool Use Failure",
        "PermissionRequest": "Permission Request",
        "PermissionDenied": "Permission Denied",
        "SessionStart": "Session Start",
        "SessionEnd": "Session End",
        "Setup": "Setup",
        "Stop": "Stop",
        "StopFailure": "Stop Failure",
        "Notification": "Notification",
        "PreCompact": "Pre-Compact",
        "PostCompact": "Post-Compact",
        "SubagentStart": "Subagent Start",
        "SubagentStop": "Subagent Stop",
        "TeammateIdle": "Teammate Idle",
        "TaskCreated": "Task Created",
        "TaskCompleted": "Task Completed",
        "ConfigChange": "Config Change",
        "cwdChanged": "CWD Changed",
        "FileChanged": "File Changed",
        "InstructionsLoaded": "Instructions Loaded",
        "Elicitation": "Elicitation",
        "ElicitationResult": "Elicitation Result",
    }
    return hook_display_names.get(hook_name, hook_name)


def create_base_hook_input(
    session_id: str,
    hook_event: HookEvent,
    cwd: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Create a base hook input dictionary.

    Args:
        session_id: The current session ID
        hook_event: The hook event type
        cwd: The current working directory
        **kwargs: Additional fields to include

    Returns:
        Dictionary with base hook input fields
    """
    return {
        "hook_event_name": hook_event,
        "session_id": session_id,
        "cwd": cwd,
        **kwargs,
    }


def parse_hook_query(hook_event: HookEvent, hook_input: dict[str, Any]) -> str | None:
    """
    Parse the match query for a hook based on the event type.

    Args:
        hook_event: The hook event type
        hook_input: The hook input data

    Returns:
        The query string to match against, or None
    """
    query_map: dict[str, str] = {
        "PreToolUse": "tool_name",
        "PostToolUse": "tool_name",
        "PostToolUseFailure": "tool_name",
        "PermissionRequest": "tool_name",
        "PermissionDenied": "tool_name",
        "SessionStart": "source",
        "Setup": "trigger",
        "PreCompact": "trigger",
        "PostCompact": "trigger",
        "Notification": "notification_type",
        "SessionEnd": "reason",
        "StopFailure": "error",
        "SubagentStart": "agent_type",
        "SubagentStop": "agent_type",
        "Elicitation": "mcp_server_name",
        "ElicitationResult": "mcp_server_name",
        "ConfigChange": "source",
        "InstructionsLoaded": "load_reason",
        "FileChanged": "file_path",
    }

    field_name = query_map.get(hook_event)
    if field_name:
        return hook_input.get(field_name)
    return None


def validate_hook_json(
    json_str: str,
) -> dict[str, Any] | None:
    """
    Validate and parse hook JSON output.

    Args:
        json_str: JSON string from hook output

    Returns:
        Parsed JSON as dict, or None if invalid

    Raises:
        ValueError: If JSON is invalid
    """
    import json

    trimmed = json_str.strip()
    if not trimmed:
        return {}

    if not trimmed.startswith("{"):
        raise ValueError(f"Hook output must be JSON object, got: {trimmed[:200]}")

    try:
        return json.loads(trimmed)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from hook: {e}")


def process_hook_json_output(
    json_output: dict[str, Any],
    command: str | None = None,
) -> HookResult:
    """
    Process the JSON output from a hook.

    Args:
        json_output: The parsed JSON output from a hook
        command: Optional command that was run

    Returns:
        Processed HookResult
    """
    result: HookResult = {
        "hook_id": "",
        "observations": [],
        "preventContinuation": False,
    }

    # Handle continue = false
    if json_output.get("continue_action") is False:
        result["preventContinuation"] = True
        if json_output.get("stopReason"):
            result["stopReason"] = json_output["stopReason"]

    # Handle decision (approve/block)
    if "decision" in json_output:
        decision = json_output["decision"]
        if decision == "approve":
            result["permissionBehavior"] = "allow"
        elif decision == "block":
            result["permissionBehavior"] = "deny"
            reason = json_output.get("reason", "Blocked by hook")
            result["blockingError"] = HookBlockingError(
                message=reason,
                command=command,
            )

    # Handle systemMessage
    if json_output.get("systemMessage"):
        result["systemMessage"] = json_output["systemMessage"]

    # Handle observations (array of strings or objects with text)
    observations = json_output.get("observations", [])
    if isinstance(observations, list):
        result["observations"] = [
            obs if isinstance(obs, str) else obs.get("text", "")
            for obs in observations
        ]

    # Handle assistant override (for prompting hooks)
    if json_output.get("assistant"):
        result["assistant"] = json_output["assistant"]

    # Handle tool override (for pre-tool hooks)
    if json_output.get("tool"):
        result["tool"] = json_output["tool"]

    # Handle resume (for hooks that return resume=true)
    if json_output.get("resume") is True:
        result["resume"] = True

    return result


def get_matching_hooks(
    hook_matchers: list[dict[str, Any]],
    hook_event: HookEvent,
    hook_input: dict[str, Any],
) -> list[MatchedHook]:
    """
    Get hooks that match the given event and input.

    Args:
        hook_matchers: List of hook matcher configurations
        hook_event: The hook event type
        hook_input: The hook input data

    Returns:
        List of matched hooks
    """
    match_query = parse_hook_query(hook_event, hook_input)
    matched_hooks: list[MatchedHook] = []

    for matcher in hook_matchers:
        pattern = matcher.get("matcher")

        # Check if pattern matches
        if pattern and match_query:
            if not matches_pattern(match_query, pattern):
                continue

        # Get hooks from this matcher
        hooks = matcher.get("hooks", [])
        for hook in hooks:
            matched_hooks.append(
                MatchedHook(
                    hook=hook,
                    plugin_root=matcher.get("pluginRoot"),
                    plugin_id=matcher.get("pluginId"),
                    skill_root=matcher.get("skillRoot"),
                    hook_source=matcher.get("hookSource", "settings"),
                )
            )

    return matched_hooks


def dedupe_hooks(hooks: list[MatchedHook]) -> list[MatchedHook]:
    """
    Deduplicate hooks by command/prompt within the same source context.

    Args:
        hooks: List of matched hooks

    Returns:
        Deduplicated list of hooks
    """
    seen: dict[str, MatchedHook] = {}

    for m in hooks:
        if m.hook.type in ("callback", "function"):
            # Callback and function hooks don't need dedup
            continue

        key = _hook_dedup_key(m)
        if key not in seen:
            seen[key] = m

    return list(seen.values())


def _hook_dedup_key(m: MatchedHook) -> str:
    """Generate a deduplication key for a hook."""
    hook = m.hook
    if hook.type == "command":
        shell = hook.get("shell", "bash")
        command = hook.get("command", "")
        if_cond = hook.get("if", "")
        return f"{m.hook_source}:{shell}:{command}:{if_cond}"
    elif hook.type == "prompt":
        prompt = hook.get("prompt", "")
        if_cond = hook.get("if", "")
        return f"{m.hook_source}:prompt:{prompt}:{if_cond}"
    elif hook.type == "http":
        url = hook.get("url", "")
        if_cond = hook.get("if", "")
        return f"{m.hook_source}:http:{url}:{if_cond}"
    elif hook.type == "agent":
        prompt = hook.get("prompt", "")
        if_cond = hook.get("if", "")
        return f"{m.hook_source}:agent:{prompt}:{if_cond}"
    return f"{m.hook_source}:{hook.type}"


def has_blocking_result(results: list[HookResult]) -> bool:
    """
    Check if any hook results contain blocking errors.

    Args:
        results: List of hook results

    Returns:
        True if any result has a blocking error
    """
    for result in results:
        if result.get("blockingError"):
            return True
        if result.get("permissionBehavior") == "deny":
            return True
    return False


def get_pre_tool_hook_blocking_message(tool_name: str) -> str:
    """
    Get the blocking message for a pre-tool hook.

    Args:
        tool_name: The tool name

    Returns:
        Blocking error message
    """
    return f"PreToolUse hook blocked tool: {tool_name}"


def get_stop_hook_message(blocking_error: HookBlockingError | None = None) -> str:
    """
    Get the message for a stop hook.

    Args:
        blocking_error: Optional blocking error

    Returns:
        Stop message
    """
    if blocking_error:
        return f"Stop hook blocked: {str(blocking_error)}"
    return "Stop hook executed"


def should_skip_hook_due_to_trust() -> bool:
    """
    Check if hooks should be skipped due to trust settings.

    Returns:
        True if hooks should be skipped
    """
    # This would integrate with trust dialog / security settings
    # For now, return False (don't skip)
    return False


# Re-export types for convenience
__all__ = [
    "HookBlockingError",
    "BaseHookInput",
    "HookMatchResult",
    "get_session_end_hook_timeout_ms",
    "get_tool_hook_timeout_ms",
    "matches_pattern",
    "get_hook_display_text",
    "create_base_hook_input",
    "parse_hook_query",
    "validate_hook_json",
    "process_hook_json_output",
    "get_matching_hooks",
    "dedupe_hooks",
    "has_blocking_result",
    "get_pre_tool_hook_blocking_message",
    "get_stop_hook_message",
    "should_skip_hook_due_to_trust",
]
