"""
TeamMemorySync types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SyncStatus(str, Enum):
    """Status of sync operation."""

    IDLE = "idle"
    SYNCING = "syncing"
    SUCCESS = "success"
    FAILED = "failed"


class TeamMemberStatus(str, Enum):
    """Status of a team member."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    OFFLINE = "offline"


@dataclass(frozen=True, slots=True)
class TeamMember:
    """A team member."""

    member_id: str
    name: str
    last_sync_at: datetime | None = None
    status: TeamMemberStatus = TeamMemberStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """A memory entry in team memory."""

    key: str
    value: str
    author: str
    created_at: datetime
    updated_at: datetime
    version: int = 1


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Result of a sync operation."""

    success: bool
    synced_entries: int
    conflicts_resolved: int
    message: str
    timestamp: datetime | None = None


@dataclass
class TeamMemorySyncState:
    """State for team memory sync service."""

    team_id: str | None = None
    members: dict[str, TeamMember] = field(default_factory=dict)
    local_memory: dict[str, MemoryEntry] = field(default_factory=dict)
    last_sync_at: datetime | None = None
    sync_status: SyncStatus = SyncStatus.IDLE
    pending_changes: dict[str, MemoryEntry] = field(default_factory=dict)
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def add_member(self, member: TeamMember) -> None:
        """Add a team member."""
        with self._lock:
            self.members[member.member_id] = member

    def remove_member(self, member_id: str) -> bool:
        """Remove a team member."""
        with self._lock:
            if member_id in self.members:
                del self.members[member_id]
                return True
            return False

    def set_memory(self, key: str, entry: MemoryEntry) -> None:
        """Set a memory entry."""
        with self._lock:
            self.local_memory[key] = entry
            self.pending_changes[key] = entry

    def get_memory(self, key: str) -> MemoryEntry | None:
        """Get a memory entry."""
        with self._lock:
            return self.local_memory.get(key)

    def list_memory(self) -> list[MemoryEntry]:
        """List all memory entries."""
        with self._lock:
            return list(self.local_memory.values())


# Global state
_state: TeamMemorySyncState | None = None


def get_team_memory_sync_state() -> TeamMemorySyncState:
    """Get the global team memory sync state."""
    global _state
    if _state is None:
        _state = TeamMemorySyncState()
    return _state
