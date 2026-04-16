from __future__ import annotations

from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

from py_claw.commands import CommandExecutionResult
from py_claw.permissions.engine import PermissionEngine
from py_claw.query.backend import BackendToolCall, BackendTurnResult, PlaceholderQueryBackend, QueryBackend
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


class TurnExecutor(Protocol):
    def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn: ...


def _resolve_query_backend(state: RuntimeState) -> QueryBackend:
    return state.query_backend or PlaceholderQueryBackend()


class BackendTurnExecutor:
    def __init__(self, backend: QueryBackend | None = None) -> None:
        self._backend = backend or PlaceholderQueryBackend()

    def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
        prepared = self._apply_runtime_defaults(prepared, context)
        result = self._backend.run_turn(prepared, context)
        return self._to_executed_turn(result)

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
    _MAX_TOOL_CONTINUATIONS = 8

    def __init__(self, state: RuntimeState | None = None, *, turn_executor: TurnExecutor | None = None) -> None:
        if state is None:
            from py_claw.cli.runtime import RuntimeState as _RuntimeState

            state = _RuntimeState()
        self.state = state
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

    @property
    def turn_executor(self) -> TurnExecutor:
        return self._turn_executor

    @property
    def runtime_turn_executor(self) -> RuntimeTurnExecutor:
        return self._runtime_turn_executor

    @property
    def transcript(self) -> list[object]:
        return list(self._transcript)

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
        if self._active_turn_state is not None:
            self._active_turn_state.transcript = list(self._transcript)
        if self._session_id is not None:
            self.save_session_state(self._session_id)

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
        if reset_session:
            self._reset_session_state()
        else:
            self._turn_count += 1

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

    def _finalize_outputs(
        self,
        outputs: list[StdoutMessage],
        session_id: str,
        *,
        reset_session: bool,
    ) -> list[StdoutMessage]:
        outputs.append(self._session_state_message(session_id, "idle"))
        self._record_turn_completion(reset_session)
        return outputs

    def _build_error_outputs(
        self,
        session_id: str,
        error: Exception,
        started: float,
        *,
        reset_session: bool,
        include_request_start: bool,
        partial_outputs: list[StdoutMessage] | None = None,
    ) -> list[StdoutMessage]:
        outputs = [self._session_state_message(session_id, "running")]
        if include_request_start:
            outputs.append(self._request_start_message(session_id))
        outputs.extend(partial_outputs or [])
        outputs.append(self._error_result_message(session_id, error, started))
        return self._finalize_outputs(outputs, session_id, reset_session=reset_session)

    def _should_emit_request_start(self, prepared: PreparedTurn | None) -> bool:
        return bool(prepared and prepared.should_query and prepared.query_text is not None)

    def _execute_turn_with_outputs(self, prepared: PreparedTurn) -> tuple[ExecutedTurn, list[StdoutMessage]]:
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
        try:
            for _ in range(self._MAX_TOOL_CONTINUATIONS):
                executed = self._turn_executor.execute(prepared, self._current_turn_context())
                if self.state.interrupt_event.is_set():
                    raise QueryTurnFailure(RuntimeError("Query interrupted"), tool_outputs)
                if not executed.tool_calls:
                    return self._apply_tool_usage_metrics(executed, web_search_requests=web_search_requests), tool_outputs
                try:
                    new_outputs, new_web_search_requests = self._execute_tool_calls(prepared, executed.tool_calls)
                    tool_outputs.extend(new_outputs)
                    web_search_requests += new_web_search_requests
                except Exception as exc:
                    raise QueryTurnFailure(exc, tool_outputs) from exc
                self._advance_turn_state_after_tool_calls(executed.tool_calls)
                if self.state.interrupt_event.is_set():
                    raise QueryTurnFailure(RuntimeError("Query interrupted"), tool_outputs)
        finally:
            self._active_turn_state = None
            self._turn_in_progress = previous_in_progress
        raise QueryTurnFailure(RuntimeError("Query exceeded maximum tool continuations"), tool_outputs)

    def _apply_tool_usage_metrics(self, executed: ExecutedTurn, *, web_search_requests: int) -> ExecutedTurn:
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
        if prepared.allowed_tools is not None and tool_call.tool_name not in prepared.allowed_tools:
            raise ToolError(f"{tool_call.tool_name} is not allowed for this turn")

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
            
            if evaluation.behavior == "ask":
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

            if evaluation.behavior != "allow":
                message = runtime._build_permission_message(tool_call.tool_name, evaluation.reason, evaluation.mode)
                if getattr(evaluation, "reason", None) == "User denied permission":
                    message = "User denied permission"
                
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
                raise ToolPermissionError(message, behavior=evaluation.behavior)

        started = perf_counter()
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
        elapsed = max(perf_counter() - started, 0.0)
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
        )

    def _execute_prepared_turn(
        self,
        prepared: PreparedTurn,
        session_id: str,
        started: float,
    ) -> list[StdoutMessage]:
        outputs: list[StdoutMessage] = [self._session_state_message(session_id, "running")]
        if self._should_emit_request_start(prepared):
            outputs.append(self._request_start_message(session_id))
        outputs.extend(prepared.immediate_outputs)
        if prepared.should_query and prepared.query_text is not None:
            executed, tool_outputs = self._execute_turn_with_outputs(prepared)
            outputs.extend(self._build_assistant_outputs(session_id, executed, started, tool_outputs=tool_outputs))
        return self._finalize_outputs(outputs, session_id, reset_session=prepared.should_reset_session)

    def handle_user_message(self, message: SDKUserMessage) -> list[StdoutMessage]:
        started = perf_counter()
        session_id = self._ensure_session_id(message.session_id)
        settings = self._load_settings()
        normalized_user = self._normalize_user_message(message, session_id)
        self._transcript.append(normalized_user)
        self._active_message_uuid = normalized_user.uuid
        prepared: PreparedTurn | None = None

        try:
            prepared = self._prepare_turn(normalized_user, settings, session_id)
            return self._execute_prepared_turn(prepared, session_id, started)
        except QueryTurnFailure as exc:
            return self._build_error_outputs(
                session_id,
                exc.error,
                started,
                reset_session=False,
                include_request_start=self._should_emit_request_start(prepared),
                partial_outputs=exc.partial_outputs,
            )
        except Exception as exc:
            return self._build_error_outputs(
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
        output: dict[str, Any],
    ) -> SDKUserMessage:
        return SDKUserMessage(
            type="user",
            message={
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": output,
                    }
                ],
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
    ) -> SDKToolProgressMessage:
        return SDKToolProgressMessage(
            type="tool_progress",
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            parent_tool_use_id=parent_tool_use_id,
            elapsed_time_seconds=elapsed_seconds,
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
        if len(error.args) == 1 and isinstance(error.args[0], str):
            return error.args[0]
        return str(error)

    def _reset_session_state(self) -> None:
        if self._session_id is not None:
            self._saved_sessions[self._session_id] = SavedSessionState(transcript=list(self._transcript), turn_count=self._turn_count)
        self._session_id = None
        self._transcript = []
        self._turn_count = 0
