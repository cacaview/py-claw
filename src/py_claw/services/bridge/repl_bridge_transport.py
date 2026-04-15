"""REPL bridge transport abstraction.

Provides a transport abstraction for replBridge that covers the surface
used by replBridge.ts. Supports both v1 (HybridTransport) and v2
(SSETransport + CCRClient) paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

# Type alias for the literal delivery status
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal


# Session state type (mirrors BridgeState but with different values)
SessionState = Literal[
    "requires_action",
    "in_progress",
    "completed",
    "failed",
]

# Stdout message type (simplified for now)
StdoutMessage = dict[str, Any]


@dataclass
class ReplBridgeTransport:
    """Transport abstraction for REPL bridge.

    Covers the surface that replBridge.ts uses against HybridTransport
    so the v1/v2 choice is confined to the construction site.

    Methods:
        write: Write a single message.
        write_batch: Write multiple messages.
        close: Close the transport.
        is_connected_status: Check if connected.
        get_state_label: Get human-readable state.
        set_on_data: Set data callback.
        set_on_close: Set close callback.
        set_on_connect: Set connect callback.
        connect: Start the transport.
        get_last_sequence_num: Get SSE sequence number high-water mark.
        report_state: Report session state (v2 only).
        report_metadata: Report external metadata (v2 only).
        report_delivery: Report event delivery status (v2 only).
        flush: Drain write queue before close (v2 only).
    """

    write: Callable[[StdoutMessage], Awaitable[None]]
    write_batch: Callable[[list[StdoutMessage]], Awaitable[None]]
    close: Callable[[], None]
    is_connected_status: Callable[[], bool]
    get_state_label: Callable[[], str]
    set_on_data: Callable[[Callable[[str], None]], None]
    set_on_close: Callable[[Callable[[int | None], None]], None]
    set_on_connect: Callable[[Callable[[], None]], None]
    connect: Callable[[], None]
    get_last_sequence_num: Callable[[], int]
    dropped_batch_count: int = 0
    report_state: Callable[[SessionState], None] = lambda _: None
    report_metadata: Callable[[dict[str, Any]], None] = lambda _: None
    report_delivery: Callable[[str, Literal["processing", "processed"]], None] = (
        lambda _, __: None
    )
    flush: Callable[[], Awaitable[None]] = lambda: _sync_resolve()


def _sync_resolve() -> Awaitable[None]:
    """Create an already-resolved awaitable."""
    async def resolved() -> None:
        pass

    return resolved()


def create_v1_repl_transport(
    hybrid: Any,
) -> ReplBridgeTransport:
    """Create a v1 transport adapter for HybridTransport.

    Args:
        hybrid: HybridTransport instance.

    Returns:
        ReplBridgeTransport adapter.
    """
    return ReplBridgeTransport(
        write=lambda msg: hybrid.write(msg),
        write_batch=lambda msgs: hybrid.write_batch(msgs),
        close=lambda: hybrid.close(),
        is_connected_status=lambda: hybrid.is_connected_status(),
        get_state_label=lambda: hybrid.get_state_label(),
        set_on_data=lambda cb: hybrid.set_on_data(cb),
        set_on_close=lambda cb: hybrid.set_on_close(cb),
        set_on_connect=lambda cb: hybrid.set_on_connect(cb),
        connect=lambda: hybrid.connect(),
        # v1 Session-Ingress WS doesn't use SSE sequence numbers
        get_last_sequence_num=lambda: 0,
        dropped_batch_count=getattr(hybrid, "dropped_batch_count", 0),
        report_state=lambda _: None,
        report_metadata=lambda _: None,
        report_delivery=lambda _, __: None,
        flush=_sync_resolve(),
    )


async def create_v2_repl_transport(
    session_url: str,
    ingress_token: str,
    session_id: str,
    initial_sequence_num: int | None = None,
    epoch: int | None = None,
    heartbeat_interval_ms: int = 20_000,
    heartbeat_jitter_fraction: float = 0.0,
    outbound_only: bool = False,
    get_auth_token: Callable[[], str | None] | None = None,
) -> ReplBridgeTransport:
    """Create a v2 transport adapter (SSETransport + CCRClient).

    Args:
        session_url: The session URL.
        ingress_token: Session ingress token.
        session_id: Session ID.
        initial_sequence_num: SSE sequence number to resume from.
        epoch: Worker epoch from POST /bridge response.
        heartbeat_interval_ms: Heartbeat interval (default 20s).
        heartbeat_jitter_fraction: Jitter fraction per beat.
        outbound_only: Skip SSE read stream if True.
        get_auth_token: Optional per-instance auth header source.

    Returns:
        ReplBridgeTransport adapter.
    """
    import httpx

    # Auth header builder
    def get_auth_headers() -> dict[str, str]:
        if get_auth_token:
            token = get_auth_token()
            if token:
                return {"Authorization": f"Bearer {token}"}
        elif ingress_token:
            return {"Authorization": f"Bearer {ingress_token}"}
        return {}

    # Register worker to get epoch if not provided
    if epoch is None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{session_url}/worker/register",
                json={},
                headers={
                    "Authorization": f"Bearer {ingress_token}",
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            epoch = int(data.get("worker_epoch", 0))

    # v2 adapter state
    ccr_initialized = False
    closed = False
    last_seq_num = initial_sequence_num or 0

    on_close_cb: Callable[[int | None], None] | None = None
    on_connect_cb: Callable[[], None] | None = None

    async def write(msg: StdoutMessage) -> None:
        """Write a single message via CCRClient."""
        await _ccr_write(msg)

    async def write_batch(msgs: list[StdoutMessage]) -> None:
        """Write multiple messages via CCRClient."""
        for m in msgs:
            if closed:
                break
            await _ccr_write(m)

    async def _ccr_write(msg: StdoutMessage) -> None:
        """Write to CCR endpoint."""
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{session_url}/worker/events",
                json=msg,
                headers={
                    **get_auth_headers(),
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                timeout=10.0,
            )

    def close() -> None:
        nonlocal closed
        closed = True

    def is_connected_status() -> bool:
        """Write-readiness, not read-readiness."""
        return ccr_initialized

    def get_state_label() -> str:
        if closed:
            return "closed"
        if ccr_initialized:
            return "connected"
        return "connecting"

    def set_on_data(cb: Callable[[str], None]) -> None:
        # SSE data callback - in a real impl would wire up SSETransport
        pass

    def set_on_close(cb: Callable[[int | None], None]) -> None:
        nonlocal on_close_cb
        on_close_cb = cb

    def set_on_connect(cb: Callable[[], None]) -> None:
        nonlocal on_connect_cb
        on_connect_cb = cb

    def connect() -> None:
        # In real impl, would start SSETransport and CCRClient.initialize()
        nonlocal ccr_initialized
        ccr_initialized = True
        if on_connect_cb:
            on_connect_cb()

    def get_last_sequence_num() -> int:
        return last_seq_num

    def report_state(state: SessionState) -> None:
        # Would POST to /worker/state
        pass

    def report_metadata(metadata: dict[str, Any]) -> None:
        # Would POST to /worker/external_metadata
        pass

    def report_delivery(
        event_id: str,
        status: Literal["processing", "processed"],
    ) -> None:
        # Would POST to /worker/events/{id}/delivery
        pass

    async def flush() -> None:
        # v2 write path would drain SerialBatchEventUploader
        pass

    return ReplBridgeTransport(
        write=write,
        write_batch=write_batch,
        close=close,
        is_connected_status=is_connected_status,
        get_state_label=get_state_label,
        set_on_data=set_on_data,
        set_on_close=set_on_close,
        set_on_connect=set_on_connect,
        connect=connect,
        get_last_sequence_num=get_last_sequence_num,
        dropped_batch_count=0,
        report_state=report_state,
        report_metadata=report_metadata,
        report_delivery=report_delivery,
        flush=flush,
    )
