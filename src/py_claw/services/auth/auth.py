"""Auth utilities for token management, API key handling, and authentication state.

This module provides Python equivalents of the TypeScript auth utilities from
ClaudeCode-main/src/utils/auth.ts, focusing on:
- Token refresh and storage
- Auth state management
- OAuth helpers
- API key caching and management
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal
from functools import lru_cache

# Default TTL for API key helper cache in milliseconds (5 minutes)
DEFAULT_API_KEY_HELPER_TTL_MS = 5 * 60 * 1000

# Default AWS STS TTL - one hour
DEFAULT_AWS_STS_TTL_MS = 60 * 60 * 1000

# Default GCP credential TTL - one hour
DEFAULT_GCP_CREDENTIAL_TTL_MS = 60 * 60 * 1000

# GCP credentials check timeout - 5 seconds
GCP_CREDENTIALS_CHECK_TIMEOUT_MS = 5_000

# AWS/GCP auth refresh timeout - 3 minutes
AUTH_REFRESH_TIMEOUT_MS = 3 * 60 * 1000

# OTel headers debounce - 29 minutes
DEFAULT_OTEL_HEADERS_DEBOUNCE_MS = 29 * 60 * 1000


class ApiKeySource(str, Enum):
    """Possible sources for API keys."""
    ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
    API_KEY_HELPER = "apiKeyHelper"
    LOGIN_MANAGED_KEY = "/login managed key"
    NONE = "none"


class AuthTokenSource(str, Enum):
    """Possible sources for auth tokens."""
    ANTHROPIC_AUTH_TOKEN = "ANTHROPIC_AUTH_TOKEN"
    CLAUDE_CODE_OAUTH_TOKEN = "CLAUDE_CODE_OAUTH_TOKEN"
    CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR = "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR"
    CCR_OAUTH_TOKEN_FILE = "CCR_OAUTH_TOKEN_FILE"
    API_KEY_HELPER = "apiKeyHelper"
    CLAUDE_AI = "claude.ai"
    NONE = "none"


@dataclass
class UserAccountInfo:
    """Information about the user's account."""
    subscription: str | None = None
    token_source: str | None = None
    api_key_source: str | None = None
    organization: str | None = None
    email: str | None = None


@dataclass
class OrgValidationResult:
    """Result of org validation."""
    valid: bool
    message: str | None = None


@dataclass
class AwsCredentials:
    """AWS credentials from credential export."""
    access_key_id: str
    secret_access_key: str
    session_token: str


# ============================================================================
# Environment and mode helpers
# ============================================================================


def _is_env_truthy(value: str | None) -> bool:
    """Check if an environment variable is set to a truthy value."""
    if not value:
        return False
    return value.lower() in ("true", "1", "yes")


def _is_bare_mode() -> bool:
    """Check if running in bare mode (API-key-only)."""
    return _is_env_truthy(os.environ.get("CLAUDE_CODE_BARE"))


def _is_managed_oauth_context() -> bool:
    """Check if running in a managed OAuth context (CCR or Claude Desktop).

    These contexts should never fall back to user's ~/.claude/settings.json API-key config.
    """
    return (
        _is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE"))
        or os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "claude-desktop"
    )


def _is_running_on_homespace() -> bool:
    """Check if running on homespace."""
    # TODO: Implement proper homespace detection
    return False


def _is_non_interactive_session() -> bool:
    """Check if this is a non-interactive session."""
    return _is_env_truthy(os.environ.get("CLAUDE_CODE_NON_INTERACTIVE"))


def _prefer_third_party_authentication() -> bool:
    """Check if third-party authentication is preferred."""
    return _is_env_truthy(os.environ.get("CLAUDE_CODE_PREFER_THIRD_PARTY_AUTH"))


def _get_claude_config_home_dir() -> str:
    """Get the Claude config home directory."""
    config_home = os.environ.get("CLAUDE_CONFIG_HOME")
    if config_home:
        return config_home
    home = os.path.expanduser("~")
    return os.path.join(home, ".claude")


# ============================================================================
# Settings helpers
# ============================================================================


def _get_settings() -> dict[str, Any]:
    """Get merged settings (deprecated)."""
    # TODO: Implement proper settings loading
    return {}


def _get_settings_for_source(source: str) -> dict[str, Any] | None:
    """Get settings for a specific source."""
    # TODO: Implement proper settings loading
    return None


def _get_global_config() -> dict[str, Any]:
    """Get global config."""
    # TODO: Implement proper config loading
    return {}


def _save_global_config(updater: Any) -> None:
    """Save global config with updater function."""
    # TODO: Implement proper config saving
    pass


def _check_has_trust_dialog_accepted() -> bool:
    """Check if trust dialog has been accepted."""
    # TODO: Implement proper trust check
    return True


# ============================================================================
# OAuth token management
# ============================================================================


# Cache for OAuth tokens
_oauth_tokens_cache: dict[str, Any] | None = None
_oauth_tokens_cache_timestamp: float = 0
_last_credentials_mtime_ms: float = 0

# In-flight promise for token refresh deduplication
_pending_refresh_check: Promise | None = None

# Pending 401 handlers for deduplication
_pending_401_handlers: dict[str, Promise[bool]] = {}

# Type alias for Promise-like objects
Promise = Any


def _get_secure_storage_data() -> dict[str, Any]:
    """Get data from secure storage."""
    # TODO: Implement proper secure storage access
    return {}


def _should_use_claude_ai_auth(scopes: list[str] | None) -> bool:
    """Check if should use Claude.ai auth based on scopes."""
    if not scopes:
        return False
    return " CLAUDE_AI_PROFILE_SCOPE" in scopes or any(
        s.startswith("https://claude.ai/auth/") for s in scopes
    )


def _is_oauth_token_expired(expires_at: float | None) -> bool:
    """Check if an OAuth token is expired."""
    if expires_at is None:
        return False
    return time.time() >= expires_at


def _is_subscription_type_consumer(plan: str | None) -> bool:
    """Check if subscription type is a consumer plan."""
    return plan in ("max", "pro")


