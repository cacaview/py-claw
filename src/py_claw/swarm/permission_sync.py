"""
Synchronized Permission Prompts for Agent Swarms

This module provides infrastructure for coordinating permission prompts across
multiple agents in a swarm. When a worker agent needs permission for a tool use,
it can forward the request to the team leader, who can then approve or deny it.

The system uses the teammate mailbox for message passing:
- Workers send permission requests to the leader's mailbox
- Leaders send permission responses to the worker's mailbox

Flow:
1. Worker agent encounters a permission prompt
2. Worker sends a permission_request message to the leader's mailbox
3. Leader polls for mailbox messages and detects permission requests
4. User approves/denies via the leader's UI
5. Leader sends a permission_response message to the worker's mailbox
6. Worker polls mailbox for responses and continues execution

Based on ClaudeCode-main/src/utils/swarm/permissionSync.ts
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Team directories
TEAMS_DIR = Path.home() / ".claude" / "teams"


def get_team_dir(team_name: str) -> Path:
    """Get the directory for a specific team."""
    sanitized = _sanitize_name(team_name)
    return TEAMS_DIR / sanitized


def get_permission_dir(team_name: str) -> Path:
    """Get the base directory for a team's permission requests."""
    return get_team_dir(team_name) / "permissions"


def _get_pending_dir(team_name: str) -> Path:
    """Get the pending directory for a team."""
    return get_permission_dir(team_name) / "pending"


def _get_resolved_dir(team_name: str) -> Path:
    """Get the resolved directory for a team."""
    return get_permission_dir(team_name) / "resolved"


async def _ensure_permission_dirs_async(team_name: str) -> None:
    """Ensure the permissions directory structure exists (async)."""
    perm_dir = get_permission_dir(team_name)
    pending_dir = _get_pending_dir(team_name)
    resolved_dir = _get_resolved_dir(team_name)

    for dir_path in [perm_dir, pending_dir, resolved_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)


def _get_pending_request_path(team_name: str, request_id: str) -> Path:
    """Get the path to a pending request file."""
    return _get_pending_dir(team_name) / f"{request_id}.json"


def _get_resolved_request_path(team_name: str, request_id: str) -> Path:
    """Get the path to a resolved request file."""
    return _get_resolved_dir(team_name) / f"{request_id}.json"


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return f"perm-{int(datetime.now().timestamp() * 1000)}-{os.urandom(4).hex()}"


@dataclass
class SwarmPermissionRequest:
    """Full request schema for a permission request from a worker to the leader."""
    id: str
    worker_id: str
    worker_name: str
    worker_color: Optional[str] = None
    team_name: str = ""
    tool_name: str = ""
    tool_use_id: str = ""
    description: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    permission_suggestions: list[Any] = field(default_factory=list)
    status: str = "pending"  # 'pending' | 'approved' | 'rejected'
    resolved_by: Optional[str] = None  # 'worker' | 'leader'
    resolved_at: Optional[int] = None
    feedback: Optional[str] = None
    updated_input: Optional[dict[str, Any]] = None
    permission_updates: Optional[list[Any]] = None
    created_at: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "id": self.id,
            "workerId": self.worker_id,
            "workerName": self.worker_name,
            "workerColor": self.worker_color,
            "teamName": self.team_name,
            "toolName": self.tool_name,
            "toolUseId": self.tool_use_id,
            "description": self.description,
            "input": self.input,
            "permissionSuggestions": self.permission_suggestions,
            "status": self.status,
            "resolvedBy": self.resolved_by,
            "resolvedAt": self.resolved_at,
            "feedback": self.feedback,
            "updatedInput": self.updated_input,
            "permissionUpdates": self.permission_updates,
            "createdAt": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SwarmPermissionRequest":
        """Create from dict."""
        return cls(
            id=data.get("id", ""),
            worker_id=data.get("workerId", ""),
            worker_name=data.get("workerName", ""),
            worker_color=data.get("workerColor"),
            team_name=data.get("teamName", ""),
            tool_name=data.get("toolName", ""),
            tool_use_id=data.get("toolUseId", ""),
            description=data.get("description", ""),
            input=data.get("input", {}),
            permission_suggestions=data.get("permissionSuggestions", []),
            status=data.get("status", "pending"),
            resolved_by=data.get("resolvedBy"),
            resolved_at=data.get("resolvedAt"),
            feedback=data.get("feedback"),
            updated_input=data.get("updatedInput"),
            permission_updates=data.get("permissionUpdates"),
            created_at=data.get("createdAt", int(datetime.now().timestamp() * 1000)),
        )


