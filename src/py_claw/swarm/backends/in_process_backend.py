"""
InProcessBackend implements TeammateExecutor for in-process teammates.

Unlike pane-based backends (tmux/iTerm2), in-process teammates run in the
same process with isolated context via contextvars. They:
- Share resources (API client, MCP connections) with the leader
- Communicate via file-based mailbox (same as pane-based teammates)
- Are terminated via AbortController (not kill-pane)

Based on ClaudeCode-main/src/utils/swarm/backends/InProcessBackend.ts
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from ..in_process_runner import (
    kill_in_process_teammate,
    spawn_in_process_teammate,
    start_in_process_teammate,
    InProcessRunnerConfig,
    InProcessSpawnConfig,
    InProcessSpawnOutput,
    TeammateIdentity,
)
from .types import (
    TeammateExecutor,
    TeammateMessage,
    TeammateSpawnConfig,
    TeammateSpawnResult,
    BackendType,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class InProcessBackend:
    """
    InProcessBackend implements TeammateExecutor for in-process teammates.

    Unlike pane-based backends (tmux/iTerm2), in-process teammates run in the
    same process with isolated context via contextvars.
    """

    type: str = "in_process"

    def __init__(self):
        """Initialize the InProcessBackend."""
        self._context: Optional[dict] = None
        self._spawned_teammates: dict[str, dict] = {}

    def set_context(self, context: dict) -> None:
        """
        Sets the context for this backend.

        Called by TeammateTool before spawning to provide necessary context.

        Args:
            context: Context dict with setAppState and other helpers
        """
        self._context = context

    async def is_available(self) -> bool:
        """
        In-process backend is always available (no external dependencies).

        Returns:
            Always True
        """
        return True

    async def spawn(self, config: TeammateSpawnConfig) -> TeammateSpawnResult:
        """
        Spawns an in-process teammate.

        Uses spawnInProcessTeammate() to:
        1. Create teammate context
        2. Create independent AbortController
        3. Register teammate in state
        4. Start agent execution

        Args:
            config: Spawn configuration

        Returns:
            TeammateSpawnResult with success status
        """
        if not self._context:
            logger.debug(f"[InProcessBackend] spawn() called without context for {config.name}")
            return TeammateSpawnResult(
                success=False,
                agent_id=f"{config.name}@{config.team_name}",
                error="InProcessBackend not initialized. Call setContext() before spawn().",
            )

        logger.debug(f"[InProcessBackend] spawn() called for {config.name}")

        spawn_config = InProcessSpawnConfig(
            name=config.name,
            team_name=config.team_name,
            prompt=config.prompt,
            color=config.color,
            plan_mode_required=config.plan_mode_required,
            model=config.model,
        )

        result: InProcessSpawnOutput = await spawn_in_process_teammate(
            spawn_config,
            self._context,
        )

        # If spawn succeeded, start the agent execution loop
        if result.success and result.task_id and result.teammate_context and result.abort_controller:
            # Build runner config
            identity = TeammateIdentity(
                agent_id=result.agent_id,
                agent_name=config.name,
                team_name=config.team_name,
                color=config.color,
                plan_mode_required=config.plan_mode_required,
                parent_session_id=result.teammate_context.get("parent_session_id"),
            )

            runner_config = InProcessRunnerConfig(
                identity=identity,
                task_id=result.task_id,
                prompt=config.prompt,
                teammate_context=result.teammate_context,
                tool_use_context=self._context,
                abort_controller=result.abort_controller,
                model=config.model,
                system_prompt=config.system_prompt,
                system_prompt_mode=config.system_prompt_mode or "default",
                allowed_tools=config.permissions,
                allow_permission_prompts=config.allow_permission_prompts,
            )

            # Track spawned teammate
            self._spawned_teammates[result.agent_id] = {
                "task_id": result.task_id,
                "pane_id": None,
            }

            # Start the agent loop in the background (fire-and-forget)
            start_in_process_teammate(runner_config)

            logger.debug(f"[InProcessBackend] Started agent execution for {result.agent_id}")

        return TeammateSpawnResult(
            success=result.success,
            agent_id=result.agent_id,
            task_id=result.task_id,
            abort_controller=result.abort_controller,
            error=result.error,
        )

    async def send_message(self, agent_id: str, message: TeammateMessage) -> None:
        """
        Sends a message to an in-process teammate.

        All teammates use file-based mailboxes for simplicity.

        Args:
            agent_id: Agent ID (format: "agentName@teamName")
            message: Message to send
        """
        logger.debug(f"[InProcessBackend] sendMessage() to {agent_id}: {message.text[:50]}...")

        # Parse agentId to get agentName and teamName
        if "@" not in agent_id:
            raise ValueError(f"Invalid agentId format: {agent_id}. Expected format: agentName@teamName")

        parts = agent_id.rsplit("@", 1)
        agent_name = parts[0]
        team_name = parts[1] if len(parts) > 1 else ""

        # Import here to avoid circular dependencies
        from ..mailbox import write_to_mailbox

        # Write to file-based mailbox
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

        logger.debug(f"[InProcessBackend] sendMessage() completed for {agent_id}")

    async def terminate(self, agent_id: str, reason: Optional[str] = None) -> bool:
        """
        Gracefully terminates an in-process teammate.

        Sends a shutdown request message to the teammate and sets the
        shutdownRequested flag. The teammate processes the request and
        either approves (exits) or rejects (continues working).

        Args:
            agent_id: Agent ID to terminate
            reason: Optional reason for termination

        Returns:
            True if termination request sent successfully
        """
        logger.debug(f"[InProcessBackend] terminate() called for {agent_id}: {reason}")

        if not self._context:
            logger.debug(f"[InProcessBackend] terminate() failed: no context set for {agent_id}")
            return False

        # Find the task for this agent
        task_info = self._spawned_teammates.get(agent_id)
        if not task_info:
            logger.debug(f"[InProcessBackend] terminate() failed: agent {agent_id} not found")
            return False

        task_id = task_info["task_id"]

        # Get current state to find the task
        get_app_state = self._context.get("get_app_state")
        if not get_app_state:
            return False

        state = get_app_state()
        task = state.get("tasks", {}).get(task_id)

        if not task:
            logger.debug(f"[InProcessBackend] terminate() failed: task not found for {agent_id}")
            return False

        # Mark the task as shutdown requested
        self._context.get("set_app_state", lambda x: x)(lambda prev: {
            **prev,
            "tasks": {
                **prev.get("tasks", {}),
                task_id: {
                    **task,
                    "shutdown_requested": True,
                }
            }
        })

        logger.debug(f"[InProcessBackend] terminate() sent shutdown request to {agent_id}")

        return True

    async def kill(self, agent_id: str) -> bool:
        """
        Force kills an in-process teammate immediately.

        Uses the teammate's AbortController to cancel all async operations
        and updates the task state to 'killed'.

        Args:
            agent_id: Agent ID to kill

        Returns:
            True if killed successfully
        """
        logger.debug(f"[InProcessBackend] kill() called for {agent_id}")

        if not self._context:
            logger.debug(f"[InProcessBackend] kill() failed: no context set for {agent_id}")
            return False

        # Find the task for this agent
        task_info = self._spawned_teammates.get(agent_id)
        if not task_info:
            logger.debug(f"[InProcessBackend] kill() failed: agent {agent_id} not found")
            return False

        task_id = task_info["task_id"]
        set_app_state = self._context.get("set_app_state")

        # Kill via the existing helper function
        killed = kill_in_process_teammate(task_id, set_app_state)

        if killed:
            del self._spawned_teammates[agent_id]
            logger.debug(f"[InProcessBackend] kill() succeeded for {agent_id}")
        else:
            logger.debug(f"[InProcessBackend] kill() failed for {agent_id}")

        return killed

    async def is_active(self, agent_id: str) -> bool:
        """
        Checks if an in-process teammate is still active.

        Returns True if the teammate exists, has status 'running',
        and its AbortController has not been aborted.

        Args:
            agent_id: Agent ID to check

        Returns:
            True if the agent is active
        """
        logger.debug(f"[InProcessBackend] isActive() called for {agent_id}")

        if not self._context:
            logger.debug(f"[InProcessBackend] isActive() failed: no context set")
            return False

        # Find the task for this agent
        task_info = self._spawned_teammates.get(agent_id)
        if not task_info:
            logger.debug(f"[InProcessBackend] isActive(): agent {agent_id} not found")
            return False

        task_id = task_info["task_id"]

        # Get current state to check task status
        get_app_state = self._context.get("get_app_state")
        if not get_app_state:
            return False

        state = get_app_state()
        task = state.get("tasks", {}).get(task_id)

        if not task:
            logger.debug(f"[InProcessBackend] isActive(): task not found for {agent_id}")
            return False

        # Check if task is running and not aborted
        is_running = task.get("status") == "running"
        abort_controller = task.get("abort_controller")
        is_aborted = getattr(abort_controller, "aborted", True) if abort_controller else True

        active = is_running and not is_aborted

        logger.debug(
            f"[InProcessBackend] isActive() for {agent_id}: {active} (running={is_running}, aborted={is_aborted})"
        )

        return active


def create_in_process_backend() -> InProcessBackend:
    """
    Factory function to create an InProcessBackend instance.

    Returns:
        New InProcessBackend instance
    """
    return InProcessBackend()


__all__ = [
    "InProcessBackend",
    "create_in_process_backend",
]
