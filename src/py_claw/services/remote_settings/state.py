"""
Remote managed settings state management.

Thread-safe state for remote settings with disk cache and eligibility tracking.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import RemoteSettingsConfig, RemoteSettingsFetchResult, RemoteSettingsResponse


@dataclass
class RemoteSettingsState:
    """
    Thread-safe state for remote managed settings.
    """
    # Cached settings from last successful fetch
    _cached_settings: dict[str, Any] | None = None

    # Cached checksum
    _cached_checksum: str | None = None

    # Eligibility state
    _is_eligible: bool | None = None  # None = not yet determined

    # Last fetch timestamp
    _last_fetch_at: float | None = None

    # Loading promise for async initialization
    _loading_promise: Any = None

    # Lock for thread safety
    _lock: threading.RLock = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_lock", threading.RLock())

    def get_cached_settings(self) -> dict[str, Any] | None:
        with self._lock:
            return self._cached_settings

    def set_cached_settings(self, settings: dict[str, Any] | None, checksum: str | None = None) -> None:
        with self._lock:
            self._cached_settings = settings
            self._cached_checksum = checksum
            if settings is not None:
                self._last_fetch_at = time.time()

    def get_cached_checksum(self) -> str | None:
        with self._lock:
            return self._cached_checksum

    def get_eligibility(self) -> bool | None:
        with self._lock:
            return self._is_eligible

    def set_eligibility(self, is_eligible: bool) -> None:
        with self._lock:
            self._is_eligible = is_eligible

    def get_last_fetch_at(self) -> float | None:
        with self._lock:
            return self._last_fetch_at

    def set_loading_promise(self, promise: Any) -> None:
        with self._lock:
            self._loading_promise = promise

    def get_loading_promise(self) -> Any:
        with self._lock:
            return self._loading_promise

    def clear(self) -> None:
        with self._lock:
            self._cached_settings = None
            self._cached_checksum = None
            self._is_eligible = None
            self._last_fetch_at = None
            self._loading_promise = None


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_state: RemoteSettingsState | None = None


def get_remote_settings_state() -> RemoteSettingsState:
    """Get the global remote settings state."""
    global _state
    if _state is None:
        _state = RemoteSettingsState()
    return _state


def reset_remote_settings_state() -> None:
    """Reset the global remote settings state (for testing)."""
    global _state
    _state = None


# ------------------------------------------------------------------
# Disk cache
# ------------------------------------------------------------------

def get_cache_file_path() -> Path:
    """Get the path to the remote settings cache file."""
    return Path("~/.claude/remote-settings.json").expanduser()


def load_settings_from_disk() -> tuple[dict[str, Any] | None, str | None]:
    """
    Load settings from disk cache.

    Returns:
        Tuple of (settings_dict, checksum) or (None, None) if not cached
    """
    cache_path = get_cache_file_path()
    if not cache_path.exists():
        return None, None

    try:
        text = cache_path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            return None, None
        settings = data.get("settings")
        checksum = data.get("checksum")
        if settings is None:
            return None, None
        return settings, checksum
    except (json.JSONDecodeError, OSError):
        return None, None


def save_settings_to_disk(settings: dict[str, Any], checksum: str) -> None:
    """Save settings to disk cache."""
    cache_path = get_cache_file_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"settings": settings, "checksum": checksum}
        cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # Non-blocking, best effort


def clear_disk_cache() -> None:
    """Clear the disk cache."""
    cache_path = get_cache_file_path()
    try:
        if cache_path.exists():
            cache_path.unlink()
    except OSError:
        pass
