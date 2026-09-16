"""Minimal advisor review mechanism (P2-5).

When ``state.advisor_model`` is set (via ``/advisor <model>``), the query
engine runs one short review per completed user-facing turn using that model
and appends the review to the response shown to the user.

The advisor reuses the session's existing query backend
(``state.query_backend.run_turn``) — no separate HTTP client — and is strictly
best-effort: the review has a hard timeout, and any failure (timeout, error,
empty reply) is silently skipped so the main turn is never affected.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from py_claw.query.backend import BackendTurnResult, QueryBackend

_logger = logging.getLogger(__name__)

#: Hard timeout for an advisor review. The main turn must never wait longer
#: than this for the advisor reply; on timeout the review is dropped.
ADVISOR_TIMEOUT_SECONDS = 30.0

#: Prefix for the review block appended to the main response.
ADVISOR_LABEL = "Advisor:"

_REVIEW_INSTRUCTION = (
    "You are a careful reviewer. A user asked an AI assistant a question and "
    "the assistant produced the answer below. Briefly review whether the "
    "answer is correct and whether it has any problems. Limit your review to "
    "2-3 sentences. If there are no problems, just reply \"LGTM\"."
)


def build_review_prompt(query_text: str, answer_text: str) -> str:
    """Build the advisor review prompt for one turn."""
    return (
        f"{_REVIEW_INSTRUCTION}\n\n"
        f"User request:\n{query_text.strip()}\n\n"
        f"Assistant answer:\n{answer_text.strip()}"
    )


def format_review_block(review_text: str) -> str:
    """Format the advisor reply as a standalone block shown after the answer."""
    return f"{ADVISOR_LABEL} {review_text.strip()}"


def run_review(
    backend: "QueryBackend",
    *,
    advisor_model: str,
    query_text: str,
    answer_text: str,
    session_id: str = "",
    state: Any = None,
    timeout: float | None = None,
) -> str | None:
    """Run one advisor review against *backend* and return the review text.

    Reuses the session's query backend (the same model-calling path as the
    main turn) with an isolated empty transcript so the review is a single,
    self-contained prompt. The call is best-effort and never raises: a
    timeout, any exception, or an empty reply yields ``None`` so the caller
    can silently skip the advisor block.
    """
    if timeout is None:
        timeout = ADVISOR_TIMEOUT_SECONDS
    query_text = (query_text or "").strip()
    answer_text = (answer_text or "").strip()
    if not query_text or not answer_text:
        return None

    # Imported lazily to avoid an import cycle (query.engine imports this
    # module at runtime from the turn loop).
    from py_claw.query.engine import PreparedTurn, QueryTurnContext

    prompt = build_review_prompt(query_text, answer_text)
    prepared = PreparedTurn(query_text=prompt, should_query=True, model=advisor_model)
    context = QueryTurnContext(state=state, session_id=session_id, transcript=[])  # type: ignore[arg-type]

    result_box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            result_box["result"] = backend.run_turn(prepared, context)
        except Exception as exc:  # noqa: BLE001 - advisor must never break the turn
            result_box["error"] = exc

    # A daemon thread so a hung review can never block process shutdown;
    # the backend's own HTTP timeout bounds how long the worker can linger.
    worker = threading.Thread(target=_worker, name="advisor-review", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        _logger.warning("Advisor review timed out after %.1fs; skipping", timeout)
        return None
    if "error" in result_box:
        _logger.warning("Advisor review failed: %s", result_box["error"])
        return None

    result: "BackendTurnResult | None" = result_box.get("result")
    text = str(getattr(result, "assistant_text", "") or "").strip()
    if not text:
        _logger.warning("Advisor review returned an empty reply; skipping")
        return None
    return text
