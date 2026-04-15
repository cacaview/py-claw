"""Auto mode state tracking for permissions."""

from __future__ import annotations

from dataclasses import dataclass

# Global auto mode state
_auto_mode_active: bool = False
_auto_mode_start_time: float | None = None


@dataclass
class AutoModeState:
    """State for auto mode tracking."""

    active: bool
    start_time: float | None = None


def is_auto_mode_active() -> bool:
    """Check if auto mode is currently active."""
    return _auto_mode_active


def set_auto_mode_active(active: bool) -> None:
    """Set the auto mode active state."""
    global _auto_mode_active, _auto_mode_start_time

    if active and not _auto_mode_active:
        import time

        _auto_mode_start_time = time.time()
    elif not active:
        _auto_mode_start_time = None

    _auto_mode_active = active


def clear_auto_mode() -> None:
    """Clear the auto mode state."""
    global _auto_mode_active, _auto_mode_start_time
    _auto_mode_active = False
    _auto_mode_start_time = None


def get_auto_mode_duration_seconds() -> float | None:
    """Get the duration auto mode has been active in seconds."""
    if not _auto_mode_active or _auto_mode_start_time is None:
        return None
    import time

    return time.time() - _auto_mode_start_time
