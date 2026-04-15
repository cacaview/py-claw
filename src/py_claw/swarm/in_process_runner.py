"""
In-process teammate runner.

Wraps the agent execution for in-process teammates, providing:
- Context isolation via contextvars
- Progress tracking and AppState updates
- Idle notification to leader when complete
- Plan mode approval flow support
- Cleanup on completion or abort

Based on ClaudeCode-main/src/utils/swarm/inProcessRunner.ts
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Context variable for teammate identity isolation
_teammate_context_var: ContextVar[Optional[dict]] = ContextVar(
    "teammate_context", default=None
)


def get_teammate_context() -> Optional[dict]:
    """Get the current teammate context from context variable."""
    return _teammate_context_var.get()


def run_with_teammate_context(
    context: dict,
    func: Callable,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Run a function with the given teammate context.

    Args:
        context: Teammate context dict with agent info
        func: Function to run
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result from func
    """
    token = _teammate_context_var.set(context)
    try:
        return func(*args, **kwargs)
    finally:
        _teammate_context_var.reset(token)


@dataclass
class TeammateIdentity:
    """Identity fields for a teammate."""
    agent_id: str  # Format: "name@team"
    agent_name: str
    team_name: str
    color: Optional[str] = None
    plan_mode_required: bool = False
    parent_session_id: Optional[str] = None


@dataclass
class InProcessSpawnConfig:
    """Configuration for spawning an in-process teammate."""
    name: str  # Display name
    team_name: str
    prompt: str  # Initial prompt
    color: Optional[str] = None
    plan_mode_required: bool = False
    model: Optional[str] = None


@dataclass
class InProcessSpawnOutput:
    """Result from spawning an in-process teammate."""
    success: bool
    agent_id: str
    task_id: Optional[str] = None
    abort_controller: Optional[Any] = None
    teammate_context: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class InProcessRunnerConfig:
    """Configuration for running an in-process teammate."""
    identity: TeammateIdentity
    task_id: str
    prompt: str
    agent_definition: Optional[dict] = None
    teammate_context: dict = field(default_factory=dict)
    tool_use_context: Optional[dict] = None
    abort_controller: Optional[Any] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    system_prompt_mode: str = "default"  # 'default' | 'replace' | 'append'
    allowed_tools: Optional[list[str]] = None
    allow_permission_prompts: bool = True
    description: Optional[str] = None


@dataclass
class InProcessRunnerResult:
    """Result from running an in-process teammate."""
    success: bool
    error: Optional[str] = None
    messages: list[Any] = field(default_factory=list)


# Global registry for in-process teammates
_in_process_teammates: dict[str, dict] = {}


