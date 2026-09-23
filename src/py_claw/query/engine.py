from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import TYPE_CHECKING, Any, Protocol, Sequence
from uuid import uuid4

from py_claw.commands import CommandExecutionResult
from py_claw.permissions.engine import PermissionEngine
from py_claw.query.backend import (
    ApiRequestError,
    BackendChunk,
    BackendToolCall,
    BackendTurnResult,
    PlaceholderQueryBackend,
    QueryBackend,
    StreamingQueryBackend,
    _build_model_usage,
    _build_usage,
)
from py_claw.schemas.common import (
    EffortLevel,
    SDKAssistantMessage,
    SDKLocalCommandOutputMessage,
    SDKPartialAssistantMessage,
    SDKPromptSuggestionMessage,
    SDKRequestStartEvent,
    SDKRequestStartMessage,
    SDKResultError,
    SDKResultSuccess,
    SDKSessionStateChangedMessage,
    SDKToolProgressMessage,
    SDKUserMessage,
)
from py_claw.schemas.control import StdoutMessage
from py_claw.settings.loader import SettingsLoadResult, get_settings_with_sources
from py_claw.tools.base import ToolError, ToolPermissionError

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


# How long the engine waits for a host to answer a ``can_use_tool`` control
# request before failing closed (deny). A prompt the host never answers must
# not block the turn.
_HOST_PERMISSION_TIMEOUT_SECONDS = 300.0


class _StreamingList(Sequence[StdoutMessage]):
    """A sequence that is both an iterator (for streaming) and indexable (for tests).

    Eagerly consumes the underlying generator on construction so that any
    side-effects (e.g. backend.run_turn() being called) happen immediately.
    After construction, both iteration and indexing read from the cached list.
    """

    __slots__ = ("_cache",)

    def __init__(self, gen: Iterator[StdoutMessage]) -> None:
        # Immediately exhaust the generator so backend calls etc. are executed
        self._cache: list[StdoutMessage] = list(gen)

    def __iter__(self) -> Iterator[StdoutMessage]:
        return iter(self._cache)

    def __getitem__(self, index: int) -> StdoutMessage:
        return self._cache[index]

    def __len__(self) -> int:
        return len(self._cache)


@dataclass(slots=True)
class PreparedTurn:
    query_text: str | None = None
    immediate_outputs: list[StdoutMessage] = field(default_factory=list)
    should_reset_session: bool = False
    should_query: bool = False
    allowed_tools: list[str] | None = None
    model: str | None = None
    effort: EffortLevel | None = None
    max_thinking_tokens: int | None = None
    system_prompt: str | None = None
    append_system_prompt: str | None = None
    json_schema: dict[str, Any] | None = None
    sdk_mcp_servers: list[str] | None = None
    prompt_suggestions: bool = False
    agent_progress_summaries: bool = False


@dataclass(slots=True)
class QueryTurnContext:
    state: RuntimeState
    session_id: str
    transcript: list[object] = field(default_factory=list)
    turn_count: int = 0
    continuation_count: int = 0
    transition_reason: str | None = None


@dataclass(slots=True)
class SavedSessionState:
    transcript: list[object] = field(default_factory=list)
    turn_count: int = 0


@dataclass(slots=True)
class QueryTurnState:
    session_id: str
    prepared: PreparedTurn
    transcript: list[object] = field(default_factory=list)
    continuation_count: int = 0
    transition_reason: str | None = None


@dataclass(slots=True)
class ToolCallRequest:
    tool_name: str
    arguments: dict[str, Any]
    tool_use_id: str | None = None
    parent_tool_use_id: str | None = None


@dataclass(slots=True)
class ExecutedTurn:
    assistant_text: str = ""
    stop_reason: str = "end_turn"
    usage: dict[str, object] = field(default_factory=dict)
    model_usage: dict[str, object] = field(default_factory=dict)
    duration_api_ms: float = 0.0
    total_cost_usd: float = 0.0
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    prompt_suggestion: str | None = None


class QueryTurnFailure(Exception):
    def __init__(self, error: Exception, partial_outputs: list[StdoutMessage] | None = None) -> None:
        super().__init__(str(error))
        self.error = error
        self.partial_outputs = list(partial_outputs or [])


def _mock_rate_limit_failure() -> "QueryTurnFailure | None":
    """Return a QueryTurnFailure when /mock-limits rate limiting is active.

    Only consulted on the turn-execution path; when mock limits are inactive
    (the default) this is a couple of dict/global lookups and returns None,
    so the real request path is untouched.
    """
    from py_claw.services.rate_limits_mocking import (
        get_mock_headerless_429_message,
        get_mock_headers,
        should_process_mock_limits,
    )

    if not should_process_mock_limits():
        return None
    message = get_mock_headerless_429_message() or "Rate limit exceeded (mocked via /mock-limits)"
    headers = get_mock_headers()
    if headers:
        reset = headers.get("anthropic-ratelimit-unified-reset")
        if reset:
            message += f"; resets in {reset}s"
    return QueryTurnFailure(ApiRequestError("rate_limit", message, 429))


# Type for streaming turn output: either an intermediate partial message,
# or the final (ExecutedTurn, tool_outputs) tuple.
StreamingTurnOutput = SDKPartialAssistantMessage | tuple[ExecutedTurn, list[StdoutMessage]]


class TurnExecutor(Protocol):
    def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn: ...

    def execute_streaming(
        self, prepared: PreparedTurn, context: QueryTurnContext
    ) -> Iterator[BackendChunk | BackendTurnResult]: ...


def _resolve_query_backend(state: RuntimeState) -> QueryBackend:
    return state.query_backend or PlaceholderQueryBackend()


def _model_friendly_tool_output(tool_name: str, output: dict[str, Any]) -> Any:
    """Render a tool result the way the model should see it.

    The raw tool output mixes model-relevant fields (stdout/stderr/exit code)
    with harness metadata (security classification). Sending that metadata as
    part of the conversation makes weaker models re-issue the same call, so
    the transcript stores a plain-text rendering instead. The structured dict
    stays available via ``tool_use_result`` for SDK consumers.
    """
    if isinstance(output, str):
        return output
    if not isinstance(output, dict):
        return output

    if "stdout" in output or "stderr" in output or "exitCode" in output:
        parts: list[str] = []
        stdout = output.get("stdout")
        if stdout:
            parts.append(str(stdout).rstrip("\n"))
        stderr = output.get("stderr")
        if stderr:
            parts.append(f"stderr:\n{str(stderr).rstrip()}")
        exit_code = output.get("exitCode")
        if exit_code not in (None, 0):
            parts.append(f"exit code: {exit_code}")
        if not parts:
            parts.append("(no output)")
        return "\n".join(parts)

    if isinstance(output.get("content"), str):
        return output["content"]
    if isinstance(output.get("text"), str):
        return output["text"]
    try:
        return json.dumps(output, ensure_ascii=False, default=str)
    except Exception:
        return str(output)


def _summarize_tool_output(output: Any, limit: int = 400) -> str:
    """Short single-line-ish preview for tool_progress events / UI display."""
    if output is None:
        return ""
    text = output if isinstance(output, str) else str(output)
    text = text.strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


