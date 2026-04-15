"""Poll interval configuration defaults for bridge.

Contains the default poll interval configuration used by both
standalone bridge (bridgeMain.ts) and REPL bridge (replBridge.ts).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PollIntervalConfig:
    """Configuration for bridge poll intervals.

    All interval values are in milliseconds.
    """

    # Poll interval when not at capacity
    poll_interval_ms_not_at_capacity: int = 1000

    # Poll interval when at capacity (0 = disabled)
    poll_interval_ms_at_capacity: int = 5000

    # Heartbeat interval while at capacity (0 = disabled)
    non_exclusive_heartbeat_interval_ms: int = 0

    # Multisession poll interval when not at capacity
    multisession_poll_interval_ms_not_at_capacity: int = 1000

    # Multisession poll interval at partial capacity
    multisession_poll_interval_ms_partial_capacity: int = 2000

    # Multisession poll interval at capacity (0 = disabled)
    multisession_poll_interval_ms_at_capacity: int = 5000

    # Reclaim sessions older than this many milliseconds
    reclaim_older_than_ms: int = 5000

    # Session keepalive interval for v2 protocol
    session_keepalive_interval_v2_ms: int = 120_000


# Default poll configuration
DEFAULT_POLL_CONFIG = PollIntervalConfig()


def get_default_poll_config() -> PollIntervalConfig:
    """Get the default poll interval configuration.

    Returns:
        The default PollIntervalConfig instance
    """
    return DEFAULT_POLL_CONFIG
