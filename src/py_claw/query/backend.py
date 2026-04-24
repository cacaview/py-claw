from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from py_claw.query.engine import PreparedTurn, QueryTurnContext


@dataclass(slots=True)
class BackendToolCall:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    tool_use_id: str | None = None
    parent_tool_use_id: str | None = None


@dataclass(slots=True)
class BackendTurnResult:
    assistant_text: str = ""
    stop_reason: str = "end_turn"
    usage: dict[str, object] = field(default_factory=dict)
    model_usage: dict[str, object] = field(default_factory=dict)
    duration_api_ms: float = 0.0
    total_cost_usd: float = 0.0
    tool_calls: list[BackendToolCall] = field(default_factory=list)
    prompt_suggestion: str | None = None


@dataclass(slots=True)
class BackendChunk:
    """A single chunk yielded during a streaming turn."""
    type: str  # 'text_delta' | 'stop_reason' | 'done'
    text: str = ""
    stop_reason: str = "end_turn"


class QueryBackend(Protocol):
    def run_turn(self, prepared: PreparedTurn, context: QueryTurnContext) -> BackendTurnResult: ...


class StreamingQueryBackend(Protocol):
    """A query backend that supports yielding streaming chunks before the final result."""

    def run_turn_streaming(
        self, prepared: PreparedTurn, context: QueryTurnContext
    ) -> Iterator[BackendChunk]:
        ...


def _estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _context_window_for_model(model: str | None) -> int:
    normalized = (model or "").lower()
    if "haiku" in normalized:
        return 200_000
    if "sonnet" in normalized or "opus" in normalized:
        return 200_000
    return 0


def _max_output_tokens_for_model(model: str | None) -> int:
    if model is None:
        return 0
    return 8_192


def _serialized_turn_input(prepared: PreparedTurn) -> str:
    sections: list[str] = []
    if prepared.system_prompt:
        sections.append(prepared.system_prompt)
    if prepared.append_system_prompt:
        sections.append(prepared.append_system_prompt)
    if prepared.json_schema is not None:
        sections.append(json.dumps(prepared.json_schema, sort_keys=True))
    if prepared.query_text:
        sections.append(prepared.query_text)
    return "\n".join(sections)


def _build_usage(
    *,
    prepared: PreparedTurn,
    assistant_text: str,
    backend_type: str,
    sdk_url: str | None = None,
) -> dict[str, object]:
    input_text = _serialized_turn_input(prepared)
    input_tokens = _estimate_tokens(input_text)
    output_tokens = _estimate_tokens(assistant_text)
    usage: dict[str, object] = {
        "backendRequests": 1,
        "backendType": backend_type,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "cacheReadInputTokens": 0,
        "cacheCreationInputTokens": 0,
        "webSearchRequests": 0,
        "inputTextLength": len(input_text),
        "outputTextLength": len(assistant_text),
    }
    if sdk_url is not None:
        usage["sdkUrl"] = sdk_url
    return usage


def _build_model_usage(
    *,
    prepared: PreparedTurn,
    assistant_text: str,
    total_cost_usd: float = 0.0,
) -> dict[str, object]:
    if prepared.model is None:
        return {}

    input_tokens = _estimate_tokens(_serialized_turn_input(prepared))
    output_tokens = _estimate_tokens(assistant_text)
    return {
        prepared.model: {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0,
            "webSearchRequests": 0,
            "costUSD": total_cost_usd,
            "contextWindow": _context_window_for_model(prepared.model),
            "maxOutputTokens": _max_output_tokens_for_model(prepared.model),
        }
    }


def _build_backend_result(
    *,
    prepared: PreparedTurn,
    assistant_text: str,
    backend_type: str,
    sdk_url: str | None = None,
    total_cost_usd: float = 0.0,
    stop_reason: str = "end_turn",
    tool_calls: list[BackendToolCall] | None = None,
    prompt_suggestion: str | None = None,
) -> BackendTurnResult:
    return BackendTurnResult(
        assistant_text=assistant_text,
        stop_reason=stop_reason,
        usage=_build_usage(prepared=prepared, assistant_text=assistant_text, backend_type=backend_type, sdk_url=sdk_url),
        model_usage=_build_model_usage(prepared=prepared, assistant_text=assistant_text, total_cost_usd=total_cost_usd),
        total_cost_usd=total_cost_usd,
        tool_calls=list(tool_calls or []),
        prompt_suggestion=prompt_suggestion,
    )