class BackendTurnExecutor:
    def __init__(self, backend: QueryBackend | None = None) -> None:
        self._backend = backend or PlaceholderQueryBackend()

    def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
        prepared = self._apply_runtime_defaults(prepared, context)
        mock_failure = _mock_rate_limit_failure()
        if mock_failure is not None:
            raise mock_failure
        result = self._backend.run_turn(prepared, context)
        return self._to_executed_turn(result)

    def execute_streaming(
        self, prepared: PreparedTurn, context: QueryTurnContext
    ) -> Iterator[BackendChunk | BackendTurnResult]:
        """Streaming execution that yields BackendChunk as they arrive.

        After the last chunk (stop_reason), yields the completed BackendTurnResult.
        Falls back to non-streaming if backend does not support streaming.
        """
        prepared = self._apply_runtime_defaults(prepared, context)
        mock_failure = _mock_rate_limit_failure()
        if mock_failure is not None:
            raise mock_failure
        if isinstance(self._backend, StreamingQueryBackend):
            chunks: list[BackendChunk] = []
            for chunk in self._backend.run_turn_streaming(prepared, context):
                chunks.append(chunk)
                yield chunk
            # Build final result from accumulated chunks
            assistant_parts = [c.text for c in chunks if c.type == "text_delta"]
            stop_reason = next((c.stop_reason for c in reversed(chunks) if c.type == "stop_reason"), "end_turn")
            assistant_text = "".join(assistant_parts)

            # Extract tool_calls from tool_calls chunks
            tool_calls: list[BackendToolCall] = []
            for chunk in chunks:
                if chunk.type == "tool_calls":
                    import json
                    try:
                        tc_list = json.loads(chunk.text)
                        for tc in tc_list:
                            tool_calls.append(BackendToolCall(
                                tool_name=tc.get("tool_name", ""),
                                arguments=tc.get("arguments", {}),
                                tool_use_id=tc.get("tool_use_id"),
                                parent_tool_use_id=tc.get("parent_tool_use_id"),
                            ))
                    except (json.JSONDecodeError, Exception):
                        pass

            result = BackendTurnResult(
                assistant_text=assistant_text,
                stop_reason=stop_reason,
                usage=_build_usage(prepared=prepared, assistant_text=assistant_text, backend_type="api"),
                model_usage=_build_model_usage(prepared=prepared, assistant_text=assistant_text, total_cost_usd=0.0),
                duration_api_ms=0.0,
                tool_calls=tool_calls,
            )
            yield result
        else:
            result = self._backend.run_turn(prepared, context)
            yield BackendChunk(type="stop_reason", stop_reason=result.stop_reason)
            yield result

    def replace_backend(self, backend: QueryBackend) -> None:
        self._backend = backend

    @property
    def backend(self) -> QueryBackend:
        return self._backend

    def _to_executed_turn(self, result: BackendTurnResult) -> ExecutedTurn:
        return ExecutedTurn(
            assistant_text=result.assistant_text,
            stop_reason=result.stop_reason,
            usage=dict(result.usage),
            model_usage=dict(result.model_usage),
            duration_api_ms=result.duration_api_ms,
            total_cost_usd=result.total_cost_usd,
            tool_calls=[self._to_tool_call_request(tool_call) for tool_call in result.tool_calls],
            prompt_suggestion=result.prompt_suggestion,
        )

    def _to_tool_call_request(self, tool_call: BackendToolCall) -> ToolCallRequest:
        return ToolCallRequest(
            tool_name=tool_call.tool_name,
            arguments=dict(tool_call.arguments),
            tool_use_id=tool_call.tool_use_id,
            parent_tool_use_id=tool_call.parent_tool_use_id,
        )

    def _apply_runtime_defaults(self, prepared: PreparedTurn, context: QueryTurnContext) -> PreparedTurn:
        state = context.state
        updated = prepared

        if updated.model is None and state.model is not None:
            updated = replace(updated, model=state.model)
        if updated.max_thinking_tokens is None and state.max_thinking_tokens is not None:
            updated = replace(updated, max_thinking_tokens=state.max_thinking_tokens)
        if updated.system_prompt is None and state.system_prompt is not None:
            updated = replace(updated, system_prompt=state.system_prompt)
        if updated.append_system_prompt is None and state.append_system_prompt is not None:
            updated = replace(updated, append_system_prompt=state.append_system_prompt)
        if updated.json_schema is None and state.json_schema is not None:
            updated = replace(updated, json_schema=state.json_schema)
        if updated.sdk_mcp_servers is None and state.sdk_mcp_servers:
            updated = replace(updated, sdk_mcp_servers=list(state.sdk_mcp_servers))
        if not updated.prompt_suggestions and state.prompt_suggestions:
            updated = replace(updated, prompt_suggestions=True)
        if not updated.agent_progress_summaries and state.agent_progress_summaries:
            updated = replace(updated, agent_progress_summaries=True)
        return updated


class PlaceholderTurnExecutor(BackendTurnExecutor):
    pass


class TurnDriver(Protocol):
    def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn: ...


class PlaceholderTurnDriver:
    def __init__(self, *, placeholder_executor: TurnExecutor | None = None) -> None:
        self._placeholder_executor = placeholder_executor or BackendTurnExecutor()

    def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
        return self._placeholder_executor.execute(prepared, context)

    def execute_streaming(
        self, prepared: PreparedTurn, context: QueryTurnContext
    ) -> Iterator[BackendChunk | BackendTurnResult]:
        executor = self._placeholder_executor
        streaming = getattr(executor, "execute_streaming", None)
        if streaming is None:
            # Executor only implements the blocking protocol: wrap its result
            # in the shape the streaming loop consumes.
            def _wrap() -> Iterator[BackendChunk | BackendTurnResult]:
                from py_claw.query.backend import BackendToolCall, BackendTurnResult as _BackendTurnResult

                executed = executor.execute(prepared, context)
                yield _BackendTurnResult(
                    assistant_text=executed.assistant_text,
                    stop_reason=executed.stop_reason,
                    usage=dict(executed.usage),
                    model_usage=dict(executed.model_usage),
                    duration_api_ms=executed.duration_api_ms,
                    total_cost_usd=executed.total_cost_usd,
                    tool_calls=[
                        BackendToolCall(
                            tool_name=call.tool_name,
                            arguments=dict(call.arguments),
                            tool_use_id=call.tool_use_id,
                            parent_tool_use_id=call.parent_tool_use_id,
                        )
                        for call in executed.tool_calls
                    ],
                    prompt_suggestion=executed.prompt_suggestion,
                )

            return _wrap()
        return streaming(prepared, context)

    def run_streaming(
        self, prepared: PreparedTurn, context: QueryTurnContext
    ) -> Iterator[BackendChunk | ExecutedTurn]:
        return self._placeholder_executor.execute_streaming(prepared, context)

    def replace_placeholder_executor(self, executor: TurnExecutor) -> None:
        self._placeholder_executor = executor

    @property
    def placeholder_executor(self) -> TurnExecutor:
        return self._placeholder_executor


class RuntimeTurnExecutor:
    def __init__(self, *, driver: TurnDriver | None = None) -> None:
        self._driver = driver or PlaceholderTurnDriver()

    def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
        return self._driver.execute(prepared, context)

    def execute_streaming(
        self, prepared: PreparedTurn, context: QueryTurnContext
    ) -> Iterator[BackendChunk | BackendTurnResult]:
        driver_streaming = getattr(self._driver, "execute_streaming", None)
        if driver_streaming is not None:
            return driver_streaming(prepared, context)
        # Driver without streaming support: wrap the blocking execute and
        # convert its ExecutedTurn into the BackendTurnResult shape the
        # streaming loop consumes.
        def _wrap() -> Iterator[BackendChunk | BackendTurnResult]:
            executed = self.execute(prepared, context)
            yield BackendTurnResult(
                assistant_text=executed.assistant_text,
                stop_reason=executed.stop_reason,
                usage=dict(executed.usage),
                model_usage=dict(executed.model_usage),
                duration_api_ms=executed.duration_api_ms,
                total_cost_usd=executed.total_cost_usd,
                tool_calls=[
                    BackendToolCall(
                        tool_name=call.tool_name,
                        arguments=dict(call.arguments),
                        tool_use_id=call.tool_use_id,
                        parent_tool_use_id=call.parent_tool_use_id,
                    )
                    for call in executed.tool_calls
                ],
                prompt_suggestion=executed.prompt_suggestion,
            )
        return _wrap()

    def run_streaming(
        self, prepared: PreparedTurn, context: QueryTurnContext
    ) -> Iterator[BackendChunk | ExecutedTurn]:
        return self._driver.run_streaming(prepared, context)

    def replace_driver(self, driver: TurnDriver) -> None:
        self._driver = driver

    def replace_fallback(self, executor: TurnExecutor) -> None:
        if isinstance(self._driver, PlaceholderTurnDriver):
            self._driver.replace_placeholder_executor(executor)
            return
        self._driver = PlaceholderTurnDriver(placeholder_executor=executor)

    @property
    def driver(self) -> TurnDriver:
        return self._driver

    @property
    def fallback(self) -> TurnExecutor:
        if isinstance(self._driver, PlaceholderTurnDriver):
            return self._driver.placeholder_executor
        raise RuntimeError("Runtime turn executor is using a non-placeholder driver")

    @property
    def backend(self) -> QueryBackend | None:
        if not isinstance(self._driver, PlaceholderTurnDriver):
            return None
        executor = self._driver.placeholder_executor
        if isinstance(executor, BackendTurnExecutor):
            return executor.backend
        return None


