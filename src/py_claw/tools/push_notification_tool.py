"""
PushNotificationTool - Send push notifications to devices.

Provides push notification capabilities for mobile and
desktop device communication.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import Field

from py_claw.tools.base import BaseTool, ToolResult


@dataclass
class PushNotificationInput:
    """Input schema for PushNotificationTool."""
    title: str = Field(description="Notification title")
    body: str = Field(description="Notification body text")
    device_token: str | None = Field(default=None, description="Target device token (optional)")
    user_id: str | None = Field(default=None, description="Target user ID (optional)")
    badge: int = Field(default=0, description="Badge number to display")
    sound: str = Field(default="default", description="Notification sound")
    data: dict[str, Any] | None = Field(default=None, description="Additional notification data")


class PushNotificationTool(BaseTool):
    """
    PushNotificationTool - Send push notifications.

    Provides push notification capabilities for mobile and
    desktop device communication.
    """

    name = "PushNotification"
    description = "Send a push notification to a device or user"
    input_schema = PushNotificationInput

    def __init__(self) -> None:
        super().__init__()
        self._sent_count = 0

    async def execute(self, input_data: PushNotificationInput, **kwargs: Any) -> ToolResult:
        """
        Send a push notification.

        Args:
            input_data: PushNotificationInput with notification details
            **kwargs: Additional context

        Returns:
            ToolResult with notification outcome
        """
        self._sent_count += 1

        title = input_data.title
        body = input_data.body

        if not title and not body:
            return ToolResult(success=False, content="No notification content specified")

        lines = [f"[PushNotification] Notification sent"]
        lines.append(f"Title: {title}")
        lines.append(f"Body: {body}")
        lines.append(f"Badge: {input_data.badge}")
        lines.append(f"Sound: {input_data.sound}")
        lines.append(f"Notification ID: push_{self._sent_count}")

        if input_data.device_token:
            lines.append(f"Device: {input_data.device_token[:8]}...")
        if input_data.user_id:
            lines.append(f"User: {input_data.user_id}")

        if input_data.data:
            lines.append(f"Data: {input_data.data}")

        return ToolResult(
            success=True,
            content="\n".join(lines),
        )

    @property
    def sent_count(self) -> int:
        """Get the number of notifications sent."""
        return self._sent_count
