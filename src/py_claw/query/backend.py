from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Mapping, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request

import httpx

from py_claw.utils.http import open_url as _open_url

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
    reasoning_text: str = ""
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


@runtime_checkable
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
        with _open_url(request, timeout=30.0) as response:
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


def _append_query_message(messages: list[dict[str, Any]], query_text: str | None) -> None:
    """Append the turn's user message unless the transcript already carries it.

    The live query path records the user message in the transcript before the
    first backend call, so appending unconditionally re-states the instruction
    AFTER every tool result. The model then faithfully answers the re-stated
    instruction by calling the tool again — an infinite tool loop. Sub-callers
    (e.g. the Agent tool) build PreparedTurn with an empty transcript and rely
    on this append, so it must stay for those cases.
    """
    if not query_text:
        return
    for message in messages:
        if message.get("role") == "user" and message.get("content") == query_text:
            return
    messages.append({"role": "user", "content": query_text})


def _normalize_chat_completions_url(api_url: str) -> str:
    """Normalize an api_url into a full chat-completions endpoint.

    Users may configure either a base URL (e.g. ``http://host:8002/v1``) or a
    full endpoint. POST always targets the returned URL, so a bare base URL
    must get ``/chat/completions`` appended.
    """
    url = (api_url or "").strip().rstrip("/")
    if not url:
        return url
    path = urlparse(url).path.rstrip("/")
    if path.endswith("/chat/completions"):
        return url
    return f"{url}/chat/completions"


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
        temperature: float | None = None,
        top_p: float | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._api_url = _normalize_chat_completions_url(api_url)
        self._model = model or "gpt-5.4"
        self._max_output_tokens = max_output_tokens
        self._tools = tools
        self._temperature = temperature
        self._top_p = top_p
        self._timeout_seconds = timeout_seconds

    def run_turn(self, prepared: PreparedTurn, context: QueryTurnContext) -> BackendTurnResult:
        # Respect a per-turn model override (e.g. the advisor model); the
        # constructor model is the default, mirroring AnthropicQueryBackend.
        return _api_request(
            prepared, context, prepared.model or self._model, self._max_output_tokens, self._api_key, self._api_url, self._tools,
            temperature=self._temperature, top_p=self._top_p, timeout_seconds=self._timeout_seconds,
        )

    def run_turn_streaming(
        self, prepared: PreparedTurn, context: QueryTurnContext
    ) -> Iterator[BackendChunk]:
        return _api_request_streaming(
            prepared, context, self._model, self._max_output_tokens, self._api_key, self._api_url, self._tools,
            temperature=self._temperature, top_p=self._top_p, timeout_seconds=self._timeout_seconds,
        )


@dataclass
class _SseParseResult:
    """Parsed SSE response across both supported wire formats."""

    text: str = ""
    reasoning_text: str = ""
    stop_reason: str = "end_turn"
    tool_calls: list[BackendToolCall] = field(default_factory=list)
    usage: dict[str, Any] | None = None


