"""
Buddy notification triggering and teaser logic.

Based on ClaudeCode-main/src/buddy/useBuddyNotification.tsx
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Teaser window: April 1-7, 2026 only. Command stays live forever after.
# Local date, not UTC — 24h rolling wave across timezones.
_TEASER_START_MONTH = 3  # April (0-indexed)
_TEASER_START_DAY = 1
_TEASER_END_DAY = 7
_TEASER_YEAR = 2026

# Live date: after March 2026
_LIVE_YEAR = 2026
_LIVE_MONTH = 3  # March (0-indexed)


def is_buddy_teaser_window() -> bool:
    """
    Check if currently in the buddy teaser window.

    Returns:
        True if in April 1-7, 2026 window
    """
    # Currently disabled for external builds
    if _is_external_build():
        return True

    now = time.localtime()
    year = now.tm_year
    month = now.tm_mon
    day = now.tm_mday

    return (
        year == _TEASER_YEAR
        and month == _TEASER_START_MONTH
        and day <= _TEASER_END_DAY
    )


def is_buddy_live() -> bool:
    """
    Check if buddy feature is live (after March 2026).

    Returns:
        True if buddy is live
    """
    # Currently disabled for external builds
    if _is_external_build():
        return True

    now = time.localtime()
    year = now.tm_year
    month = now.tm_mon

    return year > _LIVE_YEAR or (year == _LIVE_YEAR and month >= _LIVE_MONTH)


def _is_external_build() -> bool:
    """Check if running as external build."""
    return True  # py-claw is always external build


@dataclass
class BuddyNotification:
    """A buddy notification."""
    key: str
    text: str
    priority: str = "immediate"  # 'immediate' | 'normal' | 'low'
    timeout_ms: int = 15000


@dataclass
class NotificationTrigger:
    """A trigger position in text."""
    start: int
    end: int


def find_buddy_trigger_positions(text: str) -> List[NotificationTrigger]:
    """
    Find all /buddy trigger positions in text.

    Args:
        text: Text to search

    Returns:
        List of trigger positions
    """
    if not is_buddy_live():
        return []

    triggers: List[NotificationTrigger] = []
    pattern = re.compile(r"\/buddy\b")
    for m in pattern.finditer(text):
        triggers.append(NotificationTrigger(
            start=m.start(),
            end=m.end(),
        ))
    return triggers


# ---------------------------------------------------------------------------
# Notification manager
# ---------------------------------------------------------------------------


class BuddyNotificationManager:
    """
    Manages buddy notifications and teaser logic.

    Tracks active notifications and handles automatic cleanup.
    """

    def __init__(self) -> None:
        self._notifications: Dict[str, BuddyNotification] = {}
        self._callbacks: List[Callable[[], None]] = []
        self._dismiss_timers: Dict[str, float] = {}

    def add_notification(
        self,
        key: str,
        text: str,
        priority: str = "immediate",
        timeout_ms: int = 15000,
    ) -> Callable[[], None]:
        """
        Add a buddy notification.

        Args:
            key: Unique notification key
            text: Notification text
            priority: Priority level
            timeout_ms: Auto-dismiss timeout in milliseconds

        Returns:
            Dismiss function
        """
        notification = BuddyNotification(
            key=key,
            text=text,
            priority=priority,
            timeout_ms=timeout_ms,
        )
        self._notifications[key] = notification
        self._notify_callbacks()

        # Set up auto-dismiss
        if timeout_ms > 0:

            def dismiss() -> None:
                self.remove_notification(key)

            timer = time.time() + (timeout_ms / 1000.0)
            self._dismiss_timers[key] = timer

        return lambda: self.remove_notification(key)

    def remove_notification(self, key: str) -> None:
        """Remove a notification by key."""
        self._notifications.pop(key, None)
        self._dismiss_timers.pop(key, None)
        self._notify_callbacks()

    def get_notification(self, key: str) -> Optional[BuddyNotification]:
        """Get a notification by key."""
        return self._notifications.get(key)

    def list_notifications(self) -> List[BuddyNotification]:
        """List all active notifications."""
        return list(self._notifications.values())

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to notification changes."""
        self._callbacks.append(callback)
        return lambda: self._callbacks.remove(callback)

    def _notify_callbacks(self) -> None:
        """Notify all subscribers of change."""
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                pass

    def check_teaser_and_notify(
        self,
        config: dict[str, Any],
        add_notification_fn: Callable[[str, str, str, int], Callable[[], None]],
    ) -> Optional[Callable[[], None]]:
        """
        Check teaser window and show notification if appropriate.

        Args:
            config: Global config dict
            add_notification_fn: Function to add notification

        Returns:
            Dismiss function or None
        """
        if not is_buddy_live():
            return None

        companion = config.get("companion")
        if companion or not is_buddy_teaser_window():
            return None

        dismiss_fn = add_notification_fn(
            key="buddy-teaser",
            text="/buddy",
            priority="immediate",
            timeout_ms=15000,
        )
        return dismiss_fn


# Module-level singleton
_notification_manager: Optional[BuddyNotificationManager] = None


def get_notification_manager() -> BuddyNotificationManager:
    """Get the global notification manager."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = BuddyNotificationManager()
    return _notification_manager


def reset_notification_manager() -> None:
    """Reset the notification manager (for testing)."""
    global _notification_manager
    _notification_manager = None
