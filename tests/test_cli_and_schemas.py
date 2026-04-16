from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO

import pytest
from pydantic import TypeAdapter

from py_claw.cli.main import main
from py_claw.cli.runtime import RuntimeState
from py_claw.cli.structured_io import StructuredIO, StructuredIOParseError, StructuredIORequestError
from py_claw.commands import CommandRegistry
from py_claw.hooks.schemas import HooksSettings
from py_claw.query import (
    BackendToolCall,
    BackendTurnExecutor,
    BackendTurnResult,
    ExecutedTurn,
    PreparedTurn,
    QueryBackend,
    QueryRuntime,
    QueryTurnContext,
    SdkUrlQueryBackend,
    ToolCallRequest,
)
from py_claw.settings.loader import get_settings_with_sources
from py_claw.skills import parse_skill_document
from py_claw.schemas.common import (
    AsyncHookJSONOutput,
    JsonSchemaOutputFormat,
    PermissionResultAllow,
    PermissionRequestHookSpecificOutput,
    PreToolUseHookInput,
    SDKAssistantMessage,
    SDKHookResponseMessage,
    SDKLocalCommandOutputMessage,
    SDKMessage,
    SDKPartialAssistantMessage,
    SDKPromptSuggestionMessage,
    SDKRequestStartMessage,
    SDKResultError,
    SDKResultSuccess,
    SDKSessionStateChangedMessage,
    SDKTaskNotificationMessage,
    SDKToolProgressMessage,
    SyncHookJSONOutput,
)
from py_claw.schemas.control import (
    SDKControlGetContextUsageResponse,
    SDKControlGetSettingsResponse,
    SDKControlInitializeRequest,
    SDKControlMcpSetServersRequest,
    SDKControlMcpSetServersResponse,
    SDKControlRequestEnvelope,
    SDKControlResponseEnvelope,
    SDKKeepAliveMessage,
    SDKUpdateEnvironmentVariablesMessage,
    SDKUserMessage,
)
from py_claw.settings.types import SettingsModel


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "0.1.0"


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--input-format", "stream-json"], "--input-format=stream-json requires --output-format=stream-json"),
        (["--sdk-url", "http://example.com"], "--sdk-url requires both --input-format=stream-json and --output-format=stream-json"),
        (["--include-partial-messages"], "--include-partial-messages requires --print with --output-format=stream-json"),
    ],
)
def test_cli_validation_errors(argv: list[str], message: str) -> None:
    with pytest.raises(SystemExit, match=message):
        main(argv)


@contextmanager
def _serve_http(handler_type: type[BaseHTTPRequestHandler]):
    server = HTTPServer(("127.0.0.1", 0), handler_type)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_cli_stream_json_sdk_url_routes_query_backend() -> None:
    payloads: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payloads.append(json.loads(body.decode("utf-8")))
            response = {
                "response": {
                    "assistant_text": "sdk backend says hi",
                    "usage": {
                        "backendRequests": 1,
                        "backendType": "sdk-url",
                        "inputTokens": 11,
                        "outputTokens": 5,
                        "cacheReadInputTokens": 0,
                        "cacheCreationInputTokens": 0,
                        "webSearchRequests": 0,
                        "inputTextLength": 13,
                        "outputTextLength": len("sdk backend says hi"),
                    },
                    "model_usage": {},
                    "duration_api_ms": 12.5,
                    "total_cost_usd": 0.0,
                }
            }
            encoded = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    with _serve_http(Handler) as base_url:
        stdin = StringIO('{"type":"user","message":{"role":"user","content":"hello sdk url"},"parent_tool_use_id":null}\n')
        stdout = StringIO()

        assert main(
            [
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--sdk-url",
                f"{base_url}/sdk",
            ],
            stdin=stdin,
            stdout=stdout,
        ) == 0

    assert len(payloads) == 1
    request_payload = payloads[0]
    prepared = request_payload["prepared"]
    context = request_payload["context"]
    assert prepared["query_text"] == "hello sdk url"
    assert prepared["model"] is None
    assert context["continuation_count"] == 0
    assert context["turn_count"] == 0
    assert context["transcript"] == [
        {
            "type": "user",
            "message": {"role": "user", "content": "hello sdk url"},
            "session_id": context["session_id"],
            "uuid": request_payload["context"]["transcript"][0]["uuid"],
        }
    ]

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 5
    messages = [TypeAdapter(SDKMessage).validate_json(line) for line in lines]

    assert isinstance(messages[0], SDKSessionStateChangedMessage)
    assert messages[0].state == "running"
    assert isinstance(messages[1], SDKRequestStartMessage)
    assert isinstance(messages[2], SDKAssistantMessage)
    assert messages[2].message["content"] == "sdk backend says hi"
    assert isinstance(messages[3], SDKResultSuccess)
    assert messages[3].usage == {
        "backendRequests": 1,
        "backendType": "sdk-url",
        "inputTokens": 11,
        "outputTokens": 5,
        "cacheReadInputTokens": 0,
        "cacheCreationInputTokens": 0,
        "webSearchRequests": 0,
        "inputTextLength": 13,
        "outputTextLength": len("sdk backend says hi"),
        "sdkUrl": f"{base_url}/sdk",
    }
    assert messages[3].modelUsage == {}
    assert messages[3].duration_ms >= 0
    assert messages[3].duration_api_ms == 12.5
    assert isinstance(messages[4], SDKSessionStateChangedMessage)
    assert messages[4].state == "idle"



def test_cli_stream_json_sdk_url_handles_tool_continuation_end_to_end(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    payloads: list[dict[str, object]] = []
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    target = project_dir / "note.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"permissions": {"allow": [f"Read({target})"]}}),
        encoding="utf-8",
    )

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(body.decode("utf-8"))
            payloads.append(payload)
            context = payload["context"]
            if context["continuation_count"] == 0:
                response = {
                    "response": {
                        "assistant_text": "",
                        "stop_reason": "tool_use",
                        "usage": {
                            "backendRequests": 1,
                            "backendType": "sdk-url",
                            "inputTokens": 10,
                            "outputTokens": 1,
                            "cacheReadInputTokens": 0,
                            "cacheCreationInputTokens": 0,
                            "webSearchRequests": 0,
                            "inputTextLength": 13,
                            "outputTextLength": 0,
                        },
                        "model_usage": {},
                        "tool_calls": [
                            {
                                "tool_name": "Read",
                                "arguments": {"file_path": str(target)},
                                "tool_use_id": "tool-read-1",
                            }
                        ],
                    }
                }
            else:
                response = {
                    "response": {
                        "assistant_text": "Done after sdk tool",
                        "usage": {
                            "backendRequests": 1,
                            "backendType": "sdk-url",
                            "inputTokens": 12,
                            "outputTokens": 4,
                            "cacheReadInputTokens": 0,
                            "cacheCreationInputTokens": 0,
                            "webSearchRequests": 0,
                            "inputTextLength": 13,
                            "outputTextLength": len("Done after sdk tool"),
                        },
                        "model_usage": {},
                    }
                }
            encoded = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    with _serve_http(Handler) as base_url:
        stdin = StringIO('{"type":"user","message":{"role":"user","content":"read the note"},"parent_tool_use_id":null}\n')
        stdout = StringIO()

        assert main(
            [
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--sdk-url",
                f"{base_url}/sdk",
            ],
            stdin=stdin,
            stdout=stdout,
        ) == 0

    assert len(payloads) == 2
    first, second = payloads
    assert first["context"]["continuation_count"] == 0
    assert first["context"]["transition_reason"] is None
    assert second["context"]["continuation_count"] == 1
    assert second["context"]["transition_reason"] == "tool_result:Read"
    assert len(second["context"]["transcript"]) == 3
    assert second["context"]["transcript"][1]["message"]["content"][0] == {
        "type": "tool_use",
        "id": "tool-read-1",
        "name": "Read",
        "input": {"file_path": str(target)},
    }
    assert second["context"]["transcript"][2]["message"]["content"][0]["type"] == "tool_result"

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 6
    assert SDKSessionStateChangedMessage.model_validate_json(lines[0]).state == "running"
    assert SDKRequestStartMessage.model_validate_json(lines[1]).event.type == "stream_request_start"
    tool_progress = json.loads(lines[2])
    assert tool_progress["type"] == "tool_progress"
    assert tool_progress["tool_name"] == "Read"
    assert tool_progress["tool_use_id"] == "tool-read-1"
    assistant = SDKAssistantMessage.model_validate_json(lines[3])
    assert assistant.message["content"] == "Done after sdk tool"
    result = SDKResultSuccess.model_validate_json(lines[4])
    assert result.usage["backendType"] == "sdk-url"
    assert SDKSessionStateChangedMessage.model_validate_json(lines[5]).state == "idle"



