"""
Swarm service implementation.

Multi-agent orchestration service for managing teams of Claude agents.
Reference: ClaudeCode-main/src/utils/swarm/
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .constants import (
    TEAM_LEAD_NAME,
    SWARM_SESSION_NAME,
    TMUX_COMMAND,
    HIDDEN_SESSION_NAME,
    TEAMMATE_COMMAND_ENV_VAR,
    TEAMMATE_COLOR_ENV_VAR,
    PLAN_MODE_REQUIRED_ENV_VAR,
    get_swarm_socket_name,
)
from .mailbox import (
    read_mailbox,
    write_to_mailbox,
    mark_message_as_read,
    clear_mailbox,
    create_idle_notification,
    create_permission_request,
    is_permission_response,
    is_shutdown_request,
)
from .types import (
    TeammateIdentity,
    TeammateContext,
    Task,
    TaskClaimResult,
)

logger = logging.getLogger(__name__)


@dataclass
class SwarmConfig:
    """Configuration for swarm team."""

    team_name: str
    session_name: str = SWARM_SESSION_NAME
    use_tmux: bool = True
    socket_name: str | None = None


class SwarmService:
    """
    Service for managing swarm multi-agent teams.

    Provides:
    - Team creation and management
    - Teammate spawning (in-process and tmux-based)
    - Inter-agent communication via mailbox
    - Task distribution
    - Permission bridging
    """

    def __init__(self, config: SwarmConfig | None = None) -> None:
        """
        Initialize the swarm service.

        Args:
            config: Optional swarm configuration
        """
        self.config = config or SwarmConfig(team_name="default")
        self._teammates: dict[str, TeammateContext] = {}
        self._is_lead: bool = False
        self._team_name = self.config.team_name

    def set_lead_mode(self, is_lead: bool = True) -> None:
        """
        Set whether this instance is the team lead.

        Args:
            is_lead: True if this is the team lead
        """
        self._is_lead = is_lead

    def is_lead(self) -> bool:
        """Check if this instance is the team lead."""
        return self._is_lead

    def get_lead_name(self) -> str:
        """Get the team lead name."""
        return TEAM_LEAD_NAME

    def create_teammate_identity(
        self,
        agent_name: str,
        color: str | None = None,
        plan_mode_required: bool = False,
    ) -> TeammateIdentity:
        """
        Create a new teammate identity.

        Args:
            agent_name: Name for the teammate
            color: Optional color for the teammate
            plan_mode_required: Whether plan mode is required

        Returns:
            TeammateIdentity dictionary
        """
        return {
            "agent_id": str(uuid.uuid4()),
            "agent_name": agent_name,
            "team_name": self._team_name,
            "parent_session_id": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
            "color": color,
            "plan_mode_required": plan_mode_required,
        }

    async def spawn_tmux_teammate(
        self,
        identity: TeammateIdentity,
        prompt: str,
        model: str | None = None,
    ) -> bool:
        """
        Spawn a teammate in a tmux window.

        Args:
            identity: The teammate's identity
            prompt: Initial prompt for the teammate
            model: Optional model override

        Returns:
            True if spawn successful
        """
        if not self._is_lead:
            logger.error("Only team lead can spawn teammates")
            return False

        try:
            # Build the command
            cmd = [
                TMUX_COMMAND,
                "new-window",
                "-n",
                identity["agent_name"],
            ]

            # Build environment
            env = os.environ.copy()
            env[TEAMMATE_COLOR_ENV_VAR] = identity.get("color", "")
            if identity.get("plan_mode_required"):
                env[PLAN_MODE_REQUIRED_ENV_VAR] = "true"

            # TODO: Implement actual teammate spawning with proper CLI args
            logger.info(f"Spawning tmux teammate: {identity['agent_name']}")

            return True

        except Exception as e:
            logger.error(f"Failed to spawn tmux teammate: {e}")
            return False

    async def spawn_in_process_teammate(
        self,
        identity: TeammateIdentity,
        prompt: str,
        agent_definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Spawn a teammate in the same process (for lightweight teammates).

        Args:
            identity: The teammate's identity
            prompt: Initial prompt for the teammate
            agent_definition: Optional custom agent definition

        Returns:
            Result with success status and messages
        """
        # TODO: Implement in-process teammate execution
        # This requires integrating with the agent runtime
        logger.info(f"Spawning in-process teammate: {identity['agent_name']}")

        return {
            "success": True,
            "messages": [],
        }

    async def send_message_to_teammate(
        self,
        teammate_name: str,
        message: str,
        from_name: str | None = None,
    ) -> bool:
        """
        Send a message to a teammate.

        Args:
            teammate_name: Name of the teammate
            message: Message text
            from_name: Optional sender name (defaults to team lead)

        Returns:
            True if send successful
        """
        sender = from_name or TEAM_LEAD_NAME

        swarm_message = {
            "from": sender,
            "text": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "color": None,
            "read": False,
        }

        try:
            write_to_mailbox(teammate_name, swarm_message, self._team_name)
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {teammate_name}: {e}")
            return False

    async def receive_message(
        self,
        agent_name: str,
        wait: bool = True,
        timeout_ms: int = 500,
    ) -> dict[str, Any] | None:
        """
        Receive a message from an agent's mailbox.

        Args:
            agent_name: Name of the agent
            wait: Whether to wait for a message
            timeout_ms: Timeout in milliseconds (if wait=True)

        Returns:
            Message dict or None
        """
        messages = read_mailbox(agent_name, self._team_name)

        # Find first unread message
        for i, msg in enumerate(messages):
            if not msg.get("read", False):
                mark_message_as_read(agent_name, i, self._team_name)
                return msg

        if not wait:
            return None

        # TODO: Implement waiting logic
        return None

    async def list_teammates(self) -> list[str]:
        """
        List all active teammates in the team.

        Returns:
            List of teammate names
        """
        return list(self._teammates.keys())

    async def shutdown_teammate(
        self,
        teammate_name: str,
        reason: str | None = None,
    ) -> bool:
        """
        Send shutdown request to a teammate.

        Args:
            teammate_name: Name of the teammate
            reason: Optional shutdown reason

        Returns:
            True if request sent successfully
        """
        shutdown_msg = {
            "type": "shutdown",
            "from": TEAM_LEAD_NAME,
            "reason": reason or "Team lead requested shutdown",
        }

        try:
            write_to_mailbox(teammate_name, shutdown_msg, self._team_name)
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown {teammate_name}: {e}")
            return False

    async def cleanup_team(self) -> None:
        """Clean up all team resources."""
        # Clear mailboxes
        for teammate_name in self._teammates.keys():
            clear_mailbox(teammate_name, self._team_name)

        clear_mailbox(TEAM_LEAD_NAME, self._team_name)

        self._teammates.clear()


# Global service instance
_swarm_service: SwarmService | None = None


def get_swarm_service() -> SwarmService:
    """Get the global swarm service instance."""
    global _swarm_service
    if _swarm_service is None:
        _swarm_service = SwarmService()
    return _swarm_service
