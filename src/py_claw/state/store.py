"""
Global Store implementation for py_claw state management.

Provides centralized state access similar to React Context Provider.
Based on ClaudeCode-main/src/state/AppStateStore.tsx
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional, TypeVar

from .app_state import AppState, create_default_app_state
from .observable import ChangeDetector

T = TypeVar("T")


class Store:
    """
    Global state store.

    Provides centralized state management with:
    - Thread-safe state updates
    - Subscription/unsubscription
    - Selector-based state access
    - Global singleton pattern
    """

    _instance: Optional["Store"] = None
    _lock = threading.Lock()

    def __init__(self, initial_state: Optional[AppState] = None) -> None:
        self._state = ChangeDetector(initial_state or create_default_app_state())
        self._middleware: list[Callable[[AppState, AppState], None]] = []

    @classmethod
    def get_instance(cls) -> "Store":
        """Get singleton instance, creating if needed."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        with cls._lock:
            cls._instance = None

    def get_state(self) -> AppState:
        """Get current state."""
        return self._state.state

    def get_snapshot(self) -> AppState:
        """Get state snapshot (deep copy)."""
        return self._state.get_snapshot()

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to state changes."""
        return self._state.subscribe(callback)

    def update(self, updater: Callable[[AppState], AppState]) -> None:
        """
        Update state using functional updater.

        Args:
            updater: Function that takes current state and returns new state
        """
        old_state = self.get_snapshot()

        # Run middleware
        for mw in self._middleware:
            try:
                mw(old_state, self._state.state)
            except Exception:
                pass

        self._state.update(updater)

    def set(self, new_state: AppState) -> None:
        """Replace state entirely."""
        self._state.set(new_state)

    def add_middleware(
        self, middleware: Callable[[AppState, AppState], None]
    ) -> None:
        """
        Add state change middleware.

        Args:
            middleware: Called with (old_state, new_state) on each change
        """
        self._middleware.append(middleware)

    def select(self, selector: Callable[[AppState], T]) -> T:
        """
        Get derived value from state.

        Args:
            selector: Function to extract value from state

        Returns:
            Derived value
        """
        return selector(self.get_snapshot())


def create_store(initial_state: Optional[AppState] = None) -> Store:
    """
    Create a new Store instance.

    Args:
        initial_state: Optional initial state

    Returns:
        New Store instance
    """
    return Store(initial_state)


# Module-level convenience functions
_store: Optional[Store] = None


def get_global_store() -> Store:
    """Get the global store singleton."""
    global _store
    if _store is None:
        _store = Store.get_instance()
    return _store