def test_cli_stream_json_smoke_covers_initialize_slash_prompt_tool_call_and_mcp_turn(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_payloads: list[dict[str, object]] = []
    mcp_payloads: list[dict[str, object]] = []
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["ListMcpResources(remote)"]}}),
        encoding="utf-8",
    )

    class McpHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(body.decode("utf-8"))
            mcp_payloads.append(payload)
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "resources": [
                        {
                            "uri": "file://docs/readme.md",
                            "name": "README",
                            "description": "Project readme",
                            "mimeType": "text/markdown",
                        }
                    ]
                },
            }
            encoded = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    with _serve_http(McpHandler) as mcp_base_url:

        class SdkHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                payload = json.loads(body.decode("utf-8"))
                sdk_payloads.append(payload)
                context = payload["context"]
                if context["continuation_count"] == 0:
                    response = {
                        "response": {
                            "assistant_text": "",
                            "stop_reason": "tool_use",
                            "usage": {
                                "backendRequests": 1,
                                "backendType": "sdk-url",
                                "inputTokens": 9,
                                "outputTokens": 1,
                                "cacheReadInputTokens": 0,
                                "cacheCreationInputTokens": 0,
                                "webSearchRequests": 0,
                                "inputTextLength": 14,
                                "outputTextLength": 0,
                            },
                            "model_usage": {},
                            "tool_calls": [
                                {
                                    "tool_name": "ListMcpResources",
                                    "arguments": {"server": "remote"},
                                    "tool_use_id": "tool-mcp-list-1",
                                }
                            ],
                        }
                    }
                else:
                    response = {
                        "response": {
                            "assistant_text": "MCP smoke test complete",
                            "usage": {
                                "backendRequests": 1,
                                "backendType": "sdk-url",
                                "inputTokens": 14,
                                "outputTokens": 6,
                                "cacheReadInputTokens": 0,
                                "cacheCreationInputTokens": 0,
                                "webSearchRequests": 0,
                                "inputTextLength": 14,
                                "outputTextLength": len("MCP smoke test complete"),
                            },
                            "model_usage": {},
                        }
                    }
                encoded = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:
                return

        with _serve_http(SdkHandler) as sdk_base_url:
            stdin = StringIO(
                '{"type":"control_request","request_id":"req-init","request":{"subtype":"initialize"}}\n'
                '{"type":"control_request","request_id":"req-mcp","request":{"subtype":"mcp_set_servers","servers":{"remote":{"type":"http","url":"'
                + f"{mcp_base_url}/mcp"
                + '"}}}}\n'
                '{"type":"user","message":{"role":"user","content":"/help"},"parent_tool_use_id":null}\n'
                '{"type":"user","message":{"role":"user","content":"inspect remote mcp"},"parent_tool_use_id":null}\n'
            )
            stdout = StringIO()

            assert main(
                [
                    "--input-format",
                    "stream-json",
                    "--output-format",
                    "stream-json",
                    "--sdk-url",
                    f"{sdk_base_url}/sdk",
                ],
                stdin=stdin,
                stdout=stdout,
            ) == 0

    assert len(sdk_payloads) == 2
    assert sdk_payloads[0]["prepared"]["query_text"] == "inspect remote mcp"
    assert sdk_payloads[0]["context"]["continuation_count"] == 0
    assert sdk_payloads[1]["context"]["continuation_count"] == 1
    assert sdk_payloads[1]["context"]["transition_reason"] == "tool_result:ListMcpResources"
    assert sdk_payloads[1]["context"]["transcript"][3]["message"]["content"][0]["content"]["resources"] == [
        {
            "uri": "file://docs/readme.md",
            "name": "README",
            "description": "Project readme",
            "mimeType": "text/markdown",
        }
    ]

    assert len(mcp_payloads) == 1
    assert mcp_payloads[0]["method"] == "resources/list"
    assert mcp_payloads[0]["params"] == {}

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 12

    init_response = SDKControlResponseEnvelope.model_validate_json(lines[0])
    assert init_response.response.subtype == "success"
    assert init_response.response.request_id == "req-init"

    mcp_response = SDKControlResponseEnvelope.model_validate_json(lines[1])
    assert mcp_response.response.subtype == "success"
    assert mcp_response.response.request_id == "req-mcp"
    assert mcp_response.response.response == {"added": ["remote"], "removed": [], "errors": {}}

    assert SDKSessionStateChangedMessage.model_validate_json(lines[2]).state == "running"
    help_output = SDKLocalCommandOutputMessage.model_validate_json(lines[3])
    assert help_output.content.startswith("Available slash commands:")
    help_result = SDKResultSuccess.model_validate_json(lines[4])
    assert help_result.result == help_output.content
    assert SDKSessionStateChangedMessage.model_validate_json(lines[5]).state == "idle"

    assert SDKSessionStateChangedMessage.model_validate_json(lines[6]).state == "running"
    assert SDKRequestStartMessage.model_validate_json(lines[7]).event.type == "stream_request_start"
    tool_progress = json.loads(lines[8])
    assert tool_progress["type"] == "tool_progress"
    assert tool_progress["tool_name"] == "ListMcpResources"
    assert tool_progress["tool_use_id"] == "tool-mcp-list-1"
    assistant = SDKAssistantMessage.model_validate_json(lines[9])
    assert assistant.message["content"] == "MCP smoke test complete"
    result = SDKResultSuccess.model_validate_json(lines[10])
    assert result.usage["backendType"] == "sdk-url"
    assert result.result == "MCP smoke test complete"
    assert SDKSessionStateChangedMessage.model_validate_json(lines[11]).state == "idle"


class _FixedBackend:
    def __init__(self, assistant_text: str, *, backend_type: str = "custom") -> None:
        self.assistant_text = assistant_text
        self.backend_type = backend_type
        self.calls: list[tuple[PreparedTurn, QueryTurnContext]] = []

    def run_turn(self, prepared: PreparedTurn, context: QueryTurnContext) -> BackendTurnResult:
        self.calls.append((prepared, context))
        return BackendTurnResult(
            assistant_text=self.assistant_text,
            usage={"backendRequests": 1, "backendType": self.backend_type},
            model_usage={},
        )



def test_query_runtime_replace_runtime_backend_updates_shared_state() -> None:
    backend = _FixedBackend("replacement backend reply")
    state = RuntimeState(model="claude-sonnet-4-6")
    runtime = QueryRuntime(state)

    runtime.replace_runtime_backend(backend)
    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "hello replacement"},
            parent_tool_use_id=None,
        )
    )

    assert state.query_backend is backend
    assert runtime.runtime_turn_executor.backend is backend
    assert backend.calls[0][0].query_text == "hello replacement"
    assert isinstance(outputs[2], SDKAssistantMessage)
    assert outputs[2].message["content"] == "replacement backend reply"
    assert isinstance(outputs[3], SDKResultSuccess)
    assert outputs[3].usage["backendType"] == "custom"


def test_cli_stream_json_sdk_url_reports_model_usage_when_model_is_set() -> None:
    payloads: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payloads.append(json.loads(body.decode("utf-8")))
            response = {
                "response": {
                    "assistant_text": "model-backed reply",
                    "usage": {
                        "backendRequests": 1,
                        "backendType": "sdk-url",
                        "inputTokens": 21,
                        "outputTokens": 7,
                        "cacheReadInputTokens": 0,
                        "cacheCreationInputTokens": 0,
                        "webSearchRequests": 0,
                        "inputTextLength": 13,
                        "outputTextLength": len("model-backed reply"),
                    },
                    "model_usage": {
                        "claude-sonnet-4-6": {
                            "inputTokens": 21,
                            "outputTokens": 7,
                            "cacheReadInputTokens": 0,
                            "cacheCreationInputTokens": 0,
                            "webSearchRequests": 0,
                            "costUSD": 0.125,
                            "contextWindow": 200000,
                            "maxOutputTokens": 8192,
                        }
                    },
                    "total_cost_usd": 0.125,
                }
            }
            encoded = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    with _serve_http(Handler) as base_url:
        state = RuntimeState(model="claude-sonnet-4-6")
        runtime = QueryRuntime(state)
        runtime.replace_runtime_backend(SdkUrlQueryBackend(f"{base_url}/sdk"))
        outputs = runtime.handle_user_message(
            SDKUserMessage(
                type="user",
                message={"role": "user", "content": "hello sdk url"},
                parent_tool_use_id=None,
            )
        )

    assert len(payloads) == 1
    assert payloads[0]["prepared"]["model"] == "claude-sonnet-4-6"
    assert isinstance(outputs[2], SDKAssistantMessage)
    assert outputs[2].message["content"] == "model-backed reply"
    assert isinstance(outputs[3], SDKResultSuccess)
    assert outputs[3].usage == {
        "backendRequests": 1,
        "backendType": "sdk-url",
        "inputTokens": 21,
        "outputTokens": 7,
        "cacheReadInputTokens": 0,
        "cacheCreationInputTokens": 0,
        "webSearchRequests": 0,
        "inputTextLength": 13,
        "outputTextLength": len("model-backed reply"),
        "sdkUrl": f"{base_url}/sdk",
    }
    assert outputs[3].modelUsage["claude-sonnet-4-6"].inputTokens == 21
    assert outputs[3].modelUsage["claude-sonnet-4-6"].outputTokens == 7
    assert outputs[3].modelUsage["claude-sonnet-4-6"].webSearchRequests == 0
    assert outputs[3].modelUsage["claude-sonnet-4-6"].contextWindow == 200000
    assert outputs[3].modelUsage["claude-sonnet-4-6"].maxOutputTokens == 8192
    assert outputs[3].modelUsage["claude-sonnet-4-6"].costUSD == 0.125
    assert outputs[3].total_cost_usd == 0.125


def test_cli_stream_json_placeholder_backend_reports_usage_metrics() -> None:
    stdout = StringIO()

    assert main(
        ["--input-format", "stream-json", "--output-format", "stream-json", "hello from prompt"],
        stdin=StringIO(),
        stdout=stdout,
    ) == 0

    lines = stdout.getvalue().splitlines()
    result = TypeAdapter(SDKMessage).validate_json(lines[3])
    assistant = TypeAdapter(SDKMessage).validate_json(lines[2])

    assert isinstance(result, SDKResultSuccess)
    assert result.usage == {
        "backendRequests": 1,
        "backendType": "placeholder",
        "inputTokens": 5,
        "outputTokens": 23,
        "cacheReadInputTokens": 0,
        "cacheCreationInputTokens": 0,
        "webSearchRequests": 0,
        "inputTextLength": 17,
        "outputTextLength": 91,
    }
    assert result.modelUsage == {}
    assert isinstance(assistant, SDKAssistantMessage)
    assert result.usage["outputTextLength"] == len(assistant.message["content"])



def test_query_runtime_placeholder_backend_reports_model_usage() -> None:
    runtime = QueryRuntime(RuntimeState(model="claude-sonnet-4-6"))

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "hello model"},
            parent_tool_use_id=None,
        )
    )

    assert isinstance(outputs[2], SDKAssistantMessage)
    assert isinstance(outputs[3], SDKResultSuccess)
    assert outputs[3].usage == {
        "backendRequests": 1,
        "backendType": "placeholder",
        "inputTokens": 3,
        "outputTokens": 30,
        "cacheReadInputTokens": 0,
        "cacheCreationInputTokens": 0,
        "webSearchRequests": 0,
        "inputTextLength": 11,
        "outputTextLength": 120,
    }
    assert outputs[3].modelUsage["claude-sonnet-4-6"].inputTokens == 3
    assert outputs[3].modelUsage["claude-sonnet-4-6"].outputTokens == 30
    assert outputs[3].modelUsage["claude-sonnet-4-6"].contextWindow == 200000
    assert outputs[3].modelUsage["claude-sonnet-4-6"].maxOutputTokens == 8192
    assert outputs[3].modelUsage["claude-sonnet-4-6"].costUSD == 0.0

    assistant_text = outputs[2].message["content"]
    model_usage = outputs[3].modelUsage["claude-sonnet-4-6"]
    assert outputs[3].usage["outputTextLength"] == len(assistant_text)
    assert model_usage.outputTokens == outputs[3].usage["outputTokens"]
    assert model_usage.inputTokens == outputs[3].usage["inputTokens"]