def get_claude_ai_oauth_tokens() -> dict[str, Any] | None:
    """Get Claude.ai OAuth tokens from secure storage.

    Returns tokens cached in memory, or reads from secure storage if cache is stale.
    In bare mode, returns None (API-key-only).
    """
    global _oauth_tokens_cache, _oauth_tokens_cache_timestamp

    if _is_bare_mode():
        return None

    # Check for force-set OAuth token from environment variable
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if oauth_token:
        return {
            "accessToken": oauth_token,
            "refreshToken": None,
            "expiresAt": None,
            "scopes": ["user:inference"],
            "subscriptionType": None,
            "rateLimitTier": None,
        }

    # Check for OAuth token from file descriptor
    oauth_token_fd = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR")
    if oauth_token_fd:
        return {
            "accessToken": oauth_token_fd,
            "refreshToken": None,
            "expiresAt": None,
            "scopes": ["user:inference"],
            "subscriptionType": None,
            "rateLimitTier": None,
        }

    # Use cached value if fresh (30 second TTL for keychain reads)
    cache_ttl_ms = 30 * 1000
    if (
        _oauth_tokens_cache is not None
        and (time.time() * 1000 - _oauth_tokens_cache_timestamp) < cache_ttl_ms
    ):
        return _oauth_tokens_cache

    try:
        storage_data = _get_secure_storage_data()
        oauth_data = storage_data.get("claudeAiOauth")

        if not oauth_data or not oauth_data.get("accessToken"):
            return None

        # Update cache
        _oauth_tokens_cache = oauth_data
        _oauth_tokens_cache_timestamp = time.time() * 1000
        return oauth_data
    except Exception:
        return _oauth_tokens_cache


async def get_claude_ai_oauth_tokens_async() -> dict[str, Any] | None:
    """Async version of get_claude_ai_oauth_tokens.

    Reads from secure storage asynchronously to avoid blocking.
    """
    if _is_bare_mode():
        return None

    # Env var and FD tokens are sync and don't hit keychain
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR"):
        return get_claude_ai_oauth_tokens()

    try:
        storage_data = await _get_secure_storage_data_async()
        oauth_data = storage_data.get("claudeAiOauth")
        if not oauth_data or not oauth_data.get("accessToken"):
            return None
        return oauth_data
    except Exception:
        return get_claude_ai_oauth_tokens()


async def _get_secure_storage_data_async() -> dict[str, Any]:
    """Get secure storage data asynchronously."""
    # TODO: Implement proper async secure storage access
    return {}


def clear_oauth_token_cache() -> None:
    """Clear all OAuth token caches.

    Call this on 401 errors to ensure the next token read comes from
    secure storage, not stale in-memory caches.
    """
    global _oauth_tokens_cache, _oauth_tokens_cache_timestamp
    _oauth_tokens_cache = None
    _oauth_tokens_cache_timestamp = 0
    # Also clear keychain cache
    _clear_keychain_cache()


def _clear_keychain_cache() -> None:
    """Clear keychain cache."""
    pass


def save_oauth_tokens_if_needed(tokens: dict[str, Any]) -> dict[str, bool | str]:
    """Save OAuth tokens to secure storage if needed.

    Returns a dict with 'success' boolean and optional 'warning' message.
    """
    scopes = tokens.get("scopes", [])
    if not _should_use_claude_ai_auth(scopes):
        return {"success": True}

    # Skip saving inference-only tokens (from env vars)
    if not tokens.get("refreshToken") or not tokens.get("expiresAt"):
        return {"success": True}

    try:
        storage_data = _get_secure_storage_data()
        existing_oauth = storage_data.get("claudeAiOauth")

        storage_data["claudeAiOauth"] = {
            "accessToken": tokens["accessToken"],
            "refreshToken": tokens["refreshToken"],
            "expiresAt": tokens["expiresAt"],
            "scopes": scopes,
            # Fall back to existing subscription type on transient failures
            "subscriptionType": tokens.get("subscriptionType") or existing_oauth.get("subscriptionType"),
            "rateLimitTier": tokens.get("rateLimitTier") or existing_oauth.get("rateLimitTier"),
        }

        # TODO: Save to secure storage
        # _save_secure_storage_data(storage_data)

        # Clear caches
        clear_oauth_token_cache()
        _clear_betas_caches()
        _clear_tool_schema_cache()

        return {"success": True}
    except Exception as e:
        return {"success": False, "warning": str(e)}


def _clear_betas_caches() -> None:
    """Clear betas caches."""
    pass


def _clear_tool_schema_cache() -> None:
    """Clear tool schema cache."""
    pass


async def handle_oauth_401_error(failed_access_token: str) -> bool:
    """Handle a 401 "OAuth token has expired" error from the API.

    Forces a token refresh when the server says the token is expired,
    even if our local expiration check disagrees.

    Args:
        failed_access_token: The access token that was rejected with 401

    Returns:
        True if we now have a valid token, False otherwise
    """
    global _pending_401_handlers

    # Deduplicate concurrent calls with the same failed token
    if failed_access_token in _pending_401_handlers:
        return await _pending_401_handlers[failed_access_token]

    async def handle():
        try:
            return await _handle_oauth_401_error_impl(failed_access_token)
        finally:
            _pending_401_handlers.pop(failed_access_token, None)

    _pending_401_handlers[failed_access_token] = handle()
    return await handle()


async def _handle_oauth_401_error_impl(failed_access_token: str) -> bool:
    """Implementation of handle_oauth_401_error."""
    # Clear caches and re-read from keychain
    clear_oauth_token_cache()
    current_tokens = await get_claude_ai_oauth_tokens_async()

    if not current_tokens or not current_tokens.get("refreshToken"):
        return False

    # If keychain has a different token, another tab already refreshed - use it
    if current_tokens.get("accessToken") != failed_access_token:
        return True

    # Same token that failed - force refresh
    return await check_and_refresh_oauth_token_if_needed(force=True)


async def check_and_refresh_oauth_token_if_needed(
    retry_count: int = 0,
    force: bool = False,
) -> bool:
    """Check if OAuth token needs refresh and refresh if needed.

    Args:
        retry_count: Current retry attempt number
        force: If True, skip local expiration check and force refresh

    Returns:
        True if token was refreshed successfully, False otherwise
    """
    global _pending_refresh_check

    MAX_RETRIES = 5

    # Deduplicate concurrent non-retry, non-force calls
    if retry_count == 0 and not force and _pending_refresh_check:
        return await _pending_refresh_check

    async def do_refresh():
        return await _check_and_refresh_oauth_token_impl(retry_count, force)

    if retry_count == 0 and not force:
        _pending_refresh_check = do_refresh()
        try:
            return await _pending_refresh_check
        finally:
            _pending_refresh_check = None

    return await do_refresh()


