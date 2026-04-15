"""
Swarm Reconnection Module

Handles initialization of swarm context for teammates.
- Fresh spawns: Initialize from CLI args
- Resumed sessions: Initialize from teamName/agentName stored in the transcript

Based on ClaudeCode-main/src/utils/swarm/reconnection.ts
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from .team_helpers import get_team_file_path, read_team_file

if TYPE_CHECKING:
    from py_claw.types import AppState

logger = logging.getLogger(__name__)


def compute_initial_team_context(
    team_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> Optional[dict]:
    """
    Computes the initial teamContext for AppState.

    This is called synchronously at startup to compute the teamContext
    BEFORE the first interaction, eliminating the need for useEffect workarounds.

    Args:
        team_name: Team name from CLI args
        agent_id: Agent ID from CLI args (None for leader)
        agent_name: Agent name from CLI args

    Returns:
        The teamContext dict to include in initial state, or None if not a teammate
    """
    if not team_name or not agent_name:
        logger.debug(
            "[Reconnection] computeInitialTeamContext: No teammate context set (not a teammate)"
        )
        return None

    # Read team file to get lead agent ID
    team_file = read_team_file(team_name)
    if not team_file:
        logger.error(
            f"[computeInitialTeamContext] Could not read team file for {team_name}"
        )
        return None

    team_file_path = get_team_file_path(team_name)
    is_leader = not agent_id

    logger.debug(
        f"[Reconnection] Computed initial team context for {is_leader and 'leader' or f'teammate {agent_name}'} in team {team_name}"
    )

    return {
        "team_name": team_name,
        "team_file_path": str(team_file_path),
        "lead_agent_id": team_file.lead_agent_id,
        "self_agent_id": agent_id,
        "self_agent_name": agent_name,
        "is_leader": is_leader,
        "teammates": {},
    }


def initialize_teammate_context_from_session(
    team_name: str,
    agent_name: str,
) -> Optional[dict]:
    """
    Initialize teammate context from a resumed session.

    This is called when resuming a session that has teamName/agentName stored
    in the transcript. It sets up teamContext so that heartbeat
    and other swarm features work correctly.

    Args:
        team_name: Team name
        agent_name: Agent name

    Returns:
        The teamContext dict, or None if team file not found
    """
    # Read team file to get lead agent ID
    team_file = read_team_file(team_name)
    if not team_file:
        logger.error(
            f"[initializeTeammateContextFromSession] Could not read team file for {team_name} (agent: {agent_name})"
        )
        return None

    # Find the member in the team file to get their agentId
    member = None
    for m in team_file.members:
        if m.name == agent_name:
            member = m
            break

    if not member:
        logger.debug(
            f"[Reconnection] Member {agent_name} not found in team {team_name} - may have been removed"
        )

    agent_id = member.agent_id if member else None
    team_file_path = get_team_file_path(team_name)

    logger.debug(
        f"[Reconnection] Initialized agent context from session for {agent_name} in team {team_name}"
    )

    return {
        "team_name": team_name,
        "team_file_path": str(team_file_path),
        "lead_agent_id": team_file.lead_agent_id,
        "self_agent_id": agent_id,
        "self_agent_name": agent_name,
        "is_leader": False,
        "teammates": {},
    }


__all__ = [
    "compute_initial_team_context",
    "initialize_teammate_context_from_session",
]
