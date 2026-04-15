"""
Authentication utilities for API key management, OAuth tokens, and cloud provider auth.

Handles:
- API key retrieval from env, config, keychain, and apiKeyHelper
- OAuth token management and refresh
- AWS/GCP credential refresh and export
- Subscription type detection
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# Environment & platform detection
# -----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def is_bare_mode() -> bool:
    """Check if --bare mode is enabled (API-key-only, never OAuth)."""
    import sys
    return "--bare" in sys.argv


def is_env_truthy(val: str | None) -> bool:
    """Check if an environment variable value is truthy."""
    if not val:
        return False
    return val.lower() in ("1", "true", "yes", "on")


def is_running_on_homespace() -> bool:
    """Check if running on Homespace platform."""
    return is_env_truthy(os.environ.get("CLAUDE_CODE_HOMESPACE"))


def is_ci() -> bool:
    """Check if running in CI environment."""
    import sys
    return is_env_truthy(os.environ.get("CI")) or sys.argv[0].endswith("pytest")


# -----------------------------------------------------------------------------
# API Key source tracking
# -----------------------------------------------------------------------------

class ApiKeySource(Enum):
    ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
    API_KEY_HELPER = "apiKeyHelper"
    LOGIN_MANAGED_KEY = "/login managed key"
    NONE = "none"


@dataclass
class ApiKeyResult:
    key: str | None
    source: ApiKeySource


# -----------------------------------------------------------------------------
# Config directory helpers
# -----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_claude_config_home_dir() -> Path:
    """Get the Claude config directory."""
    if os.name == "nt":
        config = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    else:
        config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config) / "claude"


# -----------------------------------------------------------------------------
# API Key helper (from settings)
# -----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_configured_api_key_helper() -> str | None:
    """Get the configured apiKeyHelper from settings."""
    # Would normally load from settings - placeholder for now
    return None


@lru_cache(maxsize=1)
def get_anthropic_api_key() -> str | None:
    """Get the Anthropic API key from the best available source."""
    result = get_anthropic_api_key_with_source()
    return result.key


@lru_cache(maxsize=1)
def get_anthropic_api_key_with_source() -> ApiKeyResult:
    """
    Get the Anthropic API key with its source.

    Priority: ANTHROPIC_API_KEY env > apiKeyHelper > config/keychain
    """
    if is_bare_mode():
        # --bare: only ANTHROPIC_API_KEY or apiKeyHelper from --settings
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            return ApiKeyResult(key=api_key, source=ApiKeySource.ANTHROPIC_API_KEY)
        helper = get_configured_api_key_helper()
        if helper:
            # Would execute helper and return key
            return ApiKeyResult(key=None, source=ApiKeySource.API_KEY_HELPER)
        return ApiKeyResult(key=None, source=ApiKeySource.NONE)

    # On homespace, don't use ANTHROPIC_API_KEY (use Console key instead)
    api_key = os.environ.get("ANTHROPIC_API_KEY") if not is_running_on_homespace() else None

    if api_key:
        return ApiKeyResult(key=api_key, source=ApiKeySource.ANTHROPIC_API_KEY)

    # Check apiKeyHelper
    helper = get_configured_api_key_helper()
    if helper:
        # Would execute helper and return key
        return ApiKeyResult(key=None, source=ApiKeySource.API_KEY_HELPER)

    return ApiKeyResult(key=None, source=ApiKeySource.NONE)


def has_anthropic_api_key_auth() -> bool:
    """Check if we have a valid API key authentication."""
    result = get_anthropic_api_key_with_source()
    return result.key is not None and result.source != ApiKeySource.NONE


# -----------------------------------------------------------------------------
# OAuth token management
# -----------------------------------------------------------------------------

@dataclass
class OAuthTokens:
    """OAuth token data structure."""

    access_token: str
    refresh_token: str | None = None
    expires_at: str | None = None  # ISO timestamp
    scopes: list[str] | None = None
    subscription_type: str | None = None
    rate_limit_tier: str | None = None


def is_oauth_token_expired(expires_at: str | None) -> bool:
    """Check if an OAuth token is expired based on its expires_at timestamp."""
    if not expires_at:
        return False  # Unknown expiry = not expired
    try:
        expires_time = float(expires_at)
        return time.time() >= expires_time
    except (ValueError, TypeError):
        return False


@lru_cache(maxsize=1)
def get_claude_ai_oauth_tokens() -> OAuthTokens | None:
    """
    Get Claude.ai OAuth tokens from secure storage.
    Returns None if not authenticated or in bare mode.
    """
    if is_bare_mode():
        return None

    # Check for force-set OAuth token from environment variable
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if oauth_token:
        return OAuthTokens(
            access_token=oauth_token,
            refresh_token=None,
            expires_at=None,
            scopes=["user:inference"],
            subscription_type=None,
            rate_limit_tier=None,
        )

    # Would normally read from secure storage
    # For now, return None (placeholder)
    return None


def clear_oauth_token_cache() -> None:
    """Clear all OAuth token caches. Call on 401 errors."""
    get_claude_ai_oauth_tokens.cache_clear()


def is_claude_ai_subscriber() -> bool:
    """Check if the user is a Claude.ai subscriber."""
    tokens = get_claude_ai_oauth_tokens()
    if not tokens or not tokens.scopes:
        return False
    return "ai" in ".".join(tokens.scopes) or any(
        s in tokens.scopes for s in ("max", "pro", "team", "enterprise")
    )


def is_anthropic_auth_enabled() -> bool:
    """
    Check if direct 1P Anthropic auth is enabled.

    Disabled when:
    - --bare mode
    - Using 3rd party services (Bedrock/Vertex/Foundry)
    - User has external API key or auth token (unless managed OAuth context)
    """
    if is_bare_mode():
        return False

    is_3p = any(
        is_env_truthy(os.environ.get(f))
        for f in (
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_FOUNDRY",
        )
    )

    # Check for external auth token
    has_external_auth_token = bool(
        os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or get_configured_api_key_helper()
        or os.environ.get("CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR")
    )

    # Check for external API key
    result = get_anthropic_api_key_with_source()
    has_external_api_key = result.source in (
        ApiKeySource.ANTHROPIC_API_KEY,
        ApiKeySource.API_KEY_HELPER,
    )

    # Check for managed OAuth context (CCR/Claude Desktop)
    is_managed = is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE")) or os.environ.get(
        "CLAUDE_CODE_ENTRYPOINT"
    ) == "claude-desktop"

    should_disable = is_3p or (has_external_auth_token and not is_managed) or (
        has_external_api_key and not is_managed
    )

    return not should_disable


# -----------------------------------------------------------------------------
# Subscription type detection
# -----------------------------------------------------------------------------

def get_subscription_type() -> str | None:
    """Get the user's subscription type (max/pro/team/enterprise) or None for API."""
    if not is_anthropic_auth_enabled():
        return None
    tokens = get_claude_ai_oauth_tokens()
    if not tokens:
        return None
    return tokens.subscription_type


