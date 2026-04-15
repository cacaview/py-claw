"""
Message types for py-claw runtime.

Based on ClaudeCode-main/src/types/message.ts and src/utils/messages.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# Message type literals
MessageType = Literal["user", "assistant", "system", "progress", "attachment", "hook_result", "tool_use_summary", "tombstone", "grouped_tool_use"]
SystemMessageSubtype = Literal[
    "local_command",
    "bridge_status",
    "turn_duration",
    "thinking",
    "memory_saved",
    "stop_hook_summary",
    "informational",
    "compact_boundary",
    "microcompact_boundary",
    "permission_retry",
    "scheduled_task_fire",
    "away_summary",
    "agents_killed",
    "api_metrics",
    "api_error",
    "hook_started",
    "hook_progress",
    "hook_response",
]
ContentBlockType = Literal["text", "tool_use", "tool_result", "thinking", "redacted_thinking", "image", "document", "mcp_tool_use", "mcp_tool_result", "code_execution_tool_result", "container_upload"]


@dataclass
class ContentBlock:
    """A content block within a message."""
    type: ContentBlockType
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input_json: dict[str, Any] | None = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    is_error: bool | None = None
    content: str | None = None
    source: dict[str, Any] | None = None


@dataclass
class MessageBase:
    """Base class for all messages."""
    uuid: str | None = None
    parent_uuid: str | None = None
    timestamp: str | None = None
    is_meta: bool = False
    is_virtual: bool = False
    is_compact_summary: bool = False
    tool_use_result: str | None = None
    origin: str | None = None


@dataclass
class UserMessage(MessageBase):
    """User message."""
    type: Literal["user"] = "user"
    content: str | list[ContentBlock] = ""


@dataclass
class AssistantMessage(MessageBase):
    """Assistant message."""
    type: Literal["assistant"] = "assistant"
    content: list[ContentBlock] | None = None
    error: str | None = None


@dataclass
class SystemMessage(MessageBase):
    """System message."""
    type: Literal["system"] = "system"
    subtype: SystemMessageSubtype | None = None
    level: str | None = None
    content: str | None = None


@dataclass
class ProgressMessage(MessageBase):
    """Progress message for streaming tool updates."""
    type: Literal["progress"] = "progress"
    progress: dict[str, Any] | None = None


@dataclass
class AttachmentMessage(MessageBase):
    """Attachment message for file/directory content."""
    type: Literal["attachment"] = "attachment"
    path: str | None = None
    content: str | None = None


@dataclass
class HookResultMessage(MessageBase):
    """Hook result message."""
    type: Literal["hook_result"] = "hook_result"
    hook_id: str | None = None
    hook_name: str | None = None
    hook_event: str | None = None
    result: Any | None = None


@dataclass
class ToolUseSummaryMessage(MessageBase):
    """Tool use summary message."""
    type: Literal["tool_use_summary"] = "tool_use_summary"
    summary: str | None = None
    preceding_tool_use_ids: list[str] | None = None


@dataclass
class TombstoneMessage(MessageBase):
    """Tombstone message for deleted content."""
    type: Literal["tombstone"] = "tombstone"
    content: str | None = None


@dataclass
class GroupedToolUseMessage(MessageBase):
    """Grouped tool use message."""
    type: Literal["grouped_tool_use"] = "grouped_tool_use"
    tool_use_ids: list[str] | None = None


# Union type for all messages
Message = (
    UserMessage
    | AssistantMessage
    | SystemMessage
    | ProgressMessage
    | AttachmentMessage
    | HookResultMessage
    | ToolUseSummaryMessage
    | TombstoneMessage
    | GroupedToolUseMessage
)


@dataclass
class NormalizedMessageBase:
    """Base for normalized messages (each content block is separate)."""
    uuid: str | None = None
    parent_uuid: str | None = None
    timestamp: str | None = None
    index: int = 0  # Position within original message


@dataclass
class NormalizedUserMessage(NormalizedMessageBase):
    """Normalized user message (single content block)."""
    type: Literal["normalized_user"] = "normalized_user"
    content: str | list[ContentBlock] = ""


@dataclass
class NormalizedAssistantMessage(NormalizedMessageBase):
    """Normalized assistant message (single content block)."""
    type: Literal["normalized_assistant"] = "normalized_assistant"
    content: list[ContentBlock] | None = None


NormalizedMessage = NormalizedUserMessage | NormalizedAssistantMessage | ProgressMessage | SystemMessage | AttachmentMessage


@dataclass
class CompactMetadata:
    """Metadata for compaction."""
    trigger: str | None = None
    pre_tokens: int = 0
    preserved_segment: dict[str, Any] | None = None


@dataclass
class MessageLookups:
    """Pre-computed lookups for efficient message navigation."""
    sibling_tool_use_ids: dict[str, list[str]] = field(default_factory=dict)
    progress_messages_by_tool_use_id: dict[str, list[ProgressMessage]] = field(default_factory=dict)
    in_progress_hook_counts: dict[str, int] = field(default_factory=dict)
    resolved_hook_counts: dict[str, int] = field(default_factory=dict)
    tool_result_by_tool_use_id: dict[str, str] = field(default_factory=dict)
    tool_use_by_tool_use_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    normalized_message_count: int = 0
    resolved_tool_use_ids: set[str] = field(default_factory=set)
    errored_tool_use_ids: set[str] = field(default_factory=set)


@dataclass
class Usage:
    """Token usage statistics."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class StreamEvent:
    """Stream event from API."""
    type: str
    data: dict[str, Any] | None = None


@dataclass
class RequestStartEvent:
    """Request start event."""
    type: Literal["request_start"] = "request_start"
    request_id: str | None = None
