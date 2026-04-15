"""SDK message adapter for CCR communication.

Converts SDKMessage from CCR to internal message types and vice versa.
The CCR backend sends SDK-format messages via WebSocket, and this adapter
bridges them to internal types.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# SDK message types
SDK_ASSISTANT_MESSAGE = "assistant"
SDK_PARTIAL_ASSISTANT_MESSAGE = "partial_assistant"
SDK_RESULT_MESSAGE = "result"
SDK_SYSTEM_MESSAGE = "system"
SDK_TOOL_PROGRESS_MESSAGE = "tool_progress"
SDK_STATUS_MESSAGE = "status"


@dataclass
class SDKAssistantMessage:
    """SDK assistant message from CCR."""

    type: str = "assistant"
    uuid: str | None = None
    message: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class SDKPartialAssistantMessage:
    """SDK streaming assistant message."""

    type: str = "partial_assistant"
    event: dict[str, Any] | None = None


@dataclass
class SDKResultMessage:
    """SDK result message indicating session completion."""

    type: str = "result"
    subtype: str = "success"
    uuid: str | None = None
    errors: list[str] | None = None


@dataclass
class SDKSystemMessage:
    """SDK system message (e.g., init)."""

    type: str = "system"
    subtype: str = "informational"
    model: str | None = None
    uuid: str | None = None
    content: str | None = None


@dataclass
class SDKToolProgressMessage:
    """SDK tool progress message."""

    type: str = "tool_progress"
    tool_use_id: str | None = None
    tool_name: str | None = None
    progress: dict[str, Any] | None = None


@dataclass
class InternalAssistantMessage:
    """Internal assistant message for REPL."""

    type: str = "assistant"
    message: dict[str, Any] | None = None
    uuid: str | None = None
    request_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    error: str | None = None


@dataclass
class InternalStreamEvent:
    """Internal stream event for partial messages."""

    type: str = "stream_event"
    event: dict[str, Any] | None = None


@dataclass
class InternalSystemMessage:
    """Internal system message."""

    type: str = "system"
    subtype: str = "informational"
    content: str = ""
    level: str = "info"
    uuid: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class InternalToolProgress:
    """Internal tool progress message."""

    type: str = "tool_progress"
    tool_use_id: str | None = None
    tool_name: str | None = None
    progress: dict[str, Any] | None = None


class SDKMessageAdapter:
    """Converts SDK messages to internal message types.

    The CCR backend sends SDK-format messages via WebSocket. The REPL expects
    internal message types for rendering. This adapter bridges the two.
    """

    @staticmethod
    def to_internal_assistant(msg: dict[str, Any]) -> InternalAssistantMessage:
        """Convert SDK assistant message to internal format.

        Args:
            msg: SDK assistant message dict

        Returns:
            Internal assistant message
        """
        return InternalAssistantMessage(
            type="assistant",
            message=msg.get("message"),
            uuid=msg.get("uuid"),
            request_id=None,
            timestamp=datetime.utcnow().isoformat(),
            error=msg.get("error"),
        )

    @staticmethod
    def to_internal_stream_event(msg: dict[str, Any]) -> InternalStreamEvent:
        """Convert SDK partial message to stream event.

        Args:
            msg: SDK partial assistant message dict

        Returns:
            Internal stream event
        """
        return InternalStreamEvent(
            type="stream_event",
            event=msg.get("event"),
        )

    @staticmethod
    def to_internal_result(msg: dict[str, Any]) -> InternalSystemMessage:
        """Convert SDK result message to internal system message.

        Args:
            msg: SDK result message dict

        Returns:
            Internal system message
        """
        is_error = msg.get("subtype") != "success"
        content = (
            msg.get("errors", ["Unknown error"])[0]
            if is_error
            else "Session completed successfully"
        )

        return InternalSystemMessage(
            type="system",
            subtype="informational",
            content=content,
            level="warning" if is_error else "info",
            uuid=msg.get("uuid"),
            timestamp=datetime.utcnow().isoformat(),
        )

    @staticmethod
    def to_internal_system(msg: dict[str, Any]) -> InternalSystemMessage:
        """Convert SDK system message to internal system message.

        Args:
            msg: SDK system message dict

        Returns:
            Internal system message
        """
        content = msg.get("content", "")
        if msg.get("model"):
            content = f"Remote session initialized (model: {msg.get('model')})"

        return InternalSystemMessage(
            type="system",
            subtype=msg.get("subtype", "informational"),
            content=content,
            level="info",
            uuid=msg.get("uuid"),
            timestamp=datetime.utcnow().isoformat(),
        )

    @staticmethod
    def to_internal_tool_progress(msg: dict[str, Any]) -> InternalToolProgress:
        """Convert SDK tool progress to internal format.

        Args:
            msg: SDK tool progress message dict

        Returns:
            Internal tool progress
        """
        return InternalToolProgress(
            type="tool_progress",
            tool_use_id=msg.get("tool_use_id"),
            tool_name=msg.get("tool_name"),
            progress=msg.get("progress"),
        )

    @classmethod
    def convert(cls, msg: dict[str, Any]) -> Any:
        """Convert an SDK message to internal format.

        Args:
            msg: SDK message dict

        Returns:
            Internal message (one of InternalAssistantMessage, InternalStreamEvent,
            InternalSystemMessage, InternalToolProgress)
        """
        msg_type = msg.get("type")

        if msg_type == SDK_ASSISTANT_MESSAGE:
            return cls.to_internal_assistant(msg)
        elif msg_type == SDK_PARTIAL_ASSISTANT_MESSAGE:
            return cls.to_internal_stream_event(msg)
        elif msg_type == SDK_RESULT_MESSAGE:
            return cls.to_internal_result(msg)
        elif msg_type == SDK_SYSTEM_MESSAGE:
            return cls.to_internal_system(msg)
        elif msg_type == SDK_TOOL_PROGRESS_MESSAGE:
            return cls.to_internal_tool_progress(msg)
        else:
            logger.debug("Unknown SDK message type: %s", msg_type)
            return msg


def is_sdk_message(msg: dict[str, Any]) -> bool:
    """Check if a message is an SDKMessage (not a control message).

    Args:
        msg: Message to check

    Returns:
        True if message is an SDK message
    """
    control_types = {"control_request", "control_response", "control_cancel_request"}
    return msg.get("type") not in control_types


def is_control_message(msg: dict[str, Any]) -> bool:
    """Check if a message is a control message.

    Args:
        msg: Message to check

    Returns:
        True if message is a control message
    """
    return msg.get("type") in {
        "control_request",
        "control_response",
        "control_cancel_request",
    }
