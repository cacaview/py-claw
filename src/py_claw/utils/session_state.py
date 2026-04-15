"""
Session state management utilities.

Manages session state transitions (idle/running/requires_action) and external metadata
for CCR sidebar, push notifications, and SDK event streams.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class SessionState(str, Enum):
    """Session lifecycle states."""

    IDLE = "idle"
    RUNNING = "running"
    REQUIRES_ACTION = "requires_action"


@dataclass
class RequiresActionDetails:
    """
    Context carried with requires_action transitions so downstream surfaces
    can show what the session is blocked on.
    """

    tool_name: str
    action_description: str  # Human-readable summary, e.g. "Editing src/foo.ts"
    tool_use_id: str
    request_id: str
    input: dict | None = None  # Raw tool input for question options / plan content


# CCR external_metadata keys
@dataclass
class SessionExternalMetadata:
    """External metadata synced to CCR session API."""

    permission_mode: str | None = None
    is_ultraplan_mode: bool | None = None
    model: str | None = None
    pending_action: RequiresActionDetails | None = None
    post_turn_summary: object | None = None  # Opaque, typed at emit site
    task_summary: str | None = None  # Mid-turn progress line from summarizer


# Listeners
_state_listener: Callable[[SessionState, RequiresActionDetails | None], None] | None = None
_metadata_listener: Callable[[SessionExternalMetadata], None] | None = None
_permission_mode_listener: Callable[[str], None] | None = None


def set_session_state_changed_listener(
    cb: Callable[[SessionState, RequiresActionDetails | None], None] | None,
) -> None:
    """Register a listener for session state transitions."""
    global _state_listener
    _state_listener = cb


def set_session_metadata_changed_listener(
    cb: Callable[[SessionExternalMetadata], None] | None,
) -> None:
    """Register a listener for external metadata changes."""
    global _metadata_listener
    _metadata_listener = cb


def set_permission_mode_changed_listener(
    cb: Callable[[str], None] | None,
) -> None:
    """
    Register a listener for permission-mode changes from onChangeAppState.
    Wired by print.ts to emit an SDK system:status message so CCR/IDE clients
    see mode transitions in real time.
    """
    global _permission_mode_listener
    _permission_mode_listener = cb


# Internal state
_has_pending_action = False
_current_state: SessionState = SessionState.IDLE


def get_session_state() -> SessionState:
    """Get the current session state."""
    return _current_state


def notify_session_state_changed(
    state: SessionState,
    details: RequiresActionDetails | None = None,
) -> None:
    """
    Notify listeners of session state transitions.

    Mirrors details into external_metadata so GetSession carries the
    pending-action context. Cleared via RFC 7396 null on the next non-blocked transition.
    """
    global _current_state, _has_pending_action
    _current_state = state
    if _state_listener:
        _state_listener(state, details)

    if state == SessionState.REQUIRES_ACTION and details:
        _has_pending_action = True
        if _metadata_listener:
            _metadata_listener(
                SessionExternalMetadata(pending_action=details)
            )
    elif _has_pending_action:
        _has_pending_action = False
        if _metadata_listener:
            _metadata_listener(SessionExternalMetadata(pending_action=None))

    # task_summary cleared at idle so next turn doesn't briefly show previous turn's progress
    if state == SessionState.IDLE and _metadata_listener:
        _metadata_listener(SessionExternalMetadata(task_summary=None))


def notify_session_metadata_changed(metadata: SessionExternalMetadata) -> None:
    """Notify listeners of external metadata changes."""
    if _metadata_listener:
        _metadata_listener(metadata)


def notify_permission_mode_changed(mode: str) -> None:
    """
    Fired when toolPermissionContext.mode changes.
    Downstream listeners (CCR external_metadata PUT, SDK status stream) are
    both wired through this single choke point.
    """
    if _permission_mode_listener:
        _permission_mode_listener(mode)
