"""
Team helpers for swarm team orchestration.

Based on ClaudeCode-main/src/utils/swarm/teamHelpers.ts

Handles:
- Team file read/write
- Member management
- Session cleanup
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .types import (
    BackendType,
    CleanupOutput,
    SpawnTeamInput,
    SpawnTeamOutput,
    TeamFile,
    TeamMember,
    sanitize_agent_name,
    sanitize_name,
)

logger = logging.getLogger(__name__)

# Default teams directory
TEAMS_DIR = Path.home() / ".claude" / "teams"


def get_teams_dir() -> Path:
    """Get the teams directory."""
    teams_dir = Path(os.environ.get("CLAUDE_TEAMS_DIR", str(TEAMS_DIR)))
    teams_dir.mkdir(parents=True, exist_ok=True)
    return teams_dir


def get_team_dir(team_name: str) -> Path:
    """Get the directory for a specific team."""
    return get_teams_dir() / sanitize_name(team_name)


def get_team_file_path(team_name: str) -> Path:
    """Get the path to a team's config.json file."""
    return get_team_dir(team_name) / "config.json"


def team_file_to_dict(team_file: TeamFile) -> dict:
    """Convert TeamFile to dict for JSON serialization."""
    return {
        "name": team_file.name,
        "description": team_file.description,
        "createdAt": team_file.created_at.isoformat() if isinstance(team_file.created_at, datetime) else team_file.created_at,
        "leadAgentId": team_file.lead_agent_id,
        "leadSessionId": team_file.lead_session_id,
        "hiddenPaneIds": team_file.hidden_pane_ids,
        "teamAllowedPaths": [
            {
                "path": p.path,
                "toolName": p.tool_name,
                "addedBy": p.added_by,
                "addedAt": p.added_at.isoformat() if isinstance(p.added_at, datetime) else p.added_at,
            }
            for p in team_file.team_allowed_paths
        ],
        "members": [
            {
                "agentId": m.agent_id,
                "name": m.name,
                "agentType": m.agent_type,
                "model": m.model,
                "prompt": m.prompt,
                "color": m.color,
                "planModeRequired": m.plan_mode_required,
                "joinedAt": m.joined_at.isoformat() if isinstance(m.joined_at, datetime) else m.joined_at,
                "tmuxPaneId": m.tmux_pane_id,
                "cwd": m.cwd,
                "worktreePath": m.worktree_path,
                "sessionId": m.session_id,
                "subscriptions": m.subscriptions,
                "backendType": m.backend_type.value if isinstance(m.backend_type, BackendType) else m.backend_type,
                "isActive": m.is_active,
                "mode": m.mode,
            }
            for m in team_file.members
        ],
    }


def dict_to_team_file(data: dict) -> TeamFile:
    """Convert dict to TeamFile."""

    def parse_dt(val):
        if isinstance(val, str):
            return datetime.fromisoformat(val)
        return val

    return TeamFile(
        name=data.get("name", ""),
        description=data.get("description"),
        created_at=parse_dt(data.get("createdAt")),
        lead_agent_id=data.get("leadAgentId", ""),
        lead_session_id=data.get("leadSessionId"),
        hidden_pane_ids=data.get("hiddenPaneIds", []),
        team_allowed_paths=data.get("teamAllowedPaths", []),
        members=[
            TeamMember(
                agent_id=m.get("agentId", ""),
                name=m.get("name", ""),
                agent_type=m.get("agentType"),
                model=m.get("model"),
                prompt=m.get("prompt"),
                color=m.get("color"),
                plan_mode_required=m.get("planModeRequired", False),
                joined_at=parse_dt(m.get("joinedAt")),
                tmux_pane_id=m.get("tmuxPaneId"),
                cwd=m.get("cwd", ""),
                worktree_path=m.get("worktreePath"),
                session_id=m.get("sessionId"),
                subscriptions=m.get("subscriptions", []),
                backend_type=BackendType(m["backendType"]) if m.get("backendType") else None,
                is_active=m.get("isActive", True),
                mode=m.get("mode"),
            )
            for m in data.get("members", [])
        ],
    )


