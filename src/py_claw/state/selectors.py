"""
Selector functions for derived state.

Pure functions that compute derived state from AppState.
Based on ClaudeCode-main/src/state/selectors.ts
"""
from __future__ import annotations

from typing import Any, Optional

from .app_state import AppState


def get_viewed_teammate_task(state: AppState) -> Optional[Any]:
    """
    Get the currently viewed teammate task.

    Args:
        state: Current app state

    Returns:
        Teammate task if viewing one, None otherwise
    """
    if not state.viewing_agent_task_id:
        return None

    task = state.tasks.get(state.viewing_agent_task_id)
    if task and _is_in_process_teammate_task(task):
        return task
    return None


def get_active_agent_for_input(state: AppState) -> Optional[str]:
    """
    Get the active agent ID for input routing.

    Args:
        state: Current app state

    Returns:
        Agent ID or None
    """
    return state.selected_agent_id


def get_visible_tasks(state: AppState) -> list[Any]:
    """
    Get list of visible tasks.

    Args:
        state: Current app state

    Returns:
        List of visible task objects
    """
    return list(state.tasks.values())


def get_task_count(state: AppState) -> int:
    """
    Get total number of tasks.

    Args:
        state: Current app state

    Returns:
        Task count
    """
    return len(state.tasks)


def is_bridge_connected(state: AppState) -> bool:
    """
    Check if remote bridge is connected.

    Args:
        state: Current app state

    Returns:
        True if bridge is connected
    """
    return state.remote_connection_status == "connected"


def is_thinking_mode_enabled(state: AppState) -> bool:
    """
    Check if thinking mode is enabled.

    Args:
        state: Current app state

    Returns:
        True if thinking is enabled
    """
    return state.thinking_enabled


def get_expanded_view(state: AppState) -> str:
    """
    Get current expanded view mode.

    Args:
        state: Current app state

    Returns:
        Expanded view identifier
    """
    return getattr(state, "expanded_view", "none")


def get_mcp_client_count(state: AppState) -> int:
    """
    Get number of MCP clients.

    Args:
        state: Current app state

    Returns:
        MCP client count
    """
    return len(state.mcp_clients)


def get_enabled_plugin_count(state: AppState) -> int:
    """
    Get number of enabled plugins.

    Args:
        state: Current app state

    Returns:
        Enabled plugin count
    """
    return len(state.plugins.enabled)


def get_plugin_errors(state: AppState) -> dict[str, str]:
    """
    Get plugin errors.

    Args:
        state: Current app state

    Returns:
        Dictionary of plugin_id -> error_message
    """
    return state.plugins.errors


# Helper functions

def _is_in_process_teammate_task(task: Any) -> bool:
    """Check if task is an in-process teammate task."""
    if not task:
        return False
    # Check task type indicator
    task_type = getattr(task, "type", None) or getattr(task, "task_type", None)
    return task_type in ("teammate", "in_process", None)