def test_cli_stream_json_responds_to_initialize_request(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    stdin = StringIO('{"type":"control_request","request_id":"req-1","request":{"subtype":"initialize"}}\n')
    stdout = StringIO()

    assert main(["--input-format", "stream-json", "--output-format", "stream-json"], stdin=stdin, stdout=stdout) == 0

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    response = SDKControlResponseEnvelope.model_validate_json(lines[0])
    assert response.response.subtype == "success"
    assert response.response.request_id == "req-1"
    assert response.response.response is not None
    assert response.response.response["output_style"] == "text"
    assert response.response.response["available_output_styles"] == ["text", "json", "stream-json"]
    assert response.response.response["fast_mode_state"] == "off"
    assert [model["value"] for model in response.response.response["models"]] == [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ]
    assert response.response.response["account"] == {}



def test_cli_stream_json_prepends_prompt_as_user_message() -> None:
    stdin = StringIO('{"type":"control_request","request_id":"req-2","request":{"subtype":"initialize"}}\n')
    stdout = StringIO()

    assert main(
        ["--input-format", "stream-json", "--output-format", "stream-json", "hello from prompt"],
        stdin=stdin,
        stdout=stdout,
    ) == 0

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 6
    session_start = TypeAdapter(SDKMessage).validate_json(lines[0])
    request_start = TypeAdapter(SDKMessage).validate_json(lines[1])
    assistant = TypeAdapter(SDKMessage).validate_json(lines[2])
    result = TypeAdapter(SDKMessage).validate_json(lines[3])
    session_end = TypeAdapter(SDKMessage).validate_json(lines[4])
    response = SDKControlResponseEnvelope.model_validate_json(lines[5])
    assert isinstance(session_start, SDKSessionStateChangedMessage)
    assert session_start.state == "running"
    assert isinstance(request_start, SDKRequestStartMessage)
    assert request_start.event.type == "stream_request_start"
    assert isinstance(assistant, SDKAssistantMessage)
    assert assistant.message["content"] == (
        "Query runtime skeleton is not connected to a model yet.\n\nReceived prompt:\nhello from prompt"
    )
    assert isinstance(result, SDKResultSuccess)
    assert result.result == assistant.message["content"]
    assert isinstance(session_end, SDKSessionStateChangedMessage)
    assert session_end.state == "idle"
    assert response.response.subtype == "success"
    assert response.response.request_id == "req-2"



def test_cli_stream_json_routes_user_slash_commands_through_query_runtime(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    skill_dir = project_dir / ".claude" / "skills" / "commit"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: Create a commit\n"
        "argument-hint: <message>\n"
        "user-invocable: true\n"
        "---\n"
        "Commit changes for: ${ARGUMENTS}\n",
        encoding="utf-8",
    )
    (project_dir / ".claude" / "settings.json").write_text(
        '{"skills":["commit"]}',
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)

    stdin = StringIO(
        '{"type":"user","message":{"role":"user","content":"/help"},"parent_tool_use_id":null}\n'
        '{"type":"user","message":{"role":"user","content":"/commit ship it"},"parent_tool_use_id":null}\n'
    )
    stdout = StringIO()

    assert main(["--input-format", "stream-json", "--output-format", "stream-json"], stdin=stdin, stdout=stdout) == 0

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 9
    messages = [TypeAdapter(SDKMessage).validate_json(line) for line in lines]

    assert isinstance(messages[0], SDKSessionStateChangedMessage)
    assert messages[0].state == "running"
    assert isinstance(messages[1], SDKLocalCommandOutputMessage)
    assert messages[1].content.startswith("Available slash commands:")
    assert "/commit <message> — Create a commit" in messages[1].content
    assert isinstance(messages[2], SDKResultSuccess)
    assert messages[2].result == messages[1].content
    assert isinstance(messages[3], SDKSessionStateChangedMessage)
    assert messages[3].state == "idle"

    assert isinstance(messages[4], SDKSessionStateChangedMessage)
    assert messages[4].state == "running"
    assert isinstance(messages[5], SDKRequestStartMessage)
    assert messages[5].event.type == "stream_request_start"
    assert isinstance(messages[6], SDKAssistantMessage)
    assert messages[6].message["content"] == (
        "Query runtime skeleton is not connected to a model yet.\n\nReceived prompt:\n"
        f"Base directory for this skill: {skill_dir}\n\n"
        "Commit changes for: ship it\n"
    )
    assert "ship it" in messages[6].message["content"]
    assert "Base directory for this skill:" in messages[6].message["content"]
    assert str(skill_dir) in messages[6].message["content"]
    assert messages[6].parent_tool_use_id == ""
    assert isinstance(messages[7], SDKResultSuccess)
    assert messages[7].result == messages[6].message["content"]
    assert isinstance(messages[8], SDKSessionStateChangedMessage)
    assert messages[8].state == "idle"


def test_cli_stream_json_routes_prompt_slash_commands_into_query_path(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    skill_dir = project_dir / ".claude" / "skills" / "draft"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: Draft content\n"
        "argument-hint: <topic>\n"
        "user-invocable: true\n"
        "---\n"
        "Draft about: ${ARGUMENTS}\n",
        encoding="utf-8",
    )
    (project_dir / ".claude" / "settings.json").write_text(
        '{"skills":["draft"]}',
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)

    stdin = StringIO(
        '{"type":"user","message":{"role":"user","content":"/draft testing"},"parent_tool_use_id":null}\n'
    )
    stdout = StringIO()

    assert main(["--input-format", "stream-json", "--output-format", "stream-json"], stdin=stdin, stdout=stdout) == 0

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 5
    messages = [TypeAdapter(SDKMessage).validate_json(line) for line in lines]

    assert isinstance(messages[0], SDKSessionStateChangedMessage)
    assert messages[0].state == "running"
    assert isinstance(messages[1], SDKRequestStartMessage)
    assert messages[1].event.type == "stream_request_start"
    assert isinstance(messages[2], SDKAssistantMessage)
    assert messages[2].message["content"] == (
        "Query runtime skeleton is not connected to a model yet.\n\nReceived prompt:\n"
        f"Base directory for this skill: {skill_dir}\n\n"
        "Draft about: testing\n"
    )
    assert isinstance(messages[3], SDKResultSuccess)
    assert messages[3].result == messages[2].message["content"]
    assert isinstance(messages[4], SDKSessionStateChangedMessage)
    assert messages[4].state == "idle"



def test_command_registry_propagates_prompt_skill_metadata(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    skill_dir = project_dir / ".claude" / "skills" / "draft"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: Draft content\n"
        "argument-hint: <topic>\n"
        "model: claude-sonnet-4-6\n"
        "effort: high\n"
        "allowed-tools:\n"
        "  - Read\n"
        "  - Bash\n"
        "user-invocable: true\n"
        "---\n"
        "Draft about: ${ARGUMENTS}\n",
        encoding="utf-8",
    )
    (project_dir / ".claude" / "settings.json").write_text(
        '{"skills":["draft"]}',
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)

    state = RuntimeState(cwd=str(project_dir), home_dir=str(tmp_path / "home"))
    settings = get_settings_with_sources(
        flag_settings=state.flag_settings,
        policy_settings=state.policy_settings,
        cwd=state.cwd,
        home_dir=state.home_dir,
    )
    registry = CommandRegistry.build(skills=state.discovered_skills(settings.effective.get("skills")))

    result = registry.execute("draft", arguments="testing", state=state, settings=settings)

    assert result.should_query is True
    assert result.command.name == "draft"
    assert result.model == "claude-sonnet-4-6"
    assert result.effort == "high"
    assert result.allowed_tools == ["Read", "Bash"]
    assert result.expanded_prompt == (
        f"Base directory for this skill: {skill_dir}\n\n"
        "Draft about: testing\n"
    )



def test_cli_stream_json_includes_prompt_command_metadata_in_placeholder_output(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    skill_dir = project_dir / ".claude" / "skills" / "draft"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: Draft content\n"
        "argument-hint: <topic>\n"
        "model: claude-sonnet-4-6\n"
        "effort: high\n"
        "allowed-tools:\n"
        "  - Read\n"
        "  - Bash\n"
        "user-invocable: true\n"
        "---\n"
        "Draft about: ${ARGUMENTS}\n",
        encoding="utf-8",
    )
    (project_dir / ".claude" / "settings.json").write_text(
        '{"skills":["draft"]}',
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)

    stdin = StringIO(
        '{"type":"user","message":{"role":"user","content":"/draft testing"},"parent_tool_use_id":null}\n'
    )
    stdout = StringIO()

    assert main(["--input-format", "stream-json", "--output-format", "stream-json"], stdin=stdin, stdout=stdout) == 0

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 5
    messages = [TypeAdapter(SDKMessage).validate_json(line) for line in lines]

    assert isinstance(messages[1], SDKRequestStartMessage)
    assert messages[1].event.type == "stream_request_start"
    assert isinstance(messages[2], SDKAssistantMessage)
    assert messages[2].message["content"] == (
        "Query runtime skeleton is not connected to a model yet.\n"
        "Requested model: claude-sonnet-4-6\n"
        "Requested effort: high\n"
        "Allowed tools: Read, Bash\n"
        "\n"
        "Received prompt:\n"
        f"Base directory for this skill: {skill_dir}\n\n"
        "Draft about: testing\n"
    )
    assert isinstance(messages[3], SDKResultSuccess)
    assert messages[3].result == messages[2].message["content"]




def test_parse_skill_document_supports_metadata_lists_and_effort() -> None:
    parsed = parse_skill_document(
        "---\n"
        "description: Draft content\n"
        "allowed-tools:\n"
        "  - Read\n"
        "  - Bash\n"
        "effort: high\n"
        "user-invocable: false\n"
        "---\n"
        "Draft about: ${ARGUMENTS}\n"
    )

    assert parsed.frontmatter["description"] == "Draft content"
    assert parsed.frontmatter["allowed-tools"] == ["Read", "Bash"]
    assert parsed.frontmatter["effort"] == "high"
    assert parsed.frontmatter["user-invocable"] is False
    assert parsed.content == "Draft about: ${ARGUMENTS}\n"


def test_query_runtime_supports_replacing_turn_executor() -> None:
    class FakeTurnExecutor:
        def __init__(self) -> None:
            self.prepared: PreparedTurn | None = None
            self.context: QueryTurnContext | None = None

        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            self.prepared = prepared
            self.context = context
            return ExecutedTurn(
                assistant_text="Synthetic assistant reply",
                stop_reason="tool_use",
                usage={"output_tokens": 5},
                model_usage={
                    "claude-sonnet-4-6": {
                        "inputTokens": 0,
                        "outputTokens": 5,
                        "cacheReadInputTokens": 0,
                        "cacheCreationInputTokens": 0,
                        "webSearchRequests": 0,
                        "costUSD": 0.25,
                        "contextWindow": 200000,
                        "maxOutputTokens": 8192,
                    }
                },
                duration_api_ms=12.5,
                total_cost_usd=0.25,
            )

    executor = FakeTurnExecutor()
    runtime = QueryRuntime(turn_executor=executor)

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "hello executor"},
            parent_tool_use_id=None,
        )
    )

    assert executor.prepared is not None
    assert executor.prepared.query_text == "hello executor"
    assert executor.context is not None
    assert executor.context.turn_count == 0
    assert executor.context.transcript == [runtime.transcript[0]]
    assert len(outputs) == 5
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert outputs[0].state == "running"
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert outputs[1].event.type == "stream_request_start"
    assert isinstance(outputs[2], SDKAssistantMessage)
    assert outputs[2].message["content"] == "Synthetic assistant reply"
    assert isinstance(outputs[3], SDKResultSuccess)
    assert outputs[3].result == "Synthetic assistant reply"
    assert outputs[3].stop_reason == "tool_use"
    assert outputs[3].usage == {"output_tokens": 5}
    assert outputs[3].modelUsage["claude-sonnet-4-6"].outputTokens == 5
    assert outputs[3].modelUsage["claude-sonnet-4-6"].costUSD == 0.25
    assert outputs[3].duration_api_ms == 12.5
    assert outputs[3].total_cost_usd == 0.25
    assert isinstance(outputs[4], SDKSessionStateChangedMessage)
    assert outputs[4].state == "idle"
    assert runtime.turn_count() == 1
    assert runtime.current_session_id() is not None
    assert len(runtime.transcript) == 2
    assert runtime.state.query_runtime is runtime


