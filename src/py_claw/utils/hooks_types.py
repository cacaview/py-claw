"""
Type definitions for hooks utilities.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

# Hook event types
HookEvent = Literal[
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "PermissionDenied",
    "SessionStart",
    "SessionEnd",
    "Setup",
    "Stop",
    "StopFailure",
    "Notification",
    "PreCompact",
    "PostCompact",
    "SubagentStart",
    "SubagentStop",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "ConfigChange",
    "cwdChanged",
    "FileChanged",
    "InstructionsLoaded",
    "Elicitation",
    "ElicitationResult",
]


class HookResult(TypedDict, total=False):
    """Result from a hook execution."""

    hook_id: str
    observations: list[str]
    preventContinuation: bool
    stopReason: str | None
    permissionBehavior: Literal["allow", "deny"] | None
    blockingError: Any  # HookBlockingError or similar
    systemMessage: str | None
    assistant: dict[str, Any] | None
    tool: dict[str, Any] | None
    resume: bool | None


@dataclass
class MatchedHook:
    """A hook that matched the current event."""

    hook: dict[str, Any]
    plugin_root: str | None = None
    plugin_id: str | None = None
    skill_root: str | None = None
    hook_source: str = "settings"


# Hook input types
@dataclass
class PreToolUseHookInput:
    """Input for PreToolUse hooks."""

    hook_event_name: Literal["PreToolUse"]
    session_id: str
    tool_name: str
    tool_input: dict[str, Any]
    cwd: str


@dataclass
class PostToolUseHookInput:
    """Input for PostToolUse hooks."""

    hook_event_name: Literal["PostToolUse"]
    session_id: str
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: Any
    cwd: str


@dataclass
class PostToolUseFailureHookInput:
    """Input for PostToolUseFailure hooks."""

    hook_event_name: Literal["PostToolUseFailure"]
    session_id: str
    tool_name: str
    tool_input: dict[str, Any]
    error: str
    cwd: str


@dataclass
class PermissionDeniedHookInput:
    """Input for PermissionDenied hooks."""

    hook_event_name: Literal["PermissionDenied"]
    session_id: str
    tool_name: str
    reason: str
    cwd: str


@dataclass
class SessionStartHookInput:
    """Input for SessionStart hooks."""

    hook_event_name: Literal["SessionStart"]
    session_id: str
    source: str
    cwd: str


@dataclass
class SessionEndHookInput:
    """Input for SessionEnd hooks."""

    hook_event_name: Literal["SessionEnd"]
    session_id: str
    reason: str
    cwd: str


@dataclass
class SetupHookInput:
    """Input for Setup hooks."""

    hook_event_name: Literal["Setup"]
    session_id: str
    trigger: str
    cwd: str


@dataclass
class StopHookInput:
    """Input for Stop hooks."""

    hook_event_name: Literal["Stop"]
    session_id: str
    cwd: str


@dataclass
class StopFailureHookInput:
    """Input for StopFailure hooks."""

    hook_event_name: Literal["StopFailure"]
    session_id: str
    error: str
    cwd: str


@dataclass
class NotificationHookInput:
    """Input for Notification hooks."""

    hook_event_name: Literal["Notification"]
    session_id: str
    notification_type: str
    cwd: str


@dataclass
class PreCompactHookInput:
    """Input for PreCompact hooks."""

    hook_event_name: Literal["PreCompact"]
    session_id: str
    trigger: str
    cwd: str


@dataclass
class PostCompactHookInput:
    """Input for PostCompact hooks."""

    hook_event_name: Literal["PostCompact"]
    session_id: str
    trigger: str
    cwd: str


@dataclass
class SubagentStartHookInput:
    """Input for SubagentStart hooks."""

    hook_event_name: Literal["SubagentStart"]
    session_id: str
    agent_type: str
    cwd: str


@dataclass
class SubagentStopHookInput:
    """Input for SubagentStop hooks."""

    hook_event_name: Literal["SubagentStop"]
    session_id: str
    agent_type: str
    cwd: str


@dataclass
class TeammateIdleHookInput:
    """Input for TeammateIdle hooks."""

    hook_event_name: Literal["TeammateIdle"]
    session_id: str
    teammate_id: str
    cwd: str


@dataclass
class TaskCreatedHookInput:
    """Input for TaskCreated hooks."""

    hook_event_name: Literal["TaskCreated"]
    session_id: str
    task_id: str
    cwd: str


@dataclass
class TaskCompletedHookInput:
    """Input for TaskCompleted hooks."""

    hook_event_name: Literal["TaskCompleted"]
    session_id: str
    task_id: str
    cwd: str


@dataclass
class ConfigChangeHookInput:
    """Input for ConfigChange hooks."""

    hook_event_name: Literal["ConfigChange"]
    session_id: str
    source: str
    cwd: str


@dataclass
class CwdChangedHookInput:
    """Input for cwdChanged hooks."""

    hook_event_name: Literal["cwdChanged"]
    session_id: str
    old_cwd: str
    new_cwd: str


@dataclass
class FileChangedHookInput:
    """Input for FileChanged hooks."""

    hook_event_name: Literal["FileChanged"]
    session_id: str
    file_path: str
    cwd: str


@dataclass
class InstructionsLoadedHookInput:
    """Input for InstructionsLoaded hooks."""

    hook_event_name: Literal["InstructionsLoaded"]
    session_id: str
    load_reason: str
    cwd: str


@dataclass
class ElicitationHookInput:
    """Input for Elicitation hooks."""

    hook_event_name: Literal["Elicitation"]
    session_id: str
    mcp_server_name: str
    prompt: str
    cwd: str


@dataclass
class ElicitationResultHookInput:
    """Input for ElicitationResult hooks."""

    hook_event_name: Literal["ElicitationResult"]
    session_id: str
    mcp_server_name: str
    result: dict[str, Any]
    cwd: str


# Union type for all hook inputs
HookInput = (
    PreToolUseHookInput
    | PostToolUseHookInput
    | PostToolUseFailureHookInput
    | PermissionDeniedHookInput
    | SessionStartHookInput
    | SessionEndHookInput
    | SetupHookInput
    | StopHookInput
    | StopFailureHookInput
    | NotificationHookInput
    | PreCompactHookInput
    | PostCompactHookInput
    | SubagentStartHookInput
    | SubagentStopHookInput
    | TeammateIdleHookInput
    | TaskCreatedHookInput
    | TaskCompletedHookInput
    | ConfigChangeHookInput
    | CwdChangedHookInput
    | FileChangedHookInput
    | InstructionsLoadedHookInput
    | ElicitationHookInput
    | ElicitationResultHookInput
)


class HookJSONOutput(TypedDict, total=False):
    """JSON output format from hooks."""

    # Note: 'continue' is a reserved keyword, use 'continue_action'
    continue_action: bool | None
    decision: Literal["approve", "block"] | None
    reason: str | None
    stopReason: str | None
    systemMessage: str | None
    observations: list[str | dict[str, str]] | None
    assistant: dict[str, Any] | None
    tool: dict[str, Any] | None
    resume: bool | None


class PermissionBehavior(TypedDict):
    """Permission behavior from hook."""

    permission: Literal["allow", "deny"]
    reason: str | None
