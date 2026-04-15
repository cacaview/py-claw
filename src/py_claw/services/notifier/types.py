"""Terminal notification types and configuration."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NotificationChannel(str, Enum):
    """Available notification channels.

    Values:
        AUTO: Auto-detect terminal and use best available method.
        ITERM2: iTerm2 with notification.
        ITERM2_WITH_BELL: iTerm2 with notification and terminal bell.
        KITTY: Kitty terminal notification protocol.
        GHOSTTY: Ghostty terminal notification protocol.
        TERMINAL_BELL: Terminal bell (BEL character).
        NOTIFICATIONS_DISABLED: Disabled.
    """

    AUTO = "auto"
    ITERM2 = "iterm2"
    ITERM2_WITH_BELL = "iterm2_with_bell"
    KITTY = "kitty"
    GHOSTTY = "ghostty"
    TERMINAL_BELL = "terminal_bell"
    NOTIFICATIONS_DISABLED = "notifications_disabled"


@dataclass
class NotificationOptions:
    """Options for sending a notification.

    Attributes:
        message: The notification message body.
        title: Optional notification title (defaults to "Claude Code").
        notification_type: Type identifier for the notification.
    """

    message: str
    title: str | None = None
    notification_type: str = "general"


# Default title for notifications
DEFAULT_NOTIFICATION_TITLE = "Claude Code"