def _placeholder_response_text(prepared: PreparedTurn) -> str:
    if not prepared.query_text:
        return "Query runtime skeleton received an empty user message."

    lines = ["Query runtime skeleton is not connected to a model yet."]
    if prepared.model is not None:
        lines.append(f"Requested model: {prepared.model}")
    if prepared.effort is not None:
        lines.append(f"Requested effort: {prepared.effort}")
    if prepared.max_thinking_tokens is not None:
        lines.append(f"Max thinking tokens: {prepared.max_thinking_tokens}")
    if prepared.allowed_tools:
        lines.append(f"Allowed tools: {', '.join(prepared.allowed_tools)}")
    if prepared.sdk_mcp_servers:
        lines.append(f"SDK MCP servers: {', '.join(prepared.sdk_mcp_servers)}")
    if prepared.prompt_suggestions:
        lines.append("Prompt suggestions enabled.")
    if prepared.agent_progress_summaries:
        lines.append("Agent progress summaries enabled.")
    if prepared.system_prompt is not None:
        lines.append(f"System prompt: {prepared.system_prompt}")
    if prepared.append_system_prompt is not None:
        lines.append(f"Append system prompt: {prepared.append_system_prompt}")
    if prepared.json_schema is not None:
        lines.append("JSON schema requested.")
    lines.append("")
    lines.append("Received prompt:")
    lines.append(prepared.query_text)
    return "\n".join(lines)


def _serialize_transcript_item(item: object) -> object:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json", by_alias=True, exclude_none=True)
    if is_dataclass(item):
        return asdict(item)
    if isinstance(item, (str, int, float, bool)) or item is None:
        return item
    if isinstance(item, dict):
        return {str(key): _serialize_transcript_item(value) for key, value in item.items()}
    if isinstance(item, list):
        return [_serialize_transcript_item(value) for value in item]
    return repr(item)


def _serialize_turn_request(prepared: PreparedTurn, context: QueryTurnContext) -> dict[str, object]:
    return {
        "prepared": asdict(prepared),
        "context": {
            "session_id": context.session_id,
            "turn_count": context.turn_count,
            "continuation_count": context.continuation_count,
            "transition_reason": context.transition_reason,
            "transcript": [_serialize_transcript_item(item) for item in context.transcript],
        },
    }


def _require_mapping(payload: object, *, field_name: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"SDK backend field '{field_name}' must be a JSON object")
    return payload


def _normalize_usage(
    payload: object,
    *,
    prepared: PreparedTurn,
    assistant_text: str,
    sdk_url: str,
) -> dict[str, object]:
    if payload is None:
        return _build_usage(prepared=prepared, assistant_text=assistant_text, backend_type="sdk-url", sdk_url=sdk_url)
    usage = dict(_require_mapping(payload, field_name="usage"))
    usage.setdefault("backendRequests", 1)
    usage.setdefault("backendType", "sdk-url")
    usage.setdefault("sdkUrl", sdk_url)
    return usage


def _normalize_model_usage(
    payload: object,
    *,
    prepared: PreparedTurn,
    assistant_text: str,
    total_cost_usd: float,
) -> dict[str, object]:
    if payload is None:
        return _build_model_usage(prepared=prepared, assistant_text=assistant_text, total_cost_usd=total_cost_usd)
    return dict(_require_mapping(payload, field_name="model_usage"))


def _string_field(payload: Mapping[str, object], *names: str, default: str = "") -> str:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str):
            return value
    return default


def _float_field(payload: Mapping[str, object], *names: str, default: float = 0.0) -> float:
    for name in names:
        value = payload.get(name)
        if isinstance(value, (int, float)):
            return float(value)
    return default


