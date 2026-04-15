"""
Backend detection for swarm team orchestration.

Detects tmux and iTerm2 availability and running state.

Based on ClaudeCode-main/src/utils/swarm/backends/detection.ts
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

# Cached detection results
_is_inside_tmux_cached: Optional[bool] = None
_is_in_iterm2_cached: Optional[bool] = None

# Captured at module load time to detect if user started Claude from within tmux
ORIGINAL_TMUX = os.environ.get("TMUX")
ORIGINAL_TMUX_PANE = os.environ.get("TMUX_PANE")

# iTerm2 detection constants
TERM_PROGRAM = os.environ.get("TERM_PROGRAM", "")
ITERM_SESSION_ID = os.environ.get("ITERM_SESSION_ID", "")


def is_inside_tmux_sync() -> bool:
    """
    Checks if we're currently running inside a tmux session (synchronous version).

    Uses the original TMUX value captured at module load, not os.environ,
    because the TMUX env var may be overridden later.
    """
    return bool(ORIGINAL_TMUX)


async def is_inside_tmux() -> bool:
    """
    Checks if we're currently running inside a tmux session.

    Uses the original TMUX value captured at module load, not os.environ,
    because the TMUX env var may be overridden later.
    Caches the result since this won't change during the process lifetime.
    """
    global _is_inside_tmux_cached

    if _is_inside_tmux_cached is not None:
        return _is_inside_tmux_cached

    _is_inside_tmux_cached = is_inside_tmux_sync()
    return _is_inside_tmux_cached


def get_leader_pane_id() -> Optional[str]:
    """
    Gets the leader's tmux pane ID captured at module load.

    Returns None if not running inside tmux.
    TMUX_PANE is set by tmux to the pane ID (e.g., %0, %1).
    """
    return ORIGINAL_TMUX_PANE


def is_tmux_available() -> bool:
    """
    Checks if tmux is available on the system (installed and in PATH).
    """
    return shutil.which("tmux") is not None


def is_in_iterm2() -> bool:
    """
    Checks if we're currently running inside iTerm2.

    Uses multiple detection methods:
    1. TERM_PROGRAM env var set to "iTerm.app"
    2. ITERM_SESSION_ID env var is present
    3. Terminal detection from environment

    Caches the result since this won't change during the process lifetime.
    """
    global _is_in_iterm2_cached

    if _is_in_iterm2_cached is not None:
        return _is_in_iterm2_cached

    term_program = TERM_PROGRAM
    has_iterim_session_id = bool(ITERM_SESSION_ID)

    _is_in_iterm2_cached = term_program == "iTerm.app" or has_iterim_session_id

    return _is_in_iterm2_cached


async def is_iterm2_cli_available() -> bool:
    """
    Checks if the it2 CLI tool is available AND can reach the iTerm2 Python API.

    Uses 'session list' (not '--version') because --version succeeds even when
    the Python API is disabled in iTerm2 preferences.
    """
    try:
        result = subprocess.run(
            ["it2", "session", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def reset_detection_cache() -> None:
    """Reset all cached detection results. Used for testing."""
    global _is_inside_tmux_cached, _is_in_iterm2_cached
    _is_inside_tmux_cached = None
    _is_in_iterm2_cached = None


@dataclass
class BackendDetectionResult:
    """Result from backend detection."""
    backend_type: str
    is_native: bool
    needs_it2_setup: bool = False


async def detect_backend_type() -> Optional[BackendDetectionResult]:
    """
    Detect the best backend type to use for the current environment.

    Returns:
        BackendDetectionResult with the best backend type, or None if no backends available
    """
    # Check tmux first
    if is_tmux_available():
        is_running = await is_inside_tmux()
        return BackendDetectionResult(
            backend_type="tmux",
            is_native=is_running,
            needs_it2_setup=False,
        )

    # Check iTerm2
    if platform.system() == "Darwin" and await is_iterm2_cli_available():
        return BackendDetectionResult(
            backend_type="iterm2",
            is_native=is_in_iterm2(),
            needs_it2_setup=True,
        )

    return None


__all__ = [
    "ORIGINAL_TMUX",
    "ORIGINAL_TMUX_PANE",
    "is_inside_tmux",
    "is_inside_tmux_sync",
    "get_leader_pane_id",
    "is_tmux_available",
    "is_in_iterm2",
    "is_iterm2_cli_available",
    "reset_detection_cache",
    "BackendDetectionResult",
    "detect_backend_type",
]
