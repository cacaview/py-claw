from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Usage (defined early to avoid forward reference issues)
# =============================================================================


class Usage(BaseModel):
    """Token usage for a message."""

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


# =============================================================================
# Core Types
# =============================================================================

class MessageParam(BaseModel):
    """A message in a conversation, used for API requests."""

    role: Literal["user", "assistant"]
    content: str | list["ContentBlockParam"]


class ContentBlockParam(BaseModel):
    """A content block for API requests."""

    type: Literal["text", "image", "tool_use"]
    text: str | None = None
    source: "MediaSource | None" = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None


class MediaSource(BaseModel):
    """Media source for image content blocks."""

    type: Literal["base64", "url"]
    media_type: str
    data: str


class ToolParam(BaseModel):
    """A tool definition for API requests."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(alias="input_schema")

    model_config = ConfigDict(populate_by_name=True)


class ToolUseBlock(BaseModel):
    """A tool use content block in assistant response."""

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class ToolResultBlock(BaseModel):
    """A tool result content block in user message."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | list[ContentBlockParam]


class TextBlock(BaseModel):
    """A text content block."""

    type: Literal["text"] = "text"
    text: str


class ThinkingBlock(BaseModel):
    """A thinking content block (for extended thinking)."""

    type: Literal["thinking"] = "thinking"
    thinking: str


class ContentBlock(BaseModel):
    """A content block in assistant response."""

    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    thinking: str | None = None
    is_complete: bool | None = None


class Message(BaseModel):
    """A complete message in the API response."""

    id: str
    type: Literal["message"]
    role: Literal["user", "assistant"]
    content: list[ContentBlock]
    model: str
    stop_reason: str | None = None
    stop_sequence: int | None = None
    usage: Usage


class MessageDelta(BaseModel):
    """Delta update for streaming message response."""

    stop_reason: str | None = None
    usage: Usage | None = None


# =============================================================================
# Stream Events
# =============================================================================

class StreamEvent(BaseModel):
    """Base for stream events."""

    type: str


class MessageStartEvent(StreamEvent):
    """First event in a stream, contains the message."""

    type: Literal["message_start"] = "message_start"
    message: Message


class ContentBlockStartEvent(StreamEvent):
    """Start of a content block."""

    type: Literal["content_block_start"] = "content_block_start"
    index: int
    content_block: ContentBlock | ThinkingBlock | ToolUseBlock


class ContentBlockDeltaEvent(StreamEvent):
    """Delta update for a content block."""

    type: Literal["content_block_delta"] = "content_block_delta"
    index: int
    delta: "ContentDelta"


class ContentDelta(BaseModel):
    """The delta content."""

    type: Literal["text_delta", "thinking_delta", "input_json_delta"]
    text: str | None = None
    thinking: str | None = None
    input_json: str | None = None


class ContentBlockStopEvent(StreamEvent):
    """End of a content block."""

    type: Literal["content_block_stop"] = "content_block_stop"
    index: int


class MessageDeltaEvent(StreamEvent):
    """Final message delta with usage."""

    type: Literal["message_delta"] = "message_delta"
    delta: MessageDelta


class MessageStopEvent(StreamEvent):
    """End of the message stream."""

    type: Literal["message_stop"] = "message_stop"


class ErrorEvent(StreamEvent):
    """An error occurred."""

    type: Literal["error"] = "error"
    error: str
    code: str | None = None


class IncompleteEvent(StreamEvent):
    """Message was cut off."""

    type: Literal["incomplete"] = "incomplete"
    reason: str | None = None


# =============================================================================
# Request/Response Types
# =============================================================================

class MessageCreateParams(BaseModel):
    """Parameters for creating a message."""

    model: str
    messages: list[MessageParam]
    system: str | list[ContentBlockParam] | None = None
    tools: list[ToolParam] | None = None
    tool_choice: str | dict[str, Any] | None = None
    max_tokens: int = 4096
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    thinking: dict[str, Any] | None = None
    betas: list[str] | None = None
    metadata: dict[str, Any] | None = None
    stream: bool = False


class MessageCreateResult(BaseModel):
    """Result from creating a non-streaming message."""

    id: str
    type: Literal["message"]
    role: Literal["assistant"]
    content: list[ContentBlock]
    model: str
    stop_reason: str | None = None
    stop_sequence: int | None = None
    usage: Usage


class CountTokensResult(BaseModel):
    """Result from counting tokens."""

    input_tokens: int
    tokens_from_cache_creation: int | None = None
    tokens_from_cache_read: int | None = None


# =============================================================================
# Error Types
# =============================================================================

class APIError(BaseModel):
    """API error response."""

    type: str
    error: str


# =============================================================================
# Provider Types
# =============================================================================

ApiProvider = Literal["firstParty", "bedrock", "vertex", "foundry"]


class ProviderConfig(BaseModel):
    """Configuration for an API provider."""

    provider: ApiProvider = "firstParty"
    api_key: str | None = None
    base_url: str | None = None
    auth_token: str | None = None  # For OAuth
    # AWS Bedrock
    aws_region: str | None = None
    aws_access_key: str | None = None
    aws_secret_key: str | None = None
    aws_session_token: str | None = None
    # Google Vertex
    vertex_project_id: str | None = None
    vertex_region: str | None = None
    # Azure Foundry
    azure_endpoint: str | None = None
    azure_ad_token_provider: str | None = None


# =============================================================================
# Beta Headers
# =============================================================================

BETA_HEADERS: tuple[str, ...] = (
    "claude-code-20250219",
    "interleaved-thinking-2025-05-14",
    "context-1m-2025-08-07",
    "context-management-2025-06-27",
    "structured-outputs-2025-12-15",
    "prompt-caching-scope-2026-01-05",
    "fast-mode-2026-02-01",
    "effort-2025-11-24",
    "advisor-tool-2026-03-01",
)
