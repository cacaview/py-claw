"""
Swarm types for team orchestration.

Based on ClaudeCode-main/src/utils/swarm/teamHelpers.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class BackendType(Enum):
    """Backend type for teammate panes."""

    TMUX = "tmux"
    ITerm2 = "iterm2"
    IN_PROCESS = "in_process"
    WEB = "web"


class SessionStatus(Enum):
    """Session status."""

    PENDING = "pending"
    ACTIVE = "active"
    IDLE = "idle"
    TERMINATED = "terminated"


@dataclass(slots=True)
class TeamAllowedPath:
    """Path that all teammates can edit without asking."""

    path: str  # Directory path (absolute)
    tool_name: str  # The tool this applies to (e.g., "Edit", "Write")
    added_by: str  # Agent name who added this rule
    added_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class TeamMember:
    """A teammate in a team."""

    agent_id: str
    name: str
    agent_type: Optional[str] = None
    model: Optional[str] = None
    prompt: Optional[str] = None
    color: Optional[str] = None
    plan_mode_required: bool = False
    joined_at: datetime = field(default_factory=datetime.now)
    tmux_pane_id: Optional[str] = None
    cwd: str = ""
    worktree_path: Optional[str] = None
    session_id: Optional[str] = None
    subscriptions: list[str] = field(default_factory=list)
    backend_type: Optional[BackendType] = None
    is_active: bool = True
    mode: Optional[str] = None  # PermissionMode


@dataclass(slots=True)
class TeamFile:
    """Team configuration file structure."""

    name: str
    created_at: datetime = field(default_factory=datetime.now)
    lead_agent_id: str = ""
    lead_session_id: Optional[str] = None
    hidden_pane_ids: list[str] = field(default_factory=list)
    team_allowed_paths: list[TeamAllowedPath] = field(default_factory=list)
    members: list[TeamMember] = field(default_factory=list)
    description: Optional[str] = None


@dataclass(slots=True)
class SpawnTeamInput:
    """Input for spawnTeam operation."""

    agent_type: Optional[str] = None
    team_name: Optional[str] = None
    description: Optional[str] = None


@dataclass(slots=True)
class SpawnTeamOutput:
    """Output from spawnTeam operation."""

    team_name: str
    team_file_path: str
    lead_agent_id: str


@dataclass(slots=True)
class CleanupOutput:
    """Output from cleanup operation."""

    success: bool
    message: str
    team_name: Optional[str] = None


@dataclass(slots=True)
class TeleportResult:
    """Result of teleport operation."""

    success: bool
    message: str
    session_url: Optional[str] = None


def sanitize_name(name: str) -> str:
    """
    Sanitizes a name for use in tmux window names, worktree paths, and file paths.
    Replaces all non-alphanumeric characters with hyphens and lowercases.
    """
    import re

    return re.sub(r"[^a-zA-Z0-9]", "-", name).lower()


def sanitize_agent_name(name: str) -> str:
    """
    Sanitizes an agent name for use in deterministic agent IDs.
    Replaces @ with - to prevent ambiguity in the agentName@teamName format.
    """
    return name.replace("@", "-")
