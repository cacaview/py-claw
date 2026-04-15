"""
TeamMemorySync service.

Synchronizes memory across team members.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from py_claw.services.team_memory_sync.config import (
    get_team_memory_sync_config,
)

from .types import (
    MemoryEntry,
    SyncResult,
    SyncStatus,
    TeamMember,
    TeamMemberStatus,
    get_team_memory_sync_state,
)


def _load_local_memory() -> dict[str, MemoryEntry]:
    """Load memory from local file."""
    config = get_team_memory_sync_config()
    if not config.sync_target:
        return {}

    from pathlib import Path
    path = Path(config.sync_target)
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = {}
        for key, value in data.items():
            entries[key] = MemoryEntry(
                key=value["key"],
                value=value["value"],
                author=value.get("author", "unknown"),
                created_at=datetime.fromisoformat(value["created_at"]),
                updated_at=datetime.fromisoformat(value["updated_at"]),
                version=value.get("version", 1),
            )
        return entries
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def _save_local_memory(entries: dict[str, MemoryEntry]) -> bool:
    """Save memory to local file."""
    config = get_team_memory_sync_config()
    if not config.sync_target:
        return False

    from pathlib import Path
    path = Path(config.sync_target)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        data = {
            key: {
                "key": entry.key,
                "value": entry.value,
                "author": entry.author,
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
                "version": entry.version,
            }
            for key, entry in entries.items()
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def initialize_team(team_id: str, members: list[dict] | None = None) -> bool:
    """Initialize a team for memory sync.

    Args:
        team_id: Team identifier
        members: Optional list of team member dicts

    Returns:
        True if initialized successfully
    """
    state = get_team_memory_sync_state()
    config = get_team_memory_sync_config()

    with state._lock:
        state.team_id = team_id
        state.members.clear()

        if members:
            for m in members:
                member = TeamMember(
                    member_id=m["member_id"],
                    name=m.get("name", m["member_id"]),
                    status=TeamMemberStatus.ACTIVE,
                )
                state.members[member.member_id] = member

    # Load existing memory from sync target
    if config.sync_target:
        existing = _load_local_memory()
        with state._lock:
            state.local_memory.update(existing)

    return True


def add_team_member(member_id: str, name: str) -> TeamMember:
    """Add a member to the team.

    Args:
        member_id: Member identifier
        name: Member name

    Returns:
        Created TeamMember
    """
    state = get_team_memory_sync_state()
    member = TeamMember(
        member_id=member_id,
        name=name,
        status=TeamMemberStatus.ACTIVE,
    )
    state.add_member(member)
    return member


def remove_team_member(member_id: str) -> bool:
    """Remove a member from the team.

    Args:
        member_id: Member identifier

    Returns:
        True if removed successfully
    """
    state = get_team_memory_sync_state()
    return state.remove_member(member_id)


def set_memory(key: str, value: str, author: str) -> MemoryEntry:
    """Set a memory entry.

    Args:
        key: Memory key
        value: Memory value
        author: Author of the memory

    Returns:
        Created MemoryEntry
    """
    state = get_team_memory_sync_state()

    now = datetime.now(timezone.utc)
    existing = state.get_memory(key)

    entry = MemoryEntry(
        key=key,
        value=value,
        author=author,
        created_at=existing.created_at if existing else now,
        updated_at=now,
        version=(existing.version + 1) if existing else 1,
    )

    state.set_memory(key, entry)
    return entry


def get_memory(key: str) -> MemoryEntry | None:
    """Get a memory entry.

    Args:
        key: Memory key

    Returns:
        MemoryEntry if found, None otherwise
    """
    state = get_team_memory_sync_state()
    return state.get_memory(key)


def list_memory() -> list[MemoryEntry]:
    """List all memory entries.

    Returns:
        List of MemoryEntry objects
    """
    state = get_team_memory_sync_state()
    return state.list_memory()


def delete_memory(key: str) -> bool:
    """Delete a memory entry.

    Args:
        key: Memory key

    Returns:
        True if deleted successfully
    """
    state = get_team_memory_sync_state()
    with state._lock:
        if key in state.local_memory:
            del state.local_memory[key]
            if key in state.pending_changes:
                del state.pending_changes[key]
            return True
    return False


async def sync_memory() -> SyncResult:
    """Synchronize team memory.

    Returns:
        SyncResult with sync details
    """
    state = get_team_memory_sync_state()
    config = get_team_memory_sync_config()

    with state._lock:
        state.sync_status = SyncStatus.SYNCING

    try:
        # Load remote memory if sync target exists
        remote_memory = {}
        if config.sync_target:
            remote_memory = _load_local_memory()

        # Merge based on conflict resolution strategy
        conflicts_resolved = 0
        merged_memory = dict(remote_memory)

        with state._lock:
            for key, local_entry in state.local_memory.items():
                if key in remote_memory:
                    remote_entry = remote_memory[key]
                    if config.conflict_resolution == "local":
                        merged_memory[key] = local_entry
                    elif config.conflict_resolution == "remote":
                        pass  # Keep remote
                    else:  # merge
                        if local_entry.updated_at > remote_entry.updated_at:
                            merged_memory[key] = local_entry
                        conflicts_resolved += 1
                else:
                    merged_memory[key] = local_entry

        # Save merged memory
        success = _save_local_memory(merged_memory)

        with state._lock:
            state.local_memory = merged_memory
            state.last_sync_at = datetime.now(timezone.utc)
            state.pending_changes.clear()
            state.sync_status = SyncStatus.SUCCESS if success else SyncStatus.FAILED

        return SyncResult(
            success=success,
            synced_entries=len(merged_memory),
            conflicts_resolved=conflicts_resolved,
            message="Sync completed successfully" if success else "Sync failed",
            timestamp=datetime.now(timezone.utc),
        )

    except Exception as e:
        with state._lock:
            state.sync_status = SyncStatus.FAILED

        return SyncResult(
            success=False,
            synced_entries=0,
            conflicts_resolved=0,
            message=f"Sync failed: {e}",
            timestamp=datetime.now(timezone.utc),
        )


def get_sync_status() -> dict:
    """Get current sync status.

    Returns:
        Dictionary with sync status
    """
    state = get_team_memory_sync_state()
    config = get_team_memory_sync_config()

    return {
        "enabled": config.enabled,
        "team_id": state.team_id,
        "sync_status": state.sync_status.value,
        "member_count": len(state.members),
        "memory_entries": len(state.local_memory),
        "pending_changes": len(state.pending_changes),
        "last_sync_at": state.last_sync_at.isoformat() if state.last_sync_at else None,
    }
