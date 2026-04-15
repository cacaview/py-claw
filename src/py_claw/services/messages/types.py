"""Message types for the Python Claude Code runtime.

Based on ClaudeCode-main/src/types/message.ts and src/utils/messages.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Message origin metadata
MessageOrigin = dict[str, Any]

# Base message type
MessageBase = dict[str, Any]


@dataclass
class UserMessageContent:
    """User message content block."""

    type: str = "text"
    text: str | None = None


@dataclass
class UserMessage:
    """User message type."""

    type: Literal["user"] = "user"
    message: dict[str, Any] = field(default_factory=dict)
    uuid: str | None = None
    parentUuid: str | None = None
    timestamp: str | None = None
    createdAt: str | None = None
    isMeta: bool = False
    isVirtual: bool = False
    isCompactSummary: bool = False
    origin: MessageOrigin | None = None


@dataclass
class AssistantMessage:
    """Assistant message type."""

    type: Literal["assistant"] = "assistant"
    message: dict[str, Any] = field(default_factory=dict)
    uuid: str | None = None
    parentUuid: str | None = None
    timestamp: str | None = None
    createdAt: str | None = None
    isMeta: bool = False
    isVirtual: bool = False
    isCompactSummary: bool = False


@dataclass
class ProgressMessage:
    """Progress message type."""

    type: Literal["progress"] = "progress"
    progress: dict[str, Any] | None = None
    uuid: str | None = None


@dataclass
class SystemMessage:
    """System message type."""

    type: Literal["system"] = "system"
    subtype: str | None = None
    level: str = "info"
    message: str | None = None
    uuid: str | None = None


@dataclass
class AttachmentMessage:
    """Attachment message type."""

    type: Literal["attachment"] = "attachment"
    path: str | None = None
    uuid: str | None = None


@dataclass
class HookResultMessage:
    """Hook result message type."""

    type: Literal["hook_result"] = "hook_result"
    uuid: str | None = None


@dataclass
class ToolUseSummaryMessage:
    """Tool use summary message type."""

    type: Literal["tool_use_summary"] = "tool_use_summary"
    uuid: str | None = None


@dataclass
class TombstoneMessage:
    """Tombstone message type."""

    type: Literal["tombstone"] = "tombstone"
    uuid: str | None = None


# Union type for all messages
Message = UserMessage | AssistantMessage | ProgressMessage | SystemMessage | AttachmentMessage

# Normalized message types (after splitting multi-block messages)
NormalizedAssistantMessage = AssistantMessage
NormalizedUserMessage = UserMessage
NormalizedMessage = Message


# Content block types - using dicts for simplicity and flexibility
# These are lightweight structures, not full dataclasses

TextBlockDict = dict[str, Any]
ThinkingBlockDict = dict[str, Any]
ToolUseBlockDict = dict[str, Any]
ToolResultBlockDict = dict[str, Any]

ContentBlock = dict[str, Any]