def test_query_runtime_emits_prompt_suggestion_message() -> None:
    class PromptSuggestionExecutor:
        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            return ExecutedTurn(
                assistant_text="Synthetic assistant reply",
                prompt_suggestion="Continue from: Synthetic assistant reply",
            )

    runtime = QueryRuntime(turn_executor=PromptSuggestionExecutor())

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "hello prompt suggestion"},
            parent_tool_use_id=None,
        )
    )

    assert len(outputs) == 6
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert isinstance(outputs[2], SDKAssistantMessage)
    assert isinstance(outputs[3], SDKResultSuccess)
    assert isinstance(outputs[4], SDKPromptSuggestionMessage)
    assert outputs[4].suggestion == "Continue from: Synthetic assistant reply"
    assert isinstance(outputs[5], SDKSessionStateChangedMessage)
    assert outputs[5].state == "idle"



def test_query_runtime_clear_session_resets_executor_state() -> None:
    runtime = QueryRuntime()
    runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "hello"},
            parent_tool_use_id=None,
        )
    )

    assert runtime.turn_count() == 1
    assert runtime.current_session_id() is not None
    assert len(runtime.pending_turn_transcript("preview-session")) == 3

    runtime.clear_session()

    assert runtime.turn_count() == 0
    assert runtime.current_session_id() is None
    assert runtime.transcript == []



def test_query_runtime_runtime_executor_applies_state_model_default() -> None:
    runtime = QueryRuntime(state=RuntimeState(model="claude-opus-4-6"))

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "hello model default"},
            parent_tool_use_id=None,
        )
    )

    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert outputs[1].event.type == "stream_request_start"
    assert isinstance(outputs[2], SDKAssistantMessage)
    assert outputs[2].message["content"] == (
        "Query runtime skeleton is not connected to a model yet.\n"
        "Requested model: claude-opus-4-6\n"
        "\n"
        "Received prompt:\n"
        "hello model default"
    )



def test_query_runtime_prepares_turn_with_runtime_defaults_before_execution() -> None:
    class CapturingExecutor:
        def __init__(self) -> None:
            self.prepared: PreparedTurn | None = None

        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            self.prepared = prepared
            return ExecutedTurn(assistant_text="captured")

    executor = CapturingExecutor()
    runtime = QueryRuntime(
        state=RuntimeState(
            model="claude-opus-4-6",
            max_thinking_tokens=2048,
            system_prompt="System guidance",
            append_system_prompt="Append guidance",
            json_schema={"type": "object"},
            sdk_mcp_servers=["local", "remote"],
            prompt_suggestions=True,
            agent_progress_summaries=True,
        ),
        turn_executor=executor,
    )

    runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "hello defaults"},
            parent_tool_use_id=None,
        )
    )

    assert executor.prepared is not None
    assert executor.prepared.query_text == "hello defaults"
    assert executor.prepared.should_query is True
    assert executor.prepared.model == "claude-opus-4-6"
    assert executor.prepared.max_thinking_tokens == 2048
    assert executor.prepared.system_prompt == "System guidance"
    assert executor.prepared.append_system_prompt == "Append guidance"
    assert executor.prepared.json_schema == {"type": "object"}
    assert executor.prepared.sdk_mcp_servers == ["local", "remote"]
    assert executor.prepared.prompt_suggestions is True
    assert executor.prepared.agent_progress_summaries is True



def test_query_runtime_slash_command_prepared_turn_merges_command_and_runtime_defaults(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    skill_dir = project_dir / ".claude" / "skills" / "draft"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: Draft content\n"
        "argument-hint: <topic>\n"
        "model: claude-sonnet-4-6\n"
        "effort: high\n"
        "allowed-tools:\n"
        "  - Read\n"
        "user-invocable: true\n"
        "---\n"
        "Draft about: ${ARGUMENTS}\n",
        encoding="utf-8",
    )
    (project_dir / ".claude" / "settings.json").write_text('{"skills":["draft"]}', encoding="utf-8")
    monkeypatch.chdir(project_dir)

    class CapturingExecutor:
        def __init__(self) -> None:
            self.prepared: PreparedTurn | None = None

        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            self.prepared = prepared
            return ExecutedTurn(assistant_text="captured")

    executor = CapturingExecutor()
    runtime = QueryRuntime(
        state=RuntimeState(
            cwd=str(project_dir),
            home_dir=str(tmp_path / "home"),
            model="claude-opus-4-6",
            max_thinking_tokens=4096,
            system_prompt="System guidance",
            append_system_prompt="Append guidance",
            json_schema={"type": "object"},
            sdk_mcp_servers=["local"],
            prompt_suggestions=True,
            agent_progress_summaries=True,
        ),
        turn_executor=executor,
    )

    runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "/draft testing"},
            parent_tool_use_id=None,
        )
    )

    assert executor.prepared is not None
    assert executor.prepared.query_text == (
        f"Base directory for this skill: {skill_dir}\n\n"
        "Draft about: testing\n"
    )
    assert executor.prepared.model == "claude-sonnet-4-6"
    assert executor.prepared.effort == "high"
    assert executor.prepared.allowed_tools == ["Read"]
    assert executor.prepared.max_thinking_tokens == 4096
    assert executor.prepared.system_prompt == "System guidance"
    assert executor.prepared.append_system_prompt == "Append guidance"
    assert executor.prepared.json_schema == {"type": "object"}
    assert executor.prepared.sdk_mcp_servers == ["local"]
    assert executor.prepared.prompt_suggestions is True
    assert executor.prepared.agent_progress_summaries is True



def test_query_runtime_can_swap_runtime_turn_driver() -> None:
    class RuntimeDriver:
        def __init__(self) -> None:
            self.prepared: PreparedTurn | None = None
            self.context: QueryTurnContext | None = None

        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            self.prepared = prepared
            self.context = context
            return ExecutedTurn(assistant_text=f"runtime driver for {prepared.query_text}")

    driver = RuntimeDriver()
    runtime = QueryRuntime()
    runtime.replace_runtime_turn_driver(driver)

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "hello driver"},
            parent_tool_use_id=None,
        )
    )

    assert driver.prepared is not None
    assert driver.prepared.query_text == "hello driver"
    assert driver.context is not None
    assert driver.context.session_id == runtime.current_session_id()
    assert driver.context.turn_count == 0
    assert driver.context.transcript == [runtime.transcript[0]]
    assert runtime.turn_executor is runtime.runtime_turn_executor
    assert runtime.runtime_turn_executor.driver is driver
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert outputs[1].event.type == "stream_request_start"
    assert isinstance(outputs[2], SDKAssistantMessage)
    assert outputs[2].message["content"] == "runtime driver for hello driver"



def test_query_runtime_can_swap_runtime_fallback_executor() -> None:
    class RuntimeFallbackExecutor:
        def __init__(self) -> None:
            self.prepared: PreparedTurn | None = None
            self.context: QueryTurnContext | None = None

        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            self.prepared = prepared
            self.context = context
            return ExecutedTurn(assistant_text=f"runtime fallback for {prepared.query_text}")

    executor = RuntimeFallbackExecutor()
    runtime = QueryRuntime()
    runtime.replace_runtime_turn_fallback(executor)

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "hello fallback"},
            parent_tool_use_id=None,
        )
    )

    assert executor.prepared is not None
    assert executor.prepared.query_text == "hello fallback"
    assert executor.context is not None
    assert executor.context.session_id == runtime.current_session_id()
    assert runtime.turn_executor is runtime.runtime_turn_executor
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert outputs[1].event.type == "stream_request_start"
    assert isinstance(outputs[2], SDKAssistantMessage)
    assert outputs[2].message["content"] == "runtime fallback for hello fallback"



def test_cli_stream_json_surfaces_unknown_slash_command_as_error_result() -> None:
    stdin = StringIO(
        '{"type":"user","message":{"role":"user","content":"/does-not-exist"},"parent_tool_use_id":null}\n'
    )
    stdout = StringIO()

    assert main(["--input-format", "stream-json", "--output-format", "stream-json"], stdin=stdin, stdout=stdout) == 0

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 3
    session_start = TypeAdapter(SDKMessage).validate_json(lines[0])
    result = TypeAdapter(SDKMessage).validate_json(lines[1])
    session_end = TypeAdapter(SDKMessage).validate_json(lines[2])

    assert isinstance(session_start, SDKSessionStateChangedMessage)
    assert session_start.state == "running"
    assert isinstance(result, SDKResultError)
    assert result.subtype == "error_during_execution"
    assert result.errors == ["Unknown command: does-not-exist"]
    assert isinstance(session_end, SDKSessionStateChangedMessage)
    assert session_end.state == "idle"




