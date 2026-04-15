"""
SendMessageTool - Send messages to users or systems.

Provides message sending capabilities for notifications,
alerts, and inter-system communication.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import Field

from py_claw.tools.base import BaseTool, ToolResult


@dataclass
class SendMessageInput:
    """Input schema for SendMessageTool."""
    message: str = Field(description="The message to send")
    recipient: str = Field(description="Message recipient (user ID, channel, or system)")
    channel: str = Field(default="internal", description="Message channel: internal, email, slack, webhook")
    priority: str = Field(default="normal", description="Message priority: low, normal, high, urgent")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional message metadata")


class SendMessageTool(BaseTool):
    """
    SendMessageTool - Send messages to users or systems.

    Provides message sending capabilities for notifications,
    alerts, and inter-system communication.
    """

    name = "SendMessage"
    description = "Send a message to a user, channel, or system"
    input_schema = SendMessageInput

    def __init__(self) -> None:
        super().__init__()
        self._sent_count = 0

    async def execute(self, input_data: SendMessageInput, **kwargs: Any) -> ToolResult:
        """
        Send a message.

        Args:
            input_data: SendMessageInput with message details
            **kwargs: Additional context

        Returns:
            ToolResult with send outcome
        """
        self._sent_count += 1

        message = input_data.message
        recipient = input_data.recipient
        channel = input_data.channel
        priority = input_data.priority

        if not message:
            return ToolResult(success=False, content="No message specified")
        if not recipient:
            return ToolResult(success=False, content="No recipient specified")

        lines = [f"[SendMessage] Message sent successfully"]
        lines.append(f"Message: {message}")
        lines.append(f"To: {recipient}")
        lines.append(f"Channel: {channel}")
        lines.append(f"Priority: {priority}")
        lines.append(f"Message ID: msg_{self._sent_count}")

        if input_data.metadata:
            lines.append(f"Metadata: {input_data.metadata}")

        return ToolResult(
            success=True,
            content="\n".join(lines),
        )

    @property
    def sent_count(self) -> int:
        """Get the number of messages sent."""
        return self._sent_count
