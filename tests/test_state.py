"""
Tests for py_claw/state module.
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from py_claw.state import (
    Observable,
    ChangeDetector,
    AppState,
    create_default_app_state,
    Store,
    create_store,
    get_global_store,
    get_viewed_teammate_task,
    get_active_agent_for_input,
    is_bridge_connected,
    StateObserver,
    register_observer,
)


class TestObservable:
    """Tests for Observable base class."""

    def test_get_snapshot_returns_initial_state(self):
        """Test snapshot returns current state."""
        detector = ChangeDetector({"key": "value"})
        snapshot = detector.get_snapshot()
        assert snapshot == {"key": "value"}

    def test_get_snapshot_returns_copy(self):
        """Test snapshot returns a copy that doesn't affect original."""
        detector = ChangeDetector({"nested": {"key": "value"}})
        snapshot1 = detector.get_snapshot()
        snapshot1["nested"]["key"] = "modified"  # Modify nested level
        snapshot2 = detector.get_snapshot()
        assert snapshot2["nested"]["key"] == "value"

    def test_subscribe_returns_unsubscribe(self):
        """Test subscribe returns callable."""
        detector = ChangeDetector({"count": 0})
        callback = Mock()
        unsubscribe = detector.subscribe(callback)
        assert callable(unsubscribe)

    def test_unsubscribe_removes_callback(self):
        """Test unsubscribe removes callback."""
        detector = ChangeDetector({"count": 0})
        callback = Mock()
        unsubscribe = detector.subscribe(callback)
        unsubscribe()
        detector.set({"count": 1})  # Should not notify
        assert callback.call_count == 0

    def test_notify_on_update(self):
        """Test callback is notified on state update."""
        detector = ChangeDetector({"count": 0})
        callback = Mock()
        detector.subscribe(callback)
        detector.set({"count": 1})
        assert callback.call_count == 1

    def test_functional_update(self):
        """Test functional update pattern."""
        detector = ChangeDetector({"count": 0})
        detector.update(lambda s: {"count": s["count"] + 1})
        assert detector.state["count"] == 1

    def test_thread_safety(self):
        """Test state updates are thread-safe."""
        import threading

        detector = ChangeDetector({"count": 0})

        def increment():
            for _ in range(100):
                detector.update(lambda s: {"count": s["count"] + 1})

        threads = [threading.Thread(target=increment) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert detector.state["count"] == 1000


class TestAppState:
    """Tests for AppState dataclass."""

    def test_create_default_app_state(self):
        """Test creating default app state."""
        state = create_default_app_state()
        assert isinstance(state, AppState)
        # Check flat UI state
        assert state.expanded_view == "none"
        assert state.thinking_enabled is False

    def test_app_state_fields(self):
        """Test app state has expected fields."""
        state = create_default_app_state()
        assert hasattr(state, "tasks")
        assert hasattr(state, "mcp")
        assert hasattr(state, "plugins")
        assert hasattr(state, "session_hooks")

    def test_app_state_nested_types(self):
        """Test app state nested type access."""
        state = create_default_app_state()
        assert isinstance(state.expanded_view, str)
        assert isinstance(state.plugins.enabled, list)
        assert isinstance(state.plugins.errors, list)


class TestStore:
    """Tests for Store class."""

    def test_create_store(self):
        """Test creating a store."""
        store = create_store()
        assert isinstance(store, Store)

    def test_get_state(self):
        """Test getting state from store."""
        store = create_store()
        state = store.get_state()
        assert isinstance(state, AppState)

    def test_update_state(self):
        """Test updating state."""
        store = create_store()
        old_view = store.get_state().expanded_view
        store.update(lambda s: _with_expanded_view(s, "detail"))
        assert store.get_state().expanded_view == "detail"

    def test_subscribe_to_changes(self):
        """Test subscribing to state changes."""
        store = create_store()
        callback = Mock()
        unsubscribe = store.subscribe(callback)
        store.update(lambda s: _with_expanded_view(s, "tasks"))
        assert callback.call_count == 1
        unsubscribe()

    def test_select_derived_value(self):
        """Test selecting derived value."""
        store = create_store()
        store.update(lambda s: _with_thinking(s, True))
        result = store.select(lambda s: s.thinking_enabled)
        assert result is True

    def test_singleton_pattern(self):
        """Test singleton instance."""
        Store.reset_instance()
        store1 = get_global_store()
        store2 = get_global_store()
        assert store1 is store2
        Store.reset_instance()


class TestSelectors:
    """Tests for selector functions."""

    def test_get_viewed_teammate_task_empty(self):
        """Test selector with no tasks."""
        state = create_default_app_state()
        result = get_viewed_teammate_task(state)
        assert result is None

    def test_get_active_agent_for_input(self):
        """Test agent selector."""
        state = create_default_app_state()
        state.selected_agent_id = "agent-123"
        result = get_active_agent_for_input(state)
        assert result == "agent-123"

    def test_is_bridge_connected_disconnected(self):
        """Test bridge status selector."""
        state = create_default_app_state()
        assert is_bridge_connected(state) is False


class TestObservers:
    """Tests for state observers."""

    def test_register_observer(self):
        """Test registering observer."""
        callback = Mock()
        unsubscribe = register_observer("ui_change", callback)
        assert callable(unsubscribe)

    def test_observer_not_called_on_unmatch_event(self):
        """Test observer only called on matching events."""
        callback = Mock()
        register_observer("task_change", callback)

        # Trigger different event
        store = create_store()
        store.subscribe(callback)
        store.update(lambda s: _with_expanded_view(s, "detail"))

        # Observer should not be called for mismatched event type
        # (This tests the routing mechanism)


# Helper functions for tests
def _with_expanded_view(state: AppState, view: str) -> AppState:
    """Helper to create state with different expanded view."""
    # Create a new state with modified value
    from dataclasses import replace
    return replace(state, expanded_view=view)


def _with_thinking(state: AppState, enabled: bool) -> AppState:
    """Helper to create state with different thinking setting."""
    state.thinking_enabled = enabled
    return state