async def _check_and_refresh_oauth_token_impl(
    retry_count: int,
    force: bool,
) -> bool:
    """Implementation of check_and_refresh_oauth_token_if_needed."""
    MAX_RETRIES = 5

    # Invalidate cache if disk changed (cross-process staleness)
    await _invalidate_oauth_cache_if_disk_changed()

    # First check if token is expired with cached value
    tokens = get_claude_ai_oauth_tokens()
    if not force:
        if not tokens or not tokens.get("refreshToken"):
            return False
        if not _is_oauth_token_expired(tokens.get("expiresAt")):
            return False

    if not tokens or not tokens.get("refreshToken"):
        return False

    scopes = tokens.get("scopes", [])
    if not _should_use_claude_ai_auth(scopes):
        return False

    # Re-read tokens async to check if they're still expired
    get_claude_ai_oauth_tokens.cache_clear()
    _clear_keychain_cache()
    fresh_tokens = await get_claude_ai_oauth_tokens_async()
    if not fresh_tokens or not fresh_tokens.get("refreshToken"):
        return False
    if not _is_oauth_token_expired(fresh_tokens.get("expiresAt")):
        return False

    # Tokens are still expired, try to acquire lock and refresh
    claude_dir = _get_claude_config_home_dir()
    os.makedirs(claude_dir, exist_ok=True)

    # TODO: Implement proper lockfile
    # try:
    #     release = await lockfile.lock(claude_dir)
    # except as err:
    #     if err.code == 'ELOCKED' and retry_count < MAX_RETRIES:
    #         await sleep(1000 + random.random() * 1000)
    #         return await check_and_refresh_oauth_token_if_needed(retry_count + 1, force)
    #     return False

    try:
        # Check one more time after acquiring lock
        get_claude_ai_oauth_tokens.cache_clear()
        _clear_keychain_cache()
        locked_tokens = await get_claude_ai_oauth_tokens_async()
        if not locked_tokens or not locked_tokens.get("refreshToken"):
            return False
        if not _is_oauth_token_expired(locked_tokens.get("expiresAt")):
            return False

        # Refresh the token
        refreshed_tokens = await _refresh_oauth_token(locked_tokens["refreshToken"], scopes)
        if refreshed_tokens:
            save_oauth_tokens_if_needed(refreshed_tokens)

        # Clear caches after refreshing
        get_claude_ai_oauth_tokens.cache_clear()
        _clear_keychain_cache()
        return True
    except Exception:
        # On error, check if we have valid tokens now
        get_claude_ai_oauth_tokens.cache_clear()
        _clear_keychain_cache()
        current_tokens = await get_claude_ai_oauth_tokens_async()
        if current_tokens and not _is_oauth_token_expired(current_tokens.get("expiresAt")):
            return True
        return False


async def _invalidate_oauth_cache_if_disk_changed() -> None:
    """Invalidate OAuth cache if credentials file was modified on disk."""
    global _last_credentials_mtime_ms

    credentials_path = os.path.join(
        _get_claude_config_home_dir(),
        ".credentials.json"
    )
    try:
        stat = os.stat(credentials_path)
        if stat.st_mtime_ns != _last_credentials_mtime_ms:
            _last_credentials_mtime_ms = stat.st_mtime_ns
            clear_oauth_token_cache()
    except FileNotFoundError:
        # File doesn't exist, just clear memoize cache
        get_claude_ai_oauth_tokens.cache_clear()


async def _refresh_oauth_token(
    refresh_token: str,
    scopes: list[str],
) -> dict[str, Any] | None:
    """Refresh OAuth token using the refresh token.

    Args:
        refresh_token: The refresh token
        scopes: Current token scopes

    Returns:
        New tokens if refresh was successful, None otherwise
    """
    # TODO: Implement proper OAuth token refresh
    # This would call the OAuth refresh endpoint
    return None


# ============================================================================
# API key helpers
# ============================================================================


# Cache for API key helper
_api_key_helper_cache: dict[str, str] | None = None
_api_key_helper_cache_timestamp: float = 0
_api_key_helper_inflight: Promise | None = None
_api_key_helper_epoch: int = 0


def get_configured_api_key_helper() -> str | None:
    """Get the configured apiKeyHelper from settings.

    In bare mode, only the --settings flag source is consulted.
    """
    if _is_bare_mode():
        flag_settings = _get_settings_for_source("flagSettings")
        return flag_settings.get("apiKeyHelper") if flag_settings else None

    settings = _get_settings()
    return settings.get("apiKeyHelper")


def _is_api_key_helper_from_project_or_local_settings() -> bool:
    """Check if the configured apiKeyHelper comes from project or local settings."""
    api_key_helper = get_configured_api_key_helper()
    if not api_key_helper:
        return False

    project_settings = _get_settings_for_source("projectSettings")
    local_settings = _get_settings_for_source("localSettings")
    return (
        (project_settings or {}).get("apiKeyHelper") == api_key_helper
        or (local_settings or {}).get("apiKeyHelper") == api_key_helper
    )


def calculate_api_key_helper_ttl() -> int:
    """Calculate TTL in milliseconds for the API key helper cache.

    Uses CLAUDE_CODE_API_KEY_HELPER_TTL_MS env var if set and valid,
    otherwise defaults to 5 minutes.
    """
    env_ttl = os.environ.get("CLAUDE_CODE_API_KEY_HELPER_TTL_MS")
    if env_ttl:
        try:
            parsed = int(env_ttl)
            if parsed >= 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_API_KEY_HELPER_TTL_MS


def get_api_key_helper_elapsed_ms() -> int:
    """Get milliseconds since the API key helper fetch started."""
    if _api_key_helper_inflight and hasattr(_api_key_helper_inflight, "started_at"):
        return int((time.time() * 1000) - _api_key_helper_inflight.started_at)
    return 0


async def get_api_key_from_api_key_helper(
    is_non_interactive_session: bool,
) -> str | None:
    """Get API key from the configured apiKeyHelper command.

    Uses SWR (stale-while-revalidate) caching:
    - Returns cached value if fresh
    - Returns stale value while refreshing in background
    - Deduplicates concurrent calls
    """
    global _api_key_helper_cache, _api_key_helper_cache_timestamp, _api_key_helper_inflight

    api_key_helper = get_configured_api_key_helper()
    if not api_key_helper:
        return None

    ttl = calculate_api_key_helper_ttl()
    now_ms = time.time() * 1000

    if _api_key_helper_cache:
        if now_ms - _api_key_helper_cache_timestamp < ttl:
            return _api_key_helper_cache["value"]

        # Stale - return stale value now, refresh in background
        if not _api_key_helper_inflight:
            _api_key_helper_inflight = _run_and_cache_api_key_helper(
                is_non_interactive_session,
                is_cold=False,
                epoch=_api_key_helper_epoch,
            )
        return _api_key_helper_cache["value"]

    # Cold cache - deduplicate concurrent calls
    if _api_key_helper_inflight:
        return await _api_key_helper_inflight

    _api_key_helper_inflight = _run_and_cache_api_key_helper(
        is_non_interactive_session,
        is_cold=True,
        epoch=_api_key_helper_epoch,
    )
    return await _api_key_helper_inflight


