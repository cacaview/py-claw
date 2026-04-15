"""
Agent service types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ─── Hook Types ─────────────────────────────────────────────────────────────────


class HookEvent(str, Enum):
    """Hook events for agent lifecycle."""

    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"
    SUBAGENT_STOP_FAILURE = "SubagentStopFailure"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    TOOL_USE = "ToolUse"
    TOOL_RESULT = "ToolResult"
    MESSAGE_CREATE = "MessageCreate"
    SESSION_START = "SessionStart"
    STOP = "Stop"


@dataclass
class HookResult:
    """Result from a hook execution."""

    hook_name: str
    # Additional context strings to prepend to the conversation
    additional_contexts: list[str] = field(default_factory=list)
    # Whether to block the operation
    block: bool = False
    # Error message if hook failed
    error: str | None = None


@dataclass
class AgentHook:
    """A hook defined in agent frontmatter."""

    event: HookEvent
    prompt: str = ""
    # For tool hooks: tool name to trigger on
    tool_name: str | None = None
    # Whether this hook should block the operation
    blocking: bool = False


# ─── Tracing Types ──────────────────────────────────────────────────────────────


@dataclass
class TraceSpan:
    """A trace span for Perfetto visualization."""

    agent_id: str
    agent_type: str
    parent_id: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── Skill Preload Types ────────────────────────────────────────────────────────


@dataclass
class PreloadedSkill:
    """A preloaded skill for an agent."""

    skill_name: str
    content: list[dict[str, Any]] = field(default_factory=list)
    progress_message: str | None = None


@dataclass
class SkillPreloadResult:
    """Result from skill preloading."""

    skills: list[PreloadedSkill] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
