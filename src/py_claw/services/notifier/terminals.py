"""Terminal notification backends for different terminal emulators."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import NotificationOptions

logger = logging.getLogger(__name__)

# OSC escape sequences
BEL = "\x07"  # Bell character
ESC = "\x1b"
ST = f"{ESC}\\"  # String terminator for Kitty

# OSC command numbers
OSC_ITERM2 = 9
OSC_KITTY = 99
OSC_GHOSTTY = 777


def _osc(*parts: str | int) -> str:
    """Build an OSC escape sequence.

    Uses ST terminator for Kitty (avoids beeps), BEL for others.
    """
    terminator = ST if _is_kitty() else BEL
    return f"{ESC}]{';'.join(str(p) for p in parts)}{terminator}"


def _is_kitty() -> bool:
    """Check if running in Kitty terminal."""
    term = os.environ.get("TERM", "")
    return term == "xterm-kitty"


def _is_ghostty() -> bool:
    """Check if running in Ghostty terminal."""
    term = os.environ.get("TERM", "")
    return "ghostty" in term.lower()


def _is_iterm2() -> bool:
    """Check if running in iTerm2."""
    term = os.environ.get("TERM_PROGRAM", "")
    return term == "iTerm.app"


class TerminalBackend(ABC):
    """Base class for terminal notification backends."""

    @abstractmethod
    def send_notification(self, opts: NotificationOptions) -> bool:
        """Send a notification to this terminal.

        Returns True if sent successfully, False otherwise.
        """
        ...

    def write(self, data: str) -> None:
        """Write data to stdout."""
        sys.stdout.write(data)
        sys.stdout.flush()


class ITerm2Backend(TerminalBackend):
    """iTerm2 notification backend using OSC 9."""

    def send_notification(self, opts: NotificationOptions) -> bool:
        """Send iTerm2 notification using OSC 9."""
        try:
            title = opts.title or "Claude Code"
            # OSC 9;0: iTerm2 notification with title and body
            display = f"\n\n{title}:\n{opts.message}"
            sequence = _osc(OSC_ITERM2, 0, display)
            self.write(sequence)
            return True
        except Exception as e:
            logger.debug(f"iTerm2 notification failed: {e}")
            return False


class ITerm2WithBellBackend(ITerm2Backend):
    """iTerm2 with notification and terminal bell."""

    def send_notification(self, opts: NotificationOptions) -> bool:
        """Send iTerm2 notification and ring terminal bell."""
        result = super().send_notification(opts)
        if result:
            self.write(BEL)
        return result


class KittyBackend(TerminalBackend):
    """Kitty notification backend using OSC 99."""

    def send_notification(self, opts: NotificationOptions) -> bool:
        """Send Kitty notification using OSC 99."""
        try:
            import random

            title = opts.title or "Claude Code"
            notification_id = random.randint(0, 9999)

            # Kitty notification protocol: OSC 99 ; i=<id> : d=<delay> : p=<property> : <value>
            # i=<id>: notification id
            # d=0: don't persist
            # p=title / p=body / a=action (d=1:a=focus to show briefly)
            seq1 = _osc(OSC_KITTY, f"i={notification_id}:d=0:p=title", title)
            seq2 = _osc(OSC_KITTY, f"i={notification_id}:p=body", opts.message)
            seq3 = _osc(OSC_KITTY, f"i={notification_id}:d=1:a=focus", "")

            self.write(seq1 + seq2 + seq3)
            return True
        except Exception as e:
            logger.debug(f"Kitty notification failed: {e}")
            return False


class GhosttyBackend(TerminalBackend):
    """Ghostty notification backend using OSC 777."""

    def send_notification(self, opts: NotificationOptions) -> bool:
        """Send Ghostty notification using OSC 777."""
        try:
            title = opts.title or "Claude Code"
            # Ghostty notification protocol: OSC 777 ; notify ; <title> ; <body>
            sequence = _osc(OSC_GHOSTTY, "notify", title, opts.message)
            self.write(sequence)
            return True
        except Exception as e:
            logger.debug(f"Ghostty notification failed: {e}")
            return False


class BellBackend(TerminalBackend):
    """Terminal bell notification backend."""

    def send_notification(self, opts: NotificationOptions) -> bool:
        """Ring the terminal bell."""
        try:
            self.write(BEL)
            return True
        except Exception as e:
            logger.debug(f"Bell notification failed: {e}")
            return False


def get_backend(channel: str) -> TerminalBackend:
    """Get the notification backend for the given channel."""
    from .types import NotificationChannel

    try:
        ch = NotificationChannel(channel)
    except ValueError:
        ch = NotificationChannel.AUTO

    if ch == NotificationChannel.ITERM2:
        return ITerm2Backend()
    elif ch == NotificationChannel.ITERM2_WITH_BELL:
        return ITerm2WithBellBackend()
    elif ch == NotificationChannel.KITTY:
        return KittyBackend()
    elif ch == NotificationChannel.GHOSTTY:
        return GhosttyBackend()
    elif ch == NotificationChannel.TERMINAL_BELL:
        return BellBackend()
    else:
        return BellBackend()  # Fallback to bell
