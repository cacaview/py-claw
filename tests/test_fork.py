"""Tests for fork subprocess mechanism (AgentTool Phase 1)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from py_claw.fork.model_config import resolve_fork_model_config
from py_claw.fork.protocol import (
    ForkInitMessage,
    ForkMessage,
    ForkOutputMessage,
    ForkResultMessage,
    ForkStopMessage,
    ForkTurnMessage,
    NDJSONParser,
    build_fork_boilerplate,
)
from py_claw.fork.process import ForkedAgentProcess


class TestNDJSONParser:
    """Tests for NDJSONParser."""

    def test_parse_single_line(self):
        parser = NDJSONParser()
        results = parser.parse('{"type":"result","assistant_text":"hello"}\n')
        assert len(results) == 1
        assert results[0]["type"] == "result"
        assert results[0]["assistant_text"] == "hello"

    def test_parse_multiple_lines(self):
        parser = NDJSONParser()
        results = parser.parse('{"type":"output","delta":"hi"}\n{"type":"result","assistant_text":"done"}\n')
        assert len(results) == 2
        assert results[0]["type"] == "output"
        assert results[1]["type"] == "result"

    def test_parse_incomplete_buffer(self):
        parser = NDJSONParser()
        results = parser.parse('{"type":"result","data":"')
        assert results == []
        assert parser._buffer == '{"type":"result","data":"'

        results2 = parser.parse('more"}\n')
        assert len(results2) == 1
        assert results2[0]["type"] == "result"

    def test_parse_skips_malformed(self):
        parser = NDJSONParser()
        results = parser.parse('{"type":"ok"}\nnot json\n{"type":"done"}\n')
        assert len(results) == 2
        assert results[0]["type"] == "ok"
        assert results[1]["type"] == "done"

    def test_parse_empty_lines_skipped(self):
        parser = NDJSONParser()
        results = parser.parse('\n\n{"type":"ok"}\n\n\n')
        assert len(results) == 1
        assert results[0]["type"] == "ok"


class TestBuildForkBoilerplate:
    """Tests for fork boilerplate text generation."""

    def test_basic_boilerplate(self):
        result = build_fork_boilerplate(
            parent_session_id="parent-123",
            child_session_id="fork-456",
            transcript=[],
        )
        assert "FORK SUBAGENT" in result
        assert "parent-123" in result
        assert "fork-456" in result
        assert "EXECUTE DIRECTLY" in result

    def test_boilerplate_includes_transcript(self):
        result = build_fork_boilerplate(
            parent_session_id="p",
            child_session_id="c",
            transcript=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
        )
        assert "USER" in result
        assert "hello" in result
        assert "ASSISTANT" in result
        assert "hi there" in result

    def test_boilerplate_truncates_long_content(self):
        long_content = "x" * 1000
        result = build_fork_boilerplate(
            parent_session_id="p",
            child_session_id="c",
            transcript=[{"role": "user", "content": long_content}],
        )
        assert len(result) < 1000 + 500  # some overhead from formatting


class TestForkedAgentProcessLifecycle:
    """Tests for ForkedAgentProcess lifecycle management."""

    def test_spawn_and_terminate(self):
        """Process can be spawned and terminated cleanly."""
        process = ForkedAgentProcess(
            session_id="test-session",
            system_prompt="You are a test agent.",
            cwd=".",
        )
        process.spawn()
        assert process.is_running

        exit_code = process.terminate(timeout=5.0)
        assert exit_code is not None
        assert not process.is_running

    def test_send_init_message(self):
        """Init message is sent and child receives it."""
        process = ForkedAgentProcess(
            session_id="test-init",
            system_prompt="Test prompt",
            model="test-model",
            cwd=".",
        )
        process.spawn()
        try:
            process.send_init()
            # Child should process init without error
            time.sleep(0.2)
            assert process.is_running
        finally:
            process.terminate(timeout=5.0)

    def test_kill_force_terminates(self):
        """kill() force terminates the subprocess."""
        process = ForkedAgentProcess(
            session_id="test-kill",
            system_prompt="Test",
            cwd=".",
        )
        process.spawn()
        assert process.is_running

        exit_code = process.kill()
        assert exit_code is not None
        assert not process.is_running

    def test_double_spawn_raises(self):
        """Spawning twice raises RuntimeError."""
        process = ForkedAgentProcess(session_id="test-double", system_prompt="Test", cwd=".")
        process.spawn()
        try:
            with pytest.raises(RuntimeError, match="already spawned"):
                process.spawn()
        finally:
            process.terminate()

    def test_terminate_idempotent(self):
        """Multiple terminate calls are safe."""
        process = ForkedAgentProcess(session_id="test-idempotent", system_prompt="Test", cwd=".")
        process.spawn()
        process.terminate()
        code1 = process.terminate()
        code2 = process.terminate()
        # Both return the same exit code
        assert code1 == code2


class TestChildProcessStdio:
    """Integration tests for child process NDJSON stdio communication."""

    def test_child_process_handles_turn(self, monkeypatch):
        """Child process handles init + turn and returns result."""
        # Keep this stdio-mechanism test deterministic: never hit a real API,
        # regardless of API keys present in the test environment. Persistent
        # turns degrade fast (no network) when no key is configured.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("API_KEY", raising=False)

        process = ForkedAgentProcess(
            session_id="test-child-turn",
            system_prompt="You are helpful.",
            cwd=".",
        )
        process.spawn()
        try:
            process.send_init()

            # Send a turn
            process.send_turn("Say hello", turn_count=0)

            # Collect messages
            all_messages = []
            deadline = time.time() + 10
            while time.time() < deadline:
                msgs = process.iter_messages(timeout=2.0)
                all_messages.extend(msgs)
                if any(m.get("type") == "result" for m in all_messages):
                    break

            msg_types = [m.get("type") for m in all_messages]
            assert "result" in msg_types
            results = [m for m in all_messages if m.get("type") == "result"]
            # Exactly one result per turn (no duplicate handling)
            assert len(results) == 1

            result = results[0]
            assert "assistant_text" in result
        finally:
            process.terminate(timeout=5.0)

    def test_child_process_handles_stop(self):
        """Child process exits cleanly on stop message."""
        process = ForkedAgentProcess(
            session_id="test-child-stop",
            system_prompt="You are test.",
            cwd=".",
        )
        process.spawn()
        process.send_init()
        time.sleep(0.1)

        process.send_stop()

        # Process should exit within timeout
        deadline = time.time() + 5
        while process.is_running and time.time() < deadline:
            time.sleep(0.1)

        assert not process.is_running


class TestForkMessageTypes:
    """Tests for fork protocol message dataclasses."""

    def test_fork_init_message(self):
        msg = ForkInitMessage(
            session_id="sess-1",
            system_prompt="You are an agent.",
            model="claude-3",
            cwd="/tmp",
        )
        assert msg.type == "init"
        assert msg.session_id == "sess-1"
        assert msg.system_prompt == "You are an agent."
        assert msg.model == "claude-3"

    def test_fork_turn_message(self):
        msg = ForkTurnMessage(query_text="Hello", turn_count=5)
        assert msg.type == "turn"
        assert msg.query_text == "Hello"
        assert msg.turn_count == 5

    def test_fork_stop_message(self):
        msg = ForkStopMessage()
        assert msg.type == "stop"

    def test_fork_output_message(self):
        msg = ForkOutputMessage(delta="part1")
        assert msg.type == "output"
        assert msg.delta == "part1"

    def test_fork_result_message(self):
        msg = ForkResultMessage(
            assistant_text="Hello!",
            stop_reason="end_turn",
            usage={"tokens": 100},
        )
        assert msg.type == "result"
        assert msg.assistant_text == "Hello!"
        assert msg.stop_reason == "end_turn"
        assert msg.usage["tokens"] == 100


# ─── Real model execution in persistent turns ─────────────────────────────────


class _MockAnthropicServer:
    """Minimal local mock of the Anthropic Messages API (/v1/messages).

    The forked child process inherits the parent's environment, so pointing
    ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL at this server makes the child's
    real model path hit the mock instead of the network.
    """

    def __init__(self) -> None:
        self.responses: list[dict] = []
        self.requests: list[dict] = []
        self.fail_status: int | None = None
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _make_handler(self):
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                mock.requests.append(body)
                if mock.fail_status is not None:
                    self.send_response(mock.fail_status)
                    self.end_headers()
                    self.wfile.write(b'{"type":"error","error":{"message":"mock failure"}}')
                    return
                resp = mock.responses.pop(0) if mock.responses else None
                if resp is None:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"error":"no mock response configured"}')
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode("utf-8"))

            def log_message(self, *args):
                pass  # keep test output clean

        return Handler

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def _mock_text_response(text: str, model: str = "mock-model") -> dict:
    return {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 4},
    }


def _mock_tool_use_response(name: str, arguments: dict, tool_use_id: str = "tu_mock") -> dict:
    return {
        "id": "msg_mock_use",
        "type": "message",
        "role": "assistant",
        "model": "mock-model",
        "content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": arguments}],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }


@pytest.fixture
def mock_anthropic(monkeypatch):
    server = _MockAnthropicServer()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", server.base_url)
    yield server
    server.stop()


@pytest.fixture
def no_api_env(monkeypatch):
    """Ensure no API key is visible to child processes (fast degraded path)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:1")  # never used without a key