def _parse_sse_payload(sse_text: str) -> _SseParseResult:
    """Parse an SSE response body into text/reasoning/tool calls/usage.

    Handles the OpenAI Chat Completions formats (streaming chunks and the
    full non-chunk response) and the Anthropic Responses-style events. Tool
    calls are aggregated per ``index`` so parallel tool calls survive, and
    the model-native ``tool_call_id`` is preserved for strict backends that
    validate id pairing.
    """
    result = _SseParseResult()
    openai_calls: dict[int, dict[str, Any]] = {}
    # Anthropic-style pending tool call
    ant_tool: dict[str, Any] | None = None
    ant_args = ""

    def finalize_anthropic() -> None:
        nonlocal ant_tool, ant_args
        if ant_tool is not None and ant_args:
            try:
                ant_tool["args"] = json.loads(ant_args)
            except json.JSONDecodeError:
                pass
            result.tool_calls.append(BackendToolCall(
                tool_name=ant_tool.get("name") or "",
                arguments=ant_tool.get("args") or {},
                tool_use_id=ant_tool.get("id"),
            ))
        ant_tool = None
        ant_args = ""

    for line in sse_text.split("\n"):
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:])
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")
        if event_type == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                result.text += delta.get("text") or ""
            elif delta.get("type") == "input_json_delta" and ant_tool is not None:
                ant_args += delta.get("partial_json") or ""
        elif event_type == "content_block_stop":
            finalize_anthropic()
        elif event_type == "tool_use":
            finalize_anthropic()
            ant_tool = {"name": event.get("name"), "id": event.get("id")}
            ant_args = ""
        elif event_type == "message_stop":
            stop = (event.get("message") or {}).get("stop_reason")
            if stop:
                result.stop_reason = stop
            finalize_anthropic()

        elif event.get("object") == "chat.completion.chunk":
            choices = event.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str):
                    result.text += content
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if isinstance(reasoning, str):
                    result.reasoning_text += reasoning
                finish_reason = choices[0].get("finish_reason")
                if finish_reason:
                    result.stop_reason = "end_turn" if finish_reason == "stop" else finish_reason
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index") or 0
                    slot = openai_calls.setdefault(idx, {"id": None, "name": "", "args": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["args"] += fn["arguments"]
            usage = event.get("usage")
            if isinstance(usage, dict) and usage:
                result.usage = usage

        elif event.get("object") == "chat.completion":
            # Full non-chunk response body
            choices = event.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                if isinstance(message.get("content"), str):
                    result.text += message["content"]
                reasoning = message.get("reasoning_content") or message.get("reasoning")
                if isinstance(reasoning, str):
                    result.reasoning_text += reasoning
                for tc in message.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    openai_calls[len(openai_calls)] = {
                        "id": tc.get("id"),
                        "name": fn.get("name") or "",
                        "args": fn.get("arguments") or "",
                    }
                finish_reason = choices[0].get("finish_reason")
                if finish_reason:
                    result.stop_reason = "end_turn" if finish_reason == "stop" else finish_reason
            usage = event.get("usage")
            if isinstance(usage, dict) and usage:
                result.usage = usage

    finalize_anthropic()

    for idx in sorted(openai_calls):
        slot = openai_calls[idx]
        if not slot["name"]:
            continue
        try:
            args = json.loads(slot["args"]) if slot["args"] else {}
        except json.JSONDecodeError:
            args = {}
        result.tool_calls.append(BackendToolCall(
            tool_name=slot["name"],
            arguments=args,
            tool_use_id=slot["id"],
        ))
    return result


def _extract_usage_from_sse(sse_text: str) -> dict[str, Any] | None:
    """Pull the server-reported usage object out of an SSE body, if any."""
    return _parse_sse_payload(sse_text).usage


def _openai_usage_to_keys(usage: dict[str, Any] | None) -> dict[str, object]:
    """Map an OpenAI usage object onto py-claw usage keys."""
    if not usage:
        return {}
    mapped: dict[str, object] = {}
    if usage.get("prompt_tokens") is not None:
        mapped["inputTokens"] = usage["prompt_tokens"]
    if usage.get("completion_tokens") is not None:
        mapped["outputTokens"] = usage["completion_tokens"]
    if usage.get("total_tokens") is not None:
        mapped["totalTokens"] = usage["total_tokens"]
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict) and details.get("cached_tokens") is not None:
        mapped["cacheReadInputTokens"] = details["cached_tokens"]
    return mapped


def _parse_sse_stream(sse_text: str) -> tuple[str, str]:
    """Parse SSE-formatted text into assistant content and stop reason."""
    parsed = _parse_sse_payload(sse_text)
    return parsed.text, parsed.stop_reason


def _parse_sse_stream_with_tools(sse_text: str) -> tuple[str, str, list[BackendToolCall]]:
    """Parse SSE-formatted text into assistant content, stop reason, and tool calls."""
    parsed = _parse_sse_payload(sse_text)
    return parsed.text, parsed.stop_reason, parsed.tool_calls


class ApiRequestError(RuntimeError):
    """Classified API failure: kind is network | auth | rate_limit | server | protocol."""

    def __init__(self, kind: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status


_RETRYABLE_KINDS = {"network", "rate_limit", "server"}


def _classify_http_status(status: int) -> str:
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "rate_limit"
    if status >= 500:
        return "server"
    return "protocol"


def _request_kind_label(kind: str) -> str:
    return {
        "network": "network error",
        "auth": "authentication error (check api_key)",
        "rate_limit": "rate limited (429)",
        "server": "server error",
        "protocol": "request rejected",
    }.get(kind, kind)


def _post_sse(
    api_url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float,
    *,
    max_attempts: int = 3,
) -> str:
    """POST and return the full SSE text, with classification and backoff.

    Retries transient failures (network, 429, 5xx). A 400 that names
    ``stream_options`` falls back to a body without it once (older servers
    reject the field instead of ignoring it).
    """
    import time as _time

    attempt = 0
    delay = 0.5
    include_usage = True
    while True:
        attempt += 1
        send_body = dict(body)
        if send_body.get("stream") and include_usage:
            send_body["stream_options"] = {"include_usage": True}
        try:
            with httpx.stream("POST", api_url, json=send_body, headers=headers, timeout=timeout_seconds) as resp:
                if resp.status_code != 200:
                    error_text = resp.read().decode("utf-8", errors="replace")[:300]
                    if resp.status_code == 400 and "stream_options" in error_text and include_usage:
                        include_usage = False
                        continue
                    kind = _classify_http_status(resp.status_code)
                    raise ApiRequestError(
                        kind,
                        f"API {_request_kind_label(kind)}: HTTP {resp.status_code}: {error_text}",
                        resp.status_code,
                    )
                return resp.read().decode("utf-8")
        except httpx.HTTPError as exc:
            if attempt >= max_attempts:
                raise ApiRequestError("network", f"API network error after {attempt} attempts: {exc}") from exc
        except ApiRequestError as exc:
            if exc.kind not in _RETRYABLE_KINDS or attempt >= max_attempts:
                raise
        _time.sleep(delay)
        delay *= 3


def _merge_real_usage(
    usage_dict: dict[str, object],
    parsed: "_SseParseResult",
) -> dict[str, object]:
    """Prefer server-reported token counts over text-length estimates."""
    real = _openai_usage_to_keys(parsed.usage)
    usage_dict.update(real)
    return usage_dict


def _build_request_body(
    prepared: PreparedTurn,
    context: QueryTurnContext,
    model: str,
    max_output_tokens: int,
    tools: list[dict[str, object]] | None,
    *,
    temperature: float | None = None,
    top_p: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Assemble messages and request body shared by both request paths."""
    messages = _transcript_to_openai_messages(context.transcript)
    _append_query_message(messages, prepared.query_text)

    system_parts: list[str] = []
    if prepared.system_prompt:
        system_parts.append(prepared.system_prompt)
    if prepared.append_system_prompt:
        system_parts.append(prepared.append_system_prompt)
    system = "\n\n".join(system_parts) if system_parts else None

    # Send the system prompt as a standard role=system message. OpenAI-
    # compatible servers (vLLM included) silently ignore a top-level
    # "system" body field — verified experimentally: prompt_tokens stays
    # flat with body["system"] but grows with a role=system message.
    if system:
        messages = [{"role": "system", "content": system}] + messages

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_output_tokens,
        "stream": True,
    }
    if tools:
        body["tools"] = tools
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p
    return messages, body


_API_HEADERS = {
    "Authorization": "Bearer {api_key}",
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
}


def _headers_for(api_key: str) -> dict[str, str]:
    headers = dict(_API_HEADERS)
    headers["Authorization"] = headers["Authorization"].format(api_key=api_key)
    return headers


def _api_request(
    prepared: PreparedTurn,
    context: QueryTurnContext,
    model: str,
    max_output_tokens: int,
    api_key: str,
    api_url: str,
    tools: list[dict[str, object]] | None = None,
    *,
    temperature: float | None = None,
    top_p: float | None = None,
    timeout_seconds: float = 120.0,
) -> BackendTurnResult:
    """Call an OpenAI-compatible chat completions endpoint and parse the SSE reply."""
    _messages, body = _build_request_body(
        prepared, context, model, max_output_tokens, tools,
        temperature=temperature, top_p=top_p,
    )
    started = time.perf_counter()
    sse_text = _post_sse(api_url, body, _headers_for(api_key), timeout_seconds)
    parsed = _parse_sse_payload(sse_text)

    usage_dict = _build_usage(prepared=prepared, assistant_text=parsed.text, backend_type="api")
    _merge_real_usage(usage_dict, parsed)
    model_usage_dict = _build_model_usage(prepared=prepared, assistant_text=parsed.text, total_cost_usd=0.0)
    elapsed_ms = (time.perf_counter() - started) * 1000

    return BackendTurnResult(
        assistant_text=parsed.text,
        reasoning_text=parsed.reasoning_text,
        stop_reason=parsed.stop_reason,
        usage=usage_dict,
        model_usage=model_usage_dict,
        duration_api_ms=elapsed_ms,
        total_cost_usd=0.0,
        tool_calls=parsed.tool_calls,
    )


def _api_request_streaming(
    prepared: PreparedTurn,
    context: QueryTurnContext,
    model: str,
    max_output_tokens: int,
    api_key: str,
    api_url: str,
    tools: list[dict[str, object]] | None = None,
    *,
    temperature: float | None = None,
    top_p: float | None = None,
    timeout_seconds: float = 120.0,
) -> Iterator[BackendChunk]:
    """Generator yielding BackendChunk as SSE data arrives.

    Emits text deltas live, then parses the accumulated SSE for tool calls
    (arguments arrive split across chunks) and the server-reported usage.
    """
    _messages, body = _build_request_body(
        prepared, context, model, max_output_tokens, tools,
        temperature=temperature, top_p=top_p,
    )

    sse_text = _post_sse(api_url, body, _headers_for(api_key), timeout_seconds)
    parsed = _parse_sse_payload(sse_text)

    for line in sse_text.split("\n"):
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:])
        except json.JSONDecodeError:
            continue
        if event.get("object") != "chat.completion.chunk":
            continue
        choices = event.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str) and content:
                yield BackendChunk(type="text_delta", text=content)
            finish_reason = choices[0].get("finish_reason")
            if finish_reason:
                yield BackendChunk(
                    type="stop_reason",
                    stop_reason="end_turn" if finish_reason == "stop" else finish_reason,
                )
    if parsed.tool_calls:
        yield BackendChunk(type="tool_calls", text=json.dumps([asdict(tc) for tc in parsed.tool_calls]))
    if parsed.reasoning_text:
        yield BackendChunk(type="reasoning", text=parsed.reasoning_text)
    if parsed.usage:
        yield BackendChunk(type="usage", text=json.dumps(parsed.usage))


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
        tools: list["ToolParam"] | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._tools = list(tools or [])
        self._base_url = base_url
        self._client: "AnthropicClient | None" = None

    @property
    def client(self) -> "AnthropicClient":
        """Lazy-load the Anthropic client."""
        if self._client is None:
            from py_claw.services.api.client import AnthropicClient, _build_provider_config
            config = _build_provider_config(self._api_key)
            if self._base_url:
                # Anthropic SDK appends /v1/messages to the base URL itself.
                config.base_url = self._base_url.rstrip("/")
                if config.base_url.endswith("/v1"):
                    config.base_url = config.base_url[: -len("/v1")]
            self._client = AnthropicClient(config=config)
        return self._client

    def run_turn(self, prepared: PreparedTurn, context: QueryTurnContext) -> BackendTurnResult:
        from py_claw.services.api import MessageCreateParams, MessageParam
        from py_claw.services.api.client import AnthropicClient

        # Build messages from transcript
        dict_messages = _transcript_to_messages(context.transcript)

        # Add the current query as a user message
        _append_query_message(dict_messages, prepared.query_text)

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
            tools=self._tools or None,
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

        # Build usage from the server-reported token counts; fall back to
        # text-length estimates only when the response lacks usage.
        usage_data = {}
        if result.usage is not None:
            usage_data = {
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cache_read_input_tokens": result.usage.cache_read_input_tokens or 0,
                "cache_creation_input_tokens": result.usage.cache_creation_input_tokens or 0,
            }

        # Calculate actual cost from token counts
        from py_claw.services.cost_tracker import calculate_cost
        total_cost_usd = calculate_cost(
            model or self._model or "",
            usage_data.get("input_tokens", 0),
            usage_data.get("output_tokens", 0),
            usage_data.get("cache_read_input_tokens", 0),
            usage_data.get("cache_creation_input_tokens", 0),
        )

        usage_dict = _build_usage(
            prepared=prepared,
            assistant_text=assistant_text,
            backend_type="anthropic",
        )
        if usage_data:
            usage_dict["inputTokens"] = usage_data["input_tokens"]
            usage_dict["outputTokens"] = usage_data["output_tokens"]
            if usage_data["cache_read_input_tokens"]:
                usage_dict["cacheReadInputTokens"] = usage_data["cache_read_input_tokens"]
            if usage_data["cache_creation_input_tokens"]:
                usage_dict["cacheCreationInputTokens"] = usage_data["cache_creation_input_tokens"]
        model_usage_dict = _build_model_usage(
            prepared=prepared,
            assistant_text=assistant_text,
            total_cost_usd=total_cost_usd,
        )

        return BackendTurnResult(
            assistant_text=assistant_text,
            stop_reason=result.stop_reason or "end_turn",
            usage=usage_dict,
            model_usage=model_usage_dict,
            duration_api_ms=elapsed_ms,
            total_cost_usd=total_cost_usd,
            tool_calls=tool_calls,
            prompt_suggestion=None,
        )


def _normalize_anthropic_content(content: Any) -> Any:
    """Render transcript content blocks into API-valid Anthropic shapes.

    tool_result blocks carry the structured tool output dict; the Messages
    API only accepts a string or a list of text blocks there, so render it
    with the same model-friendly formatting the OpenAI path uses.
    """
    if not isinstance(content, list):
        return content
    normalized: list[dict[str, Any]] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            rendered = block.get("content")
            if not isinstance(rendered, str):
                rendered = _format_tool_result_content(rendered)
            fixed = dict(block)
            fixed["content"] = rendered
            normalized.append(fixed)
        else:
            normalized.append(block)
    return normalized


def _transcript_to_messages(transcript: list[object]) -> list[dict[str, Any]]:
    """Convert transcript objects to plain dict messages for JSON serialization."""
    messages: list[dict[str, Any]] = []
    for item in transcript:
        role = getattr(item, "type", None)
        if role == "user" or getattr(item, "role", None) == "user":
            content = _extract_message_content(item)
            content = _normalize_anthropic_content(content)
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
    """Format tool result content as a string for the model.

    Structured tool outputs mix model-relevant fields (stdout/stderr/exit
    code) with harness metadata (security classification). Sending that
    metadata verbatim makes weaker models re-issue the same call, so render a
    plain-text view here while the transcript itself stays structured.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if "stdout" in content or "stderr" in content or "exitCode" in content:
            parts: list[str] = []
            stdout = content.get("stdout")
            if stdout:
                parts.append(str(stdout).rstrip("\n"))
            stderr = content.get("stderr")
            if stderr:
                parts.append(f"stderr:\n{str(stderr).rstrip()}")
            exit_code = content.get("exitCode")
            if exit_code not in (None, 0):
                parts.append(f"exit code: {exit_code}")
            if parts:
                return "\n".join(parts)
        if isinstance(content.get("content"), str):
            return content["content"]
        if isinstance(content.get("text"), str):
            return content["text"]
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
    """Extract the user-facing text from API response content blocks.

    Thinking blocks are dropped: the final answer is what the transcript and
    the UI should carry (upstream Claude Code does not replay thinking as
    assistant text either).
    """
    parts: list[str] = []
    for block in content:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            parts.append(block.text)
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


def tool_definitions_to_anthropic_tools(
    tool_definitions: list[tuple[str, type]],
) -> list[ToolParam]:
    """Convert (name, Pydantic model) pairs into Anthropic ToolParam format."""
    from py_claw.services.api.types import ToolParam

    tools: list[ToolParam] = []
    for name, input_model in tool_definitions:
        schema = _pydantic_to_openai_schema(input_model)
        doc = (getattr(input_model, "__doc__", "") or "").strip()
        description = doc.split("\n")[0] if doc else None
        tools.append(ToolParam(name=name, description=description, input_schema=schema))
    return tools


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
