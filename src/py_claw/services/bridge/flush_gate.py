"""State machine for gating message writes during an initial flush.

When a bridge session starts, historical messages are flushed to the
server via a single HTTP POST. During that flush, new messages must
be queued to prevent them from arriving at the server interleaved
with the historical messages.

Lifecycle:
    start() -> enqueue() returns true, items are queued
    end()   -> returns queued items for draining, enqueue() returns false
    drop()  -> discards queued items (permanent transport close)
    deactivate() -> clears active flag without dropping items
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class FlushGate:
    """Gate for managing message flush buffering.

    Attributes:
        active: Whether a flush is currently in progress.
        pending_count: Number of items currently queued.
    """

    _active: bool = False
    _pending: list = None

    def __post_init__(self) -> None:
        if self._pending is None:
            self._pending = []

    @property
    def active(self) -> bool:
        """Whether a flush is currently in progress."""
        return self._active

    @property
    def pending_count(self) -> int:
        """Number of items currently queued."""
        return len(self._pending)

    def start(self) -> None:
        """Mark flush as in-progress.

        After calling start(), enqueue() will start queuing items.
        """
        self._active = True

    def end(self) -> list:
        """End the flush and return any queued items for draining.

        The caller is responsible for sending the returned items.
        After end(), enqueue() returns false (items go direct).
        """
        self._active = False
        items = self._pending[:]
        self._pending.clear()
        return items

    def enqueue(self, *items) -> bool:
        """Queue items if flush is active, otherwise return false.

        Args:
            *items: Items to enqueue

        Returns:
            True if items were queued (flush active),
            False if items should be sent directly (flush not active).
        """
        if not self._active:
            return False
        self._pending.extend(items)
        return True

    def drop(self) -> int:
        """Discard all queued items permanently.

        Used when the transport is permanently closed.
        Returns the number of items that were dropped.
        """
        self._active = False
        count = len(self._pending)
        self._pending.clear()
        return count

    def deactivate(self) -> None:
        """Clear the active flag without dropping queued items.

        Used when the transport is being replaced - the new transport's
        flush will drain the pending items.
        """
        self._active = False
