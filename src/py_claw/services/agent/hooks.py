"""
Agent frontmatter hooks service.

Supports agent-defined hooks from frontmatter (SubagentStart, SubagentStop, etc.)
that are scoped to the agent lifecycle and converted to session hooks.

This module provides:
- register_frontmatter_hooks(): Register hooks scoped to agent lifecycle
- clear_session_hooks(): Cleanup hooks when agent exits
- execute_subagent_start_hooks(): Execute SubagentStart hooks and yield additional contexts
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Generator

if TYPE_CHECKING:
    from py_claw.hooks.runtime import HookDispatchResult, HookRuntime
    from py_claw.settings.loader import SettingsLoadResult

logger = logging.getLogger(__name__)

# ─── Hook Event Types ───────────────────────────────────────────────────────────


@dataclass
class AgentHook:
    """A hook defined in agent frontmatter."""

    event: str
    prompt: str = ""
    # For tool hooks: tool name to trigger on
    tool_name: str | None = None
    # Whether this hook should block the operation
    blocking: bool = False


# ─── Hook Registry ───────────────────────────────────────────────────────────────


@dataclass
class _RegisteredHookSet:
    """Set of hooks registered for an agent."""

    agent_id: str
    hooks: list[AgentHook] = field(default_factory=list)
    settings_callback: Callable[[], SettingsLoadResult | None] | None = None
    runtime_callback: Callable[[], HookRuntime | None] | None = None


class _AgentHooksRegistry:
    """Thread-safe registry of agent-scoped hooks."""

    def __init__(self) -> None:
        self._hooks: dict[str, _RegisteredHookSet] = {}
        self._lock = threading.Lock()

    def register(
        self,
        agent_id: str,
        hooks: list[AgentHook],
        settings_callback: Callable[[], SettingsLoadResult | None] | None = None,
        runtime_callback: Callable[[], HookRuntime | None] | None = None,
    ) -> None:
        """Register hooks for an agent.

        Args:
            agent_id: Unique agent identifier
            hooks: List of hooks to register
            settings_callback: Callback to get current settings
            runtime_callback: Callback to get the hook runtime
        """
        with self._lock:
            self._hooks[agent_id] = _RegisteredHookSet(
                agent_id=agent_id,
                hooks=hooks,
                settings_callback=settings_callback,
                runtime_callback=runtime_callback,
            )
            logger.debug("Registered %d hooks for agent %s", len(hooks), agent_id)

    def unregister(self, agent_id: str) -> None:
        """Unregister hooks for an agent.

        Args:
            agent_id: Agent identifier
        """
        with self._lock:
            self._hooks.pop(agent_id, None)
            logger.debug("Unregistered hooks for agent %s", agent_id)

    def get(self, agent_id: str) -> _RegisteredHookSet | None:
        """Get registered hooks for an agent."""
        with self._lock:
            return self._hooks.get(agent_id)

    def get_all(self) -> dict[str, _RegisteredHookSet]:
        """Get all registered hooks."""
        with self._lock:
            return dict(self._hooks)


# Global hooks registry
_agent_hooks_registry = _AgentHooksRegistry()


# ─── Agent Hooks Service ────────────────────────────────────────────────────────


class AgentHooksService:
    """Service for managing agent frontmatter hooks.

    Provides:
    - register_frontmatter_hooks(): Register hooks scoped to agent lifecycle
    - clear_session_hooks(): Cleanup hooks when agent exits
    - execute_subagent_start_hooks(): Execute SubagentStart hooks and yield contexts
    """

    def __init__(
        self,
        cwd: str,
        settings_callback: Callable[[], SettingsLoadResult | None] | None = None,
        runtime_callback: Callable[[], HookRuntime | None] | None = None,
    ):
        """Initialize the agent hooks service.

        Args:
            cwd: Current working directory for hook execution
            settings_callback: Optional callback to get current settings
            runtime_callback: Optional callback to get the hook runtime
        """
        self._cwd = cwd
        self._settings_callback = settings_callback
        self._runtime_callback = runtime_callback

    def register_frontmatter_hooks(
        self,
        agent_id: str,
        hooks: list[AgentHook],
    ) -> None:
        """Register agent frontmatter hooks scoped to agent lifecycle.

        Frontmatter hooks are converted to session hooks and registered
        with the global hook runtime. They are keyed by agent_id so they
        can be cleared when the agent exits.

        For SubagentStart hooks, additional context is prepended to the
        agent's initial messages.

        Args:
            agent_id: Unique agent identifier
            hooks: List of frontmatter hooks
        """
        _agent_hooks_registry.register(
            agent_id=agent_id,
            hooks=hooks,
            settings_callback=self._settings_callback,
            runtime_callback=self._runtime_callback,
        )

    def clear_session_hooks(self, agent_id: str) -> None:
        """Clear hooks registered for an agent.

        Called when an agent exits to clean up its registered hooks.

        Args:
            agent_id: Agent identifier
        """
        _agent_hooks_registry.unregister(agent_id)
        logger.debug("Cleared hooks for agent %s", agent_id)

    def execute_subagent_start_hooks(
        self,
        agent_id: str,
        agent_type: str,
        signal: Any | None = None,
        timeout_ms: float = 30000.0,
    ) -> Generator[dict[str, Any], None, None]:
        """Execute SubagentStart hooks and yield additional contexts.

        SubagentStart hooks can return additional context strings that
        are prepended to the agent's initial messages.

        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent (e.g., "Explore", "Plan")
            signal: Optional AbortSignal for cancellation
            timeout_ms: Timeout in milliseconds for hook execution

        Yields:
            Dict with 'additional_contexts' key containing context strings
        """
        hook_set = _agent_hooks_registry.get(agent_id)
        if hook_set is None:
            return

        subagent_start_hooks = [
            h for h in hook_set.hooks if h.event == "SubagentStart"
        ]
        if not subagent_start_hooks:
            return

        runtime = (
            hook_set.runtime_callback()
            if hook_set.runtime_callback
            else None
        )
        settings = (
            hook_set.settings_callback()
            if hook_set.settings_callback
            else None
        )

        if runtime is None or settings is None:
            logger.debug(
                "Cannot execute SubagentStart hooks for agent %s: no runtime or settings",
                agent_id,
            )
            return

        # Execute each SubagentStart hook
        for hook in subagent_start_hooks:
            if signal is not None and getattr(signal, "aborted", False):
                break

            result: HookDispatchResult = runtime.run_subagent_start(
                settings=settings,
                cwd=self._cwd,
                agent_id=agent_id,
                agent_type=hook.prompt or agent_type,  # Use prompt as additional context
            )

            if result.content and "additionalContext" in result.content:
                yield {
                    "hook_name": "SubagentStart",
                    "additional_contexts": result.content["additionalContext"],
                }

    def get_registered_hooks(self, agent_id: str) -> list[AgentHook] | None:
        """Get hooks registered for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            List of registered hooks, or None if agent not found
        """
        hook_set = _agent_hooks_registry.get(agent_id)
        return hook_set.hooks if hook_set else None


# ─── Convenience Functions ─────────────────────────────────────────────────────


def register_agent_hooks(
    agent_id: str,
    hooks: list[AgentHook],
    cwd: str,
    settings_callback: Callable[[], SettingsLoadResult | None] | None = None,
    runtime_callback: Callable[[], HookRuntime | None] | None = None,
) -> None:
    """Register agent frontmatter hooks.

    Convenience function that creates a temporary AgentHooksService
    and registers the hooks.

    Args:
        agent_id: Unique agent identifier
        hooks: List of frontmatter hooks
        cwd: Current working directory
        settings_callback: Optional callback to get current settings
        runtime_callback: Optional callback to get the hook runtime
    """
    service = AgentHooksService(
        cwd=cwd,
        settings_callback=settings_callback,
        runtime_callback=runtime_callback,
    )
    service.register_frontmatter_hooks(agent_id, hooks)


def clear_agent_hooks(agent_id: str) -> None:
    """Clear hooks registered for an agent.

    Args:
        agent_id: Agent identifier
    """
    _agent_hooks_registry.unregister(agent_id)