class TestPersistentRealModel:
    """Persistent (non-speculation) turns execute real model calls in the child.

    These tests spawn a real child subprocess and point its model config at a
    local mock Anthropic server, verifying the full parent->child->parent
    data flow for real execution and its degraded fallbacks.
    """

    def _spawn(self, **kwargs) -> ForkedAgentProcess:
        kwargs.setdefault("cwd", ".")
        process = ForkedAgentProcess(
            session_id="test-persistent-model",
            system_prompt="You are a helpful test agent.",
            **kwargs,
        )
        process.spawn()
        process.send_init()
        return process

    def test_persistent_turn_returns_real_model_text(self, mock_anthropic):
        mock_anthropic.responses.append(_mock_text_response("REAL-MODEL-TEXT"))
        process = self._spawn(model="mock-model")
        try:
            result = process.send_turn_sync("Hello", turn_count=0, timeout=20.0)
        finally:
            process.terminate(timeout=5.0)

        assert result["assistant_text"] == "REAL-MODEL-TEXT"
        assert "Placeholder" not in result["assistant_text"]
        assert result["stop_reason"] == "end_turn"
        assert result["usage"]["backendType"] == "fork-model"
        assert result["usage"]["backendRequests"] == 1
        assert result["usage"]["inputTokens"] == 10
        assert result["usage"]["outputTokens"] == 4

        # The request carried the system prompt, the query, and the model.
        req = mock_anthropic.requests[0]
        assert req["system"] == "You are a helpful test agent."
        assert req["messages"] == [{"role": "user", "content": "Hello"}]
        assert req["model"] == "mock-model"
        assert {t["name"] for t in req["tools"]} >= {"Read", "Bash", "Write", "Edit", "Glob", "Grep"}

    def test_persistent_turn_sends_single_result_per_turn(self, mock_anthropic):
        """Regression: each turn message produces exactly one result message."""
        mock_anthropic.responses.append(_mock_text_response("ONE"))
        mock_anthropic.responses.append(_mock_text_response("TWO"))
        process = self._spawn()
        try:
            process.send_turn("First", turn_count=0)
            process.send_turn("Second", turn_count=1)
            results = []
            deadline = time.time() + 20
            while len(results) < 2 and time.time() < deadline:
                results.extend(
                    m for m in process.iter_messages(timeout=2.0) if m.get("type") == "result"
                )
        finally:
            process.terminate(timeout=5.0)

        assert [r["turn_count"] for r in results] == [0, 1]
        assert [r["assistant_text"] for r in results] == ["ONE", "TWO"]

    def test_persistent_turn_sends_conversation_history(self, mock_anthropic):
        mock_anthropic.responses.append(_mock_text_response("ANSWER-1"))
        mock_anthropic.responses.append(_mock_text_response("ANSWER-2"))
        process = self._spawn()
        try:
            r0 = process.send_turn_sync("Question one", turn_count=0, timeout=20.0)
            r1 = process.send_turn_sync("Question two", turn_count=1, timeout=20.0)
        finally:
            process.terminate(timeout=5.0)

        assert r0["assistant_text"] == "ANSWER-1"
        assert r1["assistant_text"] == "ANSWER-2"

        # Second API request must carry the full prior exchange as messages.
        second_req = mock_anthropic.requests[1]
        assert [m["role"] for m in second_req["messages"]] == ["user", "assistant", "user"]
        assert second_req["messages"][0]["content"] == "Question one"
        assert second_req["messages"][1]["content"] == "ANSWER-1"
        assert second_req["messages"][2]["content"] == "Question two"

    def test_persistent_turn_executes_tools_and_loops(self, mock_anthropic, tmp_path):
        """Tool calls from the model are executed in the child and results fed back."""
        data_file = tmp_path / "data.txt"
        data_file.write_text("TOOL-OUTPUT-777", encoding="utf-8")
        mock_anthropic.responses.append(
            _mock_tool_use_response("Read", {"path": str(data_file)})
        )
        mock_anthropic.responses.append(_mock_text_response("TOOL-LOOP-COMPLETE"))
        process = self._spawn(cwd=str(tmp_path))
        try:
            result = process.send_turn_sync(
                "Read the data file and summarize it", turn_count=0, timeout=30.0
            )
        finally:
            process.terminate(timeout=5.0)

        assert result["assistant_text"] == "TOOL-LOOP-COMPLETE"
        assert result["usage"]["backendRequests"] == 2
        assert [tc["tool_name"] for tc in result["tool_calls"]] == ["Read"]
        assert result["tool_calls"][0]["arguments"]["path"] == str(data_file)

        # The tool result (file content) was fed back to the model.
        second_req = mock_anthropic.requests[1]
        tool_results = [
            b for b in second_req["messages"][-1]["content"] if b.get("type") == "tool_result"
        ]
        assert len(tool_results) == 1
        assert tool_results[0]["tool_use_id"] == "tu_mock"
        assert "TOOL-OUTPUT-777" in json.dumps(tool_results[0])

    def test_persistent_turn_no_api_key_degrades_fast(self, no_api_env):
        process = self._spawn()
        try:
            result = process.send_turn_sync("Hello", turn_count=0, timeout=20.0)
            assert "No API key" in result["assistant_text"]
            assert "Placeholder Agent" not in result["assistant_text"]
            assert result["usage"]["backendType"] == "no_api_key"

            # The child stays alive and degrades on subsequent turns (no hang).
            result2 = process.send_turn_sync("Again", turn_count=1, timeout=20.0)
            assert "No API key" in result2["assistant_text"]
        finally:
            process.terminate(timeout=5.0)

    def test_persistent_turn_api_error_degrades_and_recovers(self, mock_anthropic):
        mock_anthropic.fail_status = 500
        process = self._spawn()
        try:
            result = process.send_turn_sync("Hello", turn_count=0, timeout=20.0)
            assert "Model API error" in result["assistant_text"]
            assert "Placeholder Agent" not in result["assistant_text"]
            assert result["usage"]["backendType"] == "model_error"

            # Child survives the failed call and recovers on the next turn.
            mock_anthropic.fail_status = None
            mock_anthropic.responses.append(_mock_text_response("RECOVERED"))
            result2 = process.send_turn_sync("Hello again", turn_count=1, timeout=20.0)
            assert result2["assistant_text"] == "RECOVERED"
            assert result2["usage"]["backendType"] == "fork-model"
        finally:
            process.terminate(timeout=5.0)