def test_cli_stream_json_clear_command_resets_session_state() -> None:
    stdin = StringIO(
        '{"type":"user","message":{"role":"user","content":"first message"},"parent_tool_use_id":null}\n'
        '{"type":"user","message":{"role":"user","content":"/status"},"parent_tool_use_id":null}\n'
        '{"type":"user","message":{"role":"user","content":"/clear"},"parent_tool_use_id":null}\n'
        '{"type":"user","message":{"role":"user","content":"/status"},"parent_tool_use_id":null}\n'
    )
    stdout = StringIO()

    assert main(["--input-format", "stream-json", "--output-format", "stream-json"], stdin=stdin, stdout=stdout) == 0

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 17
    messages = [TypeAdapter(SDKMessage).validate_json(line) for line in lines]

    assert isinstance(messages[0], SDKSessionStateChangedMessage)
    assert isinstance(messages[1], SDKRequestStartMessage)
    assert messages[1].event.type == "stream_request_start"
    assert isinstance(messages[2], SDKAssistantMessage)
    assert isinstance(messages[3], SDKResultSuccess)
    assert isinstance(messages[4], SDKSessionStateChangedMessage)

    assert isinstance(messages[6], SDKLocalCommandOutputMessage)
    assert "session_id:" in messages[6].content
    assert "transcript_messages: 3" in messages[6].content
    assert isinstance(messages[7], SDKResultSuccess)

    assert isinstance(messages[10], SDKLocalCommandOutputMessage)
    assert messages[10].content == "Session transcript cleared."
    assert isinstance(messages[11], SDKResultSuccess)
    assert messages[11].result == "Session transcript cleared."

    assert isinstance(messages[14], SDKLocalCommandOutputMessage)
    assert "transcript_messages: 1" in messages[14].content
    assert isinstance(messages[15], SDKResultSuccess)
    assert messages[15].result == messages[14].content



def test_cli_stream_json_supports_interrupt_control_request() -> None:
    stdin = StringIO('{"type":"control_request","request_id":"req-3","request":{"subtype":"interrupt"}}\n')
    stdout = StringIO()

    assert main(["--input-format", "stream-json", "--output-format", "stream-json"], stdin=stdin, stdout=stdout) == 0

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    response = SDKControlResponseEnvelope.model_validate_json(lines[0])
    assert response.response.subtype == "success"
    assert response.response.request_id == "req-3"
    assert response.response.response == {}


def test_query_runtime_interrupt_marks_active_turn_and_returns_error_result() -> None:
    state = RuntimeState()
    runtime = QueryRuntime(state=state)
    entered = threading.Event()

    class InterruptingExecutor:
        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            entered.set()
            context.state.query_runtime.interrupt()
            return ExecutedTurn(assistant_text="should not be emitted")

    runtime.replace_turn_executor(InterruptingExecutor())

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "interrupt me"},
            parent_tool_use_id=None,
        )
    )

    assert entered.is_set()
    assert len(outputs) == 4
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert outputs[0].state == "running"
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert outputs[1].event.type == "stream_request_start"
    assert isinstance(outputs[2], SDKResultError)
    assert outputs[2].errors == ["Query interrupted"]
    assert isinstance(outputs[3], SDKSessionStateChangedMessage)
    assert outputs[3].state == "idle"
    assert runtime.turn_count() == 1
    assert state.interrupt_event.is_set() is True



def test_cli_stream_json_control_set_model_updates_query_runtime_default() -> None:
    stdin = StringIO(
        '{"type":"control_request","request_id":"req-model","request":{"subtype":"set_model","model":"claude-sonnet-4-6"}}\n'
        '{"type":"user","message":{"role":"user","content":"hello after set model"},"parent_tool_use_id":null}\n'
    )
    stdout = StringIO()

    assert main(["--input-format", "stream-json", "--output-format", "stream-json"], stdin=stdin, stdout=stdout) == 0

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 6
    response = SDKControlResponseEnvelope.model_validate_json(lines[0])
    messages = [TypeAdapter(SDKMessage).validate_json(line) for line in lines[1:]]

    assert response.response.subtype == "success"
    assert response.response.request_id == "req-model"
    assert response.response.response == {}
    assert isinstance(messages[0], SDKSessionStateChangedMessage)
    assert messages[0].state == "running"
    assert isinstance(messages[1], SDKRequestStartMessage)
    assert messages[1].event.type == "stream_request_start"
    assert isinstance(messages[2], SDKAssistantMessage)
    assert messages[2].message["content"] == (
        "Query runtime skeleton is not connected to a model yet.\n"
        "Requested model: claude-sonnet-4-6\n"
        "\n"
        "Received prompt:\n"
        "hello after set model"
    )
    assert isinstance(messages[3], SDKResultSuccess)
    assert messages[3].result == messages[2].message["content"]
    assert isinstance(messages[4], SDKSessionStateChangedMessage)
    assert messages[4].state == "idle"



def test_query_runtime_emits_partial_message_when_enabled() -> None:
    runtime = QueryRuntime(state=RuntimeState(include_partial_messages=True))

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "hello partials"},
            parent_tool_use_id=None,
        )
    )

    assert len(outputs) == 6
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert outputs[0].state == "running"
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert outputs[1].event.type == "stream_request_start"
    assert isinstance(outputs[2], SDKPartialAssistantMessage)
    assert outputs[2].parent_tool_use_id == ""
    assert outputs[2].event == {
        "type": "content_block_delta",
        "delta": {
            "type": "text_delta",
            "text": "Query runtime skeleton is not connected to a model yet.\n\nReceived prompt:\nhello partials",
        },
    }
    assert isinstance(outputs[3], SDKAssistantMessage)
    assert outputs[3].message["content"] == outputs[2].event["delta"]["text"]
    assert isinstance(outputs[4], SDKResultSuccess)
    assert outputs[4].result == outputs[3].message["content"]
    assert isinstance(outputs[5], SDKSessionStateChangedMessage)
    assert outputs[5].state == "idle"



def test_cli_stream_json_emits_partial_message_when_flag_enabled() -> None:
    stdin = StringIO(
        '{"type":"user","message":{"role":"user","content":"hello partial flag"},"parent_tool_use_id":null}\n'
    )
    stdout = StringIO()

    assert main(
        [
            "--print",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--include-partial-messages",
        ],
        stdin=stdin,
        stdout=stdout,
    ) == 0

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 6
    messages = [TypeAdapter(SDKMessage).validate_json(line) for line in lines]

    assert isinstance(messages[0], SDKSessionStateChangedMessage)
    assert messages[0].state == "running"
    assert isinstance(messages[1], SDKRequestStartMessage)
    assert messages[1].event.type == "stream_request_start"
    assert isinstance(messages[2], SDKPartialAssistantMessage)
    assert messages[2].parent_tool_use_id == ""
    assert messages[2].event == {
        "type": "content_block_delta",
        "delta": {
            "type": "text_delta",
            "text": "Query runtime skeleton is not connected to a model yet.\n\nReceived prompt:\nhello partial flag",
        },
    }
    assert isinstance(messages[3], SDKAssistantMessage)
    assert messages[3].message["content"] == messages[2].event["delta"]["text"]
    assert isinstance(messages[4], SDKResultSuccess)
    assert messages[4].result == messages[3].message["content"]
    assert isinstance(messages[5], SDKSessionStateChangedMessage)
    assert messages[5].state == "idle"



def test_query_runtime_executes_tool_calls_and_continues_turn(tmp_path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    target = project_dir / "note.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"permissions": {"allow": [f"Read({target})"]}}),
        encoding="utf-8",
    )

    class ToolLoopExecutor:
        def __init__(self) -> None:
            self.calls = 0
            self.first_context: QueryTurnContext | None = None
            self.second_context: QueryTurnContext | None = None

        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            self.calls += 1
            if self.calls == 1:
                self.first_context = context
                return ExecutedTurn(
                    stop_reason="tool_use",
                    tool_calls=[
                        ToolCallRequest(
                            tool_name="Read",
                            arguments={"file_path": str(target)},
                            tool_use_id="tool-read-1",
                        )
                    ],
                )
            self.second_context = context
            return ExecutedTurn(assistant_text="Done after tool")

    executor = ToolLoopExecutor()
    runtime = QueryRuntime(
        state=RuntimeState(cwd=str(project_dir), home_dir=str(tmp_path / "home")),
        turn_executor=executor,
    )

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "read the note"},
            parent_tool_use_id=None,
        )
    )

    assert executor.calls == 2
    assert executor.first_context is not None
    assert executor.first_context.continuation_count == 0
    assert executor.first_context.transition_reason is None
    assert executor.second_context is not None
    assert executor.second_context.continuation_count == 1
    assert executor.second_context.transition_reason == "tool_result:Read"
    assert len(executor.second_context.transcript) == 3
    tool_use_message = executor.second_context.transcript[1]
    tool_result_message = executor.second_context.transcript[2]
    assert isinstance(tool_use_message, SDKAssistantMessage)
    assert tool_use_message.message["content"][0] == {
        "type": "tool_use",
        "id": "tool-read-1",
        "name": "Read",
        "input": {"file_path": str(target)},
    }
    assert isinstance(tool_result_message, SDKUserMessage)
    assert tool_result_message.isSynthetic is True
    assert tool_result_message.parent_tool_use_id == "tool-read-1"
    assert tool_result_message.tool_use_result["file"]["filePath"] == str(target)
    assert tool_result_message.message["content"][0]["type"] == "tool_result"

    assert len(outputs) == 6
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert outputs[0].state == "running"
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert outputs[1].event.type == "stream_request_start"
    assert isinstance(outputs[2], SDKToolProgressMessage)
    assert outputs[2].tool_use_id == "tool-read-1"
    assert outputs[2].tool_name == "Read"
    assert outputs[2].elapsed_time_seconds >= 0
    assert isinstance(outputs[3], SDKAssistantMessage)
    assert outputs[3].message["content"] == "Done after tool"
    assert isinstance(outputs[4], SDKResultSuccess)
    assert outputs[4].result == "Done after tool"
    assert isinstance(outputs[5], SDKSessionStateChangedMessage)
    assert outputs[5].state == "idle"

    assert len(runtime.transcript) == 4
    assert isinstance(runtime.transcript[3], SDKAssistantMessage)
    assert runtime.transcript[3].message["content"] == "Done after tool"



