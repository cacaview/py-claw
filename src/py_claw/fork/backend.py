"""ForkedAgentBackend — QueryBackend implementation that delegates to a subprocess."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from py_claw.fork.process import ForkedAgentProcess

logger = logging.getLogger(__name__)


@dataclass
class ForkedAgentBackend:
    """QueryBackend that delegates to a forked py-claw subprocess.

    This replaces PlaceholderQueryBackend for agent execution,
    enabling true process isolation and independent model inference.
    """
    _process: ForkedAgentProcess | None = field(default=None, init=False, repr=False)
    _session_id: str = field(default="", init=False, repr=False)
    _turn_count: int = field(default=0, init=False, repr=False)
    _started: bool = field(default=False, init=False, repr=False)

    def run_turn(self, prepared, context) -> "BackendTurnResult":
        """Execute a turn by sending it to the forked subprocess and waiting for result."""
        # Lazy imports to avoid circular dependency
        from py_claw.query.backend import BackendToolCall, BackendTurnResult

        if not self._started:
            self._start_process(context)

        query_text = prepared.query_text or ""
        self._process.send_turn(query_text, self._turn_count)  # type: ignore
        self._turn_count += 1

        result = self._wait_for_result()

        return BackendTurnResult(
            assistant_text=result.get("assistant_text", ""),
            stop_reason=result.get("stop_reason", "end_turn"),
            usage=result.get("usage", {}),
            model_usage=result.get("model_usage", {}),
            tool_calls=[
                BackendToolCall(
                    tool_name=tc.get("tool_name", ""),
                    arguments=tc.get("arguments", {}),
                    tool_use_id=tc.get("tool_use_id"),
                    parent_tool_use_id=tc.get("parent_tool_use_id"),
                )
                for tc in result.get("tool_calls", [])
            ],
        )

    def _start_process(self, context) -> None:
        """Spawn the forked subprocess."""
        from py_claw.fork.process import ForkedAgentProcess
        from py_claw.fork.protocol import build_fork_boilerplate

        self._session_id = f"fork-{context.session_id}"

        transcript_dicts: list[dict[str, Any]] = [
            {"role": msg.get("role", "user"), "content": msg.get("content", "")}
            for msg in context.transcript[-10:]
        ]

        boilerplate = build_fork_boilerplate(
            parent_session_id=context.session_id,
            child_session_id=self._session_id,
            transcript=transcript_dicts,
        )

        state = context.state
        system_prompt = state.system_prompt or ""
        if boilerplate:
            system_prompt = (system_prompt + "\n\n" + boilerplate).strip()

        self._process = ForkedAgentProcess(
            session_id=self._session_id,
            system_prompt=system_prompt,
            model=getattr(state, "model", None),
            cwd=state.cwd,
        )
        self._process.spawn()
        self._process.send_init()
        self._started = True

    def _wait_for_result(self) -> dict[str, Any]:
        """Wait for the result message from the forked process."""
        if self._process is None:
            raise RuntimeError("Process not started")

        while True:
            messages = self._process.iter_messages(timeout=30.0)
            for msg in messages:
                msg_type = msg.get("type")
                if msg_type == "output":
                    logger.debug("forked agent output: %s", msg.get("delta", ""))
                elif msg_type == "result":
                    return msg
                elif msg_type == "error":
                    raise RuntimeError(f"Forked agent error: {msg.get('message', 'unknown')}")

            if self._process._eof:  # type: ignore
                raise RuntimeError("Forked agent process terminated unexpectedly")

    def close(self) -> None:
        """Terminate the forked subprocess."""
        if self._process is not None:
            self._process.terminate()
            self._process = None
            self._started = False

