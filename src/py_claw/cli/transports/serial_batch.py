"""
Serial ordered event uploader with batching, retry, and backpressure.

Reference: ClaudeCode-main/src/cli/transports/SerialBatchEventUploader.ts

Features:
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
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class RetryableError(Exception):
    """Throw from config.send() to make the uploader wait a server-supplied
    duration before retrying (e.g. 429 with Retry-After).
    """

    def __init__(self, message: str, retry_after_ms: int | None = None):
        super().__init__(message)
        self.retry_after_ms = retry_after_ms


SerialBatchSendFn = Callable[[list[Any]], Awaitable[None]]


class SerialBatchEventUploader:
    """
    Serial ordered event uploader with batching, retry, and backpressure.

    Type parameter T represents the event type being uploaded.
    """

    def __init__(
        self,
        max_batch_size: int,
        max_queue_size: int,
        send: SerialBatchSendFn,
        base_delay_ms: int = 500,
        max_delay_ms: int = 8000,
        jitter_ms: int = 1000,
        max_batch_bytes: int | None = None,
        max_consecutive_failures: int | None = None,
        on_batch_dropped: Callable[[int, int], None] | None = None,
    ):
        """
        Initialize the uploader.

        Args:
            max_batch_size: Max items per POST (1 = no batching)
            max_queue_size: Max pending items before enqueue() blocks
            send: The actual HTTP call — caller controls payload format
            base_delay_ms: Base delay for exponential backoff (ms)
            max_delay_ms: Max delay cap (ms)
            jitter_ms: Random jitter range added to retry delay (ms)
            max_batch_bytes: Max serialized bytes per POST
            max_consecutive_failures: After this many failures, drop batch
            on_batch_dropped: Called when a batch is dropped
        """
        self._config: dict[str, Any] = {
            "maxBatchSize": max_batch_size,
            "maxBatchBytes": max_batch_bytes,
            "maxQueueSize": max_queue_size,
            "send": send,
            "baseDelayMs": base_delay_ms,
            "maxDelayMs": max_delay_ms,
            "jitterMs": jitter_ms,
            "maxConsecutiveFailures": max_consecutive_failures,
            "onBatchDropped": on_batch_dropped,
        }
        self._pending: list[Any] = []
        self._pending_at_close: int = 0
        self._draining: bool = False
        self._closed: bool = False
        self._backpressure_resolvers: list[Callable[[], None]] = []
        self._sleep_resolve: Callable[[], None] | None = None
        self._flush_resolvers: list[Callable[[], None]] = []
        self._dropped_batches: int = 0

    @property
    def dropped_batch_count(self) -> int:
        """Monotonic count of batches dropped via maxConsecutiveFailures."""
        return self._dropped_batches

    @property
    def pending_count(self) -> int:
        """Pending queue depth. After close(), returns the count at close time."""
        return self._pending_at_close if self._closed else len(self._pending)

    async def enqueue(self, events: Any | list[Any]) -> None:
        """
        Add events to the pending buffer.

        Returns immediately if space is available.
        Blocks (awaits) if the buffer is full — caller pauses until drain frees space.
        """
        if self._closed:
            return

        items = events if isinstance(events, list) else [events]
        if not items:
            return

        # Backpressure: wait until there's space
        while (
            len(self._pending) + len(items) > self._config["maxQueueSize"]
            and not self._closed
        ):
            await asyncio.Event().wait()

        if self._closed:
            return

        self._pending.extend(items)
        asyncio.create_task(self._drain())

    def flush(self) -> Awaitable[None]:
        """
        Block until all pending events have been sent.

        Used at turn boundaries and graceful shutdown.
        """
        if not self._pending and not self._draining:
            return asyncio.sleep(0)

        asyncio.create_task(self._drain())

        async def wait_flush() -> None:
            await asyncio.sleep(0)
            # The flush resolver will be called when drain completes

        async def flush_waiter() -> None:
            event = asyncio.Event()

            def resolver() -> None:
                event.set()

            self._flush_resolvers.append(resolver)
            await event.wait()

        return flush_waiter()

    def close(self) -> None:
        """
        Drop pending events and stop processing.

        Resolves any blocked enqueue() and flush() callers.
        """
        if self._closed:
            return

        self._closed = True
        self._pending_at_close = len(self._pending)
        self._pending = []

        if self._sleep_resolve:
            self._sleep_resolve()
            self._sleep_resolve = None

        for resolve in self._backpressure_resolvers:
            resolve()
        self._backpressure_resolvers = []

        for resolve in self._flush_resolvers:
            resolve()
        self._flush_resolvers = []

    async def _drain(self) -> None:
        """
        Drain loop.

        At most one instance runs at a time (guarded by self._draining).
        Sends batches serially. On failure, backs off and retries indefinitely.
        """
        if self._draining or self._closed:
            return

        self._draining = True
        failures = 0

        try:
            while self._pending and not self._closed:
                batch = self._take_batch()
                if not batch:
                    continue

                try:
                    await self._config["send"](batch)
                    failures = 0
                except Exception as err:  # noqa: BLE001
                    failures += 1
                    max_fails = self._config["maxConsecutiveFailures"]
                    if max_fails is not None and failures >= max_fails:
                        self._dropped_batches += 1
                        on_dropped = self._config["onBatchDropped"]
                        if on_dropped:
                            on_dropped(len(batch), failures)
                        failures = 0
                        self._release_backpressure()
                        continue

                    # Re-queue the failed batch at the front
                    self._pending = batch + self._pending
                    retry_after_ms: int | None = None
                    if isinstance(err, RetryableError):
                        retry_after_ms = err.retry_after_ms
                    await self._sleep(self._retry_delay(failures, retry_after_ms))
                    continue

                # Release backpressure waiters if space opened up
                self._release_backpressure()

        finally:
            self._draining = False
            # Notify flush waiters if queue is empty
            if not self._pending:
                for resolve in self._flush_resolvers:
                    resolve()
                self._flush_resolvers = []

    def _take_batch(self) -> list[Any]:
        """
        Pull the next batch from pending.

        Respects both maxBatchSize and maxBatchBytes. The first item is
        always taken; subsequent items only if adding them keeps the
        cumulative JSON size under maxBatchBytes.
        """
        max_batch_size = self._config["maxBatchSize"]
        max_batch_bytes = self._config["maxBatchBytes"]

        if max_batch_bytes is None:
            result = self._pending[:max_batch_size]
            self._pending = self._pending[max_batch_size:]
            return result

        bytes_count = 0
        count = 0
        while count < len(self._pending) and count < max_batch_size:
            try:
                item_bytes = len(json.dumps(self._pending[count]).encode())
            except (TypeError, ValueError):
                # Unserializable item — drop it
                self._pending.pop(count)
                continue

            if count > 0 and bytes_count + item_bytes > max_batch_bytes:
                break

            bytes_count += item_bytes
            count += 1

        result = self._pending[:count]
        self._pending = self._pending[count:]
        return result

    def _retry_delay(self, failures: int, retry_after_ms: int | None = None) -> float:
        """Calculate retry delay with exponential backoff and jitter."""
        jitter = random.random() * self._config["jitterMs"]

        if retry_after_ms is not None:
            # Jitter on top of server's hint
            clamped = max(
                self._config["baseDelayMs"],
                min(retry_after_ms, self._config["maxDelayMs"]),
            )
            return clamped + jitter

        exponential = min(
            self._config["baseDelayMs"] * (2 ** (failures - 1)),
            self._config["maxDelayMs"],
        )
        return exponential + jitter

    def _release_backpressure(self) -> None:
        """Release all backpressure waiters."""
        resolvers = self._backpressure_resolvers
        self._backpressure_resolvers = []
        for resolve in resolvers:
            resolve()

    async def _sleep(self, ms: float) -> None:
        """Sleep for the specified duration."""
        event = asyncio.Event()

        def resolver() -> None:
            event.set()

        self._sleep_resolve = resolver
        # Schedule the resolve
        loop = asyncio.get_event_loop()
        handle = loop.call_later(ms / 1000.0, resolver)
        try:
            await event.wait()
        except Exception:  # noqa: BLE001
            handle.cancel()
            raise