def test_query_runtime_interrupt_during_tool_continuation_preserves_progress(tmp_path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    target = project_dir / "note.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"permissions": {"allow": [f"Read({target})"]}}),
        encoding="utf-8",
    )

    class InterruptingContinuationExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            self.calls += 1
            if self.calls == 1:
                return ExecutedTurn(
                    stop_reason="tool_use",
                    tool_calls=[
                        ToolCallRequest(
                            tool_name="Read",
                            arguments={"file_path": str(target)},
                            tool_use_id="tool-read-1",
                        )
                    ],
                )
            context.state.query_runtime.interrupt()
            return ExecutedTurn(assistant_text="should not be emitted")

    executor = InterruptingContinuationExecutor()
    state = RuntimeState(cwd=str(project_dir), home_dir=str(tmp_path / "home"))
    runtime = QueryRuntime(state=state, turn_executor=executor)

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "interrupt after tool"},
            parent_tool_use_id=None,
        )
    )

    assert executor.calls == 2
    assert len(outputs) == 5
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert outputs[0].state == "running"
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert isinstance(outputs[2], SDKToolProgressMessage)
    assert outputs[2].tool_use_id == "tool-read-1"
    assert isinstance(outputs[3], SDKResultError)
    assert outputs[3].errors == ["Query interrupted"]
    assert isinstance(outputs[4], SDKSessionStateChangedMessage)
    assert outputs[4].state == "idle"
    assert state.interrupt_event.is_set() is True
    assert len(runtime.transcript) == 3
    assert isinstance(runtime.transcript[1], SDKAssistantMessage)
    assert isinstance(runtime.transcript[2], SDKUserMessage)
    assert runtime.transcript[2].isSynthetic is True



def test_query_runtime_cancel_async_message_during_tool_continuation_preserves_progress(tmp_path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    target = project_dir / "note.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"permissions": {"allow": [f"Read({target})"]}}),
        encoding="utf-8",
    )

    class CancellingContinuationExecutor:
        def __init__(self) -> None:
            self.calls = 0
            self.cancellation: dict[str, bool] = {}

        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            self.calls += 1
            if self.calls == 1:
                return ExecutedTurn(
                    stop_reason="tool_use",
                    tool_calls=[
                        ToolCallRequest(
                            tool_name="Read",
                            arguments={"file_path": str(target)},
                            tool_use_id="tool-read-1",
                        )
                    ],
                )
            active_message = context.transcript[0]
            assert isinstance(active_message, SDKUserMessage)
            self.cancellation["first"] = context.state.query_runtime.cancel_async_message(active_message.uuid)
            self.cancellation["second"] = context.state.query_runtime.cancel_async_message(active_message.uuid)
            return ExecutedTurn(assistant_text="should not be emitted")

    executor = CancellingContinuationExecutor()
    state = RuntimeState(cwd=str(project_dir), home_dir=str(tmp_path / "home"))
    runtime = QueryRuntime(state=state, turn_executor=executor)

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "cancel after tool"},
            parent_tool_use_id=None,
        )
    )

    assert executor.calls == 2
    assert executor.cancellation == {"first": True, "second": False}
    assert len(outputs) == 5
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert outputs[0].state == "running"
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert isinstance(outputs[2], SDKToolProgressMessage)
    assert outputs[2].tool_use_id == "tool-read-1"
    assert isinstance(outputs[3], SDKResultError)
    assert outputs[3].errors == ["Query interrupted"]
    assert isinstance(outputs[4], SDKSessionStateChangedMessage)
    assert outputs[4].state == "idle"
    assert state.interrupt_event.is_set() is True
    assert len(runtime.transcript) == 3
    assert isinstance(runtime.transcript[1], SDKAssistantMessage)
    assert isinstance(runtime.transcript[2], SDKUserMessage)
    assert runtime.transcript[2].isSynthetic is True



def test_query_runtime_cancel_async_message_interrupts_active_turn() -> None:
    state = RuntimeState()
    runtime = QueryRuntime(state=state)
    cancellation: dict[str, bool] = {}

    class CancellingExecutor:
        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            active_message = context.transcript[0]
            assert isinstance(active_message, SDKUserMessage)
            cancellation["first"] = context.state.query_runtime.cancel_async_message(active_message.uuid)
            cancellation["second"] = context.state.query_runtime.cancel_async_message(active_message.uuid)
            return ExecutedTurn(assistant_text="should not be emitted")

    runtime.replace_turn_executor(CancellingExecutor())

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "cancel me"},
            parent_tool_use_id=None,
        )
    )

    assert cancellation == {"first": True, "second": False}
    assert len(outputs) == 4
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert outputs[0].state == "running"
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert isinstance(outputs[2], SDKResultError)
    assert outputs[2].errors == ["Query interrupted"]
    assert isinstance(outputs[3], SDKSessionStateChangedMessage)
    assert outputs[3].state == "idle"
    assert state.interrupt_event.is_set() is True



def test_query_runtime_counts_web_search_requests_in_usage_and_model_usage(tmp_path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps(
            {
                "permissions": {
                    "allow": [
                        "WebSearch(query:Claude Code | allow:docs.anthropic.com)",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    class CountingBackend(QueryBackend):
        def run_turn(self, prepared: PreparedTurn, context: QueryTurnContext) -> BackendTurnResult:
            return BackendTurnResult(
                assistant_text="Done after web search",
                usage={
                    "backendRequests": 1,
                    "backendType": "placeholder",
                    "inputTokens": 4,
                    "outputTokens": 5,
                    "cacheReadInputTokens": 0,
                    "cacheCreationInputTokens": 0,
                    "webSearchRequests": 0,
                    "inputTextLength": len(prepared.query_text or ""),
                    "outputTextLength": len("Done after web search"),
                },
                model_usage={
                    "claude-sonnet-4-6": {
                        "inputTokens": 4,
                        "outputTokens": 5,
                        "cacheReadInputTokens": 0,
                        "cacheCreationInputTokens": 0,
                        "webSearchRequests": 0,
                        "costUSD": 0.0,
                        "contextWindow": 200000,
                        "maxOutputTokens": 8192,
                    }
                },
            )

    backend_executor = BackendTurnExecutor(CountingBackend())

    class ToolLoopExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            self.calls += 1
            if self.calls == 1:
                return ExecutedTurn(
                    stop_reason="tool_use",
                    tool_calls=[
                        ToolCallRequest(
                            tool_name="WebSearch",
                            arguments={
                                "query": "Claude Code",
                                "allowed_domains": ["docs.anthropic.com"],
                                "blocked_domains": [],
                            },
                            tool_use_id="tool-web-search-1",
                        )
                    ],
                )
            return backend_executor.execute(prepared, context)

    runtime = QueryRuntime(
        state=RuntimeState(cwd=str(project_dir), home_dir=str(tmp_path / "home"), model="claude-sonnet-4-6")
    )
    runtime.replace_runtime_backend(CountingBackend())
    runtime.replace_turn_executor(ToolLoopExecutor())

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "search docs"},
            parent_tool_use_id=None,
        )
    )

    assert isinstance(outputs[2], SDKToolProgressMessage)
    assert outputs[2].tool_name == "WebSearch"
    assert isinstance(outputs[3], SDKAssistantMessage)
    assert outputs[3].message["content"] == "Done after web search"
    assert isinstance(outputs[4], SDKResultSuccess)
    assert outputs[4].usage["webSearchRequests"] == 1
    assert outputs[4].modelUsage["claude-sonnet-4-6"].webSearchRequests == 1



def test_query_runtime_returns_error_after_max_tool_continuations(tmp_path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    target = project_dir / "note.txt"
    target.write_text("alpha\n", encoding="utf-8")
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"permissions": {"allow": [f"Read({target})"]}}),
        encoding="utf-8",
    )

    class LoopingExecutor:
        def __init__(self) -> None:
            self.calls = 0
            self.contexts: list[QueryTurnContext] = []

        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            self.calls += 1
            self.contexts.append(context)
            return ExecutedTurn(
                stop_reason="tool_use",
                tool_calls=[
                    ToolCallRequest(
                        tool_name="Read",
                        arguments={"file_path": str(target)},
                        tool_use_id=f"tool-read-{self.calls}",
                    )
                ],
            )

    executor = LoopingExecutor()
    runtime = QueryRuntime(
        state=RuntimeState(cwd=str(project_dir), home_dir=str(tmp_path / "home")),
        turn_executor=executor,
    )

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "loop on read"},
            parent_tool_use_id=None,
        )
    )

    assert executor.calls == 8
    assert [context.continuation_count for context in executor.contexts] == list(range(8))
    assert executor.contexts[-1].transition_reason == "tool_result:Read"
    assert len(outputs) == 12
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert outputs[0].state == "running"
    assert isinstance(outputs[1], SDKRequestStartMessage)
    tool_progress = outputs[2:-2]
    assert len(tool_progress) == 8
    assert all(isinstance(message, SDKToolProgressMessage) for message in tool_progress)
    assert [message.tool_use_id for message in tool_progress] == [f"tool-read-{index}" for index in range(1, 9)]
    assert isinstance(outputs[-2], SDKResultError)
    assert outputs[-2].errors == ["Query exceeded maximum tool continuations"]
    assert isinstance(outputs[-1], SDKSessionStateChangedMessage)
    assert outputs[-1].state == "idle"
    assert len(runtime.transcript) == 17



def test_query_runtime_returns_error_when_tool_call_violates_allowed_tools(tmp_path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    skill_dir = project_dir / ".claude" / "skills" / "restricted"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: Restricted tool test\n"
        "allowed-tools:\n"
        "  - Glob\n"
        "user-invocable: true\n"
        "---\n"
        "Use only allowed tools.\n",
        encoding="utf-8",
    )
    (project_dir / ".claude" / "settings.json").write_text('{"skills":["restricted"]}', encoding="utf-8")
    monkeypatch.chdir(project_dir)

    class ForbiddenToolExecutor:
        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            return ExecutedTurn(
                stop_reason="tool_use",
                tool_calls=[
                    ToolCallRequest(
                        tool_name="Read",
                        arguments={"file_path": str(project_dir / "secret.txt")},
                        tool_use_id="tool-read-1",
                    )
                ],
            )

    runtime = QueryRuntime(
        state=RuntimeState(cwd=str(project_dir), home_dir=str(tmp_path / "home")),
        turn_executor=ForbiddenToolExecutor(),
    )

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "/restricted"},
            parent_tool_use_id=None,
        )
    )

    assert len(outputs) == 4
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert outputs[0].state == "running"
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert outputs[1].event.type == "stream_request_start"
    assert isinstance(outputs[2], SDKResultError)
    assert outputs[2].errors == ["Read is not allowed for this turn"]
    assert isinstance(outputs[3], SDKSessionStateChangedMessage)
    assert outputs[3].state == "idle"
    assert len(runtime.transcript) == 1



