"""
Compact warning state management.

Tracks whether the "context left until autocompact" warning
should be suppressed. We suppress immediately after successful
compaction since we don't have accurate token counts until
the next API response.
"""
from __future__ import annotations

import threading

# Global compact warning state
_state: bool = False
_state_lock = threading.Lock()


def get_compact_warning_suppressed() -> bool:
    """Get whether compact warning is currently suppressed."""
    with _state_lock:
        return _state


def suppress_compact_warning() -> None:
    """Suppress the compact warning.

    Call after successful compaction to prevent warning spam
    when token counts are inaccurate.
    """
    with _state_lock:
        global _state
        _state = True


def clear_compact_warning_suppression() -> None:
    """Clear the compact warning suppression.

    Called at the start of a new compact attempt so warnings
    can be shown again if needed.
    """
    with _state_lock:
        global _state
        _state = False
