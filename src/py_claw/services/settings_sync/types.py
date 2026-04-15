"""
SettingsSync types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SyncDirection(str, Enum):
    """Direction of settings sync."""

    UPLOAD = "upload"
    DOWNLOAD = "download"
    BIDIRECTIONAL = "bidirectional"


class SyncStatus(str, Enum):
    """Status of a sync operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    CONFLICT = "conflict"


class ConflictResolution(str, Enum):
    """Conflict resolution strategies."""

    KEEP_LOCAL = "local"
    KEEP_REMOTE = "remote"
    MERGE = "merge"


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Result of a sync operation."""

    success: bool
    direction: SyncDirection
    synced_keys: list[str]
    message: str
    conflicts: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None
    checksum: str | None = None
    file_size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    """A snapshot of settings at a point in time."""

    settings: dict
    timestamp: datetime
    source: str  # "local", "remote", "manual"
    version: str | None = None
    checksum: str | None = None  # SHA-256 checksum of settings


@dataclass(frozen=True, slots=True)
class SyncMetadata:
    """Metadata for a sync operation."""
    synced_keys: list[str] = field(default_factory=list)
    checksum: str | None = None
    file_size_bytes: int | None = None
    version: str | None = None


@dataclass
class SettingsSyncState:
    """State for settings sync service."""

    last_sync_at: datetime | None = None
    last_sync_direction: SyncDirection | None = None
    total_syncs: int = 0
    failed_syncs: int = 0
    pending_changes: dict = field(default_factory=dict)
    local_snapshot: SettingsSnapshot | None = None
    remote_snapshot: SettingsSnapshot | None = None
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def record_sync(self, direction: SyncDirection, success: bool) -> None:
        """Record a sync operation."""
        with self._lock:
            self.last_sync_at = datetime.now(timezone.utc)
            self.last_sync_direction = direction
            self.total_syncs += 1
            if not success:
                self.failed_syncs += 1

    def add_pending_change(self, key: str, value: object) -> None:
        """Add a pending change."""
        with self._lock:
            self.pending_changes[key] = {
                "value": value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def clear_pending_changes(self) -> None:
        """Clear all pending changes."""
        with self._lock:
            self.pending_changes.clear()

    def get_pending_changes(self) -> dict:
        """Get pending changes as dict."""
        with self._lock:
            return dict(self.pending_changes)


# Global state
_state: SettingsSyncState | None = None


def get_settings_sync_state() -> SettingsSyncState:
    """Get the global settings sync state."""
    global _state
    if _state is None:
        _state = SettingsSyncState()
    return _state
