"""Tests for session_state services."""


import pytest

from py_claw.services.session_state import (
    SessionState,
    get_session_state,
    notify_permission_mode_changed,
    notify_session_metadata_changed,
    notify_session_state_changed,
    set_permission_mode_changed_listener,
    set_session_metadata_changed_listener,
    set_session_state_changed_listener,
)


class TestSessionState:
    """Tests for session state management."""

    def setup_method(self):
        """Reset global state before each test."""
        # Reset module-level state by reimporting
        import importlib
        import py_claw.services.session_state.session_state as sm
        importlib.reload(sm)

    def test_get_initial_state(self):
        """Test getting initial session state."""
        from py_claw.services.session_state.session_state import get_session_state

        state = get_session_state()
        assert state == "idle"

    def test_set_and_notify_state_changed(self):
        """Test setting session state changed listener."""
        from py_claw.services.session_state.session_state import (
            get_session_state,
            notify_session_state_changed,
            set_session_state_changed_listener,
        )

        states_received = []

        def listener(state, details):
            states_received.append((state, details))

        set_session_state_changed_listener(listener)
        notify_session_state_changed("running")

        assert len(states_received) == 1
        assert states_received[0][0] == "running"
        assert states_received[0][1] is None

    def test_notify_requires_action_with_details(self):
        """Test notifying requires_action with details."""
        from py_claw.services.session_state.session_state import (
            _has_pending_action,
            notify_session_state_changed,
            set_session_metadata_changed_listener,
            set_session_state_changed_listener,
        )

        states_received = []
        metadata_received = []

        set_session_state_changed_listener(lambda s, d: states_received.append((s, d)))
        set_session_metadata_changed_listener(lambda m: metadata_received.append(m))

        details = {
            "tool_name": "Bash",
            "action_description": "Running npm install",
            "tool_use_id": "123",
            "request_id": "456",
        }
        notify_session_state_changed("requires_action", details)

        assert len(states_received) == 1
        assert states_received[0][0] == "requires_action"
        assert states_received[0][1] == details

    def test_permission_mode_changed(self):
        """Test permission mode change notification."""
        from py_claw.services.session_state.session_state import (
            notify_permission_mode_changed,
            set_permission_mode_changed_listener,
        )

        modes_received = []

        def listener(mode):
            modes_received.append(mode)

        set_permission_mode_changed_listener(listener)
        notify_permission_mode_changed("allow")

        assert len(modes_received) == 1
        assert modes_received[0] == "allow"

    def test_session_metadata_changed(self):
        """Test session metadata change notification."""
        from py_claw.services.session_state.session_state import (
            notify_session_metadata_changed,
            set_session_metadata_changed_listener,
        )

        metadata_received = []

        def listener(metadata):
            metadata_received.append(metadata)

        set_session_metadata_changed_listener(listener)
        notify_session_metadata_changed({"model": "claude-3-opus"})

        assert len(metadata_received) == 1
        assert metadata_received[0]["model"] == "claude-3-opus"

    def test_state_transitions_idle_to_running_to_idle(self):
        """Test complete state transition cycle."""
        from py_claw.services.session_state.session_state import (
            get_session_state,
            notify_session_state_changed,
        )

        notify_session_state_changed("running")
        assert get_session_state() == "running"

        notify_session_state_changed("idle")
        assert get_session_state() == "idle"