def read_team_file(team_name: str) -> Optional[TeamFile]:
    """
    Reads a team file by name (sync — for sync contexts).
    Returns None if team doesn't exist.
    """
    team_path = get_team_file_path(team_name)
    try:
        with open(team_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return dict_to_team_file(data)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.exception(f"[TeammateTool] Failed to read team file for {team_name}")
        return None


async def read_team_file_async(team_name: str) -> Optional[TeamFile]:
    """
    Reads a team file by name (async — for tool handlers).
    Returns None if team doesn't exist.
    """
    import asyncio

    team_path = get_team_file_path(team_name)
    try:
        with open(team_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return dict_to_team_file(data)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.exception(f"[TeammateTool] Failed to read team file for {team_name}")
        return None


def write_team_file(team_name: str, team_file: TeamFile) -> None:
    """
    Writes a team file (sync — for sync contexts).
    Creates team directory if it doesn't exist.
    """
    team_dir = get_team_dir(team_name)
    team_dir.mkdir(parents=True, exist_ok=True)
    team_path = get_team_file_path(team_name)
    with open(team_path, "w", encoding="utf-8") as f:
        json.dump(team_file_to_dict(team_file), f, indent=2)


async def write_team_file_async(team_name: str, team_file: TeamFile) -> None:
    """
    Writes a team file (async — for tool handlers).
    Creates team directory if it doesn't exist.
    """
    import asyncio

    team_dir = get_team_dir(team_name)
    team_dir.mkdir(parents=True, exist_ok=True)
    team_path = get_team_file_path(team_name)
    with open(team_path, "w", encoding="utf-8") as f:
        json.dump(team_file_to_dict(team_file), f, indent=2)


def remove_member_from_team(
    team_name: str,
    agent_id: Optional[str] = None,
    name: Optional[str] = None,
) -> bool:
    """
    Removes a teammate from the team file by agent ID or name.
    """
    identifier = agent_id or name
    if not identifier:
        return False

    team_file = read_team_file(team_name)
    if not team_file:
        return False

    original_length = len(team_file.members)
    team_file.members = [
        m for m in team_file.members
        if not (agent_id and m.agent_id == agent_id) and not (name and m.name == name)
    ]

    if len(team_file.members) == original_length:
        return False

    write_team_file(team_name, team_file)
    return True


def add_hidden_pane_id(team_name: str, pane_id: str) -> bool:
    """Adds a pane ID to the hidden panes list in the team file."""
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    hidden_ids = team_file.hidden_pane_ids or []
    if pane_id not in hidden_ids:
        hidden_ids.append(pane_id)
        team_file.hidden_pane_ids = hidden_ids
        write_team_file(team_name, team_file)
    return True


def remove_hidden_pane_id(team_name: str, pane_id: str) -> bool:
    """Removes a pane ID from the hidden panes list."""
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    hidden_ids = team_file.hidden_pane_ids or []
    if pane_id in hidden_ids:
        hidden_ids.remove(pane_id)
        team_file.hidden_pane_ids = hidden_ids
        write_team_file(team_name, team_file)
    return True


async def cleanup_team_directories(team_name: str) -> None:
    """
    Cleans up team and task directories for a given team name.
    Also cleans up git worktrees created for teammates.
    """
    import shutil

    sanitized = sanitize_name(team_name)

    # Clean up team directory
    team_dir = get_team_dir(team_name)
    try:
        if team_dir.exists():
            shutil.rmtree(team_dir)
            logger.info(f"[TeammateTool] Cleaned up team directory: {team_dir}")
    except Exception as e:
        logger.exception(f"[TeammateTool] Failed to clean up team directory {team_dir}")

    # Clean up tasks directory
    tasks_dir = Path.home() / ".claude" / "tasks" / sanitized
    try:
        if tasks_dir.exists():
            shutil.rmtree(tasks_dir)
            logger.info(f"[TeammateTool] Cleaned up tasks directory: {tasks_dir}")
    except Exception as e:
        logger.exception(f"[TeammateTool] Failed to clean up tasks directory {tasks_dir}")


def list_teams() -> list[str]:
    """List all team names."""
    teams_dir = get_teams_dir()
    if not teams_dir.exists():
        return []
    return [d.name for d in teams_dir.iterdir() if d.is_dir() and (d / "config.json").exists()]


def remove_member_by_agent_id(team_name: str, agent_id: str) -> bool:
    """
    Removes a teammate from a team's member list by agent ID.

    Use this for in-process teammates which all share the same tmuxPaneId.

    Args:
        team_name: The name of the team
        agent_id: The agent ID of the teammate to remove (e.g., "researcher@my-team")

    Returns:
        True if the member was removed, False if team or member doesn't exist
    """
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    original_length = len(team_file.members)
    team_file.members = [
        m for m in team_file.members
        if m.agent_id != agent_id
    ]

    if len(team_file.members) == original_length:
        return False

    write_team_file(team_name, team_file)
    logger.debug(f"[TeammateTool] Removed member {agent_id} from team {team_name}")
    return True


async def set_member_active(
    team_name: str,
    member_name: str,
    is_active: bool,
) -> None:
    """
    Sets a team member's active status.

    Args:
        team_name: The name of the team
        member_name: The name of the member to update
        is_active: Whether the member is active (True) or idle (False)
    """
    team_file = await read_team_file_async(team_name)
    if not team_file:
        logger.debug(f"[TeammateTool] Cannot set member active: team {team_name} not found")
        return

    member = None
    for m in team_file.members:
        if m.name == member_name:
            member = m
            break

    if not member:
        logger.debug(f"[TeammateTool] Cannot set member active: member {member_name} not found in team {team_name}")
        return

    # Only write if the value is actually changing
    if member.is_active == is_active:
        return

    member.is_active = is_active
    await write_team_file_async(team_name, team_file)
    logger.debug(f"[TeammateTool] Set member {member_name} in team {team_name} to {'active' if is_active else 'idle'}")


__all__ = [
    "TEAMS_DIR",
    "get_teams_dir",
    "get_team_dir",
    "get_team_file_path",
    "read_team_file",
    "read_team_file_async",
    "write_team_file",
    "write_team_file_async",
    "remove_member_from_team",
    "remove_member_by_agent_id",
    "set_member_active",
    "add_hidden_pane_id",
    "remove_hidden_pane_id",
    "cleanup_team_directories",
    "list_teams",
    "SpawnTeamInput",
    "SpawnTeamOutput",
    "CleanupOutput",
    "TeamFile",
    "TeamMember",
    "sanitize_name",
    "sanitize_agent_name",
]
