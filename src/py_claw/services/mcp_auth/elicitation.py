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

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Safety net for waiting on a user answer while a UI prompter is attached.
# The dialog itself always resolves (buttons / Esc / server completion), so
# this only bounds pathological cases (e.g. the UI dies while mounted).
DEFAULT_ELICITATION_TIMEOUT_SECONDS = 600.0

# A blocking UI prompter: (server_name, params, event, timeout) -> result dict
# or None if no answer could be collected. It blocks its own (worker) thread
# while the UI thread presents the dialog; the handler runs it via
# asyncio.to_thread so the caller's event loop stays responsive.
UiPrompter = Callable[
    [str, dict[str, Any], "ElicitationRequestEvent", "float | None"],
    "dict[str, Any] | None",
]


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
    # Thread-safe resolution slot: the UI (dialog callbacks on the UI thread)
    # or handle_elicitation_complete (URL mode) pushes the user's answer in
    # via resolve(); the waiting side (prompter thread / handler) is woken by
    # wait_for_result(). First writer wins.
    _result: dict[str, Any] | None = field(default=None, repr=False)
    _resolved: threading.Event = field(default_factory=threading.Event, repr=False)
    _resolve_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def resolve(self, result: dict[str, Any]) -> None:
        """Record the user's answer and wake up any waiters.

        Thread-safe and idempotent: the first resolution wins, later calls
        (e.g. a late 'complete' notification after the user already clicked)
        are ignored.
        """
        with self._resolve_lock:
            if self._resolved.is_set():
                return
            self._result = result
            self._resolved.set()

    def is_resolved(self) -> bool:
        """Return True once an answer has been recorded."""
        return self._resolved.is_set()

    def wait_for_result(
        self,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        """Block (on the calling thread) until resolved.

        Returns the recorded answer, or None on timeout.
        """
        if self._resolved.wait(timeout):
            return self._result
        return None


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

    def find_by_request(self, server_name: str, request_id: str | int) -> int:
        """Find index of the pending event for a JSON-RPC request id."""
        for i, e in enumerate(self.events):
            if e.server_name == server_name and e.request_id == request_id:
                return i
        return -1

    def mark_completed(self, server_name: str, elicitation_id: str) -> bool:
        """Mark an elicitation as completed. Returns True if found.

        Mutates in place (no dataclass_replace): the waiting handler holds a
        reference to the same instance and relies on it keeping its
        resolution slot (_result / _resolved) intact.
        """
        idx = self.find_by_id(server_name, elicitation_id)
        if idx == -1:
            return False
        self.events[idx].completed = True
        return True

    def remove(self, idx: int) -> None:
        if 0 <= idx < len(self.events):
            self.events.pop(idx)

    def remove_event(self, event: ElicitationRequestEvent) -> bool:
        """Remove an event from the queue.

        Matches by identity, falling back to (server_name, request_id) —
        mark_completed() replaces the stored object via dataclass_replace,
        so the instance held by the waiting handler may differ.
        """
        for i, e in enumerate(self.events):
            if e is event or (
                e.server_name == event.server_name and e.request_id == event.request_id
            ):
                self.events.pop(i)
                return True
        return False


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

    def __init__(
        self,
        timeout: float | None = DEFAULT_ELICITATION_TIMEOUT_SECONDS,
    ) -> None:
        self._queue = ElicitationQueue()
        self._lock_lock = None  # Will be set if needed for async
        self._timeout = timeout
        # Blocking UI prompter, registered by the TUI (see
        # set_elicitation_ui_prompter). None => no UI available, in which
        # case elicitations degrade to a plain cancel instead of hanging.
        self._ui_prompter: UiPrompter | None = None

    @property
    def queue(self) -> list[ElicitationRequestEvent]:
        """Get current elicitation queue."""
        return self._queue.events

    @property
    def ui_prompter(self) -> UiPrompter | None:
        """The registered blocking UI prompter, if any."""
        return self._ui_prompter

    def set_ui_prompter(self, prompter: UiPrompter | None) -> None:
        """Register (or clear) the blocking UI prompter.

        The prompter presents the elicitation to the user and blocks its own
        thread until an answer is available. It must push the answer into the
        event via event.resolve() (which the UI-thread dialog callbacks do)
        and return event.wait_for_result(timeout). Return None if no answer
        could be collected (UI unavailable / timed out) — the handler then
        degrades to a cancel.
        """
        self._ui_prompter = prompter

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

    def resolve_pending(
        self,
        server_name: str,
        request_id: str | int,
        result: dict[str, Any],
    ) -> bool:
        """Push an answer into a pending elicitation (e.g. from the UI).

        Returns True if a matching pending event was found and resolved.
        Thread-safe: the waiting side (prompter thread / handler) is woken
        through the event's resolution slot.
        """
        idx = self._queue.find_by_request(server_name, request_id)
        if idx == -1:
            return False
        self._queue.events[idx].resolve(result)
        return True

    @staticmethod
    def _deliver(respond_fn: Callable[[dict[str, Any]], None] | None, result: dict[str, Any]) -> None:
        """Send the final ElicitResult back to the MCP server (best effort)."""
        if respond_fn is None:
            return
        try:
            respond_fn(result)
        except Exception:
            logger.exception("Elicitation respond_fn failed")

    async def handle_elicitation_request(
        self,
        server_name: str,
        request_id: str | int,
        params: dict[str, Any],
        signal: Any,
        respond_fn: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        """Handle an incoming elicitation request from an MCP server.

        Flow:
        1. Elicitation hooks run first and may answer programmatically.
        2. The request is registered in the pending queue
           (ElicitationRequestEvent with a thread-safe resolution slot).
        3. The registered UI prompter (TUI) presents the request and blocks
           its own worker thread while the user answers; the UI thread pushes
           the answer back via event.resolve(). It runs through
           asyncio.to_thread so the caller's event loop stays responsive for
           other MCP traffic.
        4. ElicitationResult hooks can still adjust the answer.
        5. The final result is delivered via respond_fn and returned.

        Without a UI prompter (non-interactive environments) the request
        degrades to {"action": "cancel"} immediately — it never hangs.

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
            self._deliver(respond_fn, hook_response)
            return hook_response

        # Already aborted: nothing to ask the user.
        if signal is not None and getattr(signal, "aborted", False):
            self._deliver(respond_fn, {"action": "cancel"})
            return {"action": "cancel"}

        # Register in the pending queue and wait for the user response.
        event = self.register_request(server_name, request_id, params, signal)
        event.respond = respond_fn

        prompter = self._ui_prompter
        if prompter is None:
            # No UI available (non-interactive session, tests, ...):
            # degrade gracefully instead of hanging.
            logger.debug("No UI prompter for %s; cancelling elicitation", server_name)
            self._queue.remove_event(event)
            self._deliver(respond_fn, {"action": "cancel"})
            return {"action": "cancel"}

        try:
            # The prompter blocks its own thread on event.wait_for_result()
            # (dialog mounted on the UI thread via call_from_thread). Running
            # it in a worker thread keeps this event loop free — other MCP
            # requests and handle_elicitation_complete keep flowing.
            result = await asyncio.to_thread(
                prompter, server_name, params, event, self._timeout
            )
        except Exception:
            logger.exception("Elicitation UI prompter failed for %s", server_name)
            self._queue.remove_event(event)
            self._deliver(respond_fn, {"action": "cancel"})
            return {"action": "cancel"}

        if result is None:
            # UI could not present the dialog, or the wait timed out.
            self._queue.remove_event(event)
            self._deliver(respond_fn, {"action": "cancel"})
            return {"action": "cancel"}

        # ElicitationResult hooks can still adjust the user's answer.
        result = await run_elicitation_result_hooks(
            server_name,
            result,
            signal,
            mode=mode,
            elicitation_id=elicitation_id,
        )

        # Finalize: deliver to the server and clear the pending queue.
        self._deliver(event.respond, result)
        self._queue.remove_event(event)
        return result

    async def handle_elicitation_complete(
        self,
        server_name: str,
        elicitation_id: str,
    ) -> None:
        """Handle an elicitation completion notification (URL mode).

        Called when the server confirms the user completed the URL action.
        Resolves the pending event (accept) so the waiting handler / prompter
        unblock even if the user never clicked "Completed" in the dialog.
        """
        logger.debug(
            "Received elicitation completion notification from %s: %s",
            server_name,
            elicitation_id,
        )
        if not self.complete_request(server_name, elicitation_id):
            return
        idx = self._queue.find_by_id(server_name, elicitation_id)
        if idx != -1:
            self._queue.events[idx].resolve({"action": "accept"})

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


def set_elicitation_ui_prompter(prompter: UiPrompter | None) -> None:
    """Register the blocking UI prompter on the global handler.

    Called by the TUI on mount (and cleared on exit). While a prompter is
    registered, elicitations are presented to the user; otherwise they
    degrade to a cancel.
    """
    get_elicitation_handler().set_ui_prompter(prompter)
