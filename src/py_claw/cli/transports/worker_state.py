"""
Coalescing uploader for PUT /worker (session state + metadata).

Reference: ClaudeCode-main/src/cli/transports/WorkerStateUploader.ts

Features:
- 1 in-flight PUT + 1 pending patch
- New calls coalesce into pending (never grows beyond 1 slot)
- On success: send pending if exists
- On failure: exponential backoff (clamped), retries indefinitely
  until success or close(). Absorbs any pending patches before each retry.
- No backpressure needed — naturally bounded at 2 slots

Coalescing rules:
- Top-level keys (worker_status, external_metadata) — last value wins
- Inside external_metadata / internal_metadata — RFC 7396 merge:
  keys are added/overwritten, null values preserved (server deletes)
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

WorkerStateSendFn = Callable[[dict[str, Any]], Awaitable[bool]]


def _coalesce_patches(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    """
    Coalesce two patches for PUT /worker.

    Top-level keys: overlay replaces base (last value wins).
    Metadata keys (external_metadata, internal_metadata): RFC 7396 merge
    one level deep — overlay keys are added/overwritten, null values
    preserved for server-side delete.
    """
    merged = dict(base)

    for key, value in overlay.items():
        if key in ("external_metadata", "internal_metadata") and key in merged:
            base_val = merged[key]
            if (
                isinstance(base_val, dict)
                and isinstance(value, dict)
                and value is not None
            ):
                # RFC 7396 merge — overlay keys win, nulls preserved for server
                merged[key] = {**base_val, **value}
            else:
                merged[key] = value
        else:
            merged[key] = value

    return merged


class WorkerStateUploader:
    """
    Coalescing uploader for PUT /worker (session state + metadata).

    Features:
    - 1 in-flight PUT + 1 pending patch
    - New calls coalesce into pending (never grows beyond 1 slot)
    - On success: send pending if exists
    - On failure: exponential backoff, retries indefinitely
    - No backpressure needed — naturally bounded at 2 slots
    """

    def __init__(
        self,
        send: WorkerStateSendFn,
        base_delay_ms: int = 500,
        max_delay_ms: int = 8000,
        jitter_ms: int = 1000,
    ):
        """
        Initialize the uploader.

        Args:
            send: The actual HTTP call — returns True on success
            base_delay_ms: Base delay for exponential backoff (ms)
            max_delay_ms: Max delay cap (ms)
            jitter_ms: Random jitter range added to retry delay (ms)
        """
        self._send = send
        self._base_delay_ms = base_delay_ms
        self._max_delay_ms = max_delay_ms
        self._jitter_ms = jitter_ms

        self._inflight: asyncio.Task | None = None
        self._pending: dict[str, Any] | None = None
        self._closed: bool = False

    def enqueue(self, patch: dict[str, Any]) -> None:
        """
        Enqueue a patch to PUT /worker.

        Coalesces with any existing pending patch.
        Fire-and-forget — callers don't need to await.
        """
        if self._closed:
            return

        if self._pending:
            self._pending = _coalesce_patches(self._pending, patch)
        else:
            self._pending = patch

        asyncio.create_task(self._drain())

    def close(self) -> None:
        """Stop processing and clear pending patches."""
        self._closed = True
        self._pending = None

    async def _drain(self) -> None:
        """Drain loop — sends pending patches with coalescing."""
        if self._inflight or self._closed:
            return
        if not self._pending:
            return

        payload = self._pending
        self._pending = None

        async def send_and续淌() -> None:
            await self._send_with_retry(payload)
            self._inflight = None
            if self._pending and not self._closed:
                asyncio.create_task(self._drain())

        self._inflight = asyncio.create_task(send_and续淌())

    async def _send_with_retry(self, payload: dict[str, Any]) -> None:
        """Retries indefinitely with exponential backoff until success or close()."""
        current = payload
        failures = 0

        while not self._closed:
            ok = await self._send(current)
            if ok:
                return

            failures += 1
            await self._sleep(self._retry_delay(failures))

            # Absorb any patches that arrived during the retry
            if self._pending and not self._closed:
                current = _coalesce_patches(current, self._pending)
                self._pending = None

    def _retry_delay(self, failures: int) -> float:
        """Calculate retry delay with exponential backoff and jitter."""
        exponential = min(
            self._base_delay_ms * (2 ** (failures - 1)),
            self._max_delay_ms,
        )
        jitter = random.random() * self._jitter_ms
        return exponential + jitter

    async def _sleep(self, ms: float) -> None:
        """Sleep for the specified duration."""
        await asyncio.sleep(ms / 1000.0)