class TestAgentToolForkRealModel:
    """Agent tool end-to-end: spawned teammate subagents run real model turns."""

    def _state(self, tmp_path):
        from py_claw.cli.runtime import RuntimeState
        from py_claw.query import QueryRuntime

        state = RuntimeState(cwd=str(tmp_path), flag_settings={"FORK_SUBAGENT": True})
        QueryRuntime(state)
        return state

    def test_agent_tool_teammate_real_model_end_to_end(self, mock_anthropic, tmp_path):
        state = self._state(tmp_path)
        agent_id = None
        try:
            mock_anthropic.responses.append(_mock_text_response("TEAMMATE-ANSWER-1"))
            started = state.tool_runtime.execute(
                "Agent",
                {
                    "description": "Helper",
                    "prompt": "Initial prompt",
                    "run_in_background": True,
                    "name": "bot",
                },
                cwd=str(tmp_path),
            )
            assert started.output["status"] == "teammate_spawned"
            assert started.output["result"] == "TEAMMATE-ANSWER-1"
            assert "Placeholder" not in started.output["result"]
            # Initial turn = exactly one API request (no double-send).
            assert len(mock_anthropic.requests) == 1

            agent_id = started.output["agent_id"]

            # Follow-up through SendMessage hits the persistent child.
            mock_anthropic.responses.append(_mock_text_response("TEAMMATE-ANSWER-2"))
            follow = state.tool_runtime.execute(
                "SendMessage",
                {"to": agent_id, "summary": "follow-up", "message": "What next?"},
                cwd=str(tmp_path),
            )
            assert follow.output["sent"] is True
            assert follow.output["result"] == "TEAMMATE-ANSWER-2"
            assert "Placeholder" not in follow.output["result"]
            assert follow.output["usage"]["backendType"] == "fork-model"
            assert len(mock_anthropic.requests) == 2
        finally:
            if agent_id:
                state.task_runtime.stop_forked_process(agent_id)

    def test_agent_tool_teammate_no_api_key_degrades(self, no_api_env, tmp_path):
        state = self._state(tmp_path)
        agent_id = None
        try:
            started = state.tool_runtime.execute(
                "Agent",
                {
                    "description": "Helper",
                    "prompt": "Initial prompt",
                    "run_in_background": True,
                    "name": "bot",
                },
                cwd=str(tmp_path),
            )
            assert started.output["status"] == "teammate_spawned"
            result_text = started.output["result"]
            assert "No API key" in result_text
            assert "Placeholder Agent" not in result_text

            agent_id = started.output["agent_id"]

            # SendMessage also degrades without crashing the subprocess.
            follow = state.tool_runtime.execute(
                "SendMessage",
                {"to": agent_id, "summary": "follow-up", "message": "What next?"},
                cwd=str(tmp_path),
            )
            assert "No API key" in follow.output["result"]
            assert follow.output["usage"]["backendType"] == "no_api_key"
        finally:
            if agent_id:
                state.task_runtime.stop_forked_process(agent_id)