def _tool_call_field(payload: Mapping[str, object]) -> list[BackendToolCall]:
    raw_tool_calls = payload.get("tool_calls", payload.get("toolCalls"))
    if raw_tool_calls is None:
        return []
    if not isinstance(raw_tool_calls, list):
        raise RuntimeError("SDK backend field 'tool_calls' must be a JSON array")

    tool_calls: list[BackendToolCall] = []
    for index, item in enumerate(raw_tool_calls):
        if not isinstance(item, Mapping):
            raise RuntimeError(f"SDK backend tool_calls[{index}] must be a JSON object")
        tool_name = _string_field(item, "tool_name", "toolName", "name")
        if not tool_name:
            raise RuntimeError(f"SDK backend tool_calls[{index}] is missing tool name")
        arguments = item.get("arguments", item.get("input", {}))
        if not isinstance(arguments, Mapping):
            raise RuntimeError(f"SDK backend tool_calls[{index}].arguments must be a JSON object")
        tool_calls.append(
            BackendToolCall(
                tool_name=tool_name,
                arguments=dict(arguments),
                tool_use_id=_string_field(item, "tool_use_id", "toolUseId", "id") or None,
                parent_tool_use_id=_string_field(item, "parent_tool_use_id", "parentToolUseId") or None,
            )
        )
    return tool_calls


def _parse_sdk_response(payload: object, *, prepared: PreparedTurn, sdk_url: str) -> BackendTurnResult:
    envelope = _require_mapping(payload, field_name="response")
    response = _require_mapping(envelope.get("response"), field_name="response")
    assistant_text = _string_field(response, "assistant_text", "assistantText", "result")
    stop_reason = _string_field(response, "stop_reason", "stopReason", default="end_turn") or "end_turn"
    total_cost_usd = _float_field(response, "total_cost_usd", "totalCostUsd", default=0.0)
    duration_api_ms = _float_field(response, "duration_api_ms", "durationApiMs", default=0.0)
    return BackendTurnResult(
        assistant_text=assistant_text,
        stop_reason=stop_reason,
        usage=_normalize_usage(response.get("usage"), prepared=prepared, assistant_text=assistant_text, sdk_url=sdk_url),
        model_usage=_normalize_model_usage(
            response.get("model_usage", response.get("modelUsage")),
            prepared=prepared,
            assistant_text=assistant_text,
            total_cost_usd=total_cost_usd,
        ),
        duration_api_ms=duration_api_ms,
        total_cost_usd=total_cost_usd,
        tool_calls=_tool_call_field(response),
        prompt_suggestion=_string_field(response, "prompt_suggestion", "promptSuggestion") or None,
    )


