"""
State observers for side-effect handling.

Handles state change side effects similar to onChangeAppState.ts
Based on ClaudeCode-main/src/state/onChangeAppState.ts
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .app_state import AppState


class StateObserver(ABC):
    """
    Base class for state change observers.

    Subclass and override specific methods to handle state changes.
    """

    @abstractmethod
    def on_state_change(
        self, old_state: "AppState", new_state: "AppState"
    ) -> None:
        """
        Called on any state change.

        Args:
            old_state: Previous state
            new_state: New state
        """
        pass

    def on_ui_change(
        self, old_state: "AppState", new_state: "AppState"
    ) -> None:
        """Called when UI state changes."""
        pass

    def on_task_change(
        self, old_state: "AppState", new_state: "AppState"
    ) -> None:
        """Called when task state changes."""
        pass

    def on_mcp_change(
        self, old_state: "AppState", new_state: "AppState"
    ) -> None:
        """Called when MCP state changes."""
        pass

    def on_auth_change(
        self, old_state: "AppState", new_state: "AppState"
    ) -> None:
        """Called when auth state changes."""
        pass

    def on_permission_change(
        self, old_state: "AppState", new_state: "AppState"
    ) -> None:
        """Called when permission state changes."""
        pass


def on_state_change(
    old_state: "AppState", new_state: "AppState"
) -> None:
    """
    Default state change handler.

    This is the single entry point for all state changes.
    Routes to specific handlers based on what changed.

    Args:
        old_state: Previous state
        new_state: New state
    """
    # UI changes
    if old_state.ui != new_state.ui:
        _notify("ui_change", old_state, new_state)

    # Task changes
    if old_state.tasks != new_state.tasks:
        _notify("task_change", old_state, new_state)

    # MCP changes
    if (
        old_state.mcp_clients != new_state.mcp_clients
        or old_state.mcp_tools != new_state.mcp_tools
        or old_state.mcp_servers != new_state.mcp_servers
    ):
        _notify("mcp_change", old_state, new_state)

    # Auth changes
    if old_state.auth != new_state.auth:
        _notify("auth_change", old_state, new_state)

    # Permission changes
    if (
        old_state.permission != new_state.permission
        or old_state.tool_permission_context != new_state.tool_permission_context
    ):
        _notify("permission_change", old_state, new_state)

    # Settings changes
    if old_state.settings != new_state.settings:
        _notify("settings_change", old_state, new_state)


# Observer registry
_observers: list[tuple[str, Callable[..., None]]] = []


def register_observer(
    event_type: str, callback: Callable[..., None]
) -> Callable[[], None]:
    """
    Register an observer for a specific event type.

    Args:
        event_type: Event type to watch ("*", "ui_change", "task_change", etc.)
        callback: Function to call when event occurs

    Returns:
        Unsubscribe function
    """
    _observers.append((event_type, callback))

    def unsubscribe() -> None:
        _observers.remove((event_type, callback))

    return unsubscribe


def _notify(event_type: str, old_state: "AppState", new_state: "AppState") -> None:
    """Notify all matching observers."""
    for obs_type, callback in list(_observers):
        if obs_type == "*" or obs_type == event_type:
            try:
                callback(old_state, new_state)
            except Exception:
                pass
