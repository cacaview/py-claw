"""
SettingsSync configuration.

Service for synchronizing settings across sessions.
"""
from __future__ import annotations

from dataclasses import dataclass


# Default values
_DEFAULT_INCLUDE_KEYS = ["model", "permissions", "tools", "hooks", "mcp", "skills", "agents"]
_DEFAULT_EXCLUDE_KEYS = ["apiKey", "token", "secret", "password"]


@dataclass(frozen=True)
class SettingsSyncConfig:
    """Configuration for SettingsSync service."""

    enabled: bool = False
    # Sync target (local file, remote server, etc.)
    sync_target: str | None = None
    # Auto-sync on settings change
    auto_sync: bool = True
    # Sync interval in seconds (for polling mode)
    sync_interval: int = 300
    # Include these settings keys in sync
    include_keys: tuple[str, ...] = ()
    # Exclude these settings keys from sync
    exclude_keys: tuple[str, ...] = ()
    # Conflict resolution strategy: "local", "remote", "merge"
    conflict_strategy: str = "local"

    @classmethod
    def from_settings(cls, settings: dict) -> SettingsSyncConfig:
        """Create config from settings dictionary."""
        ss_settings = settings.get("settingsSync", {})
        include = ss_settings.get("includeKeys")
        exclude = ss_settings.get("excludeKeys")
        return cls(
            enabled=ss_settings.get("enabled", False),
            sync_target=ss_settings.get("syncTarget"),
            auto_sync=ss_settings.get("autoSync", True),
            sync_interval=ss_settings.get("syncInterval", 300),
            include_keys=tuple(include) if include else _DEFAULT_INCLUDE_KEYS,
            exclude_keys=tuple(exclude) if exclude else _DEFAULT_EXCLUDE_KEYS,
            conflict_strategy=ss_settings.get("conflictStrategy", "local"),
        )


# Global config instance
_config: SettingsSyncConfig | None = None


def get_settings_sync_config() -> SettingsSyncConfig:
    """Get the current SettingsSync configuration."""
    global _config
    if _config is None:
        _config = SettingsSyncConfig(
            include_keys=_DEFAULT_INCLUDE_KEYS,
            exclude_keys=_DEFAULT_EXCLUDE_KEYS,
        )
    return _config


def set_settings_sync_config(config: SettingsSyncConfig) -> None:
    """Set the SettingsSync configuration."""
    global _config
    _config = config
