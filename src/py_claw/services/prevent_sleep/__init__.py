"""PreventSleep service - macOS caffeinate-based sleep prevention."""
from __future__ import annotations

from .service import (
    PreventSleepService,
    get_prevent_sleep_service,
    start_prevent_sleep,
    stop_prevent_sleep,
    force_stop_prevent_sleep,
    register_cleanup,
    unregister_cleanup,
    CAFFEINATE_TIMEOUT_SECONDS,
    RESTART_INTERVAL_MS,
)
from .types import PreventSleepConfig

__all__ = [
    "PreventSleepService",
    "PreventSleepConfig",
    "get_prevent_sleep_service",
    "start_prevent_sleep",
    "stop_prevent_sleep",
    "force_stop_prevent_sleep",
    "register_cleanup",
    "unregister_cleanup",
    "CAFFEINATE_TIMEOUT_SECONDS",
    "RESTART_INTERVAL_MS",
]
