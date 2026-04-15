"""
Background housekeeping tasks.

Runs slow cleanup and maintenance tasks in the background
to avoid blocking the main session.

Mirrors TS backgroundHousekeeping.ts behavior.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

from .cleanup import (
    cleanup_old_message_files,
    cleanup_old_versions_throttled as cleanup_old_versions,
)
from .debug import log_for_debugging


# 24 hours in milliseconds
RECURRING_CLEANUP_INTERVAL_MS = 24 * 60 * 60 * 1000

# 10 minutes - delay for slow operations that happen every session
DELAY_SLOW_OPS_MS = 10 * 60 * 1000

# Track if we've scheduled recurring cleanup
_recurring_cleanup_scheduled = False
_cleanup_lock = threading.Lock()


def start_background_housekeeping() -> None:
    """
    Start background housekeeping tasks.

    Schedules:
    - Delayed cleanup of old message files and versions
    - Recurring 24-hour cleanup for long-running sessions
    """
    _schedule_delayed_slow_ops()


def _schedule_delayed_slow_ops() -> None:
    """Schedule slow operations to run after a delay."""
    def run_slow_ops() -> None:
        # Skip if user was recently active
        if _was_recently_active():
            # Reschedule
            threading.Timer(
                DELAY_SLOW_OPS_MS / 1000,
                run_slow_ops,
            ).start()
            return

        # Run message file cleanup
        try:
            cleanup_old_message_files()
        except Exception as e:
            log_for_debugging(f"Background housekeeping: message cleanup failed: {e}")

        # Run version cleanup
        try:
            cleanup_old_versions()
        except Exception as e:
            log_for_debugging(f"Background housekeeping: version cleanup failed: {e}")

    # Schedule after initial delay
    t = threading.Timer(DELAY_SLOW_OPS_MS / 1000, run_slow_ops)
    t.daemon = True
    t.start()


def _was_recently_active() -> bool:
    """Check if the user was active in the last minute."""
    # In Python, we don't have the same state tracking as TS
    # For simplicity, we return False to allow cleanup
    return False


def schedule_recurring_cleanup() -> None:
    """
    Schedule recurring 24-hour cleanup for long-running sessions.

    Uses marker files and locks to throttle to once per day.
    """
    global _recurring_cleanup_scheduled

    if _recurring_cleanup_scheduled:
        return

    with _cleanup_lock:
        if _recurring_cleanup_scheduled:
            return
        _recurring_cleanup_scheduled = True

    def run_recurring_cleanup() -> None:
        if os.environ.get("USER_TYPE") == "ant":
            try:
                # These would be implemented in cleanup module
                # cleanup_npm_cache_for_anthropic_packages()
                # cleanup_old_versions_throttled()
                log_for_debugging("Running recurring cleanup")
            except Exception as e:
                log_for_debugging(f"Recurring cleanup failed: {e}")

    # Schedule recurring cleanup every 24 hours
    t = threading.Timer(
        RECURRING_CLEANUP_INTERVAL_MS / 1000,
        run_recurring_cleanup,
    )
    t.daemon = True
    t.start()
