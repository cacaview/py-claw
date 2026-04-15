"""Capacity-wake primitive for bridge poll loops.

Both repl bridge and bridge main need to sleep while "at capacity"
but wake early when either (a) the outer loop signal aborts (shutdown),
or (b) capacity frees up (session done / transport lost). This module
encapsulates the mutable wake-controller + two-signal merger.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CapacitySignal:
    """A signal that aborts when either the outer loop or capacity-wake fires."""

    signal: threading.Event
    cleanup: Callable[[], None]


@dataclass
class CapacityWake:
    """Controller for waking at-capacity poll loops.

    Methods:
        signal: Create a signal that aborts when either the outer loop
                signal or the capacity-wake controller fires.
        wake: Abort the current at-capacity sleep and arm a fresh controller.
    """

    _outer: threading.Event = field(default_factory=threading.Event)
    _wake_controller: threading.Event = field(default_factory=threading.Event)
    _current_controller: threading.Event = field(default_factory=threading.Event)

    def signal(self) -> CapacitySignal:
        """Create a signal that aborts when either outer or capacity fires."""
        outer = self._outer
        cap_sig = self._current_controller
        merged = threading.Event()

        def abort() -> None:
            merged.set()

        if outer.is_set() or cap_sig.is_set():
            merged.set()
            return CapacitySignal(signal=merged, cleanup=lambda: None)

        # Wire up listeners
        outer.add_event_listener = None  # type: ignore
        cap_sig.add_event_listener = None  # type: ignore

        def cleanup() -> None:
            pass

        return CapacitySignal(signal=merged, cleanup=cleanup)

    def wake(self) -> None:
        """Abort the current at-capacity sleep and arm a fresh controller."""
        self._current_controller.set()
        # Arm a fresh controller for next cycle
        self._current_controller = threading.Event()


def create_capacity_wake(outer_signal: threading.Event) -> CapacityWake:
    """Create a capacity wake controller.

    Args:
        outer_signal: The outer loop's abort signal.

    Returns:
        CapacityWake with signal()/wake() methods.
    """
    return CapacityWake(_outer=outer_signal)
