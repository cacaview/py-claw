"""
Notifier service - terminal notification system.

Supports iTerm2, Kitty, Ghostty with auto-detection.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import TYPE_CHECKING

from .terminals import (
    BellBackend,
    GhosttyBackend,
    ITerm2Backend,
    ITerm2WithBellBackend,
    KittyBackend,
    get_backend,
)
from .types import (
    DEFAULT_NOTIFICATION_TITLE,
    NotificationChannel,
    NotificationOptions,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _detect_terminal() -> str:
    """Detect the current terminal type."""
    # Check TERM_PROGRAM first (most reliable)
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program == "iTerm.app":
        return "iTerm.app"

    # Check TERM for Kitty and Ghostty
    term = os.environ.get("TERM", "")
    if term == "xterm-kitty":
        return "kitty"
    if "ghostty" in term.lower():
        return "ghostty"

    # Check for Apple Terminal
    if term == "xterm-256color":
        # Could be Apple Terminal or generic
        # Apple Terminal doesn't set TERM_PROGRAM
        return os.environ.get("TERM_SESSION_ID", "") and "Apple_Terminal" or ""

    return os.environ.get("TERM", "")


def _get_configured_channel() -> str:
    """Get the configured notification channel from settings."""
    # TODO: Read from settings when available
    # For now, check environment variable
    return os.environ.get("CLAUDE_NOTIFICATION_CHANNEL", "auto")


async def _execute_notification_hooks(opts: NotificationOptions) -> None:
    """Execute any registered notification hooks.

    This allows other parts of the system to react to notifications.
    """
    # TODO: Integrate with hooks system when available
    # For now, this is a no-op since the function doesn't do any async work
    # If hooks are added later, this would call hook_runtime.run_notification()
    return None


def _log_analytics_event(
    configured_channel: str,
    method_used: str,
    terminal: str,
) -> None:
    """Log analytics event for notification method used."""
    # TODO: Integrate with analytics service when available
    logger.debug(
        f"Notification: configured={configured_channel}, "
        f"method={method_used}, terminal={terminal}"
    )


async def send_notification(
    opts: NotificationOptions,
    terminal: str | None = None,
) -> bool:
    """Send a notification to the terminal.

    Args:
        opts: Notification options (message, title, type).
        terminal: Optional terminal override for testing.

    Returns:
        True if notification was sent successfully.
    """
    # Execute notification hooks
    await _execute_notification_hooks(opts)

    # Get configured channel
    configured_channel = _get_configured_channel()
    if configured_channel == "notifications_disabled":
        _log_analytics_event(configured_channel, "disabled", terminal or "")
        return False

    # Get terminal type
    detected_terminal = terminal or _detect_terminal()

    # Route to appropriate channel
    method_used = await _send_to_channel(configured_channel, opts, detected_terminal)

    # Log analytics
    _log_analytics_event(configured_channel, method_used, detected_terminal)

    return method_used != "error" and method_used != "none"


async def _send_to_channel(
    channel: str,
    opts: NotificationOptions,
    terminal: str,
) -> str:
    """Send notification to the specified channel.

    Returns the method used: 'iterm2', 'kitty', 'ghostty', 'terminal_bell',
    'disabled', 'none', or 'error'.
    """
    title = opts.title or DEFAULT_NOTIFICATION_TITLE

    try:
        if channel == "auto":
            return await _send_auto(opts, terminal)
        elif channel == "iterm2":
            backend = ITerm2Backend()
            backend.send_notification(opts)
            return "iterm2"
        elif channel == "iterm2_with_bell":
            backend = ITerm2WithBellBackend()
            backend.send_notification(opts)
            return "iterm2_with_bell"
        elif channel == "kitty":
            backend = KittyBackend()
            backend.send_notification(opts)
            return "kitty"
        elif channel == "ghostty":
            backend = GhosttyBackend()
            backend.send_notification(opts)
            return "ghostty"
        elif channel == "terminal_bell":
            backend = BellBackend()
            backend.send_notification(opts)
            return "terminal_bell"
        elif channel == "notifications_disabled":
            return "disabled"
        else:
            return "none"
    except Exception as e:
        logger.debug(f"Notification send failed: {e}")
        return "error"


async def _send_auto(
    opts: NotificationOptions,
    terminal: str,
) -> str:
    """Auto-detect terminal and send notification.

    Returns the method used or 'no_method_available'.
    """
    title = opts.title or DEFAULT_NOTIFICATION_TITLE

    if terminal == "Apple_Terminal" or terminal == "":
        # Check if bell is disabled in Apple Terminal
        bell_disabled = await _is_apple_terminal_bell_disabled()
        if bell_disabled:
            backend = BellBackend()
            backend.send_notification(opts)
            return "terminal_bell"
        return "no_method_available"

    elif terminal == "iTerm.app":
        backend = ITerm2Backend()
        backend.send_notification(opts)
        return "iterm2"

    elif terminal == "kitty":
        backend = KittyBackend()
        backend.send_notification(opts)
        return "kitty"

    elif "ghostty" in terminal.lower():
        backend = GhosttyBackend()
        backend.send_notification(opts)
        return "ghostty"

    return "no_method_available"


async def _is_apple_terminal_bell_disabled() -> bool:
    """Check if Apple Terminal has the bell disabled.

    Uses osascript to get the current profile, then reads the
    plist to check if Bell is disabled.
    """
    try:
        import plistlib

        # Get current profile name
        result = subprocess.run(
            [
                "osascript",
                "-e",
                "tell application \"Terminal\" to name of current settings of front window",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        current_profile = result.stdout.strip()
        if not current_profile:
            return False

        # Read Terminal plist
        plist_result = subprocess.run(
            ["defaults", "export", "com.apple.Terminal", "-"],
            capture_output=True,
            timeout=5,
        )
        if plist_result.returncode != 0:
            return False

        # Parse plist
        parsed: dict = plistlib.loads(plist_result.stdout)
        window_settings = parsed.get("Window Settings", {})
        profile_settings = window_settings.get(current_profile, {})
        if not profile_settings:
            return False

        return profile_settings.get("Bell") is False
    except Exception as e:
        logger.debug(f"Apple Terminal bell check failed: {e}")
        return False


class NotifierService:
    """Terminal notification service.

    Provides a service interface for sending notifications to
    various terminal emulators with auto-detection.
    """

    def __init__(self, channel: str | None = None) -> None:
        self._channel = channel or _get_configured_channel()

    async def send(
        self,
        message: str,
        title: str | None = None,
        notification_type: str = "general",
    ) -> bool:
        """Send a notification.

        Args:
            message: Notification message body.
            title: Optional title.
            notification_type: Type identifier.

        Returns:
            True if sent successfully.
        """
        opts = NotificationOptions(
            message=message,
            title=title,
            notification_type=notification_type,
        )
        return await send_notification(opts)

    async def send_iterm2(self, message: str, title: str | None = None) -> bool:
        """Send iTerm2 notification."""
        opts = NotificationOptions(
            message=message,
            title=title or DEFAULT_NOTIFICATION_TITLE,
            notification_type="iterm2",
        )
        method = await _send_to_channel("iterm2", opts, "iTerm.app")
        return method == "iterm2"

    async def send_kitty(self, message: str, title: str | None = None) -> bool:
        """Send Kitty notification."""
        opts = NotificationOptions(
            message=message,
            title=title or DEFAULT_NOTIFICATION_TITLE,
            notification_type="kitty",
        )
        method = await _send_to_channel("kitty", opts, "kitty")
        return method == "kitty"

    async def send_ghostty(self, message: str, title: str | None = None) -> bool:
        """Send Ghostty notification."""
        opts = NotificationOptions(
            message=message,
            title=title or DEFAULT_NOTIFICATION_TITLE,
            notification_type="ghostty",
        )
        method = await _send_to_channel("ghostty", opts, "ghostty")
        return method == "ghostty"

    async def send_bell(self) -> bool:
        """Send terminal bell."""
        opts = NotificationOptions(
            message="",
            notification_type="bell",
        )
        method = await _send_to_channel("terminal_bell", opts, "")
        return method == "terminal_bell"


# Global singleton instance
_service: NotifierService | None = None
_init_lock: object | None = None


def get_notifier_service() -> NotifierService:
    """Get the global NotifierService singleton."""
    global _service
    if _service is None:
        try:
            import threading

            global _init_lock
            if _init_lock is None:
                _init_lock = threading.Lock()
            with _init_lock:
                if _service is None:
                    _service = NotifierService()
        except Exception:
            if _service is None:
                _service = NotifierService()
    return _service


async def notify(
    message: str,
    title: str | None = None,
    notification_type: str = "general",
) -> bool:
    """Send a notification using the global service."""
    return await get_notifier_service().send(message, title, notification_type)
