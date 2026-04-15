"""Notification channel types and constants."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NotificationChannel(str, Enum):
    """Supported notification channel types.

    Mirrors the TS NOTIFICATION_CHANNELS constant from configConstants.ts.
    """
    AUTO = "auto"
    ITERM2 = "iterm2"
    ITERM2_WITH_BELL = "iterm2_with_bell"
    KITTY = "kitty"
    GHOSTTY = "ghostty"
    TERMINAL_BELL = "terminal_bell"
    NOTIFICATIONS_DISABLED = "notifications_disabled"


@dataclass(slots=True)
class NotificationOptions:
    """Options for sending a notification.

    Mirrors the TS NotificationOptions type.
    """
    message: str
    notification_type: str  # Used for hook matching
    title: str | None = None


# Default notification title
DEFAULT_TITLE = "Claude Code"