def test_query_runtime_returns_error_when_tool_call_permission_denied(tmp_path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    target = project_dir / "secret.txt"
    target.write_text("secret\n", encoding="utf-8")
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"permissions": {"deny": [f"Read({target})"]}}),
        encoding="utf-8",
    )

    class DeniedToolExecutor:
        def execute(self, prepared: PreparedTurn, context: QueryTurnContext) -> ExecutedTurn:
            return ExecutedTurn(
                stop_reason="tool_use",
                tool_calls=[
                    ToolCallRequest(
                        tool_name="Read",
                        arguments={"file_path": str(target)},
                        tool_use_id="tool-read-1",
                    )
                ],
            )

    runtime = QueryRuntime(
        state=RuntimeState(cwd=str(project_dir), home_dir=str(tmp_path / "home")),
        turn_executor=DeniedToolExecutor(),
    )

    outputs = runtime.handle_user_message(
        SDKUserMessage(
            type="user",
            message={"role": "user", "content": "read the secret"},
            parent_tool_use_id=None,
        )
    )

    assert len(outputs) == 4
    assert isinstance(outputs[0], SDKSessionStateChangedMessage)
    assert outputs[0].state == "running"
    assert isinstance(outputs[1], SDKRequestStartMessage)
    assert outputs[1].event.type == "stream_request_start"
    assert isinstance(outputs[2], SDKResultError)
    assert outputs[2].errors == ["Read requires permission"]
    assert isinstance(outputs[3], SDKSessionStateChangedMessage)
    assert outputs[3].state == "idle"
    assert len(runtime.transcript) == 2
    assert isinstance(runtime.transcript[1], SDKAssistantMessage)
    assert runtime.transcript[1].message["content"][0]["type"] == "tool_use"



def test_initialize_request_schema_accepts_hook_events() -> None:
    request = SDKControlInitializeRequest.model_validate(
        {
            "subtype": "initialize",
            "hooks": {
                "PreToolUse": [{"hookCallbackIds": ["cb-1"]}],
            },
            "promptSuggestions": True,
        }
    )
    assert request.subtype == "initialize"
    assert request.hooks is not None
    assert "PreToolUse" in request.hooks


def test_hooks_settings_reject_unknown_event() -> None:
    with pytest.raises(ValueError, match="Unsupported hook events"):
        HooksSettings.from_event_map({"BadEvent": []})


def test_settings_model_accepts_minimal_settings() -> None:
    settings = SettingsModel.model_validate(
        {
            "$schema": "https://json.schemastore.org/claude-code-settings.json",
            "permissions": {"allow": ["Read"]},
        }
    )
    assert settings.schema_ == "https://json.schemastore.org/claude-code-settings.json"
    assert settings.permissions is not None
    assert settings.permissions.allow == ["Read"]


def test_json_schema_output_format_uses_schema_alias() -> None:
    output = JsonSchemaOutputFormat.model_validate(
        {
            "type": "json_schema",
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
        }
    )
    assert output.schema_["type"] == "object"
    assert output.model_dump(by_alias=True)["schema"]["properties"]["name"]["type"] == "string"


def test_permission_result_allow_accepts_updated_permissions() -> None:
    result = PermissionResultAllow.model_validate(
        {
            "behavior": "allow",
            "updatedInput": {"command": "pytest"},
            "updatedPermissions": [
                {
                    "type": "addRules",
                    "rules": [{"toolName": "Bash", "ruleContent": "pytest"}],
                    "behavior": "allow",
                    "destination": "session",
                }
            ],
            "decisionClassification": "user_temporary",
        }
    )
    assert result.behavior == "allow"
    assert result.updatedInput == {"command": "pytest"}
    assert result.updatedPermissions is not None
    assert result.updatedPermissions[0].type == "addRules"


def test_mcp_set_servers_request_accepts_transport_configs() -> None:
    request = SDKControlMcpSetServersRequest.model_validate(
        {
            "subtype": "mcp_set_servers",
            "servers": {
                "local": {"command": "python", "args": ["-m", "server"]},
                "remote": {"type": "http", "url": "https://example.com/mcp"},
            },
        }
    )
    assert request.subtype == "mcp_set_servers"
    assert request.servers["local"].command == "python"
    assert request.servers["remote"].type == "http"


def test_mcp_set_servers_response_tracks_added_removed_and_errors() -> None:
    response = SDKControlMcpSetServersResponse.model_validate(
        {
            "added": ["local"],
            "removed": ["old"],
            "errors": {"broken": "connection failed"},
        }
    )
    assert response.added == ["local"]
    assert response.removed == ["old"]
    assert response.errors == {"broken": "connection failed"}


def test_get_settings_response_accepts_sources_and_applied_values() -> None:
    response = SDKControlGetSettingsResponse.model_validate(
        {
            "effective": {"model": "claude-opus-4-6"},
            "sources": [
                {"source": "userSettings", "settings": {"model": "claude-sonnet-4-6"}},
                {"source": "flagSettings", "settings": {"model": "claude-opus-4-6"}},
            ],
            "applied": {"model": "claude-opus-4-6", "effort": "high"},
        }
    )
    assert response.sources[0].source == "userSettings"
    assert response.applied is not None
    assert response.applied.effort == "high"


def test_get_context_usage_response_accepts_extended_breakdown() -> None:
    response = SDKControlGetContextUsageResponse.model_validate(
        {
            "categories": [{"name": "messages", "tokens": 100, "color": "blue"}],
            "totalTokens": 100,
            "maxTokens": 200,
            "rawMaxTokens": 200,
            "percentage": 50.0,
            "gridRows": [
                [
                    {
                        "color": "blue",
                        "isFilled": True,
                        "categoryName": "messages",
                        "tokens": 100,
                        "percentage": 50.0,
                        "squareFullness": 1.0,
                    }
                ]
            ],
            "model": "claude-opus-4-6",
            "memoryFiles": [{"path": ".claude/MEMORY.md", "type": "Project", "tokens": 10}],
            "mcpTools": [{"name": "search", "serverName": "local", "tokens": 5}],
            "agents": [{"agentType": "Explore", "source": "system", "tokens": 7}],
            "skills": {
                "totalSkills": 3,
                "includedSkills": 1,
                "tokens": 9,
                "skillFrontmatter": [{"name": "python", "source": "user", "tokens": 2}],
            },
            "isAutoCompactEnabled": True,
            "messageBreakdown": {
                "toolCallTokens": 1,
                "toolResultTokens": 2,
                "attachmentTokens": 3,
                "assistantMessageTokens": 4,
                "userMessageTokens": 5,
                "toolCallsByType": [{"name": "Read", "callTokens": 1, "resultTokens": 2}],
                "attachmentsByType": [{"name": "image", "tokens": 3}],
            },
            "apiUsage": {
                "input_tokens": 11,
                "output_tokens": 12,
                "cache_creation_input_tokens": 13,
                "cache_read_input_tokens": 14,
            },
        }
    )
    assert response.skills is not None
    assert response.skills.skillFrontmatter[0].name == "python"
    assert response.skills.skillFrontmatter[0].argumentHint is None
    assert response.skills.skillFrontmatter[0].userInvocable is None
    assert response.messageBreakdown is not None
    assert response.messageBreakdown.toolCallsByType[0].name == "Read"
    assert response.apiUsage is not None
    assert response.apiUsage.output_tokens == 12


def test_pre_tool_use_hook_input_accepts_base_and_event_fields() -> None:
    hook_input = PreToolUseHookInput.model_validate(
        {
            "session_id": "sess-1",
            "transcript_path": ".claude/transcript.jsonl",
            "cwd": "/repo",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "README.md"},
            "tool_use_id": "tool-1",
        }
    )
    assert hook_input.hook_event_name == "PreToolUse"
    assert hook_input.tool_name == "Read"
    assert hook_input.tool_use_id == "tool-1"


def test_hook_json_outputs_accept_async_and_sync_forms() -> None:
    async_output = AsyncHookJSONOutput.model_validate({"async": True, "asyncTimeout": 5})
    assert async_output.async_ is True
    assert async_output.model_dump(by_alias=True)["async"] is True

    sync_output = SyncHookJSONOutput.model_validate(
        {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "allow",
                    "updatedPermissions": [
                        {
                            "type": "addRules",
                            "rules": [{"toolName": "Read", "ruleContent": "README.md"}],
                            "behavior": "allow",
                            "destination": "session",
                        }
                    ],
                },
            },
        }
    )
    assert sync_output.continue_ is True
    assert isinstance(sync_output.hookSpecificOutput, PermissionRequestHookSpecificOutput)
    assert sync_output.hookSpecificOutput.decision.behavior == "allow"


def test_sdk_hook_response_message_accepts_outcome() -> None:
    message = SDKHookResponseMessage.model_validate(
        {
            "type": "system",
            "subtype": "hook_response",
            "hook_id": "hook-1",
            "hook_name": "lint",
            "hook_event": "PostToolUse",
            "output": "done",
            "stdout": "ok",
            "stderr": "",
            "outcome": "success",
            "uuid": "msg-1",
            "session_id": "sess-1",
        }
    )
    assert message.subtype == "hook_response"
    assert message.outcome == "success"


def test_sdk_task_notification_message_accepts_usage_block() -> None:
    message = SDKTaskNotificationMessage.model_validate(
        {
            "type": "system",
            "subtype": "task_notification",
            "task_id": "task-1",
            "status": "completed",
            "output_file": ".claude/tasks/task-1.txt",
            "summary": "done",
            "usage": {"total_tokens": 10, "tool_uses": 2, "duration_ms": 30},
            "uuid": "msg-2",
            "session_id": "sess-1",
        }
    )
    assert message.status == "completed"
    assert message.usage is not None
    assert message.usage.tool_uses == 2


