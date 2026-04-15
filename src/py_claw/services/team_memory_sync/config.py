"""
TeamMemorySync configuration.

Service for synchronizing memory across team members.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamMemorySyncConfig:
    """Configuration for TeamMemorySync service."""

    enabled: bool = False
    # Sync target (local file, shared storage, etc.)
    sync_target: str | None = None
    # Auto-sync interval in seconds
    sync_interval: int = 300
    # Include these memory keys in sync
    include_keys: tuple[str, ...] = ("memory", "context", "learnings")
    # Sync on update
    sync_on_update: bool = True
    # Conflict resolution: "local", "remote", "merge"
    conflict_resolution: str = "merge"

    @classmethod
    def from_settings(cls, settings: dict) -> TeamMemorySyncConfig:
        """Create config from settings dictionary."""
        tm_settings = settings.get("teamMemorySync", {})
        include = tm_settings.get("includeKeys")
        return cls(
            enabled=tm_settings.get("enabled", False),
            sync_target=tm_settings.get("syncTarget"),
            sync_interval=tm_settings.get("syncInterval", 300),
            include_keys=tuple(include) if include else ("memory", "context", "learnings"),
            sync_on_update=tm_settings.get("syncOnUpdate", True),
            conflict_resolution=tm_settings.get("conflictResolution", "merge"),
        )


# Global config instance
_config: TeamMemorySyncConfig | None = None


def get_team_memory_sync_config() -> TeamMemorySyncConfig:
    """Get the current TeamMemorySync configuration."""
    global _config
    if _config is None:
        _config = TeamMemorySyncConfig()
    return _config


def set_team_memory_sync_config(config: TeamMemorySyncConfig) -> None:
    """Set the TeamMemorySync configuration."""
    global _config
    _config = config
