"""
Elicitation handler for MCP servers.

Handles the MCP elicitationRequest (JSON-RPC 'elicitation' request) from an MCP server,
which asks the client (Claude Code) to prompt the user for confirmation or input.

This implements the MCP 'elicitation' feature where:
1. An MCP server sends an elicitationRequest
2. Claude Code shows a dialog to the user
3. The user responds (accept/decline/cancel)
4. The response is sent back to the MCP server
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── Elicitation Types ─────────────────────────────────────────────────────────


@dataclass
class ElicitationWaitingState:
    """Configuration for the waiting state shown after the user opens a URL."""
    action_label: str  # Button label, e.g. "Retry now" or "Skip confirmation"
    show_cancel: bool = False  # Whether to show a visible Cancel button


@dataclass
class ElicitationRequestEvent:
    """An active elicitation request event."""
    server_name: str
    request_id: str | int  # The JSON-RPC request ID
    params: dict[str, Any]  # ElicitRequestParams
    signal: Any  # AbortSignal
    respond: Callable[[dict[str, Any]], None]  # Resolves the elicitation
    waiting_state: ElicitationWaitingState | None = None
    on_waiting_dismiss: Callable[[str], None] | None = None  # 'dismiss' | 'retry' | 'cancel'
    completed: bool = False


@dataclass
class ElicitationQueue:
    """Queue of pending elicitation events."""
    events: list[ElicitationRequestEvent] = field(default_factory=list)

    def add(self, event: ElicitationRequestEvent) -> None:
        self.events.append(event)

    def find_by_id(self, server_name: str, elicitation_id: str) -> int:
        """Find index of matching elicitation event."""
        for i, e in enumerate(self.events):
            if (
                e.server_name == server_name
                and e.params.get("mode") == "url"
                and e.params.get("elicitationId") == elicitation_id
            ):
                return i
        return -1

    def mark_completed(self, server_name: str, elicitation_id: str) -> bool:
        """Mark an elicitation as completed. Returns True if found."""
        idx = self.find_by_id(server_name, elicitation_id)
        if idx == -1:
            return False
        self.events[idx] = dataclass_replace(self.events[idx], completed=True)
        return True

    def remove(self, idx: int) -> None:
        if 0 <= idx < len(self.events):
            self.events.pop(idx)


def dataclass_replace(obj: Any, **kwargs: Any) -> Any:
    """Simple dataclass replace utility."""
    from dataclasses import replace
    return replace(obj, **kwargs)


# ─── Elicitation Result ────────────────────────────────────────────────────────


@dataclass
class ElicitResult:
    """Result of an elicitation response."""
    action: str  # 'accept' | 'decline' | 'cancel'
    content: list[dict[str, Any]] | None = None


# ─── Elicitation Mode ──────────────────────────────────────────────────────────


def get_elicitation_mode(params: dict[str, Any]) -> str:
    """Get the elicitation mode ('form' or 'url')."""
    return "url" if params.get("mode") == "url" else "form"


# ─── Elicitation Hooks ─────────────────────────────────────────────────────────


async def run_elicitation_hooks(
    server_name: str,
    params: dict[str, Any],
    signal: Any,
) -> dict[str, Any] | None:
    """Run elicitation hooks and return a response if one is provided.

    Returns None if no hook responded.
    """
    # In Python implementation, hooks are run through the hooks runtime
    # For now, return None to indicate no programmatic response
    # The actual hook execution would integrate with py_claw.hooks.runtime
    return None


async def run_elicitation_result_hooks(
    server_name: str,
    result: dict[str, Any],
    signal: Any,
    mode: str | None = None,
    elicitation_id: str | None = None,
) -> dict[str, Any]:
    """Run ElicitationResult hooks after the user has responded.

    Returns the (potentially modified) ElicitResult.
    """
    # In Python implementation, hooks would be run here
    # For now, return the result unchanged
    return result


# ─── Elicitation Handler ───────────────────────────────────────────────────────


class ElicitationHandler:
    """Handler for MCP elicitation requests.

    Manages a queue of pending elicitation events and coordinates
    the elicitation flow with the user interface.
    """

    def __init__(self) -> None:
        self._queue = ElicitationQueue()
        self._lock_lock = None  # Will be set if needed for async

    @property
    def queue(self) -> list[ElicitationRequestEvent]:
        """Get current elicitation queue."""
        return self._queue.events

    def register_request(
        self,
        server_name: str,
        request_id: str | int,
        params: dict[str, Any],
        signal: Any,
    ) -> ElicitationRequestEvent:
        """Register a new elicitation request.

        Returns the created ElicitationRequestEvent.
        """
        mode = get_elicitation_mode(params)
        elicitation_id = params.get("elicitationId") if mode == "url" else None
        waiting_state = (
            ElicitationWaitingState(action_label="Skip confirmation")
            if elicitation_id else None
        )

        def make_respond(result: dict[str, Any]) -> None:
            pass  # Will be replaced by real responder

        event = ElicitationRequestEvent(
            server_name=server_name,
            request_id=request_id,
            params=params,
            signal=signal,
            respond=make_respond,
            waiting_state=waiting_state,
        )

        self._queue.add(event)
        return event

    def complete_request(
        self,
        server_name: str,
        elicitation_id: str,
    ) -> bool:
        """Mark a URL-mode elicitation as completed by the server.

        Returns True if the elicitation was found.
        """
        return self._queue.mark_completed(server_name, elicitation_id)

    def remove_request(self, idx: int) -> None:
        """Remove a request from the queue by index."""
        self._queue.remove(idx)

    async def handle_elicitation_request(
        self,
        server_name: str,
        request_id: str | int,
        params: dict[str, Any],
        signal: Any,
        respond_fn: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        """Handle an incoming elicitation request from an MCP server.

        Args:
            server_name: Name of the MCP server
            request_id: The JSON-RPC request ID
            params: ElicitRequestParams
            signal: AbortSignal
            respond_fn: Function to call with the response

        Returns:
            The ElicitResult to send back to the MCP server
        """
        mode = get_elicitation_mode(params)
        elicitation_id = params.get("elicitationId") if mode == "url" else None

        logger.debug(
            "Received elicitation request from %s: mode=%s, elicitationId=%s",
            server_name,
            mode,
            elicitation_id,
        )

        # Run elicitation hooks first - they can provide a response programmatically
        hook_response = await run_elicitation_hooks(server_name, params, signal)
        if hook_response:
            logger.debug(
                "Elicitation resolved by hook for %s",
                server_name,
            )
            return hook_response

        # Register in queue and wait for user response
        event = self.register_request(server_name, request_id, params, signal)
        event.respond = respond_fn

        # For form mode or when signal is already aborted, return cancel
        if signal is not None and getattr(signal, "aborted", False):
            return {"action": "cancel"}

        # The actual user interaction happens via the UI
        # For now, return a placeholder - real implementation would
        # integrate with the CLI/runtime to show a dialog

        # Simulate waiting for response by returning 'cancel' as default
        # This is a simplification - real implementation would block
        # until user responds or signal aborts
        return {"action": "cancel"}

    async def handle_elicitation_complete(
        self,
        server_name: str,
        elicitation_id: str,
    ) -> None:
        """Handle an elicitation completion notification (URL mode).

        Called when the server confirms the user completed the URL action.
        """
        logger.debug(
            "Received elicitation completion notification from %s: %s",
            server_name,
            elicitation_id,
        )
        self.complete_request(server_name, elicitation_id)

    def get_pending_count(self) -> int:
        """Get the number of pending elicitation requests."""
        return len(self._queue.events)


# ─── Global Elicitation Handler ────────────────────────────────────────────────


_elicitation_handler: ElicitationHandler | None = None


def get_elicitation_handler() -> ElicitationHandler:
    """Get the global elicitation handler instance."""
    global _elicitation_handler
    if _elicitation_handler is None:
        _elicitation_handler = ElicitationHandler()
    return _elicitation_handler


def reset_elicitation_handler() -> None:
    """Reset the global elicitation handler (for testing)."""
    global _elicitation_handler
    _elicitation_handler = None
