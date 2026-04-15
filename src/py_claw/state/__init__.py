"""
State management module for py_claw.

Provides React-like state management patterns using Observable pattern.

Based on ClaudeCode-main/src/state/ analysis:
- Store pattern (observable)
- AppState dataclass
- Selector pattern
- onChange observers

This module provides an alternative to the simple singleton State classes
used elsewhere in py_claw, with full thread-safety and subscription support.
"""
from __future__ import annotations

from .observable import Observable, ChangeDetector
from .app_state import AppState, create_default_app_state
from .store import Store, create_store, get_global_store
from .selectors import (
    get_viewed_teammate_task,
    get_active_agent_for_input,
    get_visible_tasks,
    get_task_count,
    is_bridge_connected,
    is_thinking_mode_enabled,
    get_expanded_view,
    get_mcp_client_count,
    get_enabled_plugin_count,
    get_plugin_errors,
)
from .observers import (
    StateObserver,
    on_state_change,
    register_observer,
)
from .teammate_helpers import (
    enter_teammate_view,
    exit_teammate_view,
    stop_or_dismiss_agent,
)

__all__ = [
    # Observable
    "Observable",
    "ChangeDetector",
    # AppState
    "AppState",
    "create_default_app_state",
    # Store
    "Store",
    "create_store",
    "get_global_store",
    # Selectors
    "get_viewed_teammate_task",
    "get_active_agent_for_input",
    # Observers
    "StateObserver",
    "on_state_change",
    "register_observer",
    # Teammate helpers
    "enter_teammate_view",
    "exit_teammate_view",
    "stop_or_dismiss_agent",
]