# ─── Parent-configured OpenAI-compatible backend ──────────────────────────────


class _MockOpenAIServer:
    """Minimal local mock of an OpenAI-compatible /chat/completions endpoint.

    Responds with a single SSE ``data:`` frame carrying a full
    chat.completion object — the same wire format the main process's
    ApiQueryBackend parses via _parse_sse_payload — followed by [DONE].
    """

    def __init__(self) -> None:
        self.responses: list[dict] = []
        self.requests: list[dict] = []
        self.request_headers: list[dict] = []
        self.fail_status: int | None = None
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _make_handler(self):
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                mock.requests.append(body)
                mock.request_headers.append(dict(self.headers))
                if mock.fail_status is not None:
                    self.send_response(mock.fail_status)
                    self.end_headers()
                    self.wfile.write(b'{"error":"mock failure"}')
                    return
                resp = mock.responses.pop(0) if mock.responses else None
                if resp is None:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"error":"no mock response configured"}')
                    return
                sse = f"data: {json.dumps(resp)}\n\ndata: [DONE]\n\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(sse.encode("utf-8"))

            def log_message(self, *args):
                pass  # keep test output clean

        return Handler

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def _openai_text_response(text: str, model: str = "mock-model") -> dict:
    return {
        "id": "chatcmpl_mock",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        # vLLM-style usage: no cached_tokens field.
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }


