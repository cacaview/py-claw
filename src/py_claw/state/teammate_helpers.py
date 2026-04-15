"""
Teammate view helpers for task state management.

Based on ClaudeCode-main/src/state/teammateViewHelpers.ts
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from .app_state import AppState


# PANEL_GRACE_MS from framework.ts — kept in sync
PANEL_GRACE_MS = 30_000


def _is_local_agent(task: Any) -> bool:
    """Check if task is a local agent task."""
    if not isinstance(task, dict):
        return getattr(task, "type", None) == "local_agent"
    return task.get("type") == "local_agent"


def _is_terminal_task_status(task: Any) -> bool:
    """Check if task has a terminal status."""
    if not isinstance(task, dict):
        return getattr(task, "status", None) in (
            "completed",
            "error",
            "cancelled",
            "failed",
        )
    status = task.get("status", "")
    return status in ("completed", "error", "cancelled", "failed")


def _release(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return task released back to stub form: retain dropped,
    messages cleared, evictAfter set if terminal.
    """
    result = dict(task)
    result["retain"] = False
    result.pop("messages", None)
    result["disk_loaded"] = False

    if _is_terminal_task_status(task):
        result["evict_after"] = int(time.time() * 1000) + PANEL_GRACE_MS
    else:
        result.pop("evict_after", None)

    return result


def enter_teammate_view(
    task_id: str,
    set_app_state: Callable[[Callable[[AppState], AppState]], None],
) -> None:
    """
    Transitions the UI to view a teammate's transcript.

    Sets viewingAgentTaskId and, for local_agent, retain: true
    (blocks eviction, enables stream-append, triggers disk bootstrap)
    and clears evictAfter. If switching from another agent,
    releases the previous one back to stub.

    Args:
        task_id: ID of the teammate task to view
        set_app_state: State setter function
    """
    prev_id: Optional[str] = None
    prev_task: Optional[Dict[str, Any]] = None

    def updater(state: AppState) -> AppState:
        nonlocal prev_id, prev_task

        tasks = dict(state.tasks)
        prev_id = getattr(state, "viewing_agent_task_id", None)
        prev_task = tasks.get(prev_id) if prev_id else None

        # Check if switching from another agent
        switching = (
            prev_id is not None
            and prev_id != task_id
            and _is_local_agent(prev_task)
            and prev_task.get("retain", False)
        )

        task = tasks.get(task_id)
        needs_retain = (
            _is_local_agent(task)
            and not task.get("retain", False)
        ) or task.get("evict_after") is not None

        needs_view = (
            getattr(state, "viewing_agent_task_id", None) != task_id
            or getattr(state, "view_selection_mode", None) != "viewing-agent"
        )

        if not needs_retain and not needs_view and not switching:
            return state

        if switching or needs_retain:
            if switching and prev_id:
                tasks[prev_id] = _release(prev_task)
            if needs_retain and task:
                tasks[task_id] = {
                    **task,
                    "retain": True,
                    "evict_after": None,
                }

        return AppState(
            **{**state.__dict__,
               "tasks": tasks,
               "viewing_agent_task_id": task_id,
               "view_selection_mode": "viewing-agent"}
        )

    set_app_state(updater)


def exit_teammate_view(
    set_app_state: Callable[[Callable[[AppState], AppState]], None],
) -> None:
    """
    Exit teammate transcript view and return to leader's view.

    Drops retain and clears messages back to stub form; if terminal,
    schedules eviction via evictAfter so the row lingers briefly.

    Args:
        set_app_state: State setter function
    """
    def updater(state: AppState) -> AppState:
        task_id = getattr(state, "viewing_agent_task_id", None)
        cleared = {
            **state.__dict__,
            "viewing_agent_task_id": None,
            "view_selection_mode": "none",
        }

        if task_id is None:
            return (
                state
                if getattr(state, "view_selection_mode", None) == "none"
                else AppState(**cleared)
            )

        task = state.tasks.get(task_id)
        if not _is_local_agent(task) or not task.get("retain", False):
            return AppState(**cleared)

        tasks = dict(state.tasks)
        tasks[task_id] = _release(task)

        return AppState(**{**cleared, "tasks": tasks})

    set_app_state(updater)


def stop_or_dismiss_agent(
    task_id: str,
    set_app_state: Callable[[Callable[[AppState], AppState]], None],
) -> None:
    """
    Context-sensitive x: running → abort, terminal → dismiss.

    Dismiss sets evictAfter=0 so the filter hides immediately.
    If viewing the dismissed agent, also exits to leader.

    Args:
        task_id: ID of the agent task
        set_app_state: State setter function
    """
    def updater(state: AppState) -> AppState:
        task = state.tasks.get(task_id)
        if not _is_local_agent(task):
            return state

        # If running, abort
        if task.get("status") == "running":
            # Abort controller should be called by caller
            return state

        # If already dismissed (evictAfter=0), no-op
        if task.get("evict_after") == 0:
            return state

        viewing_this = getattr(state, "viewing_agent_task_id", None) == task_id

        tasks = dict(state.tasks)
        released = _release(task)
        released["evict_after"] = 0
        tasks[task_id] = released

        result = {**state.__dict__, "tasks": tasks}
        if viewing_this:
            result["viewing_agent_task_id"] = None
            result["view_selection_mode"] = "none"

        return AppState(**result)

    set_app_state(updater)
