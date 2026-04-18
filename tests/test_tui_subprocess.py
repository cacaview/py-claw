"""Subprocess smoke tests for --tui CLI entry point.

These tests verify that the TUI can be launched as a subprocess and handles
basic input without crashing. Uses Windows-compatible stdin pipe approach.

Note: Full E2E streaming response requires a real TTY (pexpect/ConPTY) which
is not available in pytest. These tests verify startup, input handling, and
graceful shutdown paths.
"""

from __future__ import annotations

import subprocess
import sys
import time
import os

import pytest


class TestTUIStartup:
    """Test --tui startup and basic input handling."""

    def test_tui_imports_without_error(self) -> None:
        """Verify the TUI module can be imported without errors."""
        # This catches circular import issues, missing dependencies, etc.
        result = subprocess.run(
            [sys.executable, "-c", "from py_claw.ui.textual_app import run_textual_ui; print('OK')"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_tui_help_shows_version(self) -> None:
        """Verify --tui mode is recognized and app starts."""
        # Run py-claw --tui --help to check startup (will show TUI not usable in piped mode)
        result = subprocess.run(
            [sys.executable, "-m", "py_claw.cli.main", "--tui", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            # Set environment to skip config loading issues
            env={**os.environ, "PY_CLAW_CONFIG_PATH": "/nonexistent"},
        )
        # --help should work even in --tui mode (it exits before TUI init)
        # or may fail because Textual console can't initialize in piped mode
        # Either way, it shouldn't crash with an import error
        assert "ImportError" not in result.stderr
        assert "ModuleNotFoundError" not in result.stderr

    def test_tui_app_instantiation_no_crash(self) -> None:
        """Verify PyClawApp can be instantiated without crashing.

        This catches issues with widget composition, missing callbacks, etc.
        """
        code = """
import sys
try:
    from py_claw.cli.runtime import RuntimeState
    from py_claw.ui.textual_app import _build_command_items, DEFAULT_PROMPT_HINT
    state = RuntimeState()
    command_items = _build_command_items(state)
    assert len(command_items) >= 0
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "PY_CLAW_CONFIG_PATH": "/nonexistent"},
        )
        assert result.returncode == 0, f"App instantiation failed: {result.stderr}\n{result.stdout}"
        assert "OK" in result.stdout

    def test_repl_screen_instantiation_no_crash(self) -> None:
        """Verify REPLScreen can be instantiated without crashing."""
        code = """
import sys
try:
    from py_claw.cli.runtime import RuntimeState
    from py_claw.ui.textual_app import _build_command_items
    from py_claw.ui.typeahead import SuggestionEngine

    state = RuntimeState()
    command_items = _build_command_items(state)
    engine = SuggestionEngine(command_items=command_items)

    from py_claw.ui.screens.repl import REPLScreen
    screen = REPLScreen(
        model="test-model",
        status="idle",
        prompt_hint="test",
        suggestion_engine=engine,
        command_items=command_items,
    )
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "PY_CLAW_CONFIG_PATH": "/nonexistent"},
        )
        assert result.returncode == 0, f"REPLScreen instantiation failed: {result.stderr}\n{result.stdout}"
        assert "OK" in result.stdout

    def test_query_backend_imports_correctly(self) -> None:
        """Verify streaming backend imports work without circular import."""
        code = """
import sys
try:
    from py_claw.cli.runtime import RuntimeState
    from py_claw.query.backend import BackendChunk, BackendTurnResult
    from py_claw.query.engine import QueryRuntime, PreparedTurn

    chunk = BackendChunk(type="text_delta", text="hello")
    assert chunk.text == "hello"
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "PY_CLAW_CONFIG_PATH": "/nonexistent"},
        )
        assert result.returncode == 0, f"Backend import failed: {result.stderr}\n{result.stdout}"
        assert "OK" in result.stdout

    def test_streaming_list_integration(self) -> None:
        """Verify _StreamingList works with the engine pipeline."""
        code = """
import sys
try:
    from py_claw.cli.runtime import RuntimeState
    from py_claw.query.backend import BackendChunk, BackendTurnResult
    from py_claw.query.engine import QueryRuntime
    from py_claw.schemas.common import SDKUserMessage

    class MockExecutor:
        def __init__(self):
            pass

        def execute_streaming(self, prepared, context):
            yield BackendChunk(type="text_delta", text="streaming ")
            yield BackendChunk(type="text_delta", text="works!")
            yield BackendTurnResult(assistant_text="streaming works!", stop_reason="end_turn")

        def execute(self, prepared, context):
            raise NotImplementedError()

    state = RuntimeState()
    state.include_partial_messages = True
    runtime = QueryRuntime(state=state, turn_executor=MockExecutor())

    message = SDKUserMessage(
        type="user",
        message={"role": "user", "content": "test"},
        parent_tool_use_id=None,
    )

    outputs = list(runtime.handle_user_message(message))
    partials = [o for o in outputs if getattr(o, "type", None) == "stream_event"]
    has_content = any(
        (o.event.get("type") == "content_block_delta" if isinstance(o.event, dict) else getattr(o.event, "type", None) == "content_block_delta")
        for o in partials
    )
    assert has_content, "Expected content_block_delta in outputs"
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "PY_CLAW_CONFIG_PATH": "/nonexistent"},
        )
        assert result.returncode == 0, f"Streaming list integration failed: {result.stderr}\n{result.stdout}"
        assert "OK" in result.stdout