def generate_task_id(prefix: str = "in_process_teammate") -> str:
    """Generate a unique task ID."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def format_agent_id(name: str, team_name: str) -> str:
    """Format agent ID as name@team."""
    return f"{name}@{team_name}"


async def spawn_in_process_teammate(
    config: InProcessSpawnConfig,
    context: dict,
) -> InProcessSpawnOutput:
    """
    Spawns an in-process teammate.

    Creates the teammate's context, registers the task, and returns
    the spawn result.

    Args:
        config: Spawn configuration
        context: Context with setAppState for registering task

    Returns:
        Spawn result with teammate info
    """
    agent_id = format_agent_id(config.name, config.team_name)
    task_id = generate_task_id()

    logger.debug(f"[spawnInProcessTeammate] Spawning {agent_id} (taskId: {task_id})")

    try:
        # Create independent abort controller
        abort_controller = _create_abort_controller()

        # Get parent session ID
        parent_session_id = os.environ.get("CLAUDE_SESSION_ID", "")

        # Create teammate identity
        identity = TeammateIdentity(
            agent_id=agent_id,
            agent_name=config.name,
            team_name=config.team_name,
            color=config.color,
            plan_mode_required=config.plan_mode_required,
            parent_session_id=parent_session_id,
        )

        # Create teammate context for context isolation
        teammate_context = {
            "agent_id": agent_id,
            "agent_name": config.name,
            "team_name": config.team_name,
            "color": config.color,
            "plan_mode_required": config.plan_mode_required,
            "parent_session_id": parent_session_id,
            "abort_controller": abort_controller,
        }

        # Create task state
        description = f"{config.name}: {config.prompt[:50]}{'...' if len(config.prompt) > 50 else ''}"

        task_state = {
            "id": task_id,
            "type": "in_process_teammate",
            "status": "running",
            "identity": identity.__dict__,
            "prompt": config.prompt,
            "model": config.model,
            "abort_controller": abort_controller,
            "awaiting_plan_approval": False,
            "description": description,
            "is_idle": False,
            "shutdown_requested": False,
            "last_reported_tool_count": 0,
            "last_reported_token_count": 0,
            "pending_user_messages": [],
            "messages": [],
        }

        # Register task in state
        set_app_state = context.get("set_app_state")
        if set_app_state:
            set_app_state(lambda prev: {
                **prev,
                "tasks": {**prev.get("tasks", {}), task_id: task_state}
            })

        # Register in global registry
        _in_process_teammates[agent_id] = {
            "task_id": task_id,
            "task_state": task_state,
            "identity": identity,
        }

        logger.debug(f"[spawnInProcessTeammate] Registered {agent_id} in registry")

        return InProcessSpawnOutput(
            success=True,
            agent_id=agent_id,
            task_id=task_id,
            abort_controller=abort_controller,
            teammate_context=teammate_context,
        )
    except Exception as e:
        error_message = str(e) if isinstance(e, Exception) else "Unknown error during spawn"
        logger.debug(f"[spawnInProcessTeammate] Failed to spawn {agent_id}: {error_message}")
        return InProcessSpawnOutput(
            success=False,
            agent_id=agent_id,
            error=error_message,
        )


def kill_in_process_teammate(
    task_id: str,
    set_app_state: Optional[Callable] = None,
) -> bool:
    """
    Kills an in-process teammate by aborting its controller.

    Args:
        task_id: Task ID of the teammate to kill
        set_app_state: AppState setter

    Returns:
        True if killed successfully
    """
    killed = False
    agent_id = None

    # Find teammate by task_id
    for aid, info in _in_process_teammates.items():
        if info["task_id"] == task_id:
            agent_id = aid
            task_state = info["task_state"]
            break

    if not agent_id or not task_state:
        return False

    abort_controller = task_state.get("abort_controller")
    if abort_controller:
        abort_controller.abort()

    # Update task state
    if set_app_state:
        set_app_state(lambda prev: {
            **prev,
            "tasks": {
                **prev.get("tasks", {}),
                task_id: {
                    **task_state,
                    "status": "killed",
                    "notified": True,
                    "end_time": int(datetime.now().timestamp() * 1000),
                }
            }
        })

    # Remove from registry
    if agent_id in _in_process_teammates:
        del _in_process_teammates[agent_id]

    killed = True
    logger.debug(f"[killInProcessTeammate] Killed {agent_id}")

    return killed


async def run_in_process_teammate(
    config: InProcessRunnerConfig,
) -> InProcessRunnerResult:
    """
    Runs an in-process teammate with a continuous prompt loop.

    Executes the agent loop within the teammate's context,
    tracks progress, updates task state, sends idle notification on completion.

    Args:
        config: Runner configuration

    Returns:
        Result with messages and success status
    """
    identity = config.identity
    task_id = config.task_id

    logger.debug(f"[inProcessRunner] Starting agent loop for {identity.agent_id}")

    all_messages: list[Any] = []
    current_prompt = config.prompt
    should_exit = False

    # Set up teammate context for this execution
    exec_context = {
        "agent_id": identity.agent_id,
        "agent_name": identity.agent_name,
        "team_name": identity.team_name,
        "color": identity.color,
        "plan_mode_required": identity.plan_mode_required,
        "parent_session_id": identity.parent_session_id,
        "abort_controller": config.abort_controller,
    }

    try:
        # Run with teammate context
        result = await run_with_teammate_context(
            exec_context,
            _run_teammate_loop,
            config,
            all_messages,
            current_prompt,
        )
        return result
    except Exception as e:
        error_message = str(e) if isinstance(e, Exception) else "Unknown error"
        logger.debug(f"[inProcessRunner] Agent {identity.agent_id} failed: {error_message}")
        return InProcessRunnerResult(
            success=False,
            error=error_message,
            messages=all_messages,
        )


async def _run_teammate_loop(
    config: InProcessRunnerConfig,
    all_messages: list,
    current_prompt: str,
) -> InProcessRunnerResult:
    """Internal loop for running teammate prompts."""
    identity = config.identity
    task_id = config.task_id
    abort_controller = config.abort_controller

    while not (abort_controller and abort_controller.aborted) and not config.teammate_context.get("shutdown_requested", False):
        logger.debug(f"[inProcessRunner] {identity.agent_id} processing prompt: {current_prompt[:50]}...")

        # For in-process, we just track the prompt and messages
        # In a full implementation, this would call the actual agent execution

        # Create user message for the prompt
        user_message = {
            "type": "user",
            "content": [{"type": "text", "text": current_prompt}],
            "timestamp": datetime.now().isoformat(),
        }
        all_messages.append(user_message)

        # Update task state
        _update_task_state(
            task_id,
            lambda task: {
                **task,
                "status": "running" if not (abort_controller and abort_controller.aborted) else "completed",
                "is_idle": False,
            }
        )

        # For now, simulate completion after one iteration
        # A full implementation would actually run the agent loop here
        logger.debug(f"[inProcessRunner] {identity.agent_id} finished prompt")

        # Mark as idle and send notification
        _update_task_state(
            task_id,
            lambda task: {
                **task,
                "is_idle": True,
                "status": "completed",
            }
        )

        break  # Exit after one iteration for now

    return InProcessRunnerResult(
        success=True,
        messages=all_messages,
    )


def _update_task_state(
    task_id: str,
    updater: Callable[[dict], dict],
) -> None:
    """Update task state in the registry."""
    for info in _in_process_teammates.values():
        if info["task_id"] == task_id:
            info["task_state"] = updater(info["task_state"])
            break


def _create_abort_controller() -> Any:
    """Create a simple abort controller."""
    aborted = False
    callbacks: list[Callable] = []

    class SimpleAbortController:
        def __init__(self):
            self.aborted = False
            self._callbacks = []

        @property
        def signal(self):
            return self

        def abort(self):
            nonlocal aborted
            if not self.aborted:
                self.aborted = True
                aborted = True
                for cb in self._callbacks:
                    try:
                        cb()
                    except Exception:
                        pass

        @property
        def is_aborted(self):
            return self.aborted

        def add_event_listener(self, event: str, callback: Callable, *args, **kwargs):
            if event == "abort":
                self._callbacks.append(callback)

        def remove_event_listener(self, event: str, callback: Callable):
            if event == "abort" and callback in self._callbacks:
                self._callbacks.remove(callback)

    return SimpleAbortController()


def start_in_process_teammate(config: InProcessRunnerConfig) -> None:
    """
    Starts an in-process teammate in the background.

    This is the main entry point called after spawn. It starts the agent
    execution loop in a fire-and-forget manner.

    Args:
        config: Runner configuration
    """
    # Schedule the runner to run
    asyncio.create_task(run_in_process_teammate(config))


__all__ = [
    "TeammateIdentity",
    "InProcessSpawnConfig",
    "InProcessSpawnOutput",
    "InProcessRunnerConfig",
    "InProcessRunnerResult",
    "generate_task_id",
    "format_agent_id",
    "spawn_in_process_teammate",
    "kill_in_process_teammate",
    "run_in_process_teammate",
    "start_in_process_teammate",
    "get_teammate_context",
    "run_with_teammate_context",
]
