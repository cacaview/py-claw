"""Env-less bridge timing configuration.

Provides GrowthBook-based config for the CCR v2 env-less bridge path.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EnvLessBridgeConfig:
    """Timing configuration for env-less (v2) bridge."""

    # init-phase retry (createSession, POST /bridge, recovery)
    init_retry_max_attempts: int = 3
    init_retry_base_delay_ms: int = 500
    init_retry_jitter_fraction: float = 0.25
    init_retry_max_delay_ms: int = 4000

    # axios timeout for POST /sessions, POST /bridge, POST /archive
    http_timeout_ms: int = 10_000

    # BoundedUUIDSet ring size (echo + re-delivery dedup)
    uuid_dedup_buffer_size: int = 2000

    # CCRClient heartbeat cadence (server TTL is 60s, 20s gives 3x margin)
    heartbeat_interval_ms: int = 20_000

    # ±fraction per beat jitter
    heartbeat_jitter_fraction: float = 0.1

    # Fire proactive JWT refresh this long before expires_in
    token_refresh_buffer_ms: int = 300_000

    # Archive POST timeout in teardown (distinct from http_timeout)
    teardown_archive_timeout_ms: int = 1500

    # Deadline for onConnect after transport.connect()
    connect_timeout_ms: int = 15_000

    # Semver floor for env-less bridge path
    min_version: str = "0.0.0"

    # Whether to nudge users to upgrade claude.ai app
    should_show_app_upgrade_message: bool = False


DEFAULT_ENV_LESS_BRIDGE_CONFIG = EnvLessBridgeConfig()


def get_env_less_bridge_config() -> EnvLessBridgeConfig:
    """Fetch the env-less bridge timing config.

    In a full implementation, would read from GrowthBook.
    Currently returns defaults with environment variable overrides.

    Returns:
        EnvLessBridgeConfig with validated values.
    """
    import os

    config = EnvLessBridgeConfig()

    # Allow environment variable overrides
    if os.environ.get("ENV_LESS_BRIDGE_INIT_RETRY_MAX_ATTEMPTS"):
        try:
            config.init_retry_max_attempts = int(
                os.environ["ENV_LESS_BRIDGE_INIT_RETRY_MAX_ATTEMPTS"]
            )
        except ValueError:
            pass

    if os.environ.get("ENV_LESS_BRIDGE_HEARTBEAT_INTERVAL_MS"):
        try:
            config.heartbeat_interval_ms = int(
                os.environ["ENV_LESS_BRIDGE_HEARTBEAT_INTERVAL_MS"]
            )
        except ValueError:
            pass

    if os.environ.get("ENV_LESS_BRIDGE_HTTP_TIMEOUT_MS"):
        try:
            config.http_timeout_ms = int(
                os.environ["ENV_LESS_BRIDGE_HTTP_TIMEOUT_MS"]
            )
        except ValueError:
            pass

    return config


def check_env_less_bridge_min_version(
    current_version: str,
    min_version: str | None = None,
) -> str | None:
    """Check if current version meets minimum for env-less bridge.

    Args:
        current_version: Current CLI version.
        min_version: Minimum required version (from config if None).

    Returns:
        Error message if version is too old, None if OK.
    """
    if min_version is None:
        config = get_env_less_bridge_config()
        min_version = config.min_version

    if min_version == "0.0.0":
        return None

    # Simple semver comparison
    def parse_ver(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split(".")[:3])

    try:
        current = parse_ver(current_version)
        minimum = parse_ver(min_version)
        if current < minimum:
            return (
                f"Your version of Claude Code ({current_version}) is too old "
                f"for Remote Control. Version {min_version} or higher is required. "
                "Run `claude update` to update."
            )
    except (ValueError, AttributeError):
        pass

    return None


def should_show_app_upgrade_message() -> bool:
    """Whether to show app upgrade message for v2 bridge.

    Returns:
        True if should show the upgrade nudge.
    """
    config = get_env_less_bridge_config()
    return config.should_show_app_upgrade_message
