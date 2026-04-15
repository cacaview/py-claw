"""
SettingsSync service.

Synchronizes settings across sessions with OAuth authentication and
Claude Code backend API integration.

Based on the TypeScript settingsSync implementation.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from py_claw.services.settings_sync.config import (
    get_settings_sync_config,
)

from .types import (
    ConflictResolution,
    SettingsSnapshot,
    SyncDirection,
    SyncResult,
    SyncStatus,
    get_settings_sync_state,
)

# Maximum settings file size (500KB)
MAX_SETTINGS_SIZE_BYTES = 500 * 1024

# Default API endpoints
DEFAULT_SETTINGS_API_URL = "https://settings.claude.ai/api/v1/user-settings"
DEFAULT_SETTINGS_UPLOAD_URL = "https://settings.claude.ai/api/v1/user-settings"

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY_MS = 1000


def _filter_sensitive_keys(settings: dict, exclude_keys: list[str]) -> dict:
    """Filter out sensitive keys from settings."""
    filtered = {}
    for key, value in settings.items():
        if any(excl in key.lower() for excl in exclude_keys):
            continue
        filtered[key] = value
    return filtered


def _calculate_checksum(settings: dict) -> str:
    """Calculate SHA-256 checksum of settings."""
    json_str = json.dumps(settings, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(json_str.encode()).hexdigest()


def _is_settings_too_large(settings: dict) -> bool:
    """Check if settings exceed the maximum size limit."""
    json_str = json.dumps(settings, sort_keys=True)
    return len(json_str.encode()) > MAX_SETTINGS_SIZE_BYTES


def _get_oauth_token() -> str | None:
    """Get OAuth access token for settings sync.

    Returns:
        OAuth access token if available, None otherwise
    """
    try:
        from py_claw.services.auth.auth import get_claude_ai_oauth_tokens

        tokens = get_claude_ai_oauth_tokens()
        if tokens and tokens.get("accessToken"):
            return tokens["accessToken"]
    except ImportError:
        pass
    return None


async def _check_and_refresh_oauth_token() -> bool:
    """Check and refresh OAuth token if needed.

    Returns:
        True if token is valid after check, False otherwise
    """
    try:
        from py_claw.services.auth.auth import check_and_refresh_oauth_token_if_needed

        return await check_and_refresh_oauth_token_if_needed()
    except ImportError:
        return False


def _invalidate_settings_cache() -> None:
    """Invalidate settings caches after sync.

    Calls the appropriate cache invalidation functions to ensure
    fresh settings are loaded after sync.
    """
    try:
        from py_claw.services.auth.auth import clear_oauth_token_cache
        clear_oauth_token_cache()
    except ImportError:
        pass

    # Clear settings cache
    try:
        from py_claw.settings.loader import clear_settings_cache
        clear_settings_cache()
    except ImportError:
        pass


def _get_retry_delay(retry_count: int) -> float:
    """Calculate exponential backoff delay for retries.

    Args:
        retry_count: Current retry attempt (0-based)

    Returns:
        Delay in seconds before next retry
    """
    # Exponential backoff: 1s, 2s, 4s with jitter
    import random
    base_delay = RETRY_BASE_DELAY_MS * (2 ** retry_count)
    jitter = random.uniform(0, 0.5) * base_delay
    return (base_delay + jitter) / 1000
    """Merge local and remote settings based on strategy."""
    if strategy == ConflictResolution.KEEP_LOCAL:
        return local
    elif strategy == ConflictResolution.KEEP_REMOTE:
        return remote
    else:  # MERGE
        merged = dict(remote)
        for key, value in local.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(value, dict) and isinstance(merged[key], dict):
                merged[key] = _merge_settings(value, merged[key], ConflictResolution.MERGE)
        return merged


async def sync_settings(
    direction: SyncDirection = SyncDirection.BIDIRECTIONAL,
    settings: dict | None = None,
) -> SyncResult:
    """Synchronize settings.

    Args:
        direction: Sync direction
        settings: Current local settings (if None, loads from default location)

    Returns:
        SyncResult with sync operation details
    """
    config = get_settings_sync_config()
    state = get_settings_sync_state()
    start_time = time.time()

    if not config.enabled:
        return SyncResult(
            success=False,
            direction=direction,
            synced_keys=[],
            message="Settings sync is not enabled",
            duration_seconds=time.time() - start_time,
            error="disabled",
        )

    try:
        # Load local settings if not provided
        if settings is None:
            settings = _load_local_settings()

        # Filter sensitive keys
        filtered_settings = _filter_sensitive_keys(settings, config.exclude_keys or [])

        # Create local snapshot
        local_snapshot = SettingsSnapshot(
            settings=filtered_settings,
            timestamp=datetime.now(timezone.utc),
            source="local",
        )
        state.local_snapshot = local_snapshot

        # Determine sync target
        if config.sync_target:
            if config.sync_target.startswith("file://"):
                file_path = config.sync_target[7:]
                return await _sync_to_file(
                    file_path, filtered_settings, direction, start_time
                )
            elif config.sync_target.startswith("http://") or config.sync_target.startswith("https://"):
                return await _sync_to_server(
                    config.sync_target, filtered_settings, direction, start_time
                )

        # No sync target configured - simulate success
        state.record_sync(direction, True)

        return SyncResult(
            success=True,
            direction=direction,
            synced_keys=list(filtered_settings.keys()),
            message="Settings synced successfully (no target configured)",
            duration_seconds=time.time() - start_time,
        )

    except Exception as e:
        state.record_sync(direction, False)
        return SyncResult(
            success=False,
            direction=direction,
            synced_keys=[],
            message=f"Settings sync failed: {e}",
            duration_seconds=time.time() - start_time,
            error=str(e),
        )


async def _sync_to_file(
    file_path: str,
    settings: dict,
    direction: SyncDirection,
    start_time: float,
) -> SyncResult:
    """Sync settings to a local file."""
    state = get_settings_sync_state()
    path = Path(file_path)

    try:
        # Read existing remote settings
        remote_settings = {}
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                remote_settings = json.loads(content)
            except (json.JSONDecodeError, IOError):
                pass

        # Load local settings
        local_settings = _load_local_settings()
        config = get_settings_sync_config()

        # Merge based on strategy
        merged = _merge_settings(
            local_settings,
            remote_settings,
            ConflictResolution(config.conflict_strategy),
        )

        # Write merged settings
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")

        state.record_sync(direction, True)

        synced_keys = list(merged.keys())

        return SyncResult(
            success=True,
            direction=direction,
            synced_keys=synced_keys,
            message=f"Settings synced to {file_path}",
            duration_seconds=time.time() - start_time,
        )

    except Exception as e:
        state.record_sync(direction, False)
        return SyncResult(
            success=False,
            direction=direction,
            synced_keys=[],
            message=f"Failed to sync to file: {e}",
            duration_seconds=time.time() - start_time,
            error=str(e),
        )


async def _sync_to_server(
    server_url: str,
    settings: dict,
    direction: SyncDirection,
    start_time: float,
) -> SyncResult:
    """Sync settings to a remote server with OAuth and retry logic."""
    state = get_settings_sync_state()

    # Check if settings are too large
    if _is_settings_too_large(settings):
        return SyncResult(
            success=False,
            direction=direction,
            synced_keys=[],
            message=f"Settings too large (max {MAX_SETTINGS_SIZE_BYTES} bytes)",
            duration_seconds=time.time() - start_time,
            error="settings_too_large",
        )

    # Calculate checksum
    checksum = _calculate_checksum(settings)

    # Get OAuth token
    token = _get_oauth_token()
    if token:
        # Use OAuth authentication
        return await _sync_to_server_with_oauth(
            server_url, settings, direction, start_time, token, checksum
        )
    else:
        # Fall back to basic auth or no auth
        return await _sync_to_server_with_retry(
            server_url, settings, direction, start_time, checksum
        )


async def _sync_to_server_with_oauth(
    server_url: str,
    settings: dict,
    direction: SyncDirection,
    start_time: float,
    token: str,
    checksum: str,
) -> SyncResult:
    """Sync settings to server using OAuth authentication."""
    state = get_settings_sync_state()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "x-app": "cli",
    }

    for retry in range(MAX_RETRIES):
        try:
            import httpx

            if direction == SyncDirection.UPLOAD or direction == SyncDirection.BIDIRECTIONAL:
                response = httpx.post(
                    server_url,
                    json=settings,
                    headers=headers,
                    timeout=10,  # 10 second timeout per spec
                )
            else:
                response = httpx.get(server_url, headers=headers, timeout=10)

            if response.status_code == 401:
                # Token expired, try to refresh
                if await _check_and_refresh_oauth_token():
                    token = _get_oauth_token()
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        continue  # Retry with new token
                state.record_sync(direction, False)
                return SyncResult(
                    success=False,
                    direction=direction,
                    synced_keys=[],
                    message="OAuth token expired and refresh failed",
                    duration_seconds=time.time() - start_time,
                    error="auth_expired",
                    checksum=checksum,
                )

            response.raise_for_status()
            synced_settings = response.json() if response.content else {}

            state.record_sync(direction, True)
            _invalidate_settings_cache()

            return SyncResult(
                success=True,
                direction=direction,
                synced_keys=list(synced_settings.keys()),
                message=f"Settings synced to {server_url}",
                duration_seconds=time.time() - start_time,
                checksum=checksum,
                file_size_bytes=len(json.dumps(settings).encode()),
            )

        except ImportError:
            # httpx not available, fall back to urllib
            return await _sync_to_server_with_retry(
                server_url, settings, direction, start_time, checksum
            )

        except Exception as e:
            if retry < MAX_RETRIES - 1:
                delay = _get_retry_delay(retry)
                await asyncio.sleep(delay)
                continue

            state.record_sync(direction, False)
            return SyncResult(
                success=False,
                direction=direction,
                synced_keys=[],
                message=f"Failed to sync to server after {MAX_RETRIES} attempts: {e}",
                duration_seconds=time.time() - start_time,
                error=str(e),
                checksum=checksum,
            )

    # Should not reach here
    state.record_sync(direction, False)
    return SyncResult(
        success=False,
        direction=direction,
        synced_keys=[],
        message=f"Failed to sync after {MAX_RETRIES} attempts",
        duration_seconds=time.time() - start_time,
        checksum=checksum,
    )


async def _sync_to_server_with_retry(
    server_url: str,
    settings: dict,
    direction: SyncDirection,
    start_time: float,
    checksum: str,
) -> SyncResult:
    """Sync settings to server with basic urllib and retry logic."""
    import json as json_module
    import urllib.request

    state = get_settings_sync_state()

    data = json_module.dumps(settings).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    for retry in range(MAX_RETRIES):
        try:
            if direction == SyncDirection.UPLOAD or direction == SyncDirection.BIDIRECTIONAL:
                req = urllib.request.Request(
                    server_url,
                    data=data,
                    headers=headers,
                    method="PUT",  # Use PUT for upload per spec
                )
            else:
                req = urllib.request.Request(
                    server_url,
                    headers=headers,
                    method="GET",
                )

            with urllib.request.urlopen(req, timeout=10) as resp:
                _ = resp.read()

            state.record_sync(direction, True)
            _invalidate_settings_cache()

            return SyncResult(
                success=True,
                direction=direction,
                synced_keys=list(settings.keys()),
                message=f"Settings synced to {server_url}",
                duration_seconds=time.time() - start_time,
                checksum=checksum,
                file_size_bytes=len(data),
            )

        except Exception as e:
            if retry < MAX_RETRIES - 1:
                delay = _get_retry_delay(retry)
                await asyncio.sleep(delay)
                continue

            state.record_sync(direction, False)
            return SyncResult(
                success=False,
                direction=direction,
                synced_keys=[],
                message=f"Failed to sync to server: {e}",
                duration_seconds=time.time() - start_time,
                error=str(e),
                checksum=checksum,
            )

    state.record_sync(direction, False)
    return SyncResult(
        success=False,
        direction=direction,
        synced_keys=[],
        message=f"Failed to sync after {MAX_RETRIES} attempts",
        duration_seconds=time.time() - start_time,
        checksum=checksum,
    )


def _load_local_settings() -> dict:
    """Load local settings from default locations."""
    settings = {}

    # Try to load from common locations
    possible_paths = [
        Path.home() / ".claude" / "settings.json",
        Path(".claude" / "settings.json"),
    ]

    for path in possible_paths:
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                settings = json.loads(content)
                break
            except (json.JSONDecodeError, IOError):
                continue

    return settings


async def upload_settings(settings: dict | None = None) -> SyncResult:
    """Upload local settings to sync target.

    Args:
        settings: Settings to upload (if None, loads from default location)

    Returns:
        SyncResult with upload details
    """
    return await sync_settings(SyncDirection.UPLOAD, settings)


async def download_settings() -> SyncResult:
    """Download settings from sync target.

    Returns:
        SyncResult with download details
    """
    return await sync_settings(SyncDirection.DOWNLOAD)


def get_sync_status() -> dict:
    """Get current sync status.

    Returns:
        Dictionary with sync status information
    """
    config = get_settings_sync_config()
    state = get_settings_sync_state()

    return {
        "enabled": config.enabled,
        "sync_target": config.sync_target,
        "auto_sync": config.auto_sync,
        "conflict_strategy": config.conflict_strategy,
        "last_sync_at": state.last_sync_at.isoformat() if state.last_sync_at else None,
        "last_sync_direction": state.last_sync_direction.value if state.last_sync_direction else None,
        "total_syncs": state.total_syncs,
        "failed_syncs": state.failed_syncs,
        "pending_changes_count": len(state.pending_changes),
    }
