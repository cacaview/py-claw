"""
Observable pattern implementation for py_claw state management.

Provides thread-safe observable base class similar to React's useSyncExternalStore.
"""
from __future__ import annotations

import copy
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class Observable(ABC, Generic[T]):
    """
    Base class for observable state.

    Similar to React's useSyncExternalStore pattern:
    - subscribe() returns unsubscribe function
    - get_snapshot() returns current state
    """

    @abstractmethod
    def get_snapshot(self) -> T:
        """Return current state snapshot."""
        pass

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """
        Subscribe to state changes.

        Args:
            callback: Function called when state changes

        Returns:
            Unsubscribe function
        """
        raise NotImplementedError


class ChangeDetector(Observable[T]):
    """
    Thread-safe observable state holder.

    Implements functional update pattern similar to React's setState:
    - update(updater) applies functional update
    - All listeners notified on change
    - Thread-safe with RLock
    """

    def __init__(self, initial_state: T) -> None:
        self._state = initial_state
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []

    def get_snapshot(self) -> T:
        """Return deep copy of current state."""
        with self._lock:
            # Always use deepcopy for safety with nested structures
            return copy.deepcopy(self._state)

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to state changes. Returns unsubscribe function."""
        with self._lock:
            self._listeners.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._listeners:
                    self._listeners.remove(callback)

        return unsubscribe

    def _notify(self) -> None:
        """Notify all listeners of state change."""
        with self._lock:
            listeners = list(self._listeners)

        for listener in listeners:
            try:
                listener()
            except Exception:
                # Don't let listener errors break state management
                pass

    def update(self, updater: Callable[[T], T]) -> None:
        """
        Apply functional update to state.

        Args:
            updater: Function that takes current state and returns new state
        """
        with self._lock:
            new_state = updater(self._state)
            self._state = new_state
        self._notify()

    def set(self, new_state: T) -> None:
        """
        Replace state entirely.

        Args:
            new_state: New state value
        """
        with self._lock:
            self._state = new_state
        self._notify()

    @property
    def state(self) -> T:
        """Direct state access (not a snapshot)."""
        with self._lock:
            return self._state


@dataclass
class ObservableState(Generic[T]):
    """
    Observable wrapper for dataclass-based state.

    Provides reactive field access with notification on changes.
    """

    _state: T = field(default_factory=lambda: None)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _field_listeners: dict[str, list[Callable[[Any], None]]] = field(
        default_factory=dict, init=False
    )
    _global_listeners: list[Callable[[], None]] = field(
        default_factory=list, init=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "_lock", threading.RLock())
        object.__setattr__(self, "_field_listeners", {})
        object.__setattr__(self, "_global_listeners", [])

    def get(self, field_name: str) -> Any:
        """Get field value."""
        return getattr(self._state, field_name, None)

    def set(self, field_name: str, value: Any) -> None:
        """Set field value and notify listeners."""
        with self._lock:
            old_value = getattr(self._state, field_name, None)
            if old_value == value:
                return  # No change
            object.__setattr__(self._state, field_name, value)

        # Notify field-specific listeners
        self._notify_field(field_name, value)

        # Notify global listeners
        self._notify_global()

    def _notify_field(self, field_name: str, value: Any) -> None:
        """Notify listeners for a specific field."""
        with self._lock:
            listeners = list(self._field_listeners.get(field_name, []))

        for listener in listeners:
            try:
                listener(value)
            except Exception:
                pass

    def _notify_global(self) -> None:
        """Notify all global listeners."""
        with self._lock:
            listeners = list(self._global_listeners)

        for listener in listeners:
            try:
                listener()
            except Exception:
                pass

    def watch_field(
        self, field_name: str, callback: Callable[[Any], None]
    ) -> Callable[[], None]:
        """
        Watch a specific field for changes.

        Args:
            field_name: Name of field to watch
            callback: Called with new value when field changes

        Returns:
            Unsubscribe function
        """

        def unsubscribe() -> None:
            with self._lock:
                if field_name in self._field_listeners:
                    self._field_listeners[field_name].remove(callback)

        with self._lock:
            if field_name not in self._field_listeners:
                self._field_listeners[field_name] = []
            self._field_listeners[field_name].append(callback)

        return unsubscribe

    def watch_all(self, callback: Callable[[], None]) -> Callable[[], None]:
        """
        Watch all state changes.

        Args:
            callback: Called on any state change

        Returns:
            Unsubscribe function
        """

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._global_listeners:
                    self._global_listeners.remove(callback)

        with self._lock:
            self._global_listeners.append(callback)

        return unsubscribe
