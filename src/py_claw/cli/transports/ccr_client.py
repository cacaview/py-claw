"""
CCR (Cloud Control Reactor) Client for session management.

Reference: ClaudeCode-main/src/cli/transports/ccrClient.ts

Manages the worker lifecycle protocol with CCR v2:
- Epoch management: reads worker_epoch from environment
- Runtime state reporting: PUT /sessions/{id}/worker
- Heartbeat: POST /sessions/{id}/worker/heartbeat for liveness detection
- Event batching and delivery tracking
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import aiohttp

from .serial_batch import RetryableError, SerialBatchEventUploader
from .worker_state import WorkerStateUploader

logger = logging.getLogger(__name__)

# Default interval between heartbeat events (server TTL is 60s)
DEFAULT_HEARTBEAT_INTERVAL_MS = 20_000
# Stream event flush interval (ms)
STREAM_EVENT_FLUSH_INTERVAL_MS = 100


@dataclass
class StreamAccumulatorState:
    """
    Accumulator state for text_delta coalescing.

    Keyed by API message ID so lifetime is tied to the assistant message —
    cleared when the complete SDKAssistantMessage arrives.
    """
    by_message: dict[str, list[list[str]]] = field(default_factory=dict)
    scope_to_message: dict[str, str] = field(default_factory=dict)


def create_stream_accumulator() -> StreamAccumulatorState:
    """Create a new stream accumulator state."""
    return StreamAccumulatorState()


def _scope_key(session_id: str, parent_tool_use_id: str | None) -> str:
    """Generate scope key for a message."""
    return f"{session_id}:{parent_tool_use_id or ''}"


CCR_INIT_ERRORS = {
    "no_auth_headers": "No authentication headers available",
    "missing_epoch": "Missing worker epoch",
    "worker_register_failed": "Worker registration failed",
}


class CCRInitError(Exception):
    """Thrown by initialize(); carries a typed reason."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"CCRClient init failed: {reason}")


@dataclass
class RequestResult:
    """Result of an HTTP request to CCR."""
    ok: bool
    retry_after_ms: int | None = None