def is_max_subscriber() -> bool:
    """Check if user is a Max subscriber."""
    return get_subscription_type() == "max"


def is_pro_subscriber() -> bool:
    """Check if user is a Pro subscriber."""
    return get_subscription_type() == "pro"


def is_team_subscriber() -> bool:
    """Check if user is a Team subscriber."""
    return get_subscription_type() == "team"


def is_enterprise_subscriber() -> bool:
    """Check if user is an Enterprise subscriber."""
    return get_subscription_type() == "enterprise"


def get_subscription_name() -> str:
    """Get human-readable subscription name."""
    sub_type = get_subscription_type()
    names = {
        "enterprise": "Claude Enterprise",
        "team": "Claude Team",
        "max": "Claude Max",
        "pro": "Claude Pro",
    }
    return names.get(sub_type, "Claude API")


def has_opus_access() -> bool:
    """Check if user has Opus model access."""
    sub_type = get_subscription_type()
    return sub_type in ("max", "enterprise", "team", "pro") or sub_type is None


# -----------------------------------------------------------------------------
# API key helper execution
# -----------------------------------------------------------------------------

# Async cache for apiKeyHelper results
_api_key_helper_cache: dict[str, Any] = {}
_api_key_helper_lock = threading.Lock()


def get_api_key_from_api_key_helper(is_non_interactive: bool = False) -> str | None:
    """
    Execute apiKeyHelper and return the API key.
    Results are cached with TTL.
    """
    helper = get_configured_api_key_helper()
    if not helper:
        return None

    # Check cache
    now = time.time()
    cached = _api_key_helper_cache.get("cache")
    if cached and now - cached.get("timestamp", 0) < 5 * 60:  # 5 min TTL
        return cached.get("value")

    # Execute helper
    try:
        result = subprocess.run(
            helper,
            shell=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0 and result.stdout.strip():
            key = result.stdout.strip()
            with _api_key_helper_lock:
                _api_key_helper_cache["cache"] = {"value": key, "timestamp": now}
            return key
    except (subprocess.TimeoutExpired, OSError):
        pass

    return None


def clear_api_key_helper_cache() -> None:
    """Clear the apiKeyHelper cache."""
    with _api_key_helper_lock:
        _api_key_helper_cache.clear()


# -----------------------------------------------------------------------------
# Auth token source detection
# -----------------------------------------------------------------------------

def get_auth_token_source() -> str:
    """
    Determine where the auth token is being sourced from.
    Returns: 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN', 'claude.ai', 'none'
    """
    if is_bare_mode():
        helper = get_configured_api_key_helper()
        if helper:
            return "apiKeyHelper"
        return "none"

    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "ANTHROPIC_AUTH_TOKEN"

    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return "CLAUDE_CODE_OAUTH_TOKEN"

    tokens = get_claude_ai_oauth_tokens()
    if tokens and tokens.access_token:
        return "claude.ai"

    return "none"
