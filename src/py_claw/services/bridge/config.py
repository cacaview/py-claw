"""Bridge configuration and feature gate management."""

from __future__ import annotations

import os
from dataclasses import dataclass

from py_claw.services.bridge.types import BridgeConfig

# Default bridge configuration
DEFAULT_BRIDGE_CONFIG = BridgeConfig(
    enabled=False,
    poll_interval_seconds=1.0,
    max_poll_interval_seconds=30.0,
    max_concurrent_sessions=32,
    request_timeout_seconds=30.0,
    ping_interval_seconds=30.0,
)

# Production API base URL for CCR (Claude Code Remote)
DEFAULT_BRIDGE_BASE_URL = "https://api.anthropic.com"


@dataclass
class BridgeFeatureConfig:
    """Feature flags for bridge mode."""

    # Build-time feature flag
    bridge_mode_enabled: bool = False

    # Runtime feature gates (GrowthBook)
    ccr_bridge_enabled: bool = False

    # Environment-based settings
    env_bridge_enabled: bool = False
    env_less_bridge_enabled: bool = False


def get_bridge_feature_config() -> BridgeFeatureConfig:
    """Get the current bridge feature configuration.

    This reads from environment variables and settings.
    In a full implementation, this would also read from GrowthBook gates.
    """
    import os

    return BridgeFeatureConfig(
        bridge_mode_enabled=os.environ.get("BRIDGE_MODE", "").lower()
        in ("true", "1", "yes"),
        ccr_bridge_enabled=os.environ.get("CCR_BRIDGE_ENABLED", "").lower()
        in ("true", "1", "yes"),
        env_bridge_enabled=os.environ.get("ENABLE_BRIDGE", "").lower()
        in ("true", "1", "yes"),
        env_less_bridge_enabled=os.environ.get("ENABLE_ENV_LESS_BRIDGE", "").lower()
        in ("true", "1", "yes"),
    )


def get_bridge_config() -> BridgeConfig:
    """Get the effective bridge configuration.

    This merges defaults with any runtime configuration.
    """
    # In a full implementation, this would read from:
    # 1. Environment variables
    # 2. Settings files
    # 3. Remote settings (GrowthBook)
    # 4. OAuth account info

    feature_config = get_bridge_feature_config()

    # If bridge mode is disabled via env, return disabled config
    if not feature_config.bridge_mode_enabled:
        return DEFAULT_BRIDGE_CONFIG

    # Build effective config from feature flags
    return BridgeConfig(
        enabled=feature_config.ccr_bridge_enabled,
        base_url=None,  # Set from OAuth/config
        session_ingress_url=None,  # Set from OAuth/config
        environment_id=None,  # Set from OAuth/config
        poll_interval_seconds=DEFAULT_BRIDGE_CONFIG.poll_interval_seconds,
        max_poll_interval_seconds=DEFAULT_BRIDGE_CONFIG.max_poll_interval_seconds,
        max_concurrent_sessions=DEFAULT_BRIDGE_CONFIG.max_concurrent_sessions,
        request_timeout_seconds=DEFAULT_BRIDGE_CONFIG.request_timeout_seconds,
        ping_interval_seconds=DEFAULT_BRIDGE_CONFIG.ping_interval_seconds,
    )


def get_bridge_access_token() -> str | None:
    """Get the access token for bridge API calls.

    Returns:
        Access token string if available, None otherwise.

    Priority:
    1. BRIDGE_MODE_ACCESS_TOKEN env var (for testing/development)
    2. CLAUDE_BRIDGE_OAUTH_TOKEN env var (ant-only dev override)
    3. OAuth tokens from secure storage
    """
    # Dev override for testing
    override = os.environ.get("CLAUDE_BRIDGE_OAUTH_TOKEN") or os.environ.get(
        "BRIDGE_MODE_ACCESS_TOKEN"
    )
    if override:
        return override

    # Try OAuth tokens
    try:
        from py_claw.services.auth import get_claude_ai_oauth_tokens

        tokens = get_claude_ai_oauth_tokens()
        if tokens and tokens.get("accessToken"):
            return tokens["accessToken"]
    except Exception:
        pass

    return None


def get_bridge_base_url() -> str:
    """Get the base URL for bridge API calls.

    Returns:
        Base URL string.

    Priority:
    1. CLAUDE_BRIDGE_BASE_URL env var (ant-only dev override)
    2. BRIDGE_BASE_URL env var (general override)
    3. Default production URL
    """
    override = os.environ.get("CLAUDE_BRIDGE_BASE_URL") or os.environ.get(
        "BRIDGE_BASE_URL"
    )
    if override:
        return override.rstrip("/")

    return DEFAULT_BRIDGE_BASE_URL