async def _run_and_cache_api_key_helper(
    is_non_interactive_session: bool,
    is_cold: bool,
    epoch: int,
) -> str | None:
    """Execute apiKeyHelper and cache the result."""
    global _api_key_helper_cache, _api_key_helper_cache_timestamp, _api_key_helper_epoch, _api_key_helper_inflight

    try:
        value = await _execute_api_key_helper(is_non_interactive_session)
        if epoch != _api_key_helper_epoch:
            return value
        if value is not None:
            _api_key_helper_cache = {"value": value, "timestamp": time.time() * 1000}
        return value
    except Exception as e:
        if epoch != _api_key_helper_epoch:
            return " "
        # SWR path: keep serving stale value on transient failures
        if not is_cold and _api_key_helper_cache and _api_key_helper_cache["value"] != " ":
            _api_key_helper_cache["timestamp"] = time.time() * 1000
            return _api_key_helper_cache["value"]
        # Cold cache or prior error - cache ' ' sentinel
        _api_key_helper_cache = {"value": " ", "timestamp": time.time() * 1000}
        return " "
    finally:
        if epoch == _api_key_helper_epoch:
            _api_key_helper_inflight = None


async def _execute_api_key_helper(
    is_non_interactive_session: bool,
) -> str | None:
    """Execute the configured apiKeyHelper command."""
    api_key_helper = get_configured_api_key_helper()
    if not api_key_helper:
        return None

    # Security: Check trust for project/local settings
    if _is_api_key_helper_from_project_or_local_settings():
        if not _check_has_trust_dialog_accepted() and not is_non_interactive_session:
            return None

    # Execute the helper command
    import asyncio
    try:
        proc = await asyncio.create_subprocess_shell(
            api_key_helper,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0:
            why = f"exited {proc.returncode}"
            stderr_str = stderr.decode().strip() if stderr else ""
            raise RuntimeError(stderr_str or why)
        result = stdout.decode().strip()
        if not result:
            raise RuntimeError("did not return a value")
        return result
    except asyncio.TimeoutError:
        raise RuntimeError("timed out")


def get_api_key_from_api_key_helper_cached() -> str | None:
    """Sync cache reader - returns last fetched apiKeyHelper value without executing.

    Returns stale values to match SWR semantics.
    Returns None only if the async fetch hasn't completed yet.
    """
    return _api_key_helper_cache["value"] if _api_key_helper_cache else None


def clear_api_key_helper_cache() -> None:
    """Clear the API key helper cache and bump epoch."""
    global _api_key_helper_epoch, _api_key_helper_cache, _api_key_helper_inflight
    _api_key_helper_epoch += 1
    _api_key_helper_cache = None
    _api_key_helper_inflight = None


def _is_valid_api_key(api_key: str) -> bool:
    """Validate API key format.

    Only allows alphanumeric characters, dashes, and underscores.
    """
    return bool(re.match(r"^[a-zA-Z0-9-_]+$", api_key))


def save_api_key(api_key: str) -> None:
    """Save an API key to keychain (macOS) or config.

    Args:
        api_key: The API key to save

    Raises:
        ValueError: If the API key format is invalid
    """
    if not _is_valid_api_key(api_key):
        raise ValueError(
            "Invalid API key format. API key must contain only "
            "alphanumeric characters, dashes, and underscores."
        )

    # TODO: Implement proper keychain/config saving
    # This would save to macOS keychain on Darwin or config on other platforms

    # Update global config
    _save_global_config(lambda current: {
        **current,
        "primaryApiKey": api_key,
        "customApiKeyResponses": {
            **current.get("customApiKeyResponses", {}),
            "approved": [api_key],
            "rejected": current.get("customApiKeyResponses", {}).get("rejected", []),
        },
    })

    # Clear memo cache
    clear_api_key_helper_cache()


def remove_api_key() -> None:
    """Remove the saved API key from keychain and config."""
    # TODO: Implement proper keychain removal
    _save_global_config(lambda current: {
        **current,
        "primaryApiKey": None,
    })
    clear_api_key_helper_cache()


def is_custom_api_key_approved(api_key: str) -> bool:
    """Check if a custom API key has been approved."""
    config = _get_global_config()
    approved = config.get("customApiKeyResponses", {}).get("approved", [])
    return api_key in approved


# ============================================================================
# Auth state functions
# ============================================================================


def is_anthropic_auth_enabled() -> bool:
    """Whether direct 1P (Anthropic) auth is enabled.

    Returns False in bare mode or when using 3rd party services.
    """
    # --bare: API-key-only, never OAuth
    if _is_bare_mode():
        return False

    # SSH remote with ANTHROPIC_UNIX_SOCKET tunnels API calls through local proxy
    if os.environ.get("ANTHROPIC_UNIX_SOCKET"):
        return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))

    # Check for 3rd party services
    is_3p = (
        _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_BEDROCK"))
        or _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_VERTEX"))
        or _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_FOUNDRY"))
    )

    # Check for external API key sources
    settings = _get_settings()
    api_key_helper = settings.get("apiKeyHelper")
    has_external_auth_token = bool(
        os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or api_key_helper
        or os.environ.get("CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR")
    )

    # Get API key source
    api_key_source = get_anthropic_api_key_with_source(
        skip_retrieving_key_from_api_key_helper=True
    )["source"]
    has_external_api_key = api_key_source in (
        ApiKeySource.ANTHROPIC_API_KEY.value,
        ApiKeySource.API_KEY_HELPER.value,
    )

    # Disable Anthropic auth if:
    # 1. Using 3rd party services
    # 2. User has an external API key (regardless of proxy)
    # 3. User has an external auth token (regardless of proxy)
    should_disable = (
        is_3p
        or (has_external_auth_token and not _is_managed_oauth_context())
        or (has_external_api_key and not _is_managed_oauth_context())
    )

    return not should_disable


def get_auth_token_source() -> dict[Literal["source", "has_token"], Any]:
    """Get where the auth token is being sourced from.

    Returns:
        Dict with 'source' (AuthTokenSource value) and 'has_token' (bool)
    """
    # --bare: API-key-only
    if _is_bare_mode():
        if get_configured_api_key_helper():
            return {"source": AuthTokenSource.API_KEY_HELPER.value, "has_token": True}
        return {"source": AuthTokenSource.NONE.value, "has_token": False}

    # Check for ANTHROPIC_AUTH_TOKEN
    if os.environ.get("ANTHROPIC_AUTH_TOKEN") and not _is_managed_oauth_context():
        return {"source": AuthTokenSource.ANTHROPIC_AUTH_TOKEN.value, "has_token": True}

    # Check for CLAUDE_CODE_OAUTH_TOKEN
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return {"source": AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN.value, "has_token": True}

    # Check for OAuth token from file descriptor
    oauth_token_fd = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR")
    if oauth_token_fd:
        if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR"):
            return {
                "source": AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR.value,
                "has_token": True,
            }
        return {"source": AuthTokenSource.CCR_OAUTH_TOKEN_FILE.value, "has_token": True}

    # Check for apiKeyHelper
    api_key_helper = get_configured_api_key_helper()
    if api_key_helper and not _is_managed_oauth_context():
        return {"source": AuthTokenSource.API_KEY_HELPER.value, "has_token": True}

    # Check for Claude.ai OAuth tokens
    oauth_tokens = get_claude_ai_oauth_tokens()
    if _should_use_claude_ai_auth(oauth_tokens.get("scopes") if oauth_tokens else None) and oauth_tokens.get("accessToken"):
        return {"source": AuthTokenSource.CLAUDE_AI.value, "has_token": True}

    return {"source": AuthTokenSource.NONE.value, "has_token": False}


