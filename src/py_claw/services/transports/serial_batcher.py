"""Serial ordered event uploader with batching, retry, and backpressure.

Provides:
- At most 1 POST in-flight at a time
- Batches up to maxBatchSize items per POST
- Exponential backoff with jitter on failure
- Backpressure when queue is full
- maxConsecutiveFailures to drop stuck batches
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass, field


@dataclass
class RetryableError(Exception):
    """Error that signals the uploader should retry with an optional delay.

    The retryAfterMs field can carry a server-supplied Retry-After value.
    """

    message: str
    retry_after_ms: int | None = None


@dataclass
class SerialBatcherConfig[T]:
    """Configuration for SerialBatchEventUploader."""

    # Max items per POST (1 = no batching)
    max_batch_size: int
    # Max pending items before enqueue() blocks (backpressure)
    max_queue_size: int
    # The actual HTTP call — caller controls payload format
    send: callable  # async (batch: list[T]) -> None
    # Base delay for exponential backoff (ms)
    base_delay_ms: float
    # Max delay cap (ms)
    max_delay_ms: float
    # Random jitter range added to retry delay (ms)
    jitter_ms: float
    # After this many consecutive failures, drop the failing batch
    max_consecutive_failures: int | None = None
    # Called when a batch is dropped
    on_batch_dropped: callable | None = None  # (batch_size: int, failures: int) -> None


class SerialBatchEventUploader[T]:
    """Serial ordered event uploader with batching, retry, and backpressure.

    - enqueue() adds events to a pending buffer
    - At most 1 POST in-flight at a time
    - Drains up to maxBatchSize items per POST
    - New events accumulate while in-flight
    - On failure: exponential backoff (clamped), retries indefinitely
      until success or close() — unless maxConsecutiveFailures is set,
      in which case the failing batch is dropped and drain advances
    - flush() blocks until pending is empty and kicks drain if needed
    - Backpressure: enqueue() blocks when maxQueueSize is reached
    """

    def __init__(self, config: SerialBatcherConfig[T]) -> None:
        self._config = config
        self._pending: list[T] = []
        self._pending_at_close: int = 0
        self._draining: bool = False
        self._closed: bool = False
        self._backpressure_resolvers: list[callable] = []
        self._sleepResolve: callable | None = None
        self._flush_resolvers: list[callable] = []
        self._dropped_batches: int = 0
        self._failures: int = 0

    @property
    def dropped_batch_count(self) -> int:
        """Monotonic count of batches dropped via maxConsecutiveFailures."""
        return self._dropped_batches

    @property
    def pending_count(self) -> int:
        """Pending queue depth. After close(), returns the count at close time."""
        return self._pending_at_close if self._closed else len(self._pending)

    async def enqueue(self, events: T | list[T]) -> None:
        """Add events to the pending buffer.

        Returns immediately if space is available. Blocks (awaits) if the
        buffer is full — caller pauses until drain frees space.
        """
        if self._closed:
            return
        items = events if isinstance(events, list) else [events]
        if not items:
            return

        # Backpressure: wait until there's space
        while (
            len(self._pending) + len(items) > self._config.max_queue_size
            and not self._closed
        ):
            # Register a future that resolves when space opens
            fut: asyncio.Future = asyncio.get_event_loop().create_future()
            self._backpressure_resolvers.append(fut)
            await fut

        if self._closed:
            return
        self._pending.extend(items)
        asyncio.create_task(self._drain())

    def flush(self) -> asyncio.Future:
        """Block until all pending events have been sent."""
        if not self._pending and not self._draining:
            f: asyncio.Future = asyncio.get_event_loop().create_future()
            f.set_result(None)
            return f
        asyncio.create_task(self._drain())
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._flush_resolvers.append(fut)
        return fut

    def close(self) -> None:
        """Drop pending events and stop processing.

        Resolves any blocked enqueue() and flush() callers.
        """
        if self._closed:
            return
        self._closed = True
        self._pending_at_close = len(self._pending)
        self._pending = []
        if self._sleepResolve:
            self._sleepResolve()
            self._sleepResolve = None
        for resolve in self._backpressure_resolvers:
            if not resolve.done():
                resolve.set_result(None)
        self._backpressure_resolvers = []
        for resolve in self._flush_resolvers:
            if not resolve.done():
                resolve.set_result(None)
        self._flush_resolvers = []

    async def _drain(self) -> None:
        """Drain loop.

        At most one instance runs at a time (guarded by self._draining).
        Sends batches serially. On failure, backs off and retries indefinitely.
        """
        if self._draining or self._closed:
            return
        self._draining = True
        self._failures = 0

        try:
            while self._pending and not self._closed:
                batch = self._take_batch()
                if not batch:
                    continue

                try:
                    await self._config.send(batch)
                    self._failures = 0
                except Exception as err:
                    self._failures += 1
                    cfg = self._config
                    if (
                        cfg.max_consecutive_failures is not None
                        and self._failures >= cfg.max_consecutive_failures
                    ):
                        self._dropped_batches += 1
                        cfg.on_batch_dropped and cfg.on_batch_dropped(len(batch), self._failures)
                        self._failures = 0
                        self._release_backpressure()
                        continue

                    # Re-queue at front
                    self._pending = batch + self._pending
                    retry_after_ms: int | None = (
                        err.retry_after_ms if isinstance(err, RetryableError) else None
                    )
                    await self._sleep(self._retry_delay(retry_after_ms))
                    continue

                # Release backpressure waiters if space opened up
                self._release_backpressure()

        finally:
            self._draining = False
            # Notify flush waiters if queue is empty
            if not self._pending:
                for fut in self._flush_resolvers:
                    if not fut.done():
                        fut.set_result(None)
                self._flush_resolvers = []

    def _take_batch(self) -> list[T]:
        """Pull the next batch from pending, respecting maxBatchSize."""
        max_size = self._config.max_batch_size
        batch = self._pending[:max_size]
        self._pending = self._pending[max_size:]
        return batch

    def _retry_delay(self, retry_after_ms: int | None = None) -> float:
        """Compute retry delay with exponential backoff and jitter."""
        jitter = random.random() * self._config.jitter_ms
        if retry_after_ms is not None:
            clamped = max(self._config.base_delay_ms, min(retry_after_ms, self._config.max_delay_ms))
            return clamped + jitter
        exponential = min(
            self._config.base_delay_ms * (2 ** (self._failures - 1)),
            self._config.max_delay_ms,
        )
        return exponential + jitter

    def _release_backpressure(self) -> None:
        """Release all backpressure waiters."""
        resolvers = self._backpressure_resolvers
        self._backpressure_resolvers = []
        for fut in resolvers:
            if not fut.done():
                fut.set_result(None)

    async def _sleep(self, ms: float) -> None:
        """Sleep for ms milliseconds, allowing cancellation."""
        await asyncio.sleep(ms / 1000)
