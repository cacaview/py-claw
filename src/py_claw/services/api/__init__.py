"""Anthropic API client for py-claw.

This module provides two related functionalities:

1. API Client (from ClaudeCode-main/src/services/api/claude.ts):
   A Python-native client for the Anthropic API.

   Usage:
       from py_claw.services.api import create_client
       client = create_client()

2. Error Logging Utilities (from ClaudeCode-main/src/utils/api.ts):
   Log display title extraction, error logging, MCP error/debug logging.

   Usage:
       from py_claw.services.api.api import log_error, get_log_display_title
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Re-export all types
from py_claw.services.api.types import (
    ApiProvider,
    BETA_HEADERS,
    ContentBlock,
    ContentBlockDeltaEvent,
    ContentBlockParam,
    ContentBlockStartEvent,
    ContentBlockStopEvent,
    ContentDelta,
    CountTokensResult,
    ErrorEvent,
    IncompleteEvent,
    MediaSource,
    Message,
    MessageCreateParams,
    MessageCreateResult,
    MessageDelta,
    MessageDeltaEvent,
    MessageParam,
    MessageStartEvent,
    MessageStopEvent,
    ProviderConfig,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolParam,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
)

# Re-export client
from py_claw.services.api.client import (
    AnthropicClient,
    AsyncAnthropicClient,
)

# Re-export errors
from py_claw.services.api.errors import (
    APIError,
    AuthenticationError,
    ForbiddenError,
    InternalError,
    InvalidRequestError,
    NetworkError,
    NotFoundError,
    OverloadedError,
    PromptTooLongError,
    RateLimitError,
    classify_error,
    is_prompt_too_long,
)

# Re-export streaming utilities
from py_claw.services.api.streaming import (
    AssistantMessageBuilder,
    StreamingResult,
    parse_stream_events,
)

# Re-export error logging utilities (from ClaudeCode-main/src/utils/api.ts)
from py_claw.services.api.api import (
    ErrorLogSink,
    LogOption,
    attach_error_log_sink,
    capture_api_request,
    date_to_filename,
    get_in_memory_errors,
    get_log_display_title,
    load_error_logs,
    log_error,
    log_mcp_debug,
    log_mcp_error,
    reset_error_log_for_testing,
)

__all__ = [
    # Types
    "ApiProvider",
    "BETA_HEADERS",
    "ContentBlock",
    "ContentBlockDeltaEvent",
    "ContentBlockParam",
    "ContentBlockStartEvent",
    "ContentBlockStopEvent",
    "ContentDelta",
    "CountTokensResult",
    "ErrorEvent",
    "IncompleteEvent",
    "MediaSource",
    "Message",
    "MessageCreateParams",
    "MessageCreateResult",
    "MessageDelta",
    "MessageDeltaEvent",
    "MessageParam",
    "MessageStartEvent",
    "MessageStopEvent",
    "ProviderConfig",
    "StreamEvent",
    "TextBlock",
    "ThinkingBlock",
    "ToolParam",
    "ToolResultBlock",
    "ToolUseBlock",
    "Usage",
    # Client
    "AnthropicClient",
    "AsyncAnthropicClient",
    "create_client",
    # Errors
    "APIError",
    "AuthenticationError",
    "ForbiddenError",
    "InternalError",
    "InvalidRequestError",
    "NetworkError",
    "NotFoundError",
    "OverloadedError",
    "PromptTooLongError",
    "RateLimitError",
    "classify_error",
    "is_prompt_too_long",
    # Streaming
    "AssistantMessageBuilder",
    "StreamingResult",
    "parse_stream_events",
    # Error logging (from src/utils/api.ts)
    "ErrorLogSink",
    "LogOption",
    "attach_error_log_sink",
    "capture_api_request",
    "date_to_filename",
    "get_in_memory_errors",
    "get_log_display_title",
    "load_error_logs",
    "log_error",
    "log_mcp_debug",
    "log_mcp_error",
    "reset_error_log_for_testing",
]


def create_client(api_key: str | None = None) -> AnthropicClient:
    """Create an Anthropic API client.

    Args:
        api_key: Optional API key. If not provided, reads from
                 ANTHROPIC_API_KEY environment variable.

    Returns:
        A configured AnthropicClient instance.
    """
    from py_claw.services.api.client import AnthropicClient, _build_provider_config
    config = _build_provider_config(api_key)
    return AnthropicClient(config=config)