def get_anthropic_api_key() -> str | None:
    """Get the Anthropic API key from available sources.

    Returns:
        The API key if found, None otherwise
    """
    return get_anthropic_api_key_with_source()["key"]


def has_anthropic_api_key_auth() -> bool:
    """Check if API key auth is available."""
    result = get_anthropic_api_key_with_source(skip_retrieving_key_from_api_key_helper=True)
    return result["key"] is not None and result["source"] != ApiKeySource.NONE.value


def get_anthropic_api_key_with_source(
    skip_retrieving_key_from_api_key_helper: bool = False,
) -> dict[Literal["key", "source"], Any]:
    """Get the Anthropic API key and its source.

    Args:
        skip_retrieving_key_from_api_key_helper: If True, don't execute the helper

    Returns:
        Dict with 'key' (str or None) and 'source' (ApiKeySource value)
    """
    # --bare: hermetic auth, only ANTHROPIC_API_KEY or apiKeyHelper from --settings
    if _is_bare_mode():
        api_key_env = os.environ.get("ANTHROPIC_API_KEY")
        if api_key_env:
            return {"key": api_key_env, "source": ApiKeySource.ANTHROPIC_API_KEY.value}

        configured_helper = get_configured_api_key_helper()
        if configured_helper:
            return {
                "key": None if skip_retrieving_key_from_api_key_helper else get_api_key_from_api_key_helper_cached(),
                "source": ApiKeySource.API_KEY_HELPER.value,
            }
        return {"key": None, "source": ApiKeySource.NONE.value}

    # On homespace, don't use ANTHROPIC_API_KEY
    api_key_env = None if _is_running_on_homespace() else os.environ.get("ANTHROPIC_API_KEY")

    # Check for direct env var when using --print with third-party auth
    if _prefer_third_party_authentication() and api_key_env:
        return {"key": api_key_env, "source": ApiKeySource.ANTHROPIC_API_KEY.value}

    # In CI or test mode
    if _is_env_truthy(os.environ.get("CI")) or os.environ.get("NODE_ENV") == "test":
        # Check for API key from file descriptor first
        api_key_from_fd = os.environ.get("CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR")
        if api_key_from_fd:
            return {"key": api_key_from_fd, "source": ApiKeySource.ANTHROPIC_API_KEY.value}

        if not api_key_env and not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN env var is required"
            )

        if api_key_env:
            return {"key": api_key_env, "source": ApiKeySource.ANTHROPIC_API_KEY.value}

        return {"key": None, "source": ApiKeySource.NONE.value}

    # Check for approved ANTHROPIC_API_KEY
    if api_key_env:
        config = _get_global_config()
        approved = config.get("customApiKeyResponses", {}).get("approved", [])
        if api_key_env in approved:
            return {"key": api_key_env, "source": ApiKeySource.ANTHROPIC_API_KEY.value}

    # Check for API key from file descriptor
    api_key_from_fd = os.environ.get("CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR")
    if api_key_from_fd:
        return {"key": api_key_from_fd, "source": ApiKeySource.ANTHROPIC_API_KEY.value}

    # Check for apiKeyHelper
    api_key_helper_command = get_configured_api_key_helper()
    if api_key_helper_command:
        if skip_retrieving_key_from_api_key_helper:
            return {"key": None, "source": ApiKeySource.API_KEY_HELPER.value}
        return {
            "key": get_api_key_from_api_key_helper_cached(),
            "source": ApiKeySource.API_KEY_HELPER.value,
        }

    # Check config/keychain
    api_key_from_config = _get_api_key_from_config_or_keychain()
    if api_key_from_config:
        return api_key_from_config

    return {"key": None, "source": ApiKeySource.NONE.value}


def _get_api_key_from_config_or_keychain() -> dict[str, Any] | None:
    """Get API key from config or macOS keychain (memoized)."""
    if _is_bare_mode():
        return None

    # TODO: Implement proper keychain reading on macOS
    # This would use the 'security' command on Darwin

    config = _get_global_config()
    primary_api_key = config.get("primaryApiKey")
    if not primary_api_key:
        return None

    return {"key": primary_api_key, "source": ApiKeySource.LOGIN_MANAGED_KEY.value}


# ============================================================================
# Subscription and account state
# ============================================================================


def is_claude_ai_subscriber() -> bool:
    """Check if the user is a Claude.ai subscriber."""
    if not is_anthropic_auth_enabled():
        return False
    oauth_tokens = get_claude_ai_oauth_tokens()
    return _should_use_claude_ai_auth(oauth_tokens.get("scopes") if oauth_tokens else None)


def has_profile_scope() -> bool:
    """Check if the current OAuth token has the user:profile scope.

    Real /login tokens always include this scope. Env-var and file-descriptor
    tokens (service keys) only have 'user:inference' scope.
    """
    oauth_tokens = get_claude_ai_oauth_tokens()
    scopes = oauth_tokens.get("scopes") if oauth_tokens else None
    if not scopes:
        return False
    return "user:profile" in scopes or any(s.startswith("https://claude.ai/auth/") for s in scopes)


def is_1p_api_customer() -> bool:
    """Check if the user is a 1P (direct) API customer.

    1P API customers are users who are NOT:
    1. Claude.ai subscribers (Max, Pro, Enterprise, Team)
    2. Vertex AI users
    3. AWS Bedrock users
    4. Foundry users
    """
    # Exclude Vertex, Bedrock, and Foundry customers
    if (
        _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_BEDROCK"))
        or _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_VERTEX"))
        or _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_FOUNDRY"))
    ):
        return False

    # Exclude Claude.ai subscribers
    if is_claude_ai_subscriber():
        return False

    # Everyone else is an API customer
    return True


def get_subscription_type() -> str | None:
    """Get the subscription type.

    Returns:
        Subscription type string (max, pro, enterprise, team) or None
    """
    oauth_tokens = get_claude_ai_oauth_tokens()
    if not oauth_tokens:
        return None
    return oauth_tokens.get("subscriptionType")


def is_max_subscriber() -> bool:
    """Check if user is a Max subscriber."""
    return get_subscription_type() == "max"


def is_team_subscriber() -> bool:
    """Check if user is a Team subscriber."""
    return get_subscription_type() == "team"


def is_team_premium_subscriber() -> bool:
    """Check if user is a Team premium subscriber (Team + default_claude_max_5x tier)."""
    return get_subscription_type() == "team" and get_rate_limit_tier() == "default_claude_max_5x"


