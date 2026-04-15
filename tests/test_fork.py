"""Tests for fork subprocess mechanism (AgentTool Phase 1)."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time

import pytest

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

    def test_child_process_handles_turn(self):
        """Child process handles init + turn and returns result."""
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

            result = next(m for m in all_messages if m.get("type") == "result")
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