@dataclass
class PermissionResolution:
    """Resolution data returned when leader/worker resolves a request."""
    decision: str  # 'approved' | 'rejected'
    resolved_by: str  # 'worker' | 'leader'
    feedback: Optional[str] = None
    updated_input: Optional[dict[str, Any]] = None
    permission_updates: Optional[list[Any]] = None


def _sanitize_name(name: str) -> str:
    """Sanitize a name for use in file paths."""
    import re
    return re.sub(r"[^a-zA-Z0-9]", "-", name).lower()


async def write_permission_request(
    request: SwarmPermissionRequest,
) -> SwarmPermissionRequest:
    """
    Write a permission request to the pending directory.

    Called by worker agents when they need permission approval from the leader.

    Args:
        request: The permission request to write

    Returns:
        The written request
    """
    await _ensure_permission_dirs_async(request.team_name)

    pending_path = _get_pending_request_path(request.team_name, request.id)
    lock_file_path = _get_pending_dir(request.team_name) / ".lock"

    # Create lock file
    lock_file_path.touch()

    try:
        # Async file lock would be better, but for now we just write
        # In a production system, you'd use asyncio.Lock or filelock library
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(request.to_dict(), f, indent=2)

        logger.debug(
            f"[PermissionSync] Wrote pending request {request.id} from {request.worker_name} for {request.tool_name}"
        )

        return request
    except Exception as e:
        logger.debug(f"[PermissionSync] Failed to write permission request: {e}")
        logger.error(f"[PermissionSync] Failed to write permission request: {e}")
        raise


async def read_pending_permissions(
    team_name: Optional[str] = None,
) -> list[SwarmPermissionRequest]:
    """
    Read all pending permission requests for a team.

    Called by the team leader to see what requests need attention.

    Args:
        team_name: Team name (uses env var if not provided)

    Returns:
        List of pending permission requests
    """
    if not team_name:
        team_name = os.environ.get("CLAUDE_TEAM_NAME", "")

    if not team_name:
        logger.debug("[PermissionSync] No team name available")
        return []

    pending_dir = _get_pending_dir(team_name)

    if not pending_dir.exists():
        return []

    try:
        files = list(pending_dir.iterdir())
    except Exception as e:
        logger.debug(f"[PermissionSync] Failed to read pending requests: {e}")
        return []

    json_files = [f for f in files if f.suffix == ".json" and f.name != ".lock"]

    results: list[SwarmPermissionRequest] = []

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            request = SwarmPermissionRequest.from_dict(data)
            results.append(request)
        except Exception as e:
            logger.debug(f"[PermissionSync] Failed to read request file {file_path}: {e}")

    # Sort by creation time (oldest first)
    results.sort(key=lambda r: r.created_at)

    return results


async def read_resolved_permission(
    request_id: str,
    team_name: Optional[str] = None,
) -> Optional[SwarmPermissionRequest]:
    """
    Read a resolved permission request by ID.

    Called by workers to check if their request has been resolved.

    Args:
        request_id: Request ID to look up
        team_name: Team name

    Returns:
        The resolved request, or None if not yet resolved
    """
    if not team_name:
        team_name = os.environ.get("CLAUDE_TEAM_NAME", "")

    if not team_name:
        return None

    resolved_path = _get_resolved_request_path(team_name, request_id)

    if not resolved_path.exists():
        return None

    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SwarmPermissionRequest.from_dict(data)
    except Exception as e:
        logger.debug(f"[PermissionSync] Failed to read resolved request {request_id}: {e}")
        return None