class QueryRuntime:
    # Default per-turn tool-continuation cap. 8 was tuned for single-shot Q&A
    # and terminated real agentic tasks (a clone + edit + test + fix cycle
    # easily exceeds 8 tool calls per turn); the identical-call loop guard
    # still stops true runaway loops. Override with the
    # PYCLAW_MAX_TOOL_CONTINUATIONS env var (e.g. a host that wants a tighter
    # budget), or via the instance attribute in tests.
    _MAX_TOOL_CONTINUATIONS = 100

    def __init__(self, state: RuntimeState | None = None, *, turn_executor: TurnExecutor | None = None) -> None:
        if state is None:
            from py_claw.cli.runtime import RuntimeState as _RuntimeState

            state = _RuntimeState()
        self.state = state
        # Instance knob (defaults to the class constant, overridable via the
        # PYCLAW_MAX_TOOL_CONTINUATIONS env var) so tests can shrink the
        # tool-continuation loop without monkeypatching the whole class.
        env_cap = os.environ.get("PYCLAW_MAX_TOOL_CONTINUATIONS", "").strip()
        try:
            env_cap_value = int(env_cap) if env_cap else 0
        except ValueError:
            env_cap_value = 0
        if env_cap_value > 0:
            self.max_tool_continuations = env_cap_value
        else:
            self.max_tool_continuations = self._MAX_TOOL_CONTINUATIONS
        self.state.query_runtime = self
        self._runtime_turn_executor = RuntimeTurnExecutor(
            driver=PlaceholderTurnDriver(placeholder_executor=BackendTurnExecutor(_resolve_query_backend(self.state)))
        )
        self._turn_executor = turn_executor or self._runtime_turn_executor
        self._session_id: str | None = None
        self._turn_count = 0
        self._transcript: list[object] = []
        self._saved_sessions: dict[str, SavedSessionState] = {}
        self._cancelled_message_uuids: set[str] = set()
        self._turn_in_progress = False
        self._active_turn_state: QueryTurnState | None = None
        self._active_message_uuid: str | None = None
        self._persisted_transcript_count = 0
        self._file_mutations: list[dict[str, Any]] = []  # Track file changes per turn

    @property
    def turn_executor(self) -> TurnExecutor:
        return self._turn_executor

    @property
    def runtime_turn_executor(self) -> RuntimeTurnExecutor:
        return self._runtime_turn_executor

    @property
    def transcript(self) -> list[object]:
        return list(self._transcript)

    def rewind_messages(self, count: int) -> tuple[bool, str]:
        """Remove the last N messages from the transcript.

        Returns (success, message) tuple.
        """
        if count <= 0:
            return False, "Count must be a positive integer"
        if count >= len(self._transcript):
            return False, f"Cannot rewind {count} messages: only {len(self._transcript)} messages in history"

        # Save the messages being removed for potential undo
        removed = self._transcript[-count:]
        self._transcript = self._transcript[:-count]

        # Update active turn state if present
        if self._active_turn_state is not None:
            self._active_turn_state.transcript = list(self._transcript)

        # Save session state
        if self._session_id is not None:
            self.save_session_state(self._session_id)

        return True, f"Rewound {count} messages ({len(self._transcript)} remaining)"

    def message_count(self) -> int:
        """Return the number of messages in the current transcript."""
        return len(self._transcript)

    def get_message_history(self) -> list[object]:
        """Return a copy of the message history."""
        return list(self._transcript)

    def record_file_mutation(self, path: str, operation: str, *, old_content: str | None = None, new_content: str | None = None) -> None:
        """Record a file mutation for potential rewind."""
        self._file_mutations.append({
            "path": path,
            "operation": operation,
            "old_content": old_content,
            "new_content": new_content,
            "turn_count": self._turn_count,
            "session_id": self._session_id,
        })

    def get_file_mutations(self, since_turn: int | None = None) -> list[dict[str, Any]]:
        """Get file mutations, optionally filtered by turn number."""
        if since_turn is None:
            return list(self._file_mutations)
        return [m for m in self._file_mutations if m["turn_count"] >= since_turn]

    def execute_turn(self, prepared: PreparedTurn) -> ExecutedTurn:
        self.state.interrupt_event.clear()
        self._turn_in_progress = True
        try:
            executed, _ = self._execute_turn_with_outputs(prepared)
        finally:
            self._turn_in_progress = False
        if self.state.interrupt_event.is_set():
            raise RuntimeError("Query interrupted")
        return executed

    def current_session_id(self) -> str | None:
        return self._session_id

    def turn_count(self) -> int:
        return self._turn_count

    def replace_turn_executor(self, executor: TurnExecutor) -> None:
        self._turn_executor = executor

    def use_runtime_turn_executor(self) -> None:
        self._turn_executor = self._runtime_turn_executor

    def replace_runtime_turn_driver(self, driver: TurnDriver) -> None:
        self._runtime_turn_executor.replace_driver(driver)
        self._turn_executor = self._runtime_turn_executor

    def replace_runtime_turn_fallback(self, executor: TurnExecutor) -> None:
        self._runtime_turn_executor.replace_fallback(executor)
        self._turn_executor = self._runtime_turn_executor

    def replace_runtime_backend(self, backend: QueryBackend) -> None:
        self.state.query_backend = backend
        self._runtime_turn_executor.replace_fallback(BackendTurnExecutor(backend))
        self._turn_executor = self._runtime_turn_executor

    def pending_turn_transcript(self, session_id: str) -> list[object]:
        return [*self._transcript, self._session_state_message(session_id, "running")]

    def save_session_state(self, session_id: str) -> None:
        self._saved_sessions[session_id] = SavedSessionState(transcript=list(self._transcript), turn_count=self._turn_count)

    def restore_session_state(self, session_id: str) -> bool:
        saved = self._saved_sessions.get(session_id)
        if saved is None:
            return False
        self._session_id = session_id
        self._transcript = list(saved.transcript)
        self._turn_count = saved.turn_count
        return True

    def replace_transcript(self, transcript: list[object]) -> None:
        self._transcript = list(transcript)
        self._persisted_transcript_count = 0
        if self._active_turn_state is not None:
            self._active_turn_state.transcript = list(self._transcript)
        if self._session_id is not None:
            self.save_session_state(self._session_id)

    #: Prefix for pre-compact transcript snapshots (in-memory rollback).
    _COMPACT_SNAPSHOT_PREFIX = "compact-snapshot:"

    def save_compact_snapshot(self, session_id: str) -> str:
        """Snapshot the current transcript before a destructive compact.

        Reuses the in-memory saved-session store so a manual /compact can be
        rolled back via ``restore_compact_snapshot``. Returns the snapshot id.
        """
        snapshot_id = f"{self._COMPACT_SNAPSHOT_PREFIX}{session_id}"
        self._saved_sessions[snapshot_id] = SavedSessionState(
            transcript=list(self._transcript),
            turn_count=self._turn_count,
        )
        return snapshot_id

    def discard_compact_snapshot(self, session_id: str) -> None:
        """Drop the pre-compact snapshot (used when compaction fails)."""
        self._saved_sessions.pop(f"{self._COMPACT_SNAPSHOT_PREFIX}{session_id}", None)

    def restore_compact_snapshot(self, session_id: str) -> tuple[bool, str]:
        """Restore the pre-compact transcript snapshot, if one exists.

        Writes the snapshot back through the same ``replace_transcript``
        path used for other transcript replacements.
        """
        snapshot_id = f"{self._COMPACT_SNAPSHOT_PREFIX}{session_id}"
        saved = self._saved_sessions.get(snapshot_id)
        if saved is None:
            return False, "no pre-compact snapshot available (run /compact first)"
        count = len(saved.transcript)
        self.replace_transcript(saved.transcript)
        self._turn_count = saved.turn_count
        self._saved_sessions.pop(snapshot_id, None)
        return True, f"Rolled back compact: restored {count} messages"

    def saved_session_ids(self) -> list[str]:
        return sorted(self._saved_sessions)

    def clear_session(self) -> None:
        self._reset_session_state()

    def interrupt(self) -> None:
        self.state.interrupt_event.set()

    def cancel_async_message(self, message_uuid: str) -> bool:
        if message_uuid in self._cancelled_message_uuids:
            return False
        if self._turn_in_progress and self._active_message_uuid == message_uuid:
            self._cancelled_message_uuids.add(message_uuid)
            self.interrupt()
            return True
        return False

    def _current_turn_context(self) -> QueryTurnContext:
        turn_state = self._active_turn_state
        if turn_state is None:
            return QueryTurnContext(
                state=self.state,
                session_id=self._session_id or str(uuid4()),
                transcript=self.transcript,
                turn_count=self._turn_count,
            )
        return QueryTurnContext(
            state=self.state,
            session_id=turn_state.session_id,
            transcript=list(turn_state.transcript),
            turn_count=self._turn_count,
            continuation_count=turn_state.continuation_count,
            transition_reason=turn_state.transition_reason,
        )

    def _record_turn_completion(self, reset_session: bool) -> None:
        if self._session_id is not None:
            self.save_session_state(self._session_id)
            self._persist_session_transcript()
        if reset_session:
            self._reset_session_state()
        else:
            self._turn_count += 1

    def _persist_session_transcript(self) -> None:
        """Append not-yet-persisted transcript entries to the session file."""
        from py_claw.services.session_storage.writer import append_session_entries

        new_entries = self._transcript[self._persisted_transcript_count:]
        if not new_entries:
            return
        written = append_session_entries(
            session_id=self._session_id or "",
            cwd=self.state.cwd,
            entries=new_entries,
        )
        if written:
            self._persisted_transcript_count += len(new_entries)

    def _build_assistant_outputs(
        self,
        session_id: str,
        executed: ExecutedTurn,
        started: float,
        *,
        tool_outputs: list[StdoutMessage] | None = None,
    ) -> list[StdoutMessage]:
        assistant = self._assistant_message(session_id, executed.assistant_text)
        self._transcript.append(assistant)
        outputs: list[StdoutMessage] = list(tool_outputs or [])
        partial = self._partial_assistant_message(session_id, executed.assistant_text)
        if partial is not None:
            outputs.append(partial)
        outputs.extend(
            [
                assistant,
                self._result_message(
                    session_id,
                    executed.assistant_text,
                    started,
                    stop_reason=executed.stop_reason,
                    usage=executed.usage,
                    model_usage=executed.model_usage,
                    duration_api_ms=executed.duration_api_ms,
                    total_cost_usd=executed.total_cost_usd,
                ),
            ]
        )
        prompt_suggestion = self._prompt_suggestion_message(session_id, executed.prompt_suggestion)
        if prompt_suggestion is not None:
            outputs.append(prompt_suggestion)
        return outputs

    def _maybe_run_advisor_review(self, prepared: PreparedTurn, executed: ExecutedTurn) -> ExecutedTurn:
        """Attach the advisor review to the final response, if configured.

        No-op (zero overhead, no extra API call) when ``state.advisor_model``
        is unset, or when the turn did not end with a normal model response.
        When an advisor is configured, one short review of this turn is run
        with the advisor model and appended after the main response. The
        review is best-effort (hard timeout, silent skip on any failure), so
        the correctness and completeness of the main response is never
        affected by it.
        """
        if not self.state.advisor_model or executed.stop_reason != "end_turn":
            return executed
        from py_claw.query.backend import PlaceholderQueryBackend

        backend = self.state.query_backend
        if backend is None or isinstance(backend, PlaceholderQueryBackend):
            return executed

        from py_claw.services.advisor import format_review_block, run_review

        review = run_review(
            backend,
            advisor_model=self.state.advisor_model,
            query_text=prepared.query_text or "",
            answer_text=executed.assistant_text or "",
            session_id=self._session_id or "",
            state=self.state,
        )
        if not review:
            return executed
        return ExecutedTurn(
            assistant_text=f"{executed.assistant_text}\n\n{format_review_block(review)}",
            stop_reason=executed.stop_reason,
            usage=executed.usage,
            model_usage=executed.model_usage,
            duration_api_ms=executed.duration_api_ms,
            total_cost_usd=executed.total_cost_usd,
            tool_calls=executed.tool_calls,
            prompt_suggestion=executed.prompt_suggestion,
        )

    def _finalize_outputs(
        self,
        outputs: list[StdoutMessage],
        session_id: str,
        *,
        reset_session: bool,
    ) -> list[StdoutMessage]:
        yield from outputs
        yield self._session_state_message(session_id, "idle")
        self._record_turn_completion(reset_session)

    def _build_error_outputs(
        self,
        session_id: str,
        error: Exception,
        started: float,
        *,
        reset_session: bool,
        include_request_start: bool,
        partial_outputs: list[StdoutMessage] | None = None,
        skip_initial_state: bool = False,
    ) -> list[StdoutMessage]:
        outputs: list[StdoutMessage] = [] if skip_initial_state else [self._session_state_message(session_id, "running")]
        if include_request_start:
            outputs.append(self._request_start_message(session_id))
        outputs.extend(partial_outputs or [])
        outputs.append(self._error_result_message(session_id, error, started))
        return self._finalize_outputs(outputs, session_id, reset_session=reset_session)

    def _turn_failure_message(self, failure: QueryTurnFailure) -> Exception:
        """The user-facing message for a turn failure.

        Wraps the underlying error in a plain ``RuntimeError(str(error))`` so
        the surfaced text is exactly the message the failing path produced
        (e.g. a host's deny message) rather than a repr of the exception class.
        """
        return RuntimeError(str(failure.error))

    def _should_emit_request_start(self, prepared: PreparedTurn | None) -> bool:
        return bool(prepared and prepared.should_query and prepared.query_text is not None)

    def _execute_turn_with_outputs_streaming(
        self, prepared: PreparedTurn
    ) -> Iterator[SDKPartialAssistantMessage | tuple[ExecutedTurn, list[StdoutMessage]]]:
        """Streaming version: yields intermediate partial messages and finally (ExecutedTurn, tool_outputs).

        Uses execute_streaming() if the executor supports it; falls back to the
        synchronous execute() method otherwise.
        """
        previous_in_progress = self._turn_in_progress
        self._turn_in_progress = True
        if self._session_id is None:
            self._session_id = str(uuid4())
        self._active_turn_state = QueryTurnState(
            session_id=self._session_id,
            prepared=prepared,
            transcript=list(self._transcript),
        )
        tool_outputs: list[StdoutMessage] = []
        web_search_requests = 0
        previous_call_signature: str | None = None
        identical_call_streak = 0
        try:
            for _ in range(self.max_tool_continuations):
                executed: ExecutedTurn | None = None
                # Check if the executor supports streaming
                if hasattr(self._turn_executor, "execute_streaming"):
                    accumulated_text = ""
                    streaming_finished = False
                    stream_usage: dict[str, Any] | None = None
                    stream_reasoning = ""
                    for item in self._turn_executor.execute_streaming(prepared, self._current_turn_context()):
                        if isinstance(item, BackendChunk):
                            if item.type == "text_delta":
                                accumulated_text += item.text
                                partial = self._partial_assistant_message(self._session_id or "", accumulated_text)
                                if partial is not None:
                                    yield partial
                            elif item.type == "stop_reason":
                                streaming_finished = True
                            elif item.type == "usage":
                                try:
                                    stream_usage = json.loads(item.text)
                                except json.JSONDecodeError:
                                    stream_usage = None
                            elif item.type == "reasoning":
                                stream_reasoning += item.text
                        elif isinstance(item, BackendTurnResult):
                            executed = self._to_executed_turn(item)
                            streaming_finished = True

                    if self.state.interrupt_event.is_set():
                        raise QueryTurnFailure(RuntimeError("Query interrupted"), tool_outputs)

                    if streaming_finished and executed is not None:
                        if stream_usage:
                            from py_claw.query.backend import _openai_usage_to_keys
                            executed.usage.update(_openai_usage_to_keys(stream_usage))
                        if not executed.tool_calls:
                            executed = self._apply_tool_usage_metrics(executed, web_search_requests=web_search_requests)
                            # Run stop hooks after model response
                            stop_result = self._run_stop_hooks(executed, session_id=self._session_id or "")
                            if stop_result.prevent_continuation:
                                # Inject blocking errors as tool outputs and stop
                                for error in stop_result.blocking_errors:
                                    tool_outputs.append(self._error_result_message(self._session_id or "", RuntimeError(error), perf_counter()))
                                yield executed, list(tool_outputs)
                                return
                            # If stop hooks provided additional context, inject it
                            if stop_result.additional_context:
                                executed = ExecutedTurn(
                                    assistant_text=executed.assistant_text + "\n\n" + stop_result.additional_context,
                                    stop_reason=executed.stop_reason,
                                    usage=executed.usage,
                                    model_usage=executed.model_usage,
                                    duration_api_ms=executed.duration_api_ms,
                                    total_cost_usd=executed.total_cost_usd,
                                    tool_calls=executed.tool_calls,
                                    prompt_suggestion=executed.prompt_suggestion,
                                )
                            # Check budget before yielding final result
                            budget_result = self._check_budget_and_maybe_compact(executed, tool_outputs=tool_outputs)
                            if budget_result is not None:
                                yield budget_result, list(tool_outputs)
                                return
                            yield executed, list(tool_outputs)
                            return
                    else:
                        raise QueryTurnFailure(RuntimeError("Streaming executor returned no result"), tool_outputs)
                else:
                    # Non-streaming fallback
                    executed = self._turn_executor.execute(prepared, self._current_turn_context())
                    if self.state.interrupt_event.is_set():
                        raise QueryTurnFailure(RuntimeError("Query interrupted"), tool_outputs)
                    if not executed.tool_calls:
                        executed = self._apply_tool_usage_metrics(executed, web_search_requests=web_search_requests)
                        # Run stop hooks after model response
                        stop_result = self._run_stop_hooks(executed, session_id=self._session_id or "")
                        if stop_result.prevent_continuation:
                            for error in stop_result.blocking_errors:
                                tool_outputs.append(self._error_result_message(self._session_id or "", RuntimeError(error), perf_counter()))
                            yield executed, list(tool_outputs)
                            return
                        if stop_result.additional_context:
                            executed = ExecutedTurn(
                                assistant_text=executed.assistant_text + "\n\n" + stop_result.additional_context,
                                stop_reason=executed.stop_reason,
                                usage=executed.usage,
                                model_usage=executed.model_usage,
                                duration_api_ms=executed.duration_api_ms,
                                total_cost_usd=executed.total_cost_usd,
                                tool_calls=executed.tool_calls,
                                prompt_suggestion=executed.prompt_suggestion,
                            )
                        # Check budget before yielding final result
                        budget_result = self._check_budget_and_maybe_compact(executed, tool_outputs=tool_outputs)
                        if budget_result is not None:
                            yield budget_result, list(tool_outputs)
                            return
                        yield executed, list(tool_outputs)
                        return

                self._guard_against_tool_loop(executed.tool_calls, previous_call_signature=previous_call_signature, streak=identical_call_streak, tool_outputs=tool_outputs)
                previous_call_signature, identical_call_streak = self._track_tool_call_streak(
                    executed.tool_calls, previous_call_signature, identical_call_streak
                )

                # Common path: executed with tool_calls
                try:
                    new_outputs, new_web_search = self._execute_tool_calls(prepared, executed.tool_calls)
                    tool_outputs.extend(new_outputs)
                    web_search_requests += new_web_search
                except Exception as exc:
                    raise QueryTurnFailure(exc, tool_outputs) from exc
                self._advance_turn_state_after_tool_calls(executed.tool_calls)
                # Check budget after tool calls complete
                budget_result = self._check_budget_and_maybe_compact(executed, tool_outputs=tool_outputs)
                if budget_result is not None:
                    yield budget_result, list(tool_outputs)
                    return
                # Check auto-compact between turns
                self._check_auto_compact(tool_outputs=tool_outputs)
                if self.state.interrupt_event.is_set():
                    raise QueryTurnFailure(RuntimeError("Query interrupted"), tool_outputs)
        finally:
            self._turn_in_progress = previous_in_progress
            self._active_turn_state = None
        raise QueryTurnFailure(
            RuntimeError(
                f"Turn stopped after {self.max_tool_continuations} tool continuations without a final answer. "
                "The model kept requesting tool calls; check the tool results above or reduce the task scope."
            ),
            tool_outputs,
        )

    def _execute_turn_with_outputs(self, prepared: PreparedTurn) -> tuple[ExecutedTurn, list[StdoutMessage]]:
        """Synchronous version for backward compatibility."""
        previous_in_progress = self._turn_in_progress
        self._turn_in_progress = True
        if self._session_id is None:
            self._session_id = str(uuid4())
        self._active_turn_state = QueryTurnState(
            session_id=self._session_id,
            prepared=prepared,
            transcript=list(self._transcript),
        )
        tool_outputs: list[StdoutMessage] = []
        web_search_requests = 0
        previous_call_signature: str | None = None
        identical_call_streak = 0
        try:
            for _ in range(self.max_tool_continuations):
                executed = self._turn_executor.execute(prepared, self._current_turn_context())
                if self.state.interrupt_event.is_set():
                    raise QueryTurnFailure(RuntimeError("Query interrupted"), tool_outputs)
                if not executed.tool_calls:
                    executed = self._apply_tool_usage_metrics(executed, web_search_requests=web_search_requests)
                    # Run stop hooks after model response
                    stop_result = self._run_stop_hooks(executed, session_id=self._session_id or "")
                    if stop_result.prevent_continuation:
                        for error in stop_result.blocking_errors:
                            tool_outputs.append(self._error_result_message(self._session_id or "", RuntimeError(error), perf_counter()))
                        return executed, tool_outputs
                    if stop_result.additional_context:
                        executed = ExecutedTurn(
                            assistant_text=executed.assistant_text + "\n\n" + stop_result.additional_context,
                            stop_reason=executed.stop_reason,
                            usage=executed.usage,
                            model_usage=executed.model_usage,
                            duration_api_ms=executed.duration_api_ms,
                            total_cost_usd=executed.total_cost_usd,
                            tool_calls=executed.tool_calls,
                            prompt_suggestion=executed.prompt_suggestion,
                        )
                    # Check budget before returning final result
                    budget_result = self._check_budget_and_maybe_compact(executed, tool_outputs=tool_outputs)
                    if budget_result is not None:
                        return budget_result, tool_outputs
                    return executed, tool_outputs
                self._guard_against_tool_loop(executed.tool_calls, previous_call_signature=previous_call_signature, streak=identical_call_streak, tool_outputs=tool_outputs)
                previous_call_signature, identical_call_streak = self._track_tool_call_streak(
                    executed.tool_calls, previous_call_signature, identical_call_streak
                )
                try:
                    new_outputs, new_web_search_requests = self._execute_tool_calls(prepared, executed.tool_calls)
                    tool_outputs.extend(new_outputs)
                    web_search_requests += new_web_search_requests
                except Exception as exc:
                    raise QueryTurnFailure(exc, tool_outputs) from exc
                self._advance_turn_state_after_tool_calls(executed.tool_calls)
                # Check budget after tool calls complete
                budget_result = self._check_budget_and_maybe_compact(executed, tool_outputs=tool_outputs)
                if budget_result is not None:
                    return budget_result, tool_outputs
                # Check auto-compact between turns
                self._check_auto_compact(tool_outputs=tool_outputs)
                if self.state.interrupt_event.is_set():
                    raise QueryTurnFailure(RuntimeError("Query interrupted"), tool_outputs)
        finally:
            self._active_turn_state = None
            self._turn_in_progress = previous_in_progress
        raise QueryTurnFailure(
            RuntimeError(
                f"Turn stopped after {self.max_tool_continuations} tool continuations without a final answer. "
                "The model kept requesting tool calls; check the tool results above or reduce the task scope."
            ),
            tool_outputs,
        )

    def _to_executed_turn(self, result: BackendTurnResult) -> ExecutedTurn:
        """Convert a backend turn result into the engine turn shape."""
        return ExecutedTurn(
            assistant_text=result.assistant_text,
            stop_reason=result.stop_reason,
            usage=dict(result.usage),
            model_usage=dict(result.model_usage),
            duration_api_ms=result.duration_api_ms,
            total_cost_usd=result.total_cost_usd,
            tool_calls=[
                ToolCallRequest(
                    tool_name=tool_call.tool_name,
                    arguments=dict(tool_call.arguments),
                    tool_use_id=tool_call.tool_use_id,
                    parent_tool_use_id=tool_call.parent_tool_use_id,
                )
                for tool_call in result.tool_calls
            ],
            prompt_suggestion=result.prompt_suggestion,
        )

    @staticmethod
    def _tool_call_signature(tool_calls: list[ToolCallRequest]) -> str:
        """Signature used to detect the model repeating identical calls."""
        parts: list[str] = []
        for call in tool_calls:
            try:
                args = json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, default=str)
            except Exception:
                args = str(call.arguments)
            parts.append(f"{call.tool_name}:{args}")
        return "|".join(parts)

    def _track_tool_call_streak(
        self,
        tool_calls: list[ToolCallRequest],
        previous_signature: str | None,
        streak: int,
    ) -> tuple[str | None, int]:
        signature = self._tool_call_signature(tool_calls)
        if previous_signature is not None and signature == previous_signature:
            return signature, streak + 1
        return signature, 1

    def _guard_against_tool_loop(
        self,
        tool_calls: list[ToolCallRequest],
        *,
        previous_call_signature: str | None,
        streak: int,
        tool_outputs: list[StdoutMessage] | None = None,
    ) -> None:
        """Abort the turn when the model repeats the exact same tool calls.

        Weak OpenAI-compatible models sometimes re-issue the identical call
        indefinitely; each extra round costs a full prompt re-send, so stop
        after two consecutive identical rounds with an actionable message.
        """
        if previous_call_signature is None or streak < 2:
            return
        if self._tool_call_signature(tool_calls) != previous_call_signature:
            return
        names = ", ".join(dict.fromkeys(call.tool_name for call in tool_calls))
        raise QueryTurnFailure(
            RuntimeError(
                f"Tool call loop detected: {names} was issued with identical arguments "
                f"{streak + 1} times in a row. The model is not progressing; interrupt the turn "
                "or rephrase the request."
            ),
            partial_outputs=tool_outputs,
        )

    def _apply_tool_usage_metrics(self, executed: ExecutedTurn, *, web_search_requests: int) -> ExecutedTurn:
        # Accumulate session cost regardless of web search
        from py_claw.services.cost_tracker import accumulate_session_cost
        accumulate_session_cost(
            self.state,
            executed.usage,
            executed.model_usage,
            executed.total_cost_usd,
            executed.duration_api_ms,
        )
        self.state.session_turn_count += 1

        if web_search_requests <= 0:
            return executed

        usage = dict(executed.usage)
        usage["webSearchRequests"] = int(usage.get("webSearchRequests", 0)) + web_search_requests

        model_usage: dict[str, object] = {}
        for model_name, metrics in executed.model_usage.items():
            if isinstance(metrics, dict):
                updated_metrics = dict(metrics)
                updated_metrics["webSearchRequests"] = int(updated_metrics.get("webSearchRequests", 0)) + web_search_requests
                model_usage[model_name] = updated_metrics
            else:
                model_usage[model_name] = metrics

        executed.usage = usage
        executed.model_usage = model_usage
        return executed

    def _check_budget_and_maybe_compact(
        self, executed: ExecutedTurn, *, tool_outputs: list[StdoutMessage]
    ) -> ExecutedTurn | None:
        """Check token/cost budget after each turn.

        Returns ``None`` if the budget is fine (or auto-compact was attempted),
        or an ``ExecutedTurn`` to yield immediately when the budget is truly
        exceeded and cannot be compacted away.
        """
        from py_claw.services.cost_tracker import check_budget_exceeded

        exceeded, reason = check_budget_exceeded(self.state)
        if not exceeded:
            return None

        # Budget exceeded -- try auto-compact first
        try:
            from py_claw.services.compact.auto_trigger import should_auto_compact

            model = self.state.model or "claude-sonnet-4-20250514"
            total_tokens = self.state.session_input_tokens + self.state.session_output_tokens
            result = should_auto_compact(total_tokens=total_tokens, model=model)
            if result.should_trigger:
                warning = self._build_budget_warning_message(reason, auto_compacting=True)
                if warning is not None:
                    tool_outputs.append(warning)
                # Return None to allow the loop to continue -- compact will be
                # triggered externally by the compact service.
                return None
        except Exception:
            pass

        # Budget truly exceeded and cannot compact -- stop the loop
        return ExecutedTurn(
            assistant_text=f"[Budget limit reached: {reason}]",
            stop_reason="budget_exceeded",
            usage=executed.usage,
            model_usage=executed.model_usage,
            duration_api_ms=executed.duration_api_ms,
            total_cost_usd=executed.total_cost_usd,
            tool_calls=[],
            prompt_suggestion=None,
        )

    def _check_auto_compact(self, *, tool_outputs: list[StdoutMessage]) -> bool:
        """Check if auto-compact should be triggered.

        Returns True if a compact was recommended and an informational
        message was appended to *tool_outputs*.
        """
        import importlib

        mod = importlib.import_module("py_claw.services.compact.auto_compact_integration")
        check_fn = mod.check_and_trigger_auto_compact  # type: ignore[attr-defined]

        triggered, message = check_fn(self.state)
        if triggered and message:
            try:
                from py_claw.schemas.common import SDKLocalCommandOutputMessage
                from uuid import uuid4

                warning = SDKLocalCommandOutputMessage(
                    type="system",
                    subtype="local_command_output",
                    content=f"📦 {message}",
                    uuid=str(uuid4()),
                    session_id=self._session_id or "",
                )
                tool_outputs.append(warning)  # type: ignore[arg-type]
            except Exception:
                pass
        return triggered

    def _build_budget_warning_message(
        self, reason: str, *, auto_compacting: bool = False
    ) -> StdoutMessage | None:
        """Build a system message about budget status."""
        from py_claw.schemas.common import SDKLocalCommandOutputMessage
        from uuid import uuid4

        suffix = " Auto-compacting context..." if auto_compacting else ""
        return SDKLocalCommandOutputMessage(  # type: ignore[return-value]
            type="system",
            subtype="local_command_output",
            content=f"⚠️ Budget warning: {reason}{suffix}",
            uuid=str(uuid4()),
            session_id=self._session_id or "",
        )

    def _advance_turn_state_after_tool_calls(self, tool_calls: list[ToolCallRequest]) -> None:
        turn_state = self._active_turn_state
        if turn_state is None:
            return
        turn_state.continuation_count += 1
        turn_state.transition_reason = "tool_result"
        turn_state.transcript = list(self._transcript)

        if tool_calls:
            last_tool_call = tool_calls[-1]
            turn_state.transition_reason = f"tool_result:{last_tool_call.tool_name}"

        self._active_turn_state = turn_state

    def _execute_tool_calls(
        self,
        prepared: PreparedTurn,
        tool_calls: list[ToolCallRequest],
    ) -> tuple[list[StdoutMessage], int]:
        settings = self._load_settings()
        outputs: list[StdoutMessage] = []
        web_search_requests = 0
        for tool_call in tool_calls:
            if self.state.interrupt_event.is_set():
                raise RuntimeError("Query interrupted")
            outputs.append(self._execute_tool_call(prepared, settings, tool_call))
            if tool_call.tool_name == "WebSearch":
                web_search_requests += 1
        return outputs, web_search_requests

    def _execute_tool_call(
        self,
        prepared: PreparedTurn,
        settings: SettingsLoadResult,
        tool_call: ToolCallRequest,
    ) -> SDKToolProgressMessage:
        tool_input = dict(tool_call.arguments)
        tool_use_id = tool_call.tool_use_id or str(uuid4())
        parent_tool_use_id = tool_call.parent_tool_use_id or ""
        assistant_step = self._assistant_tool_use_message(
            self._session_id or str(uuid4()),
            tool_call=ToolCallRequest(
                tool_name=tool_call.tool_name,
                arguments=tool_input,
                tool_use_id=tool_use_id,
                parent_tool_use_id=parent_tool_use_id,
            ),
        )
        self._transcript.append(assistant_step)

        started = perf_counter()
        try:
            result, tool_input = self._run_tool_call(prepared, settings, tool_call, tool_input, tool_use_id)
        except (ToolError, ToolPermissionError) as exc:
            # Tool-level failures — a blocked command, an out-of-scope path,
            # a denied permission, a disallowed tool — are recoverable: the
            # exact error text goes back to the model as the tool result, so
            # it can correct course instead of the whole turn dying on one
            # failed call.
            error_text = f"Error: {self._exception_message(exc)}"
            self._transcript.append(
                self._synthetic_tool_result_message(
                    self._session_id or str(uuid4()),
                    tool_use_id=tool_use_id,
                    output=error_text,
                    is_error=True,
                )
            )
            return self._tool_progress_message(
                self._session_id or str(uuid4()),
                tool_use_id=tool_use_id,
                tool_name=tool_call.tool_name,
                parent_tool_use_id=parent_tool_use_id or None,
                elapsed_seconds=max(perf_counter() - started, 0.0),
                tool_input=tool_input,
                tool_response=_summarize_tool_output(error_text),
            )
        elapsed = max(perf_counter() - started, 0.0)
        # The transcript keeps the structured output (SDK consumers rely on
        # it); the model-friendly plain-text rendering happens in the backend
        # when the transcript is converted to provider messages.
        self._transcript.append(
            self._synthetic_tool_result_message(
                self._session_id or str(uuid4()),
                tool_use_id=tool_use_id,
                output=result.output,
            )
        )
        return self._tool_progress_message(
            self._session_id or str(uuid4()),
            tool_use_id=tool_use_id,
            tool_name=result.tool_name,
            parent_tool_use_id=parent_tool_use_id or None,
            elapsed_seconds=elapsed,
            tool_input=tool_input,
            tool_response=_summarize_tool_output(_model_friendly_tool_output(result.tool_name, result.output)),
        )

    def _run_tool_call(
        self,
        prepared: PreparedTurn,
        settings: SettingsLoadResult,
        tool_call: ToolCallRequest,
        tool_input: dict[str, Any],
        tool_use_id: str,
    ) -> tuple[Any, dict[str, Any]]:
        """Run the permission flow and the tool itself; raises on failure.

        Returns ``(result, tool_input)`` — the input may be updated by a
        permission decision (host/user-provided overrides). ToolError /
        ToolPermissionError raised here are expected, recoverable failures;
        the caller turns them into an error tool result.
        """
        if prepared.allowed_tools is not None and tool_call.tool_name not in prepared.allowed_tools:
            raise ToolError(f"{tool_call.tool_name} is not allowed for this turn")

        permission_engine = PermissionEngine.from_settings(settings, mode=self.state.permission_mode)
        runtime = self.state.tool_runtime
        permission_target = runtime.permission_target_for(tool_call.tool_name, tool_input)
        hook_result = self.state.hook_runtime.run_permission_request(
            settings=settings,
            cwd=self.state.cwd,
            tool_name=tool_call.tool_name,
            tool_input=tool_input,
            content=permission_target.content,
            permission_mode=self.state.permission_mode,
        )
        explicit_allow = False
        if hook_result.permission_decision is not None:
            decision = hook_result.permission_decision
            if decision.behavior == "allow":
                explicit_allow = True
                tool_input = dict(decision.updated_input or tool_input)
            else:
                raise ToolPermissionError(
                    decision.message or f"{tool_call.tool_name} requires permission",
                    behavior=decision.behavior,
                )

        if not explicit_allow:
            permission_target = runtime.permission_target_for(tool_call.tool_name, tool_input)
            evaluation = permission_engine.evaluate(permission_target.tool_name, permission_target.content)

            if evaluation.behavior == "ask" and tool_call.tool_name in self.state.session_allowed_tools:
                # User chose "always allow" for this tool earlier in the session.
                explicit_allow = True
                evaluation.behavior = "allow"
                evaluation.reason = "session_allow"
            elif evaluation.behavior == "ask":
                callback = getattr(self.state, "permission_ask_callback", None)
                if callback is not None:
                    behavior, updated_input, callback_msg = callback(
                        tool_use_id, tool_call.tool_name, tool_input, permission_target.content
                    )
                    if behavior == "allow":
                        explicit_allow = True
                        if updated_input is not None:
                            tool_input = updated_input
                        evaluation.behavior = "allow"
                    else:
                        evaluation.behavior = "deny"
                        evaluation.reason = callback_msg or "User denied permission"
                else:
                    host_decision = self._ask_host_for_permission(tool_call.tool_name, tool_input, tool_use_id)
                    if host_decision is not None:
                        host_behavior, host_input, host_message = host_decision
                        if host_behavior == "allow":
                            explicit_allow = True
                            if host_input is not None:
                                tool_input = host_input
                            evaluation.behavior = "allow"
                        else:
                            evaluation.behavior = "deny"
                            evaluation.reason = host_message or "Host denied permission"

            if evaluation.behavior != "allow":
                message = runtime._build_permission_message(tool_call.tool_name, evaluation.reason, evaluation.mode)
                # Preserve the exact host/user decision text (deny message,
                # timeout, channel error) instead of collapsing it to the
                # generic "requires permission" wording. Internal engine
                # reasons ("mode", "deny_rule", "ask", ...) still get the
                # standard wording.
                if (
                    evaluation.behavior == "deny"
                    and evaluation.reason
                    and not evaluation.reason.startswith(("mode", "deny_rule", "ask"))
                ):
                    message = str(evaluation.reason)

                self.state.hook_runtime.run_permission_denied(
                    settings=settings,
                    cwd=self.state.cwd,
                    tool_name=tool_call.tool_name,
                    tool_input=tool_input,
                    tool_use_id=tool_use_id,
                    content=permission_target.content,
                    reason=message,
                    permission_mode=self.state.permission_mode,
                )
                denied = ToolPermissionError(message, behavior=evaluation.behavior)
                denied._denied_reason = message
                raise denied

        result = runtime.execute(
            tool_call.tool_name,
            tool_input,
            cwd=self.state.cwd,
            permission_engine=None if explicit_allow else permission_engine,
            hook_runtime=self.state.hook_runtime,
            hook_settings=settings,
            tool_use_id=tool_use_id,
            permission_mode=self.state.permission_mode,
        )
        return result, tool_input

    def _ask_host_for_permission(
        self, tool_name: str, tool_input: dict[str, Any], tool_use_id: str
    ) -> tuple[str, dict[str, Any] | None, str | None] | None:
        """Ask a stream-json host to answer a permission ask via ``can_use_tool``.

        Only runs when a host request/response channel is installed (i.e. the
        process speaks the stream-json control protocol); TUI callbacks are
        handled before this point and print mode has no channel, so both keep
        their existing behavior. A host deny, timeout, or error is returned as
        a deny decision rather than raised, so the caller's deny path (hooks,
        ToolPermissionError, error-result surfacing) is unchanged.
        """
        channel = getattr(self.state, "host_permission_channel", None)
        if channel is None:
            return None
        try:
            channel.send(tool_name, tool_input, tool_use_id)
        except Exception as exc:
            return ("deny", None, f"Failed to send {tool_name} permission request to host: {exc}")
        try:
            response = channel.wait(_HOST_PERMISSION_TIMEOUT_SECONDS)
        except Exception as exc:
            return ("deny", None, f"Host permission request for {tool_name} failed: {exc}")
        if response is None:
            return ("deny", None, f"{tool_name} permission request timed out waiting for the host")
        behavior = getattr(response, "behavior", None)
        if behavior == "allow":
            updated_input = getattr(response, "updatedInput", None)
            if not isinstance(updated_input, dict):
                updated_input = None
            return ("allow", updated_input, None)
        message = getattr(response, "message", None)
        if not isinstance(message, str) or not message:
            message = f"Host denied permission for {tool_name}"
        return ("deny", None, message)

    def _execute_prepared_turn(
        self,
        prepared: PreparedTurn,
        session_id: str,
        started: float,
    ):
        """Generator that yields StdoutMessage as they are produced.

        Enables streaming: intermediate tool-progress and partial-assistant
        messages are yielded before the final result.
        """
        yield self._session_state_message(session_id, "running")
        if self._should_emit_request_start(prepared):
            yield self._request_start_message(session_id)
        yield from prepared.immediate_outputs
        if prepared.should_query and prepared.query_text is not None:
            try:
                for item in self._execute_turn_with_outputs_streaming(prepared):
                    if isinstance(item, SDKPartialAssistantMessage):
                        # Intermediate streaming text delta
                        yield item
                    else:
                        # Final (ExecutedTurn, tool_outputs)
                        executed, tool_outputs = item
                        executed = self._maybe_run_advisor_review(prepared, executed)
                        yield from self._build_assistant_outputs(
                            session_id, executed, started, tool_outputs=tool_outputs
                        )
            except QueryTurnFailure as exc:
                # We have already yielded session_state(running) and request_start.
                # Tell _build_error_outputs to skip the initial state to avoid duplication.
                yield from self._build_error_outputs(
                    session_id,
                    self._turn_failure_message(exc),
                    started,
                    reset_session=False,
                    include_request_start=False,
                    partial_outputs=exc.partial_outputs,
                    skip_initial_state=True,
                )
                return  # terminates generator — StopIteration propagates to caller
        yield from self._finalize_outputs([], session_id, reset_session=prepared.should_reset_session)

    def handle_user_message(self, message: SDKUserMessage) -> _StreamingList:
        """Returns a lazy streaming list of messages.

        Iterating over the result yields messages as they are produced
        (intermediate tool-progress, partial-assistant, and final results).
        Indexing the result materialises the underlying generator on demand.
        """
        return _StreamingList(self._handle_user_message_gen(message))

    def _handle_user_message_gen(self, message: SDKUserMessage) -> Iterator[StdoutMessage]:
        started = perf_counter()
        session_id = self._ensure_session_id(message.session_id)
        self.state.interrupt_event.clear()
        settings = self._load_settings()
        normalized_user = self._normalize_user_message(message, session_id)
        self._transcript.append(normalized_user)
        self._active_message_uuid = normalized_user.uuid
        prepared: PreparedTurn | None = None

        try:
            prepared = self._prepare_turn(normalized_user, settings, session_id)
            generator = self._execute_prepared_turn(prepared, session_id, started)
            yield from generator
        except QueryTurnFailure as exc:
            # The turn generator re-raises QueryTurnFailure after it already
            # emitted its own session_state(running)/request_start/error outputs,
            # so swallow it here (yielding from an except clause would terminate
            # the generator without letting the finally block run).
            return
        except Exception as exc:
            # Only reached if _prepare_turn or the outer try block raises
            # before yielding anything from the inner generator.
            yield from self._build_error_outputs(
                session_id,
                exc,
                started,
                reset_session=False,
                include_request_start=self._should_emit_request_start(prepared),
            )
        finally:
            self._active_message_uuid = None

    def _prepare_turn(
        self,
        message: SDKUserMessage,
        settings: SettingsLoadResult,
        session_id: str,
    ) -> PreparedTurn:
        text = self._extract_text(message.message)
        if text.startswith("/"):
            prepared = self._prepare_slash_command(text, settings, session_id)
            return self._apply_runtime_defaults(prepared)
        prepared = PreparedTurn(query_text=text, should_query=True)
        return self._apply_runtime_defaults(prepared)

    def _prepare_slash_command(
        self,
        text: str,
        settings: SettingsLoadResult,
        session_id: str,
    ) -> PreparedTurn:
        body = text[1:].strip()
        if not body:
            output_text = "Slash command input was empty."
            return PreparedTurn(
                immediate_outputs=[
                    self._local_command_output_message(session_id, output_text),
                    self._result_message(session_id, output_text),
                ]
            )

        name, _, arguments = body.partition(" ")
        registry = self.state.build_command_registry(settings.effective.get("skills"))
        result = registry.execute(
            name,
            arguments=arguments.strip(),
            state=self.state,
            settings=settings,
            session_id=session_id,
            transcript_size=len(self._transcript),
        )
        if result.output_text is not None:
            return PreparedTurn(
                immediate_outputs=self._render_command_result(result, session_id),
                should_reset_session=result.command.name == "clear",
            )
        return PreparedTurn(
            query_text=result.expanded_prompt or "",
            should_reset_session=result.command.name == "clear",
            should_query=result.should_query,
            allowed_tools=result.allowed_tools,
            model=result.model,
            effort=result.effort,
        )

    def _handle_slash_command(
        self,
        text: str,
        settings: SettingsLoadResult,
        session_id: str,
    ) -> tuple[list[StdoutMessage], bool]:
        prepared = self._prepare_slash_command(text, settings, session_id)
        return prepared.immediate_outputs, prepared.should_reset_session

    def _render_command_result(
        self,
        result: CommandExecutionResult,
        session_id: str,
    ) -> list[StdoutMessage]:
        outputs: list[StdoutMessage] = []
        if result.output_text is not None:
            outputs.append(self._local_command_output_message(session_id, result.output_text))
            outputs.append(self._result_message(session_id, result.output_text))
        return outputs

    def _apply_runtime_defaults(self, prepared: PreparedTurn) -> PreparedTurn:
        updated = prepared

        if updated.model is None and self.state.model is not None:
            updated = replace(updated, model=self.state.model)
        if updated.max_thinking_tokens is None and self.state.max_thinking_tokens is not None:
            updated = replace(updated, max_thinking_tokens=self.state.max_thinking_tokens)
        if updated.system_prompt is None and self.state.system_prompt is not None:
            updated = replace(updated, system_prompt=self.state.system_prompt)
        backend = self.state.query_backend
        if updated.system_prompt is None and backend is not None and not isinstance(backend, PlaceholderQueryBackend):
            # Real backends get the default identity/env/tool-guidance prompt;
            # the placeholder backend echoes the prompt into its canned reply,
            # which would turn the guidance into output noise.
            from py_claw.services.system_prompt import build_default_system_prompt, is_default_system_prompt_enabled

            if is_default_system_prompt_enabled(self.state):
                try:
                    updated = replace(updated, system_prompt=build_default_system_prompt(self.state))
                except Exception:
                    pass
        if updated.append_system_prompt is None and self.state.append_system_prompt is not None:
            updated = replace(updated, append_system_prompt=self.state.append_system_prompt)
        if updated.json_schema is None and self.state.json_schema is not None:
            updated = replace(updated, json_schema=self.state.json_schema)
        if updated.sdk_mcp_servers is None and self.state.sdk_mcp_servers:
            updated = replace(updated, sdk_mcp_servers=list(self.state.sdk_mcp_servers))
        if not updated.prompt_suggestions and self.state.prompt_suggestions:
            updated = replace(updated, prompt_suggestions=True)
        if not updated.agent_progress_summaries and self.state.agent_progress_summaries:
            updated = replace(updated, agent_progress_summaries=True)
        return updated

    def _load_settings(self) -> SettingsLoadResult:
        return get_settings_with_sources(
            flag_settings=self.state.flag_settings,
            policy_settings=self.state.policy_settings,
            cwd=self.state.cwd,
            home_dir=self.state.home_dir,
        )

    def _ensure_session_id(self, incoming_session_id: str | None) -> str:
        if self._session_id is None:
            self._session_id = incoming_session_id or str(uuid4())
        return self._session_id

    def _normalize_user_message(self, message: SDKUserMessage, session_id: str) -> SDKUserMessage:
        return SDKUserMessage(
            type="user",
            message=message.message,
            parent_tool_use_id=message.parent_tool_use_id,
            isSynthetic=message.isSynthetic,
            tool_use_result=message.tool_use_result,
            priority=message.priority,
            timestamp=message.timestamp,
            uuid=message.uuid or str(uuid4()),
            session_id=session_id,
        )

    def _extract_text(self, payload: object) -> str:
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            content = payload.get("content")
            if isinstance(content, str):
                return content.strip()
        return ""

    def _assistant_message(self, session_id: str, content: str) -> SDKAssistantMessage:
        return SDKAssistantMessage(
            type="assistant",
            message={"role": "assistant", "content": content},
            parent_tool_use_id="",
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _assistant_tool_use_message(self, session_id: str, *, tool_call: ToolCallRequest) -> SDKAssistantMessage:
        return SDKAssistantMessage(
            type="assistant",
            message={
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_call.tool_use_id or "",
                        "name": tool_call.tool_name,
                        "input": tool_call.arguments,
                    }
                ],
            },
            parent_tool_use_id=tool_call.parent_tool_use_id or "",
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _synthetic_tool_result_message(
        self,
        session_id: str,
        *,
        tool_use_id: str,
        output: dict[str, Any] | str,
        is_error: bool = False,
    ) -> SDKUserMessage:
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": output,
        }
        if is_error:
            # The Anthropic API's tool_result block carries is_error so the
            # model can tell a failed call from a successful one.
            block["is_error"] = True
        return SDKUserMessage(
            type="user",
            message={
                "role": "user",
                "content": [block],
            },
            parent_tool_use_id=tool_use_id,
            isSynthetic=True,
            tool_use_result=output,
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _tool_progress_message(
        self,
        session_id: str,
        *,
        tool_use_id: str,
        tool_name: str,
        parent_tool_use_id: str | None,
        elapsed_seconds: float,
        tool_input: dict[str, Any] | None = None,
        tool_response: str | None = None,
    ) -> SDKToolProgressMessage:
        return SDKToolProgressMessage(
            type="tool_progress",
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            parent_tool_use_id=parent_tool_use_id,
            elapsed_time_seconds=elapsed_seconds,
            tool_input=tool_input,
            tool_response=tool_response,
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _request_start_message(self, session_id: str) -> SDKRequestStartMessage:
        return SDKRequestStartMessage(
            type="stream_event",
            event=SDKRequestStartEvent(type="stream_request_start"),
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _partial_assistant_message(self, session_id: str, content: str) -> SDKPartialAssistantMessage | None:
        if not self.state.include_partial_messages:
            return None
        return SDKPartialAssistantMessage(
            type="stream_event",
            event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": content}},
            parent_tool_use_id="",
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _prompt_suggestion_message(
        self,
        session_id: str,
        suggestion: str | None,
    ) -> SDKPromptSuggestionMessage | None:
        if not suggestion:
            return None
        return SDKPromptSuggestionMessage(
            type="prompt_suggestion",
            suggestion=suggestion,
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _local_command_output_message(self, session_id: str, content: str) -> SDKLocalCommandOutputMessage:
        return SDKLocalCommandOutputMessage(
            type="system",
            subtype="local_command_output",
            content=content,
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _session_state_message(self, session_id: str, state: str) -> SDKSessionStateChangedMessage:
        return SDKSessionStateChangedMessage(
            type="system",
            subtype="session_state_changed",
            state=state,
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _result_message(
        self,
        session_id: str,
        result_text: str,
        started: float | None = None,
        *,
        stop_reason: str = "end_turn",
        usage: dict[str, object] | None = None,
        model_usage: dict[str, object] | None = None,
        duration_api_ms: float = 0.0,
        total_cost_usd: float = 0.0,
    ) -> SDKResultSuccess:
        duration_ms = 0.0 if started is None else max((perf_counter() - started) * 1000, 0.0)
        return SDKResultSuccess(
            type="result",
            subtype="success",
            duration_ms=duration_ms,
            duration_api_ms=duration_api_ms,
            is_error=False,
            num_turns=self._turn_count + 1,
            result=result_text,
            stop_reason=stop_reason,
            total_cost_usd=total_cost_usd,
            usage=usage or {},
            modelUsage=model_usage or {},
            permission_denials=[],
            fast_mode_state="off",
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _error_result_message(
        self,
        session_id: str,
        error: Exception,
        started: float | None = None,
    ) -> SDKResultError:
        duration_ms = 0.0 if started is None else max((perf_counter() - started) * 1000, 0.0)
        return SDKResultError(
            type="result",
            subtype="error_during_execution",
            duration_ms=duration_ms,
            duration_api_ms=0.0,
            is_error=True,
            num_turns=self._turn_count + 1,
            stop_reason="error",
            total_cost_usd=0.0,
            usage={},
            modelUsage={},
            permission_denials=[],
            errors=[self._exception_message(error)],
            fast_mode_state="off",
            uuid=str(uuid4()),
            session_id=session_id,
        )

    def _exception_message(self, error: Exception) -> str:
        # The exact host/user permission-decision text (deny message,
        # timeout, channel error) is carried on the originating
        # ToolPermissionError; it may be wrapped in a QueryTurnFailure by
        # the tool-continuation loop, so walk the cause chain.
        current: BaseException | None = error
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if isinstance(current, ToolPermissionError):
                denied_reason = getattr(current, "_denied_reason", None)
                if denied_reason:
                    return str(denied_reason)
            current = current.__cause__ or current.__context__
        if len(error.args) == 1 and isinstance(error.args[0], str):
            return error.args[0]
        return str(error)

    def _run_stop_hooks(self, executed: ExecutedTurn, *, session_id: str, subagent_id: str | None = None) -> Any:
        """Run stop hooks after model response."""
        from py_claw.query.stop_hooks import handle_stop_hooks, StopHookResult
        try:
            return handle_stop_hooks(
                self.state,
                session_id=session_id,
                last_assistant_message=executed.assistant_text[:2000],  # Truncate for hook input
                subagent_id=subagent_id,
            )
        except Exception:
            # Stop hooks should never crash the query loop
            return StopHookResult()

    def _reset_session_state(self) -> None:
        if self._session_id is not None:
            self._saved_sessions[self._session_id] = SavedSessionState(transcript=list(self._transcript), turn_count=self._turn_count)
        self._session_id = None
        self._transcript = []
        self._turn_count = 0
        self._persisted_transcript_count = 0