def test_sdk_message_union_accepts_hook_and_task_messages() -> None:
    adapter = TypeAdapter(SDKMessage)

    hook_message = adapter.validate_python(
        {
            "type": "system",
            "subtype": "hook_response",
            "hook_id": "hook-1",
            "hook_name": "lint",
            "hook_event": "PostToolUse",
            "output": "done",
            "stdout": "ok",
            "stderr": "",
            "outcome": "success",
            "uuid": "msg-1",
            "session_id": "sess-1",
        }
    )
    task_message = adapter.validate_python(
        {
            "type": "system",
            "subtype": "task_notification",
            "task_id": "task-1",
            "status": "completed",
            "output_file": ".claude/tasks/task-1.txt",
            "summary": "done",
            "uuid": "msg-2",
            "session_id": "sess-1",
        }
    )

    assert isinstance(hook_message, SDKHookResponseMessage)
    assert isinstance(task_message, SDKTaskNotificationMessage)
    assert task_message.summary == "done"


def test_sdk_message_union_accepts_prompt_suggestion_message() -> None:
    adapter = TypeAdapter(SDKMessage)
    message = adapter.validate_python(
        {
            "type": "prompt_suggestion",
            "suggestion": "Continue from: hello world",
            "uuid": "msg-3",
            "session_id": "sess-1",
        }
    )

    assert isinstance(message, SDKPromptSuggestionMessage)
    assert message.suggestion == "Continue from: hello world"


def test_structured_io_ignores_keep_alive_and_applies_env_updates() -> None:
    io = StructuredIO()
    os.environ.pop("PY_CLAW_TEST_ENV", None)

    messages = io.feed_text(
        '{"type":"keep_alive"}\n'
        '{"type":"update_environment_variables","variables":{"PY_CLAW_TEST_ENV":"set"}}\n'
    )

    assert messages == []
    assert os.environ["PY_CLAW_TEST_ENV"] == "set"
    os.environ.pop("PY_CLAW_TEST_ENV", None)


def test_structured_io_returns_control_request_messages() -> None:
    io = StructuredIO()

    messages = io.feed_text(
        '{"type":"control_request","request_id":"req-1","request":{"subtype":"initialize"}}\n'
    )

    assert len(messages) == 1
    message = messages[0]
    assert isinstance(message, SDKControlRequestEnvelope)
    assert message.request_id == "req-1"
    assert message.request.subtype == "initialize"


def test_structured_io_tracks_pending_requests_and_consumes_response() -> None:
    io = StructuredIO()
    request = SDKControlInitializeRequest(subtype="initialize")

    envelope = io.send_request(request, request_id="req-1")
    assert envelope.request_id == "req-1"
    assert "req-1" in io.pending_requests

    messages = io.feed_text(
        '{"type":"control_response","response":{"subtype":"success","request_id":"req-1","response":{}}}\n'
    )

    assert messages == []
    assert "req-1" not in io.pending_requests
    assert io.take_completed_response("req-1") == {}


def test_structured_io_can_replay_orphan_control_response() -> None:
    io = StructuredIO(replay_user_messages=True)

    messages = io.feed_text(
        '{"type":"control_response","response":{"subtype":"success","request_id":"missing","response":{}}}\n'
    )

    assert len(messages) == 1
    message = messages[0]
    assert isinstance(message, SDKControlResponseEnvelope)
    assert message.response.request_id == "missing"


def test_structured_io_prepends_user_message_before_stream_content() -> None:
    io = StructuredIO()
    io.prepend_user_message("hello")

    messages = io.feed_text(
        '{"type":"control_request","request_id":"req-2","request":{"subtype":"initialize"}}\n'
    )

    assert len(messages) == 2
    user_message, request_message = messages
    assert user_message.type == "user"
    assert request_message.type == "control_request"
    assert request_message.request_id == "req-2"


def test_structured_io_write_serializes_json_line() -> None:
    io = StructuredIO()
    output = io.write(SDKKeepAliveMessage(type="keep_alive"))

    assert output == '{"type":"keep_alive"}\n'
    assert isinstance(io.stdout_messages[0], SDKKeepAliveMessage)


def test_structured_io_rejects_invalid_json_line() -> None:
    io = StructuredIO()

    with pytest.raises(StructuredIOParseError, match="Error parsing streaming input line"):
        io.feed_text("not-json\n")


def test_structured_io_cancel_request_removes_pending_entry() -> None:
    io = StructuredIO()
    io.send_request(SDKControlInitializeRequest(subtype="initialize"), request_id="req-3")

    cancel_message = io.cancel_request("req-3")

    assert cancel_message.request_id == "req-3"
    assert "req-3" not in io.pending_requests
    assert io.stdout_messages[-1].type == "control_cancel_request"


def test_structured_io_rejects_send_request_after_input_closed() -> None:
    io = StructuredIO()

    assert io.close_input() == []

    with pytest.raises(StructuredIORequestError, match="Stream closed"):
        io.send_request(SDKControlInitializeRequest(subtype="initialize"))


def test_structured_io_buffers_partial_chunks_until_newline() -> None:
    io = StructuredIO()

    assert io.feed_text('{"type":"control_request"') == []
    messages = io.feed_text(',"request_id":"req-4","request":{"subtype":"initialize"}}\n')

    assert len(messages) == 1
    assert isinstance(messages[0], SDKControlRequestEnvelope)
    assert messages[0].request_id == "req-4"


def test_structured_io_accepts_replay_user_messages() -> None:
    io = StructuredIO()

    messages = io.feed_text(
        '{"type":"user","message":{"role":"user","content":"hello"},"parent_tool_use_id":null,"uuid":"msg-1","session_id":"sess-1","isReplay":true}\n'
    )

    assert len(messages) == 1
    assert messages[0].type == "user"
    assert messages[0].session_id == "sess-1"
    assert getattr(messages[0], "isReplay", False) is True


def test_structured_io_validates_response_type_before_storing_result() -> None:
    io = StructuredIO()
    io.send_request(
        SDKControlInitializeRequest(subtype="initialize"),
        response_type=SDKControlGetSettingsResponse,
        request_id="req-5",
    )

    assert io.feed_text(
        '{"type":"control_response","response":{"subtype":"success","request_id":"req-5","response":{"effective":{}}}}\n'
    ) == []

    with pytest.raises(Exception):
        io.take_completed_response("req-5")


def test_structured_io_surfaces_error_responses_via_take_completed_response() -> None:
    io = StructuredIO()
    io.send_request(SDKControlInitializeRequest(subtype="initialize"), request_id="req-6")

    assert io.feed_text(
        '{"type":"control_response","response":{"subtype":"error","request_id":"req-6","error":"denied"}}\n'
    ) == []

    with pytest.raises(StructuredIORequestError, match="denied"):
        io.take_completed_response("req-6")


def test_structured_io_close_input_marks_pending_requests_failed() -> None:
    io = StructuredIO()
    io.send_request(SDKControlInitializeRequest(subtype="initialize"), request_id="req-7")

    assert io.close_input() == []

    with pytest.raises(StructuredIORequestError, match="Tool permission stream closed before response received"):
        io.take_completed_response("req-7")

    with pytest.raises(StructuredIORequestError, match="Stream closed"):
        io.feed_text("{}")


def test_structured_io_iter_messages_closes_input_at_end() -> None:
    io = StructuredIO()

    messages = list(
        io.iter_messages([
            '{"type":"control_request","request_id":"req-8","request":{"subtype":"initialize"}}\n'
        ])
    )

    assert len(messages) == 1
    assert messages[0].request_id == "req-8"

    with pytest.raises(StructuredIORequestError, match="Stream closed"):
        io.send_request(SDKControlInitializeRequest(subtype="initialize"))


def test_structured_io_close_input_flushes_final_line() -> None:
    io = StructuredIO()

    assert io.feed_text('{"type":"control_request","request_id":"req-9","request":{"subtype":"initialize"}}') == []
    messages = io.close_input()

    assert len(messages) == 1
    assert messages[0].request_id == "req-9"


def test_structured_io_take_completed_response_requires_known_request() -> None:
    io = StructuredIO()

    with pytest.raises(StructuredIORequestError, match="Unknown or incomplete request"):
        io.take_completed_response("missing")


def test_structured_io_rejects_invalid_user_role() -> None:
    io = StructuredIO()

    with pytest.raises(StructuredIOParseError, match="Error parsing streaming input line"):
        io.feed_text(
            '{"type":"user","message":{"role":"assistant","content":"nope"},"parent_tool_use_id":null}\n'
        )


def test_structured_io_returns_replayed_control_response_when_enabled() -> None:
    io = StructuredIO(replay_user_messages=True)
    io.send_request(SDKControlInitializeRequest(subtype="initialize"), request_id="req-10")

    messages = io.feed_text(
        '{"type":"control_response","response":{"subtype":"success","request_id":"req-10","response":{}}}\n'
    )

    assert len(messages) == 1
    assert isinstance(messages[0], SDKControlResponseEnvelope)
    assert io.take_completed_response("req-10") == {}


def test_structured_io_write_serializes_control_request() -> None:
    io = StructuredIO()
    payload = io.write(
        SDKControlRequestEnvelope(
            type="control_request",
            request_id="req-11",
            request=SDKControlInitializeRequest(subtype="initialize"),
        )
    )

    assert payload == '{"type":"control_request","request_id":"req-11","request":{"subtype":"initialize"}}\n'


def test_control_response_envelope_accepts_nested_pending_requests() -> None:
    response = SDKControlResponseEnvelope.model_validate(
        {
            "type": "control_response",
            "response": {
                "subtype": "error",
                "request_id": "req-12",
                "error": "blocked",
                "pending_permission_requests": [
                    {
                        "type": "control_request",
                        "request_id": "req-child",
                        "request": {"subtype": "initialize"},
                    }
                ],
            },
        }
    )

    assert response.response.subtype == "error"
    assert response.response.pending_permission_requests is not None
    assert response.response.pending_permission_requests[0].request_id == "req-child"


def test_structured_io_rejects_partial_json_on_close() -> None:
    io = StructuredIO()
    io.feed_text('{"type":"control_request"')

    with pytest.raises(StructuredIOParseError, match="Error parsing streaming input line"):
        io.close_input()


def test_structured_io_can_parse_update_environment_message_directly() -> None:
    message = StructuredIO().process_line(
        '{"type":"update_environment_variables","variables":{"A":"B"}}'
    )

    assert message is None
    assert os.environ["A"] == "B"
    os.environ.pop("A", None)


def test_structured_io_can_parse_user_message_directly() -> None:
    message = StructuredIO().process_line(
        '{"type":"user","message":{"role":"user","content":"hi"},"parent_tool_use_id":null}'
    )

    assert isinstance(message, SDKUserMessage)
    assert message.type == "user"
