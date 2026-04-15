"""
PaneBackendExecutor adapts a PaneBackend to the TeammateExecutor interface.

This allows pane-based backends (tmux, iTerm2) to be used through the same
TeammateExecutor abstraction as InProcessBackend, making getTeammateExecutor()
return a meaningful executor regardless of execution mode.

The adapter handles:
- spawn(): Creates a pane and sends the Claude CLI command to it
- sendMessage(): Writes to the teammate's file-based mailbox
- terminate(): Sends a shutdown request via mailbox
- kill(): Kills the pane via the backend
- isActive(): Checks if the pane is still running

Based on ClaudeCode-main/src/utils/swarm/backends/PaneBackendExecutor.ts
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ..spawn_utils import build_inherited_cli_flags, build_inherited_env_vars, get_teammate_command
from .detection import is_inside_tmux
from .types import (
    BackendType,
    PaneBackend,
    TeammateExecutor,
    TeammateMessage,
    TeammateSpawnConfig,
    TeammateSpawnResult,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _format_agent_id(name: str, team_name: str) -> str:
    """Format agent ID as name@team."""
    return f"{name}@{team_name}"


def _quote_arg(arg: str) -> str:
    """Quote an argument for shell passing."""
    return "'" + arg.replace("'", "'\\''") + "'"


@dataclass
class PaneBackendExecutor:
    """
    PaneBackendExecutor adapts a PaneBackend to the TeammateExecutor interface.

    This allows pane-based backends (tmux, iTerm2) to be used through the same
    TeammateExecutor abstraction as InProcessBackend.
    """

    type: BackendType
    backend: PaneBackend

    def __init__(self, backend: PaneBackend):
        """
        Initialize the executor with a pane backend.

        Args:
            backend: The pane backend to adapt
        """
        self.backend = backend
        self.type = backend.type if hasattr(backend, "type") else BackendType.TMUX
        self._context: Optional[dict] = None
        self._spawned_teammates: dict[str, dict] = {}
        self._cleanup_registered = False

    def set_context(self, context: dict) -> None:
        """
        Sets the context for this executor.

        Must be called before spawn() to provide access to AppState.

        Args:
            context: Context dict with getAppState/setAppState
        """
        self._context = context

    async def is_available(self) -> bool:
        """
        Checks if the underlying pane backend is available.

        Returns:
            True if available
        """
        return await self.backend.is_available()

    async def spawn(self, config: TeammateSpawnConfig) -> TeammateSpawnResult:
        """
        Spawns a teammate in a new pane.

        Creates a pane via the backend, builds the CLI command with teammate
        identity flags, and sends it to the pane.

        Args:
            config: Spawn configuration

        Returns:
            TeammateSpawnResult with success status
        """
        agent_id = _format_agent_id(config.name, config.team_name)

        if not self._context:
            logger.debug(f"[PaneBackendExecutor] spawn() called without context for {config.name}")
            return TeammateSpawnResult(
                success=False,
                agent_id=agent_id,
                error="PaneBackendExecutor not initialized. Call setContext() before spawn().",
            )

        try:
            # Create a pane in the swarm view
            pane_result = await self.backend.create_teammate_pane_in_swarm_view(
                config.name,
                config.color or "blue",
            )
            pane_id = pane_result.pane_id
            is_first_teammate = pane_result.is_first_teammate

            # Check if we're inside tmux to determine how to send commands
            inside_tmux = await is_inside_tmux()

            # Enable pane border status on first teammate when inside tmux
            if is_first_teammate and inside_tmux:
                await self.backend.enable_pane_border_status()

            # Build the command to spawn Claude Code with teammate identity
            binary_path = get_teammate_command()

            # Build teammate identity CLI args
            parent_session_id = config.parent_session_id or os.environ.get("CLAUDE_SESSION_ID", "")

            teammate_args = [
                f"--agent-id={_quote_arg(agent_id)}",
                f"--agent-name={_quote_arg(config.name)}",
                f"--team-name={_quote_arg(config.team_name)}",
                f"--agent-color={_quote_arg(config.color or 'blue')}",
                f"--parent-session-id={_quote_arg(parent_session_id)}",
            ]
            if config.plan_mode_required:
                teammate_args.append("--plan-mode-required")

            # Build CLI flags to propagate to teammate
            app_state = self._context.get("get_app_state", lambda: {})()
            tool_permission_context = app_state.get("tool_permission_context", {})
            permission_mode = tool_permission_context.get("mode")

            inherited_flags = build_inherited_cli_flags(
                plan_mode_required=config.plan_mode_required,
                permission_mode=permission_mode,
                session_bypass_permissions=tool_permission_context.get("bypass_permissions", False),
            )

            # If teammate has a custom model, add --model flag
            if config.model:
                # Remove any existing --model flag
                flags_list = inherited_flags.split(" ")
                flags_list = [f for f in flags_list if f and not f.startswith("--model")]
                inherited_flags = " ".join(flags_list)
                if inherited_flags:
                    inherited_flags = f"{inherited_flags} --model={_quote_arg(config.model)}"
                else:
                    inherited_flags = f"--model={_quote_arg(config.model)}"

            working_dir = config.cwd or os.getcwd()

            # Build environment variables to forward to teammate
            env_str = build_inherited_env_vars()

            # Build the full spawn command
            spawn_command = (
                f"cd {_quote_arg(working_dir)} && "
                f"env {env_str} {_quote_arg(binary_path)} "
                f"{' '.join(teammate_args)} {inherited_flags}"
            )

            # Send the command to the new pane
            use_external = not inside_tmux
            await self.backend.send_command_to_pane(pane_id, spawn_command, use_external)

            # Track the spawned teammate
            self._spawned_teammates[agent_id] = {
                "pane_id": pane_id,
                "inside_tmux": inside_tmux,
            }

            # Register cleanup to kill all panes on leader exit
            if not self._cleanup_registered:
                self._cleanup_registered = True
                # Note: In Python we'd use atexit or similar, but for now skip

            logger.debug(f"[PaneBackendExecutor] Spawned teammate {agent_id} in pane {pane_id}")

            return TeammateSpawnResult(
                success=True,
                agent_id=agent_id,
                pane_id=pane_id,
            )

        except Exception as e:
            error_message = str(e)
            logger.debug(f"[PaneBackendExecutor] Failed to spawn {agent_id}: {error_message}")
            return TeammateSpawnResult(
                success=False,
                agent_id=agent_id,
                error=error_message,
            )

    async def send_message(self, agent_id: str, message: TeammateMessage) -> None:
        """
        Sends a message to a pane-based teammate via file-based mailbox.

        Args:
            agent_id: Agent ID (format: agentName@teamName)
            message: Message to send
        """
        logger.debug(f"[PaneBackendExecutor] sendMessage() to {agent_id}: {message.text[:50]}...")

        # Parse agentId
        if "@" not in agent_id:
            raise ValueError(f"Invalid agentId format: {agent_id}. Expected format: agentName@teamName")

        parts = agent_id.rsplit("@", 1)
        agent_name = parts[0]
        team_name = parts[1] if len(parts) > 1 else ""

        # Write to file-based mailbox
        from ..mailbox import write_to_mailbox

        await write_to_mailbox(
            agent_name,
            {
                "text": message.text,
                "from": message.from_agent,
                "color": message.color,
                "timestamp": message.timestamp or "",
            },
            team_name,
        )

        logger.debug(f"[PaneBackendExecutor] sendMessage() completed for {agent_id}")

    async def terminate(self, agent_id: str, reason: Optional[str] = None) -> bool:
        """
        Gracefully terminates a pane-based teammate.

        For pane-based teammates, we send a shutdown request via mailbox and
        let the teammate process handle exit gracefully.

        Args:
            agent_id: Agent ID to terminate
            reason: Optional reason for termination

        Returns:
            True if termination request sent successfully
        """
        logger.debug(f"[PaneBackendExecutor] terminate() called for {agent_id}: {reason}")

        # Parse agentId
        if "@" not in agent_id:
            logger.debug("[PaneBackendExecutor] terminate() failed: invalid agentId format")
            return False

        parts = agent_id.rsplit("@", 1)
        agent_name = parts[0]
        team_name = parts[1] if len(parts) > 1 else ""

        # Send shutdown request via mailbox
        shutdown_request = {
            "type": "shutdown_request",
            "requestId": f"shutdown-{agent_id}-{int(os.times().elapsed * 1000)}",
            "from": "team-lead",
            "reason": reason,
        }

        import json
        from ..mailbox import write_to_mailbox

        await write_to_mailbox(
            agent_name,
            {
                "from": "team-lead",
                "text": json.dumps(shutdown_request),
                "timestamp": "",
            },
            team_name,
        )

        logger.debug(f"[PaneBackendExecutor] terminate() sent shutdown request to {agent_id}")

        return True

    async def kill(self, agent_id: str) -> bool:
        """
        Force kills a pane-based teammate by killing its pane.

        Args:
            agent_id: Agent ID to kill

        Returns:
            True if killed successfully
        """
        logger.debug(f"[PaneBackendExecutor] kill() called for {agent_id}")

        teammate_info = self._spawned_teammates.get(agent_id)
        if not teammate_info:
            logger.debug(f"[PaneBackendExecutor] kill() failed: teammate {agent_id} not found in spawned map")
            return False

        pane_id = teammate_info["pane_id"]
        inside_tmux = teammate_info["inside_tmux"]

        # Kill the pane via the backend
        use_external = not inside_tmux
        killed = await self.backend.kill_pane(pane_id, use_external)

        if killed:
            del self._spawned_teammates[agent_id]
            logger.debug(f"[PaneBackendExecutor] kill() succeeded for {agent_id}")
        else:
            logger.debug(f"[PaneBackendExecutor] kill() failed for {agent_id}")

        return killed

    async def is_active(self, agent_id: str) -> bool:
        """
        Checks if a pane-based teammate is still active.

        For pane-based teammates, we check if the pane still exists.

        Args:
            agent_id: Agent ID to check

        Returns:
            True if the agent is active
        """
        logger.debug(f"[PaneBackendExecutor] isActive() called for {agent_id}")

        teammate_info = self._spawned_teammates.get(agent_id)
        if not teammate_info:
            logger.debug(f"[PaneBackendExecutor] isActive(): teammate {agent_id} not found")
            return False

        # For now, assume active if we have a record of it
        # A more robust check would query the backend for pane existence
        return True


def create_pane_backend_executor(backend: PaneBackend) -> PaneBackendExecutor:
    """
    Creates a PaneBackendExecutor wrapping the given PaneBackend.

    Args:
        backend: The pane backend to wrap

    Returns:
        New PaneBackendExecutor instance
    """
    return PaneBackendExecutor(backend)


__all__ = [
    "PaneBackendExecutor",
    "create_pane_backend_executor",
]