def is_enterprise_subscriber() -> bool:
    """Check if user is an Enterprise subscriber."""
    return get_subscription_type() == "enterprise"


def is_pro_subscriber() -> bool:
    """Check if user is a Pro subscriber."""
    return get_subscription_type() == "pro"


def is_consumer_subscriber() -> bool:
    """Check if user is a consumer subscriber (Max or Pro)."""
    return is_claude_ai_subscriber() and _is_subscription_type_consumer(get_subscription_type())


def get_rate_limit_tier() -> str | None:
    """Get the rate limit tier."""
    if not is_anthropic_auth_enabled():
        return None
    oauth_tokens = get_claude_ai_oauth_tokens()
    if not oauth_tokens:
        return None
    return oauth_tokens.get("rateLimitTier")


def get_subscription_name() -> str:
    """Get the human-readable subscription name."""
    subscription_type = get_subscription_type()

    switch = {
        "enterprise": "Claude Enterprise",
        "team": "Claude Team",
        "max": "Claude Max",
        "pro": "Claude Pro",
    }
    return switch.get(subscription_type, "Claude API") if subscription_type else "Claude API"


def has_opus_access() -> bool:
    """Check if user has Opus model access.

    Returns True for subscribers (Max, Pro, Enterprise, Team) and API users.
    """
    subscription_type = get_subscription_type()
    return subscription_type in ("max", "enterprise", "team", "pro", None)


# ============================================================================
# Account info
# ============================================================================


def get_account_information() -> UserAccountInfo | None:
    """Get information about the user's account.

    Returns:
        UserAccountInfo with subscription, token source, API key source, etc.
    """
    # Only provide account info for first-party Anthropic API
    # TODO: Implement proper API provider detection
    # if get_api_provider() != "firstParty":
    #     return None

    auth_token_source = get_auth_token_source()["source"]
    info = UserAccountInfo()

    if auth_token_source in (
        AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN.value,
        AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR.value,
    ):
        info.token_source = auth_token_source
    elif is_claude_ai_subscriber():
        info.subscription = get_subscription_name()
    else:
        info.token_source = auth_token_source

    api_key_result = get_anthropic_api_key_with_source()
    if api_key_result["key"]:
        info.api_key_source = api_key_result["source"]

    # Get organization and email from OAuth account info
    oauth_account = get_oauth_account_info()
    if oauth_account:
        if auth_token_source == AuthTokenSource.CLAUDE_AI.value or api_key_result["source"] == ApiKeySource.LOGIN_MANAGED_KEY.value:
            if oauth_account.get("organizationName"):
                info.organization = oauth_account["organizationName"]
        if oauth_account.get("emailAddress"):
            info.email = oauth_account["emailAddress"]

    return info


def get_oauth_account_info() -> dict[str, Any] | None:
    """Get OAuth account information when Anthropic auth is enabled.

    Returns None when using external API keys or third-party services.
    """
    if not is_anthropic_auth_enabled():
        return None
    config = _get_global_config()
    return config.get("oauthAccount")


def is_overage_provisioning_allowed() -> bool:
    """Check if overage/extra usage provisioning is allowed.

    Only allowed for Stripe/Apple/Google Play billing types.
    """
    if not is_claude_ai_subscriber():
        return False

    account_info = get_oauth_account_info()
    billing_type = account_info.get("billingType") if account_info else None
    if not billing_type:
        return False

    return billing_type in (
        "stripe_subscription",
        "stripe_subscription_contracted",
        "apple_subscription",
        "google_play_subscription",
    )


# ============================================================================
# Cloud provider auth helpers
# ============================================================================


# Cache for AWS credentials
_aws_credentials_cache: dict[str, AwsCredentials] | None = None
_aws_credentials_cache_timestamp: float = 0


def _get_configured_aws_auth_refresh() -> str | None:
    """Get the configured awsAuthRefresh from settings."""
    settings = _get_settings()
    return settings.get("awsAuthRefresh")


def _get_configured_aws_credential_export() -> str | None:
    """Get the configured awsCredentialExport from settings."""
    settings = _get_settings()
    return settings.get("awsCredentialExport")


def _is_aws_auth_refresh_from_project_settings() -> bool:
    """Check if awsAuthRefresh comes from project settings."""
    aws_auth_refresh = _get_configured_aws_auth_refresh()
    if not aws_auth_refresh:
        return False
    project_settings = _get_settings_for_source("projectSettings")
    local_settings = _get_settings_for_source("localSettings")
    return (
        (project_settings or {}).get("awsAuthRefresh") == aws_auth_refresh
        or (local_settings or {}).get("awsAuthRefresh") == aws_auth_refresh
    )


def _is_aws_credential_export_from_project_settings() -> bool:
    """Check if awsCredentialExport comes from project settings."""
    aws_credential_export = _get_configured_aws_credential_export()
    if not aws_credential_export:
        return False
    project_settings = _get_settings_for_source("projectSettings")
    local_settings = _get_settings_for_source("localSettings")
    return (
        (project_settings or {}).get("awsCredentialExport") == aws_credential_export
        or (local_settings or {}).get("awsCredentialExport") == aws_credential_export
    )


async def _check_sts_caller_identity() -> bool:
    """Check AWS STS caller identity.

    Returns True if credentials are valid.
    """
    # TODO: Implement proper STS caller identity check
    return False


async def _refresh_and_get_aws_credentials_impl() -> AwsCredentials | None:
    """Implementation of refreshAndGetAwsCredentials with TTL caching."""
    global _aws_credentials_cache, _aws_credentials_cache_timestamp

    now_ms = time.time() * 1000
    if (
        _aws_credentials_cache
        and (now_ms - _aws_credentials_cache_timestamp) < DEFAULT_AWS_STS_TTL_MS
    ):
        return _aws_credentials_cache

    # First run auth refresh if needed
    refreshed = await _run_aws_auth_refresh()

    # Get credentials from export
    credentials = await _get_aws_creds_from_credential_export()

    # Clear AWS INI cache if we did any work
    if refreshed or credentials:
        _clear_aws_ini_cache()

    if credentials:
        _aws_credentials_cache = credentials
        _aws_credentials_cache_timestamp = now_ms

    return credentials


@lru_cache(maxsize=1)
def _get_cached_aws_credentials() -> AwsCredentials | None:
    """Cached wrapper for AWS credentials (sync, for use with memoization)."""
    # Note: This is a placeholder. In Python we'd use asyncio to call the async version.
    return None


async def refresh_and_get_aws_credentials() -> AwsCredentials | None:
    """Refresh AWS authentication and get credentials with cache clearing.

    Combines runAwsAuthRefresh, getAwsCredsFromCredentialExport, and clearAwsIniCache.
    """
    return await _refresh_and_get_aws_credentials_impl()


def clear_aws_credentials_cache() -> None:
    """Clear the AWS credentials cache."""
    global _aws_credentials_cache, _aws_credentials_cache_timestamp
    _aws_credentials_cache = None
    _aws_credentials_cache_timestamp = 0


