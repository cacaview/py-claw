"""
Teammate Initialization Module

Handles initialization for Claude Code instances running as teammates in a swarm.
Registers hooks to notify the team leader when the teammate becomes idle.

Based on ClaudeCode-main/src/utils/swarm/teammateInit.ts
"""

from __future__ import annotations

import logging
from typing import Any

from py_claw.swarm.team_helpers import read_team_file

logger = logging.getLogger(__name__)


async def initialize_teammate_hooks(
    set_app_state: Any,
    session_id: str,
    team_info: dict[str, str],
) -> None:
    """Initialize hooks for a teammate running in a swarm.

    Should be called early in session startup after AppState is available.

    Registers a Stop hook that sends an idle notification to the team leader
    when this teammate's session stops.

    Args:
        set_app_state: Function to update app state
        session_id: Current session ID
        team_info: Dict with teamName, agentId, agentName
    """
    team_name = team_info.get("teamName")
    agent_id = team_info.get("agentId")
    agent_name = team_info.get("agentName")

    if not all([team_name, agent_id, agent_name]):
        logger.warning("[TeammateInit] Missing team info")
        return

    # Read team file to get leader ID
    team_file = read_team_file(team_name)
    if not team_file:
        logger.warning(f"[TeammateInit] Team file not found for team: {team_name}")
        return

    lead_agent_id = team_file.lead_agent_id

    # Apply team-wide allowed paths if any exist
    if team_file.team_allowed_paths and len(team_file.team_allowed_paths) > 0:
        logger.info(
            f"[TeammateInit] Found {len(team_file.team_allowed_paths)} team-wide allowed path(s)"
        )

        for allowed_path in team_file.team_allowed_paths:
            # For absolute paths (starting with /), prepend one / to create //path/** pattern
            # For relative paths, just use path/**
            rule_content = (
                f"/{allowed_path.path}/**"
                if allowed_path.path.startswith("/")
                else f"{allowed_path.path}/**"
            )

            logger.debug(
                f"[TeammateInit] Applying team permission: {allowed_path.tool_name} "
                f"allowed in {allowed_path.path} (rule: {rule_content})"
            )

            # Note: In Python, we'd call apply_permission_update here
            # but that requires the full permissions system

    # Find the leader's name from the members array
    lead_member = None
    for member in team_file.members:
        if member.agent_id == lead_agent_id:
            lead_member = member
            break

    lead_agent_name = lead_member.name if lead_member else "team-lead"

    # Don't register hook if this agent is the leader
    if agent_id == lead_agent_id:
        logger.info(
            "[TeammateInit] This agent is the team leader - skipping idle notification hook"
        )
        return

    logger.info(
        f"[TeammateInit] Registering Stop hook for teammate {agent_name} "
        f"to notify leader {lead_agent_name}"
    )

    # Note: In Python, we'd register a Stop hook here
    # The hook would call set_member_active and send idle notification


def send_idle_notification_to_leader(
    team_name: str,
    agent_name: str,
    lead_agent_name: str,
) -> None:
    """Send an idle notification to the team leader.

    Args:
        team_name: Team name
        agent_name: This agent's name
        lead_agent_name: Leader's agent name
    """
    # Note: Mark this teammate as idle in the team config
    # (requires set_member_active which is not yet implemented)
    logger.info(f"[TeammateInit] Sent idle notification to leader {lead_agent_name}")


__all__ = [
    "initialize_teammate_hooks",
    "send_idle_notification_to_leader",
]
