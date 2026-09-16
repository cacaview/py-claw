"""Tests for the MCP elicitation handler: UI wiring, queue, degradation.

Covers the P2-3 behavior:
- a registered (UI) prompter's answer is returned as accept/decline/cancel
  and delivered via respond_fn;
- without a UI prompter the handler degrades to cancel and never hangs;
- hook interception still short-circuits before any UI interaction;
- url-mode 'complete' notifications resolve the pending wait out-of-band;
- the resolution slot on ElicitationRequestEvent is thread-safe and
  first-writer-wins (the UI thread pushes answers from a different thread).
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

import py_claw.services.mcp_auth.elicitation as elicitation_module
from py_claw.services.mcp_auth.elicitation import (
    ElicitationHandler,
    ElicitationRequestEvent,
    get_elicitation_handler,
    reset_elicitation_handler,
    set_elicitation_ui_prompter,
)


class _AbortSignal:
    def __init__(self, aborted: bool = False) -> None:
        self.aborted = aborted


@pytest.fixture(autouse=True)
def _clean_global_handler() -> None:
    reset_elicitation_handler()
    yield
    reset_elicitation_handler()


def _form_params() -> dict:
    return {
        "message": "What is your name?",
        "requestedSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "title": "Name"}},
        },
    }


def _make_event() -> ElicitationRequestEvent:
    return ElicitationRequestEvent(
        server_name="srv",
        request_id=1,
        params={},
        signal=None,
        respond=lambda result: None,
    )


async def _wait_until_pending(handler: ElicitationHandler, count: int = 1) -> None:
    """Yield to the loop until the handler has registered the request."""
    for _ in range(200):
        if handler.get_pending_count() == count:
            return
        await asyncio.sleep(0.005)
    assert handler.get_pending_count() == count


# ─── handle_elicitation_request: UI prompter answers ──────────────────────────


@pytest.mark.asyncio
async def test_handle_elicitation_request_accepts_ui_response() -> None:
    handler = ElicitationHandler()
    called: list[tuple[str, dict]] = []

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        called.append((server_name, params))
        event.resolve({"action": "accept", "content": {"name": "py-claw"}})
        return event.wait_for_result(timeout)

    handler.set_ui_prompter(prompter)
    delivered: list[dict] = []
    result = await handler.handle_elicitation_request(
        "srv", 1, _form_params(), None, delivered.append
    )

    assert result == {"action": "accept", "content": {"name": "py-claw"}}
    assert delivered == [result]  # respond_fn got the final answer
    assert called == [("srv", _form_params())]
    assert handler.get_pending_count() == 0


@pytest.mark.asyncio
async def test_handle_elicitation_request_decline_from_ui() -> None:
    handler = ElicitationHandler()

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        event.resolve({"action": "decline"})
        return event.wait_for_result(timeout)

    handler.set_ui_prompter(prompter)
    delivered: list[dict] = []
    result = await handler.handle_elicitation_request(
        "srv", 1, _form_params(), None, delivered.append
    )

    assert result == {"action": "decline"}
    assert delivered == [{"action": "decline"}]
    assert handler.get_pending_count() == 0


@pytest.mark.asyncio
async def test_handle_elicitation_request_cancel_from_ui() -> None:
    handler = ElicitationHandler()

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        event.resolve({"action": "cancel"})
        return event.wait_for_result(timeout)

    handler.set_ui_prompter(prompter)
    delivered: list[dict] = []
    result = await handler.handle_elicitation_request(
        "srv", 1, _form_params(), None, delivered.append
    )

    assert result == {"action": "cancel"}
    assert delivered == [{"action": "cancel"}]
    assert handler.get_pending_count() == 0


@pytest.mark.asyncio
async def test_prompter_returning_none_degrades_to_cancel() -> None:
    """UI could not present the dialog (e.g. app stopped) -> cancel, no hang."""
    handler = ElicitationHandler()

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        return None

    handler.set_ui_prompter(prompter)
    delivered: list[dict] = []
    result = await asyncio.wait_for(
        handler.handle_elicitation_request("srv", 1, _form_params(), None, delivered.append),
        timeout=5.0,
    )

    assert result == {"action": "cancel"}
    assert delivered == [{"action": "cancel"}]
    assert handler.get_pending_count() == 0


# ─── No-UI degradation ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_ui_prompter_degrades_to_cancel_without_hanging() -> None:
    handler = ElicitationHandler(timeout=0.01)
    delivered: list[dict] = []
    start = time.monotonic()
    result = await asyncio.wait_for(
        handler.handle_elicitation_request("srv", 1, _form_params(), None, delivered.append),
        timeout=5.0,
    )

    assert result == {"action": "cancel"}
    assert delivered == [{"action": "cancel"}]
    assert handler.get_pending_count() == 0
    # Degrades immediately — must not wait on anything.
    assert time.monotonic() - start < 1.0


# ─── Hook interception is preserved ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hook_response_short_circuits_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = ElicitationHandler()
    called: list[str] = []

    async def fake_hooks(server_name: str, params: dict, signal) -> dict | None:
        return {"action": "accept", "content": {"auto": True}}

    monkeypatch.setattr(elicitation_module, "run_elicitation_hooks", fake_hooks)

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        called.append(server_name)
        return {"action": "accept", "content": {"wrong": True}}

    handler.set_ui_prompter(prompter)
    delivered: list[dict] = []
    result = await handler.handle_elicitation_request(
        "srv", 1, _form_params(), None, delivered.append
    )

    assert result == {"action": "accept", "content": {"auto": True}}
    assert called == []  # UI was never involved
    assert delivered == [result]
    assert handler.get_pending_count() == 0


@pytest.mark.asyncio
async def test_result_hook_can_modify_ui_response(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = ElicitationHandler()

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        event.resolve({"action": "accept", "content": {"a": "1"}})
        return event.wait_for_result(timeout)

    handler.set_ui_prompter(prompter)

    seen: list[dict] = []

    async def fake_result_hooks(
        server_name: str,
        result: dict,
        signal,
        mode: str | None = None,
        elicitation_id: str | None = None,
    ) -> dict:
        seen.append(result)
        return {"action": "decline"}

    monkeypatch.setattr(elicitation_module, "run_elicitation_result_hooks", fake_result_hooks)
    delivered: list[dict] = []
    result = await handler.handle_elicitation_request(
        "srv", 1, _form_params(), None, delivered.append
    )

    assert seen == [{"action": "accept", "content": {"a": "1"}}]
    assert result == {"action": "decline"}
    assert delivered == [{"action": "decline"}]
    assert handler.get_pending_count() == 0


# ─── Abort signal ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aborted_signal_returns_cancel_without_ui() -> None:
    handler = ElicitationHandler()
    called: list[int] = []

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        called.append(1)
        return None

    handler.set_ui_prompter(prompter)
    delivered: list[dict] = []
    result = await handler.handle_elicitation_request(
        "srv", 1, _form_params(), _AbortSignal(aborted=True), delivered.append
    )

    assert result == {"action": "cancel"}
    assert called == []
    assert delivered == [{"action": "cancel"}]
    assert handler.get_pending_count() == 0


# ─── Queue / resolution-slot mechanics ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_pending_pushes_answer_into_queue() -> None:
    """The 'UI side pushes the answer into the queue' API, used by tests and
    by the TUI prompter under the hood."""
    handler = ElicitationHandler(timeout=5)

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        return event.wait_for_result(timeout)

    handler.set_ui_prompter(prompter)
    delivered: list[dict] = []
    task = asyncio.create_task(
        handler.handle_elicitation_request("srv", 7, _form_params(), None, delivered.append)
    )
    await _wait_until_pending(handler)

    assert handler.resolve_pending("srv", 7, {"action": "decline"}) is True
    assert handler.resolve_pending("srv", 999, {"action": "accept"}) is False

    result = await asyncio.wait_for(task, timeout=5.0)
    assert result == {"action": "decline"}
    assert delivered == [{"action": "decline"}]
    assert handler.get_pending_count() == 0


@pytest.mark.asyncio
async def test_url_mode_server_completion_resolves_pending_wait() -> None:
    """URL mode: the server's 'complete' notification resolves the request
    even while the dialog is still open (no user click needed)."""
    handler = ElicitationHandler(timeout=10)

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        # Simulates the TUI prompter: dialog mounted, thread blocked.
        return event.wait_for_result(timeout)

    handler.set_ui_prompter(prompter)
    delivered: list[dict] = []
    task = asyncio.create_task(
        handler.handle_elicitation_request(
            "srv",
            2,
            {
                "mode": "url",
                "url": "https://auth.example/cb",
                "elicitationId": "e-1",
                "message": "Confirm in your browser",
            },
            None,
            delivered.append,
        )
    )
    await _wait_until_pending(handler)

    await handler.handle_elicitation_complete("srv", "e-1")
    result = await asyncio.wait_for(task, timeout=5.0)

    assert result == {"action": "accept"}
    assert delivered == [{"action": "accept"}]
    assert handler.get_pending_count() == 0


@pytest.mark.asyncio
async def test_prompter_timeout_degrades_to_cancel() -> None:
    handler = ElicitationHandler(timeout=0.05)

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        assert timeout == 0.05
        return event.wait_for_result(timeout)  # nobody resolves

    handler.set_ui_prompter(prompter)
    delivered: list[dict] = []
    result = await asyncio.wait_for(
        handler.handle_elicitation_request("srv", 1, _form_params(), None, delivered.append),
        timeout=5.0,
    )

    assert result == {"action": "cancel"}
    assert delivered == [{"action": "cancel"}]
    assert handler.get_pending_count() == 0


@pytest.mark.asyncio
async def test_prompter_exception_degrades_to_cancel() -> None:
    handler = ElicitationHandler()

    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        raise RuntimeError("UI exploded")

    handler.set_ui_prompter(prompter)
    delivered: list[dict] = []
    result = await handler.handle_elicitation_request(
        "srv", 1, _form_params(), None, delivered.append
    )

    assert result == {"action": "cancel"}
    assert delivered == [{"action": "cancel"}]
    assert handler.get_pending_count() == 0


@pytest.mark.asyncio
async def test_event_loop_stays_responsive_while_awaiting_answer() -> None:
    """Waiting on the UI (via asyncio.to_thread) must not freeze the caller's
    event loop: coroutines on the same loop keep running while an elicitation
    is pending."""
    handler = ElicitationHandler(timeout=5)

    def blocking_prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        return event.wait_for_result(timeout)

    handler.set_ui_prompter(blocking_prompter)
    delivered: list[dict] = []
    task = asyncio.create_task(
        handler.handle_elicitation_request("srv", 1, _form_params(), None, delivered.append)
    )
    await _wait_until_pending(handler)

    # The loop is free: bounded coroutine work completes while the elicitation
    # is still waiting on the UI (if the loop were blocked, this await would
    # never return and the test would time out).
    for _ in range(20):
        await asyncio.sleep(0.001)
    assert handler.get_pending_count() == 1  # still pending, loop was not stuck

    # Now answer from the "UI side" and verify the wait unwinds.
    assert handler.resolve_pending("srv", 1, {"action": "accept", "content": {"name": "x"}})
    result = await asyncio.wait_for(task, timeout=5.0)
    assert result == {"action": "accept", "content": {"name": "x"}}
    assert delivered == [result]
    assert handler.get_pending_count() == 0


# ─── ElicitationRequestEvent resolution slot ──────────────────────────────────


def test_event_resolve_is_thread_safe_and_first_writer_wins() -> None:
    event = _make_event()
    answers = [
        {"action": "accept", "content": {"from": "ui-thread"}},
        {"action": "cancel"},
        {"action": "decline"},
    ]
    threads = [threading.Thread(target=event.resolve, args=(a,)) for a in answers]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert event.is_resolved()
    first = event.wait_for_result(timeout=1.0)
    assert first is not None
    assert first["action"] in ("accept", "cancel", "decline")
    # Later resolves must not overwrite the recorded answer.
    assert event.wait_for_result(timeout=0.1) == first


def test_event_wait_for_result_returns_none_on_timeout() -> None:
    event = _make_event()
    start = time.monotonic()
    assert event.wait_for_result(timeout=0.05) is None
    assert not event.is_resolved()
    assert time.monotonic() - start < 1.0


# ─── Global setter ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_global_ui_prompter_via_setter() -> None:
    def prompter(server_name: str, params: dict, event, timeout: float | None) -> dict | None:
        event.resolve({"action": "accept", "content": {"g": 1}})
        return event.wait_for_result(timeout)

    set_elicitation_ui_prompter(prompter)
    handler = get_elicitation_handler()
    assert handler.ui_prompter is prompter

    delivered: list[dict] = []
    result = await handler.handle_elicitation_request(
        "srv", 1, _form_params(), None, delivered.append
    )
    assert result == {"action": "accept", "content": {"g": 1}}
    assert delivered == [result]