async def _run_aws_auth_refresh() -> bool:
    """Run awsAuthRefresh to perform interactive authentication.

    Returns True if refresh was executed, False if skipped (credentials valid).
    """
    aws_auth_refresh = _get_configured_aws_auth_refresh()
    if not aws_auth_refresh:
        return False

    # SECURITY: Check if from project settings
    if _is_aws_auth_refresh_from_project_settings():
        if not _check_has_trust_dialog_accepted() and not _is_non_interactive_session():
            return False

    try:
        # Check if credentials are already valid
        await _check_sts_caller_identity()
        return False  # Credentials valid, skip refresh
    except Exception:
        return await _refresh_aws_auth(aws_auth_refresh)


async def _refresh_aws_auth(aws_auth_refresh: str) -> bool:
    """Execute the AWS auth refresh command.

    Args:
        aws_auth_refresh: The command to run

    Returns:
        True if command succeeded, False otherwise
    """
    import asyncio

    try:
        proc = await asyncio.create_subprocess_shell(
            aws_auth_refresh,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            timeout=AUTH_REFRESH_TIMEOUT_MS // 1000,
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False


async def _get_aws_creds_from_credential_export() -> AwsCredentials | None:
    """Get AWS credentials from awsCredentialExport.

    Expects JSON output containing AWS credentials.
    """
    aws_credential_export = _get_configured_aws_credential_export()
    if not aws_credential_export:
        return None

    # SECURITY: Check if from project settings
    if _is_aws_credential_export_from_project_settings():
        if not _check_has_trust_dialog_accepted() and not _is_non_interactive_session():
            return None

    try:
        # Check if credentials are already valid
        await _check_sts_caller_identity()
        return None  # Credentials valid, skip export
    except Exception:
        pass

    import asyncio
    try:
        proc = await asyncio.create_subprocess_shell(
            aws_credential_export,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0 or not stdout:
            return None

        import json
        aws_output = json.loads(stdout.decode().strip())

        # Validate AWS STS output structure
        if not _is_valid_aws_sts_output(aws_output):
            return None

        return AwsCredentials(
            access_key_id=aws_output["Credentials"]["AccessKeyId"],
            secret_access_key=aws_output["Credentials"]["SecretAccessKey"],
            session_token=aws_output["Credentials"]["SessionToken"],
        )
    except Exception:
        return None


def _is_valid_aws_sts_output(output: dict[str, Any]) -> bool:
    """Validate AWS STS output structure."""
    if not isinstance(output, dict):
        return False
    credentials = output.get("Credentials")
    if not isinstance(credentials, dict):
        return False
    return all(
        credentials.get(key) is not None
        for key in ("AccessKeyId", "SecretAccessKey", "SessionToken")
    )


def _clear_aws_ini_cache() -> None:
    """Clear AWS INI file cache."""
    pass


def prefetch_aws_credentials_if_safe() -> None:
    """Prefetch AWS credentials only if workspace trust is established.

    This allows starting potentially slow AWS commands early for trusted
    workspaces while maintaining security for untrusted ones.
    """
    aws_auth_refresh = _get_configured_aws_auth_refresh()
    aws_credential_export = _get_configured_aws_credential_export()

    if not aws_auth_refresh and not aws_credential_export:
        return

    if _is_aws_auth_refresh_from_project_settings() or _is_aws_credential_export_from_project_settings():
        if not _check_has_trust_dialog_accepted() and not _is_non_interactive_session():
            return

    # Safe to prefetch
    import asyncio
    asyncio.create_task(refresh_and_get_aws_credentials())


# ============================================================================
# GCP auth helpers
# ============================================================================


# Cache for GCP credentials
_gcp_credentials_cache_timestamp: float = 0


def _get_configured_gcp_auth_refresh() -> str | None:
    """Get the configured gcpAuthRefresh from settings."""
    settings = _get_settings()
    return settings.get("gcpAuthRefresh")


def _is_gcp_auth_refresh_from_project_settings() -> bool:
    """Check if gcpAuthRefresh comes from project settings."""
    gcp_auth_refresh = _get_configured_gcp_auth_refresh()
    if not gcp_auth_refresh:
        return False
    project_settings = _get_settings_for_source("projectSettings")
    local_settings = _get_settings_for_source("localSettings")
    return (
        (project_settings or {}).get("gcpAuthRefresh") == gcp_auth_refresh
        or (local_settings or {}).get("gcpAuthRefresh") == gcp_auth_refresh
    )


async def _check_gcp_credentials_valid() -> bool:
    """Check if GCP credentials are currently valid.

    Uses the same authentication chain that the Vertex SDK uses.
    """
    # TODO: Implement proper GCP credentials check
    # This would use google-auth-library
    return False


async def _run_gcp_auth_refresh() -> bool:
    """Run gcpAuthRefresh to perform interactive authentication.

    Returns True if refresh was executed, False if skipped (credentials valid).
    """
    gcp_auth_refresh = _get_configured_gcp_auth_refresh()
    if not gcp_auth_refresh:
        return False

    # SECURITY: Check if from project settings
    if _is_gcp_auth_refresh_from_project_settings():
        if not _check_has_trust_dialog_accepted() and not _is_non_interactive_session():
            return False

    try:
        is_valid = await _check_gcp_credentials_valid()
        if is_valid:
            return False  # Credentials valid, skip refresh
    except Exception:
        pass

    return await _refresh_gcp_auth(gcp_auth_refresh)


async def _refresh_gcp_auth(gcp_auth_refresh: str) -> bool:
    """Execute the GCP auth refresh command.

    Args:
        gcp_auth_refresh: The command to run

    Returns:
        True if command succeeded, False otherwise
    """
    import asyncio

    try:
        proc = await asyncio.create_subprocess_shell(
            gcp_auth_refresh,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            timeout=AUTH_REFRESH_TIMEOUT_MS // 1000,
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False


async def _refresh_gcp_credentials_if_needed_impl() -> bool:
    """Implementation of refreshGcpCredentialsIfNeeded with TTL caching."""
    global _gcp_credentials_cache_timestamp

    now_ms = time.time() * 1000
    if (now_ms - _gcp_credentials_cache_timestamp) < DEFAULT_GCP_CREDENTIAL_TTL_MS:
        return False

    refreshed = await _run_gcp_auth_refresh()
    if refreshed:
        _gcp_credentials_cache_timestamp = now_ms

    return refreshed


async def refresh_gcp_credentials_if_needed() -> bool:
    """Refresh GCP credentials if needed (memoized with TTL)."""
    return await _refresh_gcp_credentials_if_needed_impl()


def clear_gcp_credentials_cache() -> None:
    """Clear the GCP credentials cache."""
    global _gcp_credentials_cache_timestamp
    _gcp_credentials_cache_timestamp = 0


def prefetch_gcp_credentials_if_safe() -> None:
    """Prefetch GCP credentials only if workspace trust is established.

    This allows starting potentially slow GCP commands early for trusted
    workspaces while maintaining security for untrusted ones.
    """
    gcp_auth_refresh = _get_configured_gcp_auth_refresh()
    if not gcp_auth_refresh:
        return

    if _is_gcp_auth_refresh_from_project_settings():
        if not _check_has_trust_dialog_accepted() and not _is_non_interactive_session():
            return

    # Safe to prefetch
    import asyncio
    asyncio.create_task(refresh_gcp_credentials_if_needed())


# ============================================================================
# OTel headers helper
# ============================================================================


# Cache for OTel headers
_otel_headers_cache: dict[str, str] | None = None
_otel_headers_cache_timestamp: float = 0


def _get_configured_otel_headers_helper() -> str | None:
    """Get the configured otelHeadersHelper from settings."""
    settings = _get_settings()
    return settings.get("otelHeadersHelper")


def _is_otel_headers_helper_from_project_or_local_settings() -> bool:
    """Check if otelHeadersHelper comes from project or local settings."""
    otel_headers_helper = _get_configured_otel_headers_helper()
    if not otel_headers_helper:
        return False
    project_settings = _get_settings_for_source("projectSettings")
    local_settings = _get_settings_for_source("localSettings")
    return (
        (project_settings or {}).get("otelHeadersHelper") == otel_headers_helper
        or (local_settings or {}).get("otelHeadersHelper") == otel_headers_helper
    )


def get_otel_headers_from_helper() -> dict[str, str]:
    """Get OpenTelemetry headers from the configured otelHeadersHelper.

    Returns an empty dict if not configured or if trust is not established.

    Raises:
        RuntimeError: If the helper returns invalid output
    """
    global _otel_headers_cache, _otel_headers_cache_timestamp

    otel_headers_helper = _get_configured_otel_headers_helper()
    if not otel_headers_helper:
        return {}

    # Return cached headers if still valid (debounce)
    debounce_ms_str = os.environ.get("CLAUDE_CODE_OTEL_HEADERS_HELPER_DEBOUNCE_MS")
    debounce_ms = int(debounce_ms_str) if debounce_ms_str else DEFAULT_OTEL_HEADERS_DEBOUNCE_MS

    now_ms = time.time() * 1000
    if _otel_headers_cache and (now_ms - _otel_headers_cache_timestamp) < debounce_ms:
        return _otel_headers_cache

    # Check trust for project/local settings
    if _is_otel_headers_helper_from_project_or_local_settings():
        if not _check_has_trust_dialog_accepted():
            return {}

    import asyncio
    try:
        proc = asyncio.run(asyncio.create_subprocess_shell(
            otel_headers_helper,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        ))
        stdout, stderr = proc.communicate(timeout=30)
        result = stdout.decode().strip() if stdout else ""

        if not result:
            raise RuntimeError("otelHeadersHelper did not return a valid value")

        import json
        headers = json.loads(result)

        if not isinstance(headers, dict) or headers is None:
            raise RuntimeError(
                "otelHeadersHelper must return a JSON object with string key-value pairs"
            )

        # Validate all values are strings
        for key, value in headers.items():
            if not isinstance(value, str):
                raise RuntimeError(
                    f'otelHeadersHelper returned non-string value for key "{key}": {type(value)}'
                )

        # Cache the result
        _otel_headers_cache = headers
        _otel_headers_cache_timestamp = now_ms
        return headers

    except Exception as e:
        raise RuntimeError(
            f"Error getting OpenTelemetry headers from otelHeadersHelper: {e}"
        )


# ============================================================================
# Org validation
# ============================================================================


async def validate_force_login_org() -> OrgValidationResult:
    """Validate that the active OAuth token belongs to the required organization.

    Returns OrgValidationResult with valid=True if org matches or no org is required.
    Returns OrgValidationResult with valid=False and error message if validation fails.

    Fails closed: if forceLoginOrgUUID is set and we cannot determine the
    token's org (network error, missing profile data), validation fails.
    """
    # SSH remote: real auth lives on the local machine
    if os.environ.get("ANTHROPIC_UNIX_SOCKET"):
        return OrgValidationResult(valid=True)

    if not is_anthropic_auth_enabled():
        return OrgValidationResult(valid=True)

    # Get required org from policy settings
    policy_settings = _get_settings_for_source("policySettings")
    required_org_uuid = policy_settings.get("forceLoginOrgUUID") if policy_settings else None
    if not required_org_uuid:
        return OrgValidationResult(valid=True)

    # Ensure the access token is fresh before hitting the profile endpoint
    await check_and_refresh_oauth_token_if_needed()

    tokens = get_claude_ai_oauth_tokens()
    if not tokens:
        return OrgValidationResult(valid=True)

    # Get token source to determine if it's an env var token
    auth_source = get_auth_token_source()["source"]
    is_env_var_token = auth_source in (
        AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN.value,
        AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR.value,
    )

    # Fetch the authoritative org UUID from the profile endpoint
    profile = await _get_oauth_profile_from_oauth_token(tokens.get("accessToken"))
    if not profile:
        # Fail closed - we can't verify the org
        return OrgValidationResult(
            valid=False,
            message=(
                f"Unable to verify organization for the current authentication token.\n"
                f"This machine requires organization {required_org_uuid} but the profile could not be fetched.\n"
                f"This may be a network error, or the token may lack the user:profile scope.\n"
                f"Try again, or obtain a full-scope token via 'claude auth login'."
            ),
        )

    token_org_uuid = profile.get("organization", {}).get("uuid")
    if token_org_uuid == required_org_uuid:
        return OrgValidationResult(valid=True)

    if is_env_var_token:
        env_var_name = (
            AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN.value
            if auth_source == AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN.value
            else AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR.value
        )
        return OrgValidationResult(
            valid=False,
            message=(
                f"The {env_var_name} environment variable provides a token for a\n"
                f"different organization than required by this machine's managed settings.\n\n"
                f"Required organization: {required_org_uuid}\n"
                f"Token organization:   {token_org_uuid}\n\n"
                f"Remove the environment variable or obtain a token for the correct organization."
            ),
        )

    return OrgValidationResult(
        valid=False,
        message=(
            f"Your authentication token belongs to organization {token_org_uuid},\n"
            f"but this machine requires organization {required_org_uuid}.\n\n"
            f"Please log in with the correct organization: claude auth login"
        ),
    )


async def _get_oauth_profile_from_oauth_token(access_token: str) -> dict[str, Any] | None:
    """Fetch the OAuth profile using the access token.

    Args:
        access_token: The OAuth access token

    Returns:
        Profile data if successful, None otherwise
    """
    # TODO: Implement proper profile fetch
    return None
