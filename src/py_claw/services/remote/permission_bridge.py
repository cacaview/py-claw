"""Remote permission bridge for CCR session permission handling.

Handles permission requests and responses for remote CCR sessions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from py_claw.services.remote.types import RemotePermissionRequest

logger = logging.getLogger(__name__)


@dataclass
class RemotePermissionResult:
    """Result of a permission request."""

    behavior: str  # "allow" or "deny"
    updated_input: dict[str, Any] | None = None
    message: str | None = None


@dataclass
class PendingPermission:
    """A pending permission request."""

    request_id: str
    tool_use_id: str | None = None
    tool_name: str | None = None
    input_params: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    future: asyncio.Future | None = None


class RemotePermissionBridge:
    """Bridge for handling permission requests in remote sessions.

    Manages the permission request/response flow for CCR sessions:
    1. Receives permission request from CCR via WebSocket
    2. Presents request to local user (via callback)
    3. Sends response back to CCR
    """

    def __init__(
        self,
        on_permission_ask: Callable[[str, dict[str, Any]], tuple[str, dict[str, Any] | None, str | None]] | None = None,
    ):
        """Initialize the permission bridge.

        Args:
            on_permission_ask: Callback to ask user for permission.
                Called with (request_id, params) and should return
                (behavior, updated_input, message).
        """
        self._on_permission_ask = on_permission_ask
        self._pending: dict[str, PendingPermission] = {}
        self._lock = asyncio.Lock()

    async def handle_permission_request(
        self,
        request: RemotePermissionRequest,
        request_id: str,
    ) -> RemotePermissionResult:
        """Handle an incoming permission request.

        Args:
            request: The permission request
            request_id: Request ID for response correlation

        Returns:
            Permission result (allow/deny with optional updated input)
        """
        params = request.params or {}
        tool_use_id = params.get("tool_use_id")
        tool_name = params.get("tool_name")
        input_params = params.get("input", {})

        # Create pending permission
        pending = PendingPermission(
            request_id=request_id,
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            input_params=input_params,
        )

        async with self._lock:
            self._pending[request_id] = pending

        try:
            # Ask user if callback provided
            if self._on_permission_ask:
                behavior, updated_input, message = self._on_permission_ask(
                    request_id, params
                )
                return RemotePermissionResult(
                    behavior=behavior,
                    updated_input=updated_input,
                    message=message,
                )

            # Default deny for remote sessions
            logger.warning(
                "No permission ask callback, defaulting to deny for %s",
                tool_name,
            )
            return RemotePermissionResult(
                behavior="deny",
                message=f"Permission denied for {tool_name}",
            )

        finally:
            async with self._lock:
                self._pending.pop(request_id, None)

    async def handle_permission_cancelled(
        self,
        request_id: str,
        tool_use_id: str | None,
    ) -> None:
        """Handle cancellation of a pending permission request.

        Args:
            request_id: Request ID that was cancelled
            tool_use_id: Tool use ID that was cancelled
        """
        async with self._lock:
            pending = self._pending.pop(request_id, None)

        if pending:
            logger.info(
                "Permission request cancelled: request_id=%s tool_use_id=%s",
                request_id,
                tool_use_id,
            )

    def set_permission_ask_callback(
        self,
        callback: Callable[[str, dict[str, Any]], tuple[str, dict[str, Any] | None, str | None]],
    ) -> None:
        """Set the callback for asking user permission.

        Args:
            callback: Called with (request_id, params) and should return
                (behavior, updated_input, message).
        """
        self._on_permission_ask = callback

    def get_pending_count(self) -> int:
        """Get the number of pending permission requests."""
        return len(self._pending)