def _openai_tool_calls_response(calls: list[tuple[str, str, dict]], model: str = "mock-model") -> dict:
    return {
        "id": "chatcmpl_mock_use",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)},
                        }
                        for call_id, name, args in calls
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 6, "completion_tokens": 3, "total_tokens": 9},
    }


@pytest.fixture
def mock_openai(monkeypatch, tmp_path):
    """OpenAI-compatible mock server + parent config pointing at it.

    The parent process resolves the config (PY_CLAW_CONFIG_PATH) at
    send_init() time and hands the backend to the child via the init
    message, so the child's OpenAI path is exercised end-to-end.
    """
    server = _MockOpenAIServer()
    config_path = tmp_path / "openai-config.json"

    def write_config(**api_overrides) -> None:
        api = {
            "api_key": "mock-openai-key",
            "api_url": f"{server.base_url}/v1",
            "model": "mock-model",
            "temperature": 0.3,
            "top_p": 0.9,
        }
        api.update(api_overrides)
        config_path.write_text(json.dumps({"api": api}), encoding="utf-8")

    write_config()
    monkeypatch.setenv("PY_CLAW_CONFIG_PATH", str(config_path))
    # The OpenAI path must not lean on Anthropic env vars.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    yield types.SimpleNamespace(
        server=server,
        config_path=config_path,
        write_config=write_config,
    )
    server.stop()


