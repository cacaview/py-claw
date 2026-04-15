"""PreventSleep service types and configuration."""
from __future__ import annotations

from dataclasses import dataclass

# Default caffeinate timeout in seconds (5 minutes)
DEFAULT_CAFFEINATE_TIMEOUT_SECONDS = 300

# Default restart interval in milliseconds (4 minutes)
DEFAULT_RESTART_INTERVAL_MS = 4 * 60 * 1000


@dataclass
class PreventSleepConfig:
    """Configuration for the prevent sleep service.

    Attributes:
        timeout_seconds: Caffeinate process timeout. Process auto-exits after
            this duration, providing self-healing if the Python process is
            killed with SIGKILL.
        restart_interval_ms: How often to restart caffeinate before the
            timeout expires. Should be less than timeout_seconds.
        unref_process: Whether to prevent the caffeinate process from
            keeping the Python process alive.
    """

    timeout_seconds: int = DEFAULT_CAFFEINATE_TIMEOUT_SECONDS
    restart_interval_ms: int = DEFAULT_RESTART_INTERVAL_MS
    unref_process: bool = True