def _sdk_backend_request(prepared: PreparedTurn, context: QueryTurnContext, sdk_url: str) -> BackendTurnResult:
    request_payload = _serialize_turn_request(prepared, context)
    request_body = json.dumps(request_payload).encode("utf-8")
    request = Request(
        sdk_url,
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30.0) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace").strip()
        detail = f": {error_body}" if error_body else ""
        raise RuntimeError(f"SDK backend request failed with HTTP {exc.code}{detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"SDK backend request failed: {exc.reason}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("SDK backend returned invalid JSON") from exc
    return _parse_sdk_response(payload, prepared=prepared, sdk_url=sdk_url)


def _placeholder_prompt_suggestion(prepared: PreparedTurn) -> str | None:
    if not prepared.prompt_suggestions or not prepared.query_text:
        return None
    prompt = prepared.query_text.strip()
    if not prompt:
        return None
    compact = " ".join(prompt.split())
    if len(compact) > 120:
        compact = compact[:117].rstrip() + "..."
    return f"Continue from: {compact}"


class PlaceholderQueryBackend:
    def run_turn(self, prepared: PreparedTurn, context: QueryTurnContext) -> BackendTurnResult:
        _logger.warning(
            "Using PlaceholderQueryBackend - no real model backend configured. "
            "Use --sdk-url argument or configure sdk_url in settings to enable real model inference."
        )
        assistant_text = _placeholder_response_text(prepared)
        return _build_backend_result(
            prepared=prepared,
            assistant_text=assistant_text,
            backend_type="placeholder",
            prompt_suggestion=_placeholder_prompt_suggestion(prepared),
        )


class SdkUrlQueryBackend:
    def __init__(self, sdk_url: str) -> None:
        self.sdk_url = sdk_url

    def run_turn(self, prepared: PreparedTurn, context: QueryTurnContext) -> BackendTurnResult:
        return _sdk_backend_request(prepared, context, self.sdk_url)


class ApiQueryBackend:
    """Query backend for OpenAI/API-compatible endpoints.

    Uses streaming SSE at the configured api_url.
    Configure via ApiConfig passed from py_claw.config.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str,
        model: str | None = None,
        max_output_tokens: int = 8192,
        tools: list[dict[str, object]] | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_url = api_url
        self._model = model or "gpt-5.4"
        self._max_output_tokens = max_output_tokens
        self._tools = tools

    def run_turn(self, prepared: PreparedTurn, context: QueryTurnContext) -> BackendTurnResult:
        return _api_request(prepared, context, self._model, self._max_output_tokens, self._api_key, self._api_url, self._tools)

    def run_turn_streaming(
        self, prepared: PreparedTurn, context: QueryTurnContext
    ) -> Iterator[BackendChunk]:
        return _api_request_streaming(
            prepared, context, self._model, self._max_output_tokens, self._api_key, self._api_url, self._tools
        )


def _parse_sse_stream(sse_text: str) -> tuple[str, str]:
    """Parse SSE-formatted text into assistant content and stop reason.

    Handles both OpenAI Responses API SSE format and OpenAI Chat Completions SSE format.
    Returns (assistant_text, stop_reason).
    """
    assistant_text, stop_reason, _ = _parse_sse_stream_with_tools(sse_text)
    return assistant_text, stop_reason


def _parse_sse_stream_with_tools(sse_text: str) -> tuple[str, str, list[BackendToolCall]]:
    """Parse SSE-formatted text into assistant content, stop reason, and tool calls.

    Handles both OpenAI Responses API SSE format and OpenAI Chat Completions SSE format.
    Returns (assistant_text, stop_reason, tool_calls).
    """
    assistant_parts: list[str] = []
    stop_reason = "end_turn"
    tool_calls: list[BackendToolCall] = []
    current_tool_call: dict[str, Any] | None = None
    current_tool_args = ""

    for line in sse_text.split("\n"):
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:])
        except json.JSONDecodeError:
            continue

        # Handle OpenAI Responses API format
        event_type = event.get("type")
        if event_type == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                assistant_parts.append(delta.get("text", ""))
            elif delta.get("type") == "input_json_delta":
                # Tool call arguments in streaming mode
                if current_tool_call is not None:
                    current_tool_args += delta.get("partial_json", "")
        elif event_type == "content_block_stop":
            # Finish current tool call if any
            if current_tool_call is not None and current_tool_args:
                try:
                    args = json.loads(current_tool_args)
                    current_tool_call["args"] = args
                except json.JSONDecodeError:
                    pass
                tool_calls.append(BackendToolCall(
                    tool_name=current_tool_call["name"],
                    arguments=current_tool_call.get("args", {}),
                ))
            current_tool_call = None
            current_tool_args = ""
        elif event_type == "tool_use":
            # Start of a tool call
            name = event.get("name")
            id_ = event.get("id")
            current_tool_call = {"name": name, "id": id_}
            current_tool_args = ""
        elif event_type == "message_stop":
            msg = event.get("message", {})
            stop_reason = msg.get("stop_reason") or "end_turn"
            # Finalize any remaining tool call
            if current_tool_call is not None and current_tool_args:
                try:
                    args = json.loads(current_tool_args)
                    current_tool_call["args"] = args
                except json.JSONDecodeError:
                    pass
                tool_calls.append(BackendToolCall(
                    tool_name=current_tool_call["name"],
                    arguments=current_tool_call.get("args", {}),
                ))
            current_tool_call = None

        # Handle OpenAI Chat Completions format
        elif event.get("object") == "chat.completion.chunk":
            choices = event.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                if "content" in delta:
                    assistant_parts.append(delta.get("content", ""))
                finish_reason = choices[0].get("finish_reason")
                if finish_reason:
                    stop_reason = "end_turn" if finish_reason == "stop" else finish_reason
                # Handle tool_calls in Chat Completions format
                if "tool_calls" in delta:
                    for tc in delta["tool_calls"]:
                        if tc.get("index", 0) == 0:  # First tool call
                            if "function" in tc:
                                if current_tool_call is None:
                                    current_tool_call = {"name": tc["function"]["name"], "args": ""}
                                current_tool_args += tc["function"].get("arguments", "")
                # Check for tool call end
                if finish_reason == "tool_calls" or (finish_reason == "stop" and current_tool_call):
                    if current_tool_call is not None and current_tool_args:
                        try:
                            args = json.loads(current_tool_args)
                            tool_calls.append(BackendToolCall(
                                tool_name=current_tool_call["name"],
                                arguments=args,
                            ))
                        except json.JSONDecodeError:
                            pass
                    current_tool_call = None
                    current_tool_args = ""

    return "".join(assistant_parts), stop_reason, tool_calls


def _api_request(
    prepared: PreparedTurn,
    context: QueryTurnContext,
    model: str,
    max_output_tokens: int,
    api_key: str,
    api_url: str,
    tools: list[dict[str, object]] | None = None,
) -> BackendTurnResult:
    """Call OpenAI/API-compatible /v1/messages with streaming SSE, parse into BackendTurnResult."""
    messages = _transcript_to_openai_messages(context.transcript)
    if prepared.query_text:
        messages.append({"role": "user", "content": prepared.query_text})

    system_parts: list[str] = []
    if prepared.system_prompt:
        system_parts.append(prepared.system_prompt)
    if prepared.append_system_prompt:
        system_parts.append(prepared.append_system_prompt)
    system = "\n\n".join(system_parts) if system_parts else None

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_output_tokens,
        "stream": True,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    try:
        with httpx.stream("POST", api_url, json=body, headers=headers, timeout=60.0) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Right codes API returned HTTP {resp.status_code}: {resp.text[:200]}")
            text = resp.read().decode("utf-8")
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Right codes API request failed: {exc}") from exc

    # Parse SSE stream
    assistant_text, stop_reason, tool_calls = _parse_sse_stream_with_tools(text)

    return BackendTurnResult(
        assistant_text=assistant_text,
        stop_reason=stop_reason,
        usage=_build_usage(prepared=prepared, assistant_text=assistant_text, backend_type="api"),
        model_usage=_build_model_usage(prepared=prepared, assistant_text=assistant_text, total_cost_usd=0.0),
        duration_api_ms=0.0,
        tool_calls=tool_calls,
    )


def _api_request_streaming(
    prepared: PreparedTurn,
    context: QueryTurnContext,
    model: str,
    max_output_tokens: int,
    api_key: str,
    api_url: str,
    tools: list[dict[str, object]] | None = None,
) -> Iterator[BackendChunk]:
    """Generator that yields BackendChunk as SSE data arrives.

    Accumulates full SSE response and parses it at the end to extract tool_calls properly.
    """
    messages: list[dict[str, Any]] = _transcript_to_openai_messages(context.transcript)
    if prepared.query_text:
        messages.append({"role": "user", "content": prepared.query_text})

    system_parts: list[str] = []
    if prepared.system_prompt:
        system_parts.append(prepared.system_prompt)
    if prepared.append_system_prompt:
        system_parts.append(prepared.append_system_prompt)
    system = "\n\n".join(system_parts) if system_parts else None

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_output_tokens,
        "stream": True,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    # Accumulate full SSE response for proper tool_calls parsing
    sse_parts: list[str] = []

    try:
        with httpx.stream("POST", api_url, json=body, headers=headers, timeout=60.0) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Right codes API returned HTTP {resp.status_code}: {resp.text[:200]}")
            for line in resp.iter_lines():
                if not line:
                    continue
                sse_parts.append(line)
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:])
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type")
                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield BackendChunk(type="text_delta", text=text)
                elif event_type == "message_stop":
                    msg = event.get("message", {})
                    stop_reason = msg.get("stop_reason") or "end_turn"
                    yield BackendChunk(type="stop_reason", stop_reason=stop_reason)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Right codes API request failed: {exc}") from exc

    # Parse the accumulated SSE to extract tool_calls
    if sse_parts:
        sse_text = "\n".join(sse_parts)
        _, stop_reason, tool_calls = _parse_sse_stream_with_tools(sse_text)
        if tool_calls:
            yield BackendChunk(type="tool_calls", text=json.dumps([tc.__dict__ for tc in tool_calls]))


class AnthropicQueryBackend:
    """Query backend that calls the Anthropic API directly.

    Uses the official `anthropic` Python SDK. Configure via:
    - ANTHROPIC_API_KEY environment variable
    - Or pass api_key to __init__
    """

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        max_output_tokens: int = 8192,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._client: "AnthropicClient | None" = None

    @property
    def client(self) -> "AnthropicClient":
        """Lazy-load the Anthropic client."""
        if self._client is None:
            from py_claw.services.api.client import AnthropicClient, _build_provider_config
            config = _build_provider_config(self._api_key)
            self._client = AnthropicClient(config=config)
        return self._client

    def run_turn(self, prepared: PreparedTurn, context: QueryTurnContext) -> BackendTurnResult:
        from py_claw.services.api import MessageCreateParams, MessageParam
        from py_claw.services.api.client import AnthropicClient

        # Build messages from transcript
        dict_messages = _transcript_to_messages(context.transcript)

        # Add the current query as a user message
        if prepared.query_text:
            dict_messages.append({"role": "user", "content": prepared.query_text})

        # Convert to MessageParam for the API client
        messages = [MessageParam(role=m["role"], content=m["content"]) for m in dict_messages]

        # Determine model
        model = prepared.model or self._model or "claude-sonnet-4-20250514"

        # Build system prompt
        system_parts: list[str] = []
        if prepared.system_prompt:
            system_parts.append(prepared.system_prompt)
        if prepared.append_system_prompt:
            system_parts.append(prepared.append_system_prompt)
        system = "\n\n".join(system_parts) if system_parts else None

        # Build params
        params = MessageCreateParams(
            model=model,
            messages=messages,
            system=system,
            max_tokens=prepared.max_thinking_tokens or self._max_output_tokens,
        )

        # Call API
        started = time.perf_counter()
        try:
            result = self.client.create_message(params)
        except Exception as exc:
            _logger.error("Anthropic API call failed: %s", exc)
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000

        # Extract assistant text
        assistant_text = _extract_text_from_content(result.content)

        # Extract tool calls
        tool_calls = _extract_tool_calls_from_content(result.content)

        # Build usage
        usage_dict = _build_usage(
            prepared=prepared,
            assistant_text=assistant_text,
            backend_type="anthropic",
        )
        model_usage_dict = _build_model_usage(
            prepared=prepared,
            assistant_text=assistant_text,
            total_cost_usd=0.0,  # SDK doesn't provide cost in response
        )

        return BackendTurnResult(
            assistant_text=assistant_text,
            stop_reason=result.stop_reason or "end_turn",
            usage=usage_dict,
            model_usage=model_usage_dict,
            duration_api_ms=elapsed_ms,
            total_cost_usd=0.0,
            tool_calls=tool_calls,
            prompt_suggestion=None,
        )


def _transcript_to_messages(transcript: list[object]) -> list[dict[str, Any]]:
    """Convert transcript objects to plain dict messages for JSON serialization."""
    messages: list[dict[str, Any]] = []
    for item in transcript:
        role = getattr(item, "type", None)
        if role == "user" or getattr(item, "role", None) == "user":
            content = _extract_message_content(item)
            if content:
                messages.append({"role": "user", "content": content})
        elif role == "assistant" or getattr(item, "role", None) == "assistant":
            content = _extract_assistant_content(item)
            if content:
                messages.append({"role": "assistant", "content": content})
    return messages


def _transcript_to_openai_messages(transcript: list[object]) -> list[dict[str, Any]]:
    """Convert transcript to OpenAI API message format with proper tool result handling.

    Tool results are converted to 'tool' role messages as required by OpenAI API.
    Assistant tool_use blocks are extracted to the 'tool_calls' field.
    """
    messages: list[dict[str, Any]] = []
    for item in transcript:
        item_type = getattr(item, "type", None)
        item_role = getattr(item, "role", None)

        if item_type == "user" or item_role == "user":
            # Check if this is a tool result (synthetic message with tool_result content)
            msg = getattr(item, "message", None)
            if isinstance(msg, dict) and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        # Convert to OpenAI tool result format
                        messages.append({
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": _format_tool_result_content(block.get("content", "")),
                        })
            else:
                # Regular user message
                content = _extract_message_content(item)
                if content:
                    messages.append({"role": "user", "content": content})

        elif item_type == "assistant" or item_role == "assistant":
            # Extract tool_use blocks from content and put them in tool_calls field
            msg = getattr(item, "message", None)
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            tool_calls: list[dict[str, Any]] = []
            text_content: list[str] = []

            if isinstance(msg, dict):
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "tool_use":
                                # Extract tool_use as Chat Completions tool_call format
                                tool_calls.append({
                                    "id": block.get("id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": block.get("name", ""),
                                        "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                                    },
                                })
                            else:
                                # Keep other content blocks as text
                                if block.get("type") == "text":
                                    text_content.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_content.append(block)
                elif isinstance(content, str):
                    text_content.append(content)

            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            if text_content:
                assistant_msg["content"] = "\n".join(text_content)
            elif not tool_calls:
                continue  # Skip empty assistant messages

            messages.append(assistant_msg)

    return messages


def _format_tool_result_content(content: Any) -> str:
    """Format tool result content as a string for OpenAI API."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    if isinstance(content, list):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _extract_message_content(item: object) -> str | list[dict[str, Any]]:
    """Extract content from a user message transcript item."""
    if hasattr(item, "message"):
        msg = item.message
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            return content or ""
        if hasattr(msg, "content"):
            return getattr(msg, "content", "") or ""
    if hasattr(item, "content"):
        content = getattr(item, "content", "")
        if isinstance(content, str):
            return content
        return content or ""
    return ""


def _extract_assistant_content(item: object) -> str | list[dict[str, Any]]:
    """Extract content from an assistant message transcript item."""
    if hasattr(item, "message"):
        msg = item.message
        if isinstance(msg, dict):
            return msg.get("content", "")
        if hasattr(msg, "content"):
            return getattr(msg, "content", "") or ""
    if hasattr(item, "content"):
        content = getattr(item, "content", "")
        if isinstance(content, str):
            return content
        return content or ""
    return ""


def _extract_text_from_content(content: list[Any]) -> str:
    """Extract text from API response content blocks."""
    parts: list[str] = []
    for block in content:
        if hasattr(block, "text") and block.text:
            parts.append(block.text)
        elif hasattr(block, "thinking") and block.thinking:
            # Include thinking in brackets
            parts.append(f"[Thinking: {block.thinking}]")
    return "".join(parts)


def _extract_tool_calls_from_content(content: list[Any]) -> list[BackendToolCall]:
    """Extract tool use blocks from API response content."""
    tool_calls: list[BackendToolCall] = []
    for block in content:
        if hasattr(block, "type") and block.type == "tool_use":
            tool_calls.append(
                BackendToolCall(
                    tool_name=block.name or "",
                    arguments=dict(block.input or {}),
                    tool_use_id=block.id,
                )
            )
    return tool_calls


def _pydantic_to_openai_schema(input_model: type) -> dict[str, Any]:
    """Convert a Pydantic model to OpenAI function parameters schema."""
    if input_model is None:
        return {"type": "object", "properties": {}}

    # Get JSON schema from Pydantic model
    schema = input_model.model_json_schema()

    # Extract properties
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    # Convert to OpenAI format
    parameters = {
        "type": "object",
        "properties": properties,
    }
    if required:
        parameters["required"] = required

    return parameters


def tool_definitions_to_openai_tools(
    tool_definitions: list[tuple[str, type]],
) -> list[dict[str, Any]]:
    """Convert a list of (name, Pydantic model) to OpenAI tools format.

    Args:
        tool_definitions: List of (tool_name, input_model_class) tuples

    Returns:
        List of OpenAI tool dictionaries
    """
    tools = []
    for name, input_model in tool_definitions:
        schema = _pydantic_to_openai_schema(input_model)
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "parameters": schema,
            },
        })
    return tools
