"""Poll interval configuration with GrowthBook integration.

Provides poll interval configuration that can be dynamically
updated via GrowthBook feature flags.
"""

from __future__ import annotations

import logging
from typing import Any

from py_claw.services.bridge.poll_config_defaults import (
    DEFAULT_POLL_CONFIG,
    PollIntervalConfig,
)

logger = logging.getLogger(__name__)


# Cache for the poll configuration
_cached_config: PollIntervalConfig = DEFAULT_POLL_CONFIG
_last_refresh_ms: int = 0
_cache_TTL_ms: int = 5 * 60 * 1000  # 5 minutes


def _validate_poll_config(raw: dict[str, Any]) -> PollIntervalConfig:
    """Validate and normalize a raw poll configuration.

    Args:
        raw: Raw configuration dictionary

    Returns:
        Validated PollIntervalConfig or defaults if validation fails
    """
    try:
        # Validate required numeric fields
        poll_not_at_capacity = raw.get("poll_interval_ms_not_at_capacity", 1000)
        poll_at_capacity = raw.get("poll_interval_ms_at_capacity", 5000)
        heartbeat = raw.get("non_exclusive_heartbeat_interval_ms", 0)
        reclaim_older = raw.get("reclaim_older_than_ms", 5000)
        keepalive_v2 = raw.get("session_keepalive_interval_v2_ms", 120_000)

        # Apply minimum bounds
        if poll_not_at_capacity < 100:
            poll_not_at_capacity = 100

        # at-capacity must be 0 (disabled) or >= 100
        if poll_at_capacity != 0 and poll_at_capacity < 100:
            poll_at_capacity = 5000  # Fall back to default

        # heartbeat must be >= 0
        if heartbeat < 0:
            heartbeat = 0

        # reclaim_older_than must be >= 1
        if reclaim_older_than_ms := raw.get("reclaim_older_than_ms"):
            if reclaim_older_than_ms < 1:
                reclaim_older_than_ms = 5000
        else:
            reclaim_older_than_ms = 5000

        # keepalive_v2 must be >= 0
        if keepalive_v2 < 0:
            keepalive_v2 = 120_000

        # Validate at-capacity liveness: must have either heartbeat OR at-capacity polling
        if heartbeat == 0 and poll_at_capacity == 0:
            logger.warning(
                "Poll config validation failed: at-capacity liveness requires "
                "non_exclusive_heartbeat_interval_ms > 0 or poll_interval_ms_at_capacity > 0"
            )
            return DEFAULT_POLL_CONFIG

        # Multisession intervals
        multisession_not_at = raw.get(
            "multisession_poll_interval_ms_not_at_capacity", 1000
        )
        multisession_partial = raw.get(
            "multisession_poll_interval_ms_partial_capacity", 2000
        )
        multisession_at = raw.get("multisession_poll_interval_ms_at_capacity", 5000)

        if multisession_not_at < 100:
            multisession_not_at = 1000
        if multisession_partial < 100:
            multisession_partial = 2000
        if multisession_at != 0 and multisession_at < 100:
            multisession_at = 5000

        # Validate multisession at-capacity liveness
        if heartbeat == 0 and multisession_at == 0:
            logger.warning(
                "Poll config validation failed: multisession at-capacity liveness requires "
                "non_exclusive_heartbeat_interval_ms > 0 or "
                "multisession_poll_interval_ms_at_capacity > 0"
            )
            return DEFAULT_POLL_CONFIG

        return PollIntervalConfig(
            poll_interval_ms_not_at_capacity=poll_not_at_capacity,
            poll_interval_ms_at_capacity=poll_at_capacity,
            non_exclusive_heartbeat_interval_ms=heartbeat,
            multisession_poll_interval_ms_not_at_capacity=multisession_not_at,
            multisession_poll_interval_ms_partial_capacity=multisession_partial,
            multisession_poll_interval_ms_at_capacity=multisession_at,
            reclaim_older_than_ms=reclaim_older_than_ms,
            session_keepalive_interval_v2_ms=keepalive_v2,
        )

    except (TypeError, ValueError) as e:
        logger.warning(f"Poll config validation error: {e}")
        return DEFAULT_POLL_CONFIG


def _get_growthbook_value(
    feature_key: str,
    default: Any,
) -> Any:
    """Get a value from analytics dynamic config cache.

    This mirrors the TS bridge poll config path closely enough for Python:
    values come from the analytics/GrowthBook-style dynamic config service,
    which supports cached config values and refresh listeners.

    Args:
        feature_key: The feature flag key
        default: Default value if not found

    Returns:
        The feature value or default
    """
    try:
        from py_claw.services.analytics import get_analytics_service

        service = get_analytics_service()
        if not service.initialized:
            service.initialize()
        return service.get_dynamic_config(feature_key, default)
    except Exception as exc:
        logger.debug("Failed to load dynamic config %s: %s", feature_key, exc)
        return default


def get_poll_interval_config() -> PollIntervalConfig:
    """Fetch the bridge poll interval config from GrowthBook.

    Validates the served JSON against the schema; falls back
    to defaults if the flag is absent, malformed, or partially-specified.

    Shared by bridgeMain.ts (standalone) and replBridge.ts (REPL) so ops
    can tune both poll rates fleet-wide with a single config push.

    Returns:
        The validated PollIntervalConfig
    """
    global _cached_config, _last_refresh_ms

    import time

    current_ms = int(time.time() * 1000)

    # Check if cache needs refresh
    if current_ms - _last_refresh_ms > _cache_TTL_ms:
        raw = _get_growthbook_value(
            "tengu_bridge_poll_interval_config",
            DEFAULT_POLL_CONFIG,
        )

        # Convert to dict if it's a dataclass
        if hasattr(raw, "__dataclass_fields__"):
            raw = {
                f.name: getattr(raw, f.name)
                for f in raw.__dataclass_fields__.values()
            }

        if isinstance(raw, dict):
            validated = _validate_poll_config(raw)
            if validated is not DEFAULT_POLL_CONFIG or raw:
                _cached_config = validated

        _last_refresh_ms = current_ms

    return _cached_config


def reset_poll_config_cache() -> None:
    """Reset the poll config cache (for testing)."""
    global _cached_config, _last_refresh_ms
    _cached_config = DEFAULT_POLL_CONFIG
    _last_refresh_ms = 0