class TestResolveForkModelConfig:
    """Parent-side mapping of the py-claw config onto the child's model_config."""

    def test_openai_config_maps_all_fields(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "api": {
                    "api_key": "k1",
                    "api_url": "http://10.0.0.1:8002/v1/chat/completions",
                    "model": "qwen3.8",
                    "temperature": 0.2,
                    "top_p": 0.8,
                    "timeout_seconds": 30,
                }
            }),
            encoding="utf-8",
        )
        monkeypatch.setenv("PY_CLAW_CONFIG_PATH", str(config_path))
        cfg = resolve_fork_model_config()
        assert cfg == {
            "backend": "openai",
            "api_key": "k1",
            "api_url": "http://10.0.0.1:8002/v1/chat/completions",
            "model": "qwen3.8",
            "temperature": 0.2,
            "top_p": 0.8,
            "timeout_seconds": 30,
        }

    def test_anthropic_config_strips_v1_suffix(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "api": {
                    "api_key": "k2",
                    "api_url": "https://api.example.com/v1",
                    "model": "claude-x",
                    "protocol": "anthropic",
                }
            }),
            encoding="utf-8",
        )
        monkeypatch.setenv("PY_CLAW_CONFIG_PATH", str(config_path))
        cfg = resolve_fork_model_config()
        assert cfg == {
            "backend": "anthropic",
            "api_key": "k2",
            "api_url": "https://api.example.com",
            "model": "claude-x",
        }

    def test_unconfigured_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PY_CLAW_CONFIG_PATH", str(tmp_path / "missing.json"))
        assert resolve_fork_model_config() is None

    def test_openai_without_url_returns_none(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"api": {"api_key": "k1"}}), encoding="utf-8")
        monkeypatch.setenv("PY_CLAW_CONFIG_PATH", str(config_path))
        assert resolve_fork_model_config() is None

    def test_openai_without_key_still_reports_openai_backend(self, tmp_path, monkeypatch):
        """URL present but no key: the child must learn the protocol is OpenAI
        so it degrades with OpenAI-specific guidance (not the Anthropic env
        fallback)."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"api": {"api_url": "http://10.0.0.1:8002/v1"}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("PY_CLAW_CONFIG_PATH", str(config_path))
        cfg = resolve_fork_model_config()
        assert cfg is not None
        assert cfg["backend"] == "openai"
        assert cfg["api_key"] == ""
        assert cfg["api_url"] == "http://10.0.0.1:8002/v1"


class TestPersistentOpenAIModel:
    """Persistent turns run over the parent-configured OpenAI-compatible backend.

    The parent resolves its py-claw config and passes the backend to the child
    via the init message; the child then speaks chat/completions (SSE) with
    the same request format as the main process's ApiQueryBackend.
    """

    def _spawn(self, **kwargs) -> ForkedAgentProcess:
        kwargs.setdefault("cwd", ".")
        process = ForkedAgentProcess(
            session_id="test-persistent-openai",
            system_prompt="You are a helpful test agent.",
            **kwargs,
        )
        process.spawn()
        process.send_init()
        return process

    def test_persistent_turn_openai_real_model_text(self, mock_openai):
        mock_openai.server.responses.append(_openai_text_response("OPENAI-TEXT"))
        process = self._spawn()
        try:
            result = process.send_turn_sync("Hello", turn_count=0, timeout=20.0)
        finally:
            process.terminate(timeout=5.0)

        assert result["assistant_text"] == "OPENAI-TEXT"
        assert "Placeholder" not in result["assistant_text"]
        assert result["stop_reason"] == "end_turn"
        assert result["usage"]["backendType"] == "fork-model-openai"
        assert result["usage"]["backendRequests"] == 1
        assert result["usage"]["inputTokens"] == 12
        assert result["usage"]["outputTokens"] == 5

        # Request format must match the main process's OpenAI backend:
        # system prompt as a role=system message (vLLM drops a top-level
        # "system" body field), streaming with usage, OpenAI function tools,
        # Bearer auth, and the parent config's sampling params.
        req = mock_openai.server.requests[0]
        assert "system" not in req
        assert req["messages"][0] == {"role": "system", "content": "You are a helpful test agent."}
        assert req["messages"][1] == {"role": "user", "content": "Hello"}
        assert req["model"] == "mock-model"
        assert req["stream"] is True
        assert req["stream_options"] == {"include_usage": True}
        assert req["temperature"] == 0.3
        assert req["top_p"] == 0.9
        assert {t["function"]["name"] for t in req["tools"]} >= {"Read", "Bash", "Write", "Edit", "Glob", "Grep"}
        assert all(t["type"] == "function" for t in req["tools"])
        assert mock_openai.server.request_headers[0].get("Authorization") == "Bearer mock-openai-key"

    def test_persistent_turn_openai_tool_loop(self, mock_openai, tmp_path):
        """OpenAI tool_calls are executed in the child and fed back as role=tool."""
        data_file = tmp_path / "data.txt"
        data_file.write_text("OPENAI-TOOL-OUTPUT-42", encoding="utf-8")
        mock_openai.server.responses.append(
            _openai_tool_calls_response([("call_1", "Read", {"path": str(data_file)})])
        )
        mock_openai.server.responses.append(_openai_text_response("OPENAI-TOOL-COMPLETE"))
        process = self._spawn(cwd=str(tmp_path))
        try:
            result = process.send_turn_sync(
                "Read the data file and summarize it", turn_count=0, timeout=30.0
            )
        finally:
            process.terminate(timeout=5.0)

        assert result["assistant_text"] == "OPENAI-TOOL-COMPLETE"
        assert result["usage"]["backendType"] == "fork-model-openai"
        assert result["usage"]["backendRequests"] == 2
        assert [tc["tool_name"] for tc in result["tool_calls"]] == ["Read"]
        assert result["tool_calls"][0]["arguments"]["path"] == str(data_file)

        # The tool result was fed back to the model as a role=tool message
        # paired with the assistant message's tool_calls.
        second_req = mock_openai.server.requests[1]
        assert "system" not in second_req
        tool_msg = second_req["messages"][-1]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_1"
        assert "OPENAI-TOOL-OUTPUT-42" in tool_msg["content"]
        assistant_msg = second_req["messages"][-2]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["tool_calls"][0]["id"] == "call_1"
        assert assistant_msg["tool_calls"][0]["function"]["name"] == "Read"

    def test_persistent_turn_openai_no_key_degrades(self, mock_openai):
        """OpenAI backend configured but no key: fast degradation, no HTTP call."""
        mock_openai.write_config(api_key="")
        process = self._spawn()
        try:
            result = process.send_turn_sync("Hello", turn_count=0, timeout=20.0)
            assert "No API key" in result["assistant_text"]
            assert "Placeholder Agent" not in result["assistant_text"]
            assert result["usage"]["backendType"] == "no_api_key"

            # The child stays alive and degrades on subsequent turns (no hang).
            result2 = process.send_turn_sync("Again", turn_count=1, timeout=20.0)
            assert "No API key" in result2["assistant_text"]
        finally:
            process.terminate(timeout=5.0)
        assert mock_openai.server.requests == []  # no HTTP call was made

    def test_persistent_turn_openai_api_error_degrades_and_recovers(self, mock_openai):
        mock_openai.server.fail_status = 500
        process = self._spawn()
        try:
            result = process.send_turn_sync("Hello", turn_count=0, timeout=30.0)
            assert "Model API error" in result["assistant_text"]
            assert "Placeholder Agent" not in result["assistant_text"]
            assert result["usage"]["backendType"] == "model_error"

            # Child survives the failed call and recovers on the next turn.
            mock_openai.server.fail_status = None
            mock_openai.server.responses.append(_openai_text_response("OPENAI-RECOVERED"))
            result2 = process.send_turn_sync("Hello again", turn_count=1, timeout=30.0)
            assert result2["assistant_text"] == "OPENAI-RECOVERED"
            assert result2["usage"]["backendType"] == "fork-model-openai"
        finally:
            process.terminate(timeout=5.0)

    def test_persistent_turn_explicit_model_config(self, mock_openai):
        """An explicit model_config field (no config file) drives the OpenAI path."""
        mock_openai.config_path.unlink()
        mock_openai.server.responses.append(_openai_text_response("EXPLICIT-CFG"))
        process = self._spawn(
            model_config={
                "backend": "openai",
                "api_key": "explicit-key",
                "api_url": f"{mock_openai.server.base_url}/v1",
                "model": "mock-model",
            }
        )
        try:
            result = process.send_turn_sync("Hello", turn_count=0, timeout=20.0)
        finally:
            process.terminate(timeout=5.0)

        assert result["assistant_text"] == "EXPLICIT-CFG"
        assert result["usage"]["backendType"] == "fork-model-openai"
        assert mock_openai.server.request_headers[0].get("Authorization") == "Bearer explicit-key"

    def test_anthropic_protocol_config_uses_anthropic_path(self, mock_anthropic, tmp_path, monkeypatch):
        """Parent config with protocol=anthropic routes the child to the
        existing Anthropic path (backendType fork-model) using config creds."""
        mock_anthropic.responses.append(_mock_text_response("ANTHROPIC-VIA-CONFIG"))
        config = {
            "api": {
                "api_key": "config-anthropic-key",
                "api_url": mock_anthropic.base_url + "/v1",
                "model": "mock-model",
                "protocol": "anthropic",
            }
        }
        config_path = tmp_path / "anthropic-config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.setenv("PY_CLAW_CONFIG_PATH", str(config_path))
        # Env must not be able to satisfy the child — only the config can.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("API_KEY", raising=False)

        process = self._spawn()
        try:
            result = process.send_turn_sync("Hello", turn_count=0, timeout=20.0)
        finally:
            process.terminate(timeout=5.0)

        assert result["assistant_text"] == "ANTHROPIC-VIA-CONFIG"
        assert result["usage"]["backendType"] == "fork-model"