class InternalEvent:
    """Internal event structure for CCR."""

    def __init__(
        self,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        is_compaction: bool = False,
        agent_id: str | None = None,
        event_metadata: dict[str, Any] | None = None,
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.payload = payload
        self.is_compaction = is_compaction
        self.agent_id = agent_id
        self.event_metadata = event_metadata


class CCRClient:
    """
    Manages the worker lifecycle protocol with CCR v2.

    Features:
    - Epoch management from CLAUDE_CODE_WORKER_EPOCH env var
    - Runtime state reporting via WorkerStateUploader
    - Heartbeat for liveness detection
    - Event batching via SerialBatchEventUploader
    - Text delta coalescing for stream events
    """

    def __init__(
        self,
        session_url: str,
        get_auth_headers: Callable[[], dict[str, str]] | None = None,
        heartbeat_interval_ms: int = DEFAULT_HEARTBEAT_INTERVAL_MS,
        on_epoch_mismatch: Callable[[], None] | None = None,
    ):
        """
        Initialize CCRClient.

        Args:
            session_url: Base URL for the session (e.g. https://api.example.com/v1/code/sessions/{id})
            get_auth_headers: Callback to get auth headers. Defaults to env var.
            heartbeat_interval_ms: Heartbeat interval in milliseconds
            on_epoch_mismatch: Callback when epoch mismatch detected
        """
        self._session_url = session_url.rstrip("/")
        self._session_id = session_url.split("/")[-1]
        self._get_auth_headers = get_auth_headers or self._default_get_auth_headers
        self._heartbeat_interval_ms = heartbeat_interval_ms
        self._on_epoch_mismatch = on_epoch_mismatch or (lambda: exit(1))

        self._worker_epoch: int = 0
        self._heartbeat_timer: asyncio.Task | None = None
        self._heartbeat_in_flight: bool = False
        self._closed: bool = False
        self._consecutive_auth_failures: int = 0

        # Stream event buffer and accumulator
        self._stream_event_buffer: list[dict[str, Any]] = []
        self._stream_event_timer: asyncio.Task | None = None
        self._stream_text_accumulator = create_stream_accumulator()

        # Uploaders
        self._worker_state = WorkerStateUploader(
            send=self._send_worker_state,
            base_delay_ms=500,
            max_delay_ms=30_000,
            jitter_ms=500,
        )

        self._event_uploader = SerialBatchEventUploader(
            max_batch_size=100,
            max_queue_size=100_000,
            send=self._send_events,
            base_delay_ms=500,
            max_delay_ms=30_000,
            jitter_ms=500,
        )

        self._internal_event_uploader = SerialBatchEventUploader(
            max_batch_size=100,
            max_queue_size=200,
            send=self._send_internal_events,
            base_delay_ms=500,
            max_delay_ms=30_000,
            jitter_ms=500,
        )

        self._delivery_uploader = SerialBatchEventUploader(
            max_batch_size=64,
            max_queue_size=64,
            send=self._send_delivery,
            base_delay_ms=500,
            max_delay_ms=30_000,
            jitter_ms=500,
        )

    def _default_get_auth_headers(self) -> dict[str, str]:
        """Get auth headers from environment variables."""
        headers = {}
        token = os.environ.get("CLAUDE_CODE_SESSION_ACCESS_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _send_worker_state(self, body: dict[str, Any]) -> bool:
        """Send worker state update."""
        result = await self.request(
            "put",
            "/worker",
            {**body, "worker_epoch": self._worker_epoch},
        )
        return result.ok

    async def _send_events(self, batch: list[dict[str, Any]]) -> None:
        """Send client events."""
        result = await self.request(
            "post",
            "/worker/events",
            {"worker_epoch": self._worker_epoch, "events": batch},
        )
        if not result.ok:
            raise RetryableError(
                "client event POST failed",
                result.retry_after_ms,
            )

    async def _send_internal_events(self, batch: list[dict[str, Any]]) -> None:
        """Send internal events."""
        result = await self.request(
            "post",
            "/worker/internal-events",
            {"worker_epoch": self._worker_epoch, "events": batch},
        )
        if not result.ok:
            raise RetryableError(
                "internal event POST failed",
                result.retry_after_ms,
            )

    async def _send_delivery(self, batch: list[dict[str, Any]]) -> None:
        """Send delivery confirmations."""
        result = await self.request(
            "post",
            "/worker/events/delivery",
            {
                "worker_epoch": self._worker_epoch,
                "updates": [
                    {"event_id": d["event_id"], "status": d["status"]}
                    for d in batch
                ],
            },
        )
        if not result.ok:
            raise RetryableError(
                "delivery POST failed",
                result.retry_after_ms,
            )

    async def request(
        self,
        method: str,
        path: str,
        body: Any,
        timeout: int = 10_000,
    ) -> RequestResult:
        """
        Send an authenticated HTTP request to CCR.

        Handles auth headers, 409 epoch mismatch, and error logging.
        Returns RequestResult with ok=True on 2xx.
        """
        auth_headers = self._get_auth_headers()
        if not auth_headers:
            return RequestResult(ok=False)

        url = f"{self._session_url}{path}"
        headers = {
            **auth_headers,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        timeout_obj = aiohttp.ClientTimeout(total=timeout / 1000.0)

        try:
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                async with session.request(
                    method, url, json=body, headers=headers
                ) as response:
                    if 200 <= response.status < 300:
                        self._consecutive_auth_failures = 0
                        return RequestResult(ok=True)

                    if response.status == 409:
                        self._handle_epoch_mismatch()

                    if response.status in (401, 403):
                        self._consecutive_auth_failures += 1
                        if self._consecutive_auth_failures >= 10:
                            logger.error(
                                "CCRClient: Too many auth failures, giving up"
                            )
                            self._on_epoch_mismatch()

                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After")
                        retry_ms = int(retry_after) * 1000 if retry_after else None
                        return RequestResult(ok=False, retry_after_ms=retry_ms)

                    return RequestResult(ok=False)

        except aiohttp.ClientError as e:
            logger.debug(f"CCRClient request error: {e}")
            return RequestResult(ok=False)

    def _handle_epoch_mismatch(self) -> None:
        """Handle epoch mismatch (409 response)."""
        logger.warning("CCRClient: Epoch mismatch detected")
        self._on_epoch_mismatch()

    async def initialize(self, epoch: int | None = None) -> dict[str, Any] | None:
        """
        Initialize the session worker.

        Args:
            epoch: Worker epoch. Falls back to CLAUDE_CODE_WORKER_EPOCH env var.

        Returns:
            Worker state metadata if available.
        """
        auth_headers = self._get_auth_headers()
        if not auth_headers:
            raise CCRInitError("no_auth_headers")

        if epoch is None:
            raw_epoch = os.environ.get("CLAUDE_CODE_WORKER_EPOCH")
            try:
                epoch = int(raw_epoch) if raw_epoch else 0
            except ValueError:
                epoch = 0

        if epoch == 0:
            raise CCRInitError("missing_epoch")

        self._worker_epoch = epoch

        # Get worker state concurrently with registration
        restored_task = asyncio.create_task(self._get_worker_state())

        # Register worker
        result = await self.request(
            "put",
            "/worker",
            {
                "worker_status": "idle",
                "worker_epoch": self._worker_epoch,
                "external_metadata": {
                    "pending_action": None,
                    "task_summary": None,
                },
            },
        )

        if not result.ok:
            raise CCRInitError("worker_register_failed")

        # Start heartbeat
        self._start_heartbeat()

        # Wait for restored state
        metadata = await restored_task
        logger.info(
            f"CCRClient: initialized, epoch={self._worker_epoch}"
        )

        return metadata

    async def _get_worker_state(self) -> dict[str, Any] | None:
        """Get worker state from server."""
        auth_headers = self._get_auth_headers()
        if not auth_headers:
            return None

        url = f"{self._session_url}/worker"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=auth_headers
                ) as response:
                    if 200 <= response.status < 300:
                        data = await response.json()
                        return data.get("worker", {}).get(
                            "external_metadata"
                        )
        except Exception:
            pass

        return None

    def _start_heartbeat(self) -> None:
        """Start the heartbeat timer."""
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()

        async def heartbeat_loop() -> None:
            while not self._closed:
                await asyncio.sleep(self._heartbeat_interval_ms / 1000.0)
                if not self._closed:
                    await self._send_heartbeat()

        self._heartbeat_timer = asyncio.create_task(heartbeat_loop())

    async def _send_heartbeat(self) -> None:
        """Send heartbeat to CCR."""
        if self._heartbeat_in_flight or self._closed:
            return

        self._heartbeat_in_flight = True
        try:
            await self.request(
                "post",
                "/worker/heartbeat",
                {"worker_epoch": self._worker_epoch},
            )
        finally:
            self._heartbeat_in_flight = False

    def report_state(self, state: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Report worker state.

        Args:
            state: Worker state (idle, working, etc.)
            metadata: Optional metadata to include
        """
        payload: dict[str, Any] = {
            "worker_status": state,
            "worker_epoch": self._worker_epoch,
        }
        if metadata:
            payload["external_metadata"] = metadata
        self._worker_state.enqueue(payload)

    def write_event(self, event: dict[str, Any]) -> None:
        """
        Write an event to CCR.

        Args:
            event: Event payload
        """
        self._event_uploader.enqueue({"payload": event})

    def write_internal_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        is_compaction: bool = False,
        agent_id: str | None = None,
    ) -> None:
        """
        Write an internal event.

        Args:
            event_type: Type of the event
            payload: Event payload
            is_compaction: Whether this is a compaction event
            agent_id: Optional agent ID
        """
        event = InternalEvent(
            event_id=self._generate_event_id(),
            event_type=event_type,
            payload=payload,
            is_compaction=is_compaction,
            agent_id=agent_id,
        )
        self._internal_event_uploader.enqueue(
            {"payload": event.__dict__, "is_compaction": is_compaction}
        )

    def report_delivery(
        self,
        event_id: str,
        status: str = "received",
    ) -> None:
        """
        Report event delivery status.

        Args:
            event_id: ID of the delivered event
            status: Delivery status (received, processing, processed)
        """
        self._delivery_uploader.enqueue({"eventId": event_id, "status": status})

    def _generate_event_id(self) -> str:
        """Generate a unique event ID."""
        import uuid
        return str(uuid.uuid4())

    def close(self) -> None:
        """Close the CCR client."""
        self._closed = True

        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

        if self._stream_event_timer:
            self._stream_event_timer.cancel()
            self._stream_event_timer = None

        self._worker_state.close()
        self._event_uploader.close()
        self._internal_event_uploader.close()
        self._delivery_uploader.close()

        logger.info("CCRClient: closed")