async def resolve_permission(
    request_id: str,
    resolution: PermissionResolution,
    team_name: Optional[str] = None,
) -> bool:
    """
    Resolve a permission request.

    Called by the team leader (or worker in self-resolution cases).
    Writes the resolution to resolved/, removes from pending/.

    Args:
        request_id: Request ID to resolve
        resolution: Resolution data
        team_name: Team name

    Returns:
        True if resolved successfully
    """
    if not team_name:
        team_name = os.environ.get("CLAUDE_TEAM_NAME", "")

    if not team_name:
        logger.debug("[PermissionSync] No team name available")
        return False

    await _ensure_permission_dirs_async(team_name)

    pending_path = _get_pending_request_path(team_name, request_id)
    resolved_path = _get_resolved_request_path(team_name, request_id)
    lock_file_path = _get_pending_dir(team_name) / ".lock"

    lock_file_path.touch()

    try:
        # Read the pending request
        if not pending_path.exists():
            logger.debug(f"[PermissionSync] Pending request not found: {request_id}")
            return False

        with open(pending_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        request = SwarmPermissionRequest.from_dict(data)

        # Update with resolution data
        request.status = "approved" if resolution.decision == "approved" else "rejected"
        request.resolved_by = resolution.resolved_by
        request.resolved_at = int(datetime.now().timestamp() * 1000)
        request.feedback = resolution.feedback
        request.updated_input = resolution.updated_input
        request.permission_updates = resolution.permission_updates

        # Write to resolved directory
        with open(resolved_path, "w", encoding="utf-8") as f:
            json.dump(request.to_dict(), f, indent=2)

        # Remove from pending directory
        pending_path.unlink()

        logger.debug(f"[PermissionSync] Resolved request {request_id} with {resolution.decision}")

        return True
    except Exception as e:
        logger.debug(f"[PermissionSync] Failed to resolve request: {e}")
        logger.error(f"[PermissionSync] Failed to resolve request: {e}")
        return False
    finally:
        if lock_file_path.exists():
            try:
                lock_file_path.unlink()
            except Exception:
                pass


async def cleanup_old_resolutions(
    team_name: Optional[str] = None,
    max_age_ms: int = 3600000,  # 1 hour default
) -> int:
    """
    Clean up old resolved permission files.

    Called periodically to prevent file accumulation.

    Args:
        team_name: Team name
        max_age_ms: Maximum age in milliseconds (default: 1 hour)

    Returns:
        Number of files cleaned up
    """
    if not team_name:
        team_name = os.environ.get("CLAUDE_TEAM_NAME", "")

    if not team_name:
        return 0

    resolved_dir = _get_resolved_dir(team_name)

    if not resolved_dir.exists():
        return 0

    try:
        files = list(resolved_dir.iterdir())
    except Exception as e:
        logger.debug(f"[PermissionSync] Failed to cleanup resolutions: {e}")
        return 0

    json_files = [f for f in files if f.suffix == ".json"]
    now = datetime.now().timestamp() * 1000

    cleaned_count = 0

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            request = SwarmPermissionRequest.from_dict(data)

            resolved_at = request.resolved_at or request.created_at
            if now - resolved_at >= max_age_ms:
                file_path.unlink()
                logger.debug(f"[PermissionSync] Cleaned up old resolution: {file_path.name}")
                cleaned_count += 1
        except Exception:
            # If we can't parse it, clean it up anyway
            try:
                file_path.unlink()
                cleaned_count += 1
            except Exception:
                pass

    if cleaned_count > 0:
        logger.debug(f"[PermissionSync] Cleaned up {cleaned_count} old resolutions")

    return cleaned_count


async def delete_resolved_permission(
    request_id: str,
    team_name: Optional[str] = None,
) -> bool:
    """
    Delete a resolved permission file.

    Called after a worker has processed the resolution.

    Args:
        request_id: Request ID to delete
        team_name: Team name

    Returns:
        True if deleted successfully
    """
    if not team_name:
        team_name = os.environ.get("CLAUDE_TEAM_NAME", "")

    if not team_name:
        return False

    resolved_path = _get_resolved_request_path(team_name, request_id)

    if not resolved_path.exists():
        return False

    try:
        resolved_path.unlink()
        logger.debug(f"[PermissionSync] Deleted resolved permission: {request_id}")
        return True
    except Exception as e:
        logger.debug(f"[PermissionSync] Failed to delete resolved permission: {e}")
        return False


def is_team_leader(team_name: Optional[str] = None) -> bool:
    """
    Check if the current agent is a team leader.

    Args:
        team_name: Team name

    Returns:
        True if this is the team leader
    """
    if not team_name:
        team_name = os.environ.get("CLAUDE_TEAM_NAME", "")

    if not team_name:
        return False

    # Team leaders don't have an agent ID set
    agent_id = os.environ.get("CLAUDE_AGENT_ID", "")
    return not agent_id or agent_id == "team-lead"


def is_swarm_worker() -> bool:
    """
    Check if the current agent is a worker in a swarm.

    Returns:
        True if this is a swarm worker
    """
    team_name = os.environ.get("CLAUDE_TEAM_NAME", "")
    agent_id = os.environ.get("CLAUDE_AGENT_ID", "")

    return bool(team_name) and bool(agent_id) and not is_team_leader()


# Alias for backward compatibility
submit_permission_request = write_permission_request


__all__ = [
    "SwarmPermissionRequest",
    "PermissionResolution",
    "generate_request_id",
    "write_permission_request",
    "read_pending_permissions",
    "read_resolved_permission",
    "resolve_permission",
    "cleanup_old_resolutions",
    "delete_resolved_permission",
    "is_team_leader",
    "is_swarm_worker",
    "submit_permission_request",
]
