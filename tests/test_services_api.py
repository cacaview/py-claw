"""Tests for services/api module - error logging utilities.

These tests cover the error logging functionality from
ClaudeCode-main/src/utils/api.ts.
"""

from __future__ import annotations

import pytest

from py_claw.services.api.api import (
    ErrorInfo,
    ErrorLogSink,
    LogOption,
    _add_to_in_memory_error_log,
    _in_memory_error_log,
    _queue,
    _to_error,
    _is_env_truthy,
    attach_error_log_sink,
    date_to_filename,
    get_in_memory_errors,
    get_log_display_title,
    log_error,
    log_mcp_error,
    log_mcp_debug,
    reset_error_log_for_testing,
)


class TestErrorConversion:
    """Tests for error conversion utilities."""

    def test_to_error_from_exception(self):
        """Test converting Exception to Exception."""
        exc = ValueError("test error")
        result = _to_error(exc)
        assert isinstance(result, Exception)
        assert str(result) == "test error"

    def test_to_error_from_string(self):
        """Test converting string to Exception."""
        result = _to_error("string error")
        assert isinstance(result, Exception)
        assert str(result) == "string error"

    def test_to_error_from_dict(self):
        """Test converting dict to Exception."""
        result = _to_error({"error": "test"})
        assert isinstance(result, Exception)
        assert str(result) == "{'error': 'test'}"


class TestEnvTruthy:
    """Tests for environment truthy checking."""

    def test_is_env_truthy_truthy_values(self):
        """Test that 1 and true are truthy."""
        assert _is_env_truthy("1") is True
        assert _is_env_truthy("true") is True
        assert _is_env_truthy("yes") is True
        assert _is_env_truthy("TRUE") is True

    def test_is_env_truthy_falsy_values(self):
        """Test that 0 and false are falsy."""
        assert _is_env_truthy("0") is False
        assert _is_env_truthy("false") is False
        assert _is_env_truthy("no") is False

    def test_is_env_truthy_none(self):
        """Test that None is falsy."""
        assert _is_env_truthy(None) is False


class TestDateToFilename:
    """Tests for date to filename conversion."""

    def test_date_to_filename_basic(self):
        """Test basic date to filename conversion."""
        from datetime import datetime, timezone

        date = datetime(2024, 1, 15, 10, 30, 0, 0, tzinfo=timezone.utc)
        result = date_to_filename(date)
        assert "2024-01-15" in result
        assert ":" not in result
        assert "." not in result


class TestInMemoryErrorLog:
    """Tests for in-memory error log."""

    def setup_method(self):
        """Reset error log before each test."""
        reset_error_log_for_testing()

    def test_add_to_in_memory_error_log(self):
        """Test adding error to in-memory log."""
        error_info = ErrorInfo(error="test error", timestamp="2024-01-15T10:00:00Z")
        _add_to_in_memory_error_log(error_info)

        errors = get_in_memory_errors()
        assert len(errors) == 1
        assert errors[0].error == "test error"

    def test_in_memory_error_log_bounded(self):
        """Test that in-memory log is bounded to 100 errors."""
        from py_claw.services.api.api import MAX_IN_MEMORY_ERRORS

        # Add more than MAX errors
        for i in range(MAX_IN_MEMORY_ERRORS + 10):
            _add_to_in_memory_error_log(
                ErrorInfo(error=f"error {i}", timestamp="2024-01-15T10:00:00Z")
            )

        errors = get_in_memory_errors()
        assert len(errors) == MAX_IN_MEMORY_ERRORS
        # First errors should be removed
        assert errors[0].error == "error 10"

    def test_get_in_memory_errors_returns_copy(self):
        """Test that get_in_memory_errors returns a copy."""
        error_info = ErrorInfo(error="test", timestamp="2024-01-15T10:00:00Z")
        _add_to_in_memory_error_log(error_info)

        errors1 = get_in_memory_errors()
        errors1.clear()

        errors2 = get_in_memory_errors()
        assert len(errors2) == 1


class TestLogError:
    """Tests for log_error function."""

    def setup_method(self):
        """Reset error log before each test."""
        import os

        # Ensure error reporting is enabled for these tests
        os.environ.pop("DISABLE_ERROR_REPORTING", None)
        reset_error_log_for_testing()

    def test_log_error_with_exception(self):
        """Test logging an Exception."""
        log_error(ValueError("test error"))
        errors = get_in_memory_errors()
        assert len(errors) == 1
        assert "test error" in errors[0].error

    def test_log_error_with_string(self):
        """Test logging a string."""
        log_error("string error")
        errors = get_in_memory_errors()
        assert len(errors) == 1
        assert "string error" in errors[0].error

    def test_log_error_queued_when_no_sink(self):
        """Test that errors are queued when no sink is attached."""
        log_error(ValueError("queued error"))
        assert len(_queue) == 1
        assert _queue[0]["type"] == "error"


class TestErrorLogSink:
    """Tests for ErrorLogSink functionality."""

    def setup_method(self):
        """Reset error log before each test."""
        import os

        # Ensure error reporting is enabled for these tests
        os.environ.pop("DISABLE_ERROR_REPORTING", None)
        reset_error_log_for_testing()

    def test_attach_error_log_sink_idempotent(self):
        """Test that attaching sink is idempotent."""
        sink_calls = []

        def mock_log_error(err):
            sink_calls.append(err)

        sink1 = ErrorLogSink(
            log_error=mock_log_error,
            log_mcp_error=lambda *args: None,
            log_mcp_debug=lambda *args: None,
            get_errors_path=lambda: "",
            get_mcp_logs_path=lambda *args: "",
        )

        attach_error_log_sink(sink1)
        attach_error_log_sink(sink1)  # Second call should be no-op

        log_error(ValueError("test"))
        assert len(sink_calls) == 1

    def test_sink_receives_queued_errors(self):
        """Test that sink receives queued errors on attach."""
        sink_calls = []

        def mock_log_error(err):
            sink_calls.append(err)

        sink = ErrorLogSink(
            log_error=mock_log_error,
            log_mcp_error=lambda *args: None,
            log_mcp_debug=lambda *args: None,
            get_errors_path=lambda: "",
            get_mcp_logs_path=lambda *args: "",
        )

        # Queue an error before attaching sink
        log_error(ValueError("queued"))

        # Attach sink
        attach_error_log_sink(sink)

        # Queued error should be delivered
        assert len(sink_calls) == 1
        assert "queued" in str(sink_calls[0])


class TestLogMCPError:
    """Tests for log_mcp_error function."""

    def setup_method(self):
        """Reset error log before each test."""
        reset_error_log_for_testing()

    def test_log_mcp_error_queued_when_no_sink(self):
        """Test that MCP errors are queued when no sink."""
        log_mcp_error("test-server", ValueError("mcp error"))
        assert len(_queue) == 1
        assert _queue[0]["type"] == "mcpError"
        assert _queue[0]["serverName"] == "test-server"


class TestLogMCPDebug:
    """Tests for log_mcp_debug function."""

    def setup_method(self):
        """Reset error log before each test."""
        reset_error_log_for_testing()

    def test_log_mcp_debug_queued_when_no_sink(self):
        """Test that MCP debug messages are queued when no sink."""
        log_mcp_debug("test-server", "debug message")
        assert len(_queue) == 1
        assert _queue[0]["type"] == "mcpDebug"
        assert _queue[0]["serverName"] == "test-server"
        assert _queue[0]["message"] == "debug message"


class TestGetLogDisplayTitle:
    """Tests for get_log_display_title function."""

    def test_agent_name_priority(self):
        """Test that agent_name takes priority."""
        log = LogOption(date="2024-01-15")
        log.agent_name = "My Agent"
        log.custom_title = "Custom"
        log.summary = "Summary"

        title = get_log_display_title(log)
        assert title == "My Agent"

    def test_custom_title_priority(self):
        """Test that custom_title is used when no agent_name."""
        log = LogOption(date="2024-01-15")
        log.custom_title = "Custom Title"
        log.summary = "Summary"

        title = get_log_display_title(log)
        assert title == "Custom Title"

    def test_summary_fallback(self):
        """Test that summary is used when no agent/custom title."""
        log = LogOption(date="2024-01-15")
        log.summary = "Session Summary"

        title = get_log_display_title(log)
        assert title == "Session Summary"

    def test_session_id_fallback(self):
        """Test that session_id is used as last resort."""
        log = LogOption(date="2024-01-15")
        log.session_id = "abc12345def"

        title = get_log_display_title(log)
        assert "abc12345" in title

    def test_default_title_fallback(self):
        """Test default_title is used when no other title."""
        log = LogOption(date="2024-01-15")

        title = get_log_display_title(log, default_title="Default")
        assert title == "Default"

    def test_autonomous_session_label(self):
        """Test Autonomous session label for tick-tagged prompts."""
        log = LogOption(date="2024-01-15")
        log.first_prompt = "<tick>Goal: do something</tick>"

        title = get_log_display_title(log)
        assert title == "Autonomous session"


class TestResetErrorLogForTesting:
    """Tests for reset_error_log_for_testing function."""

    def setup_method(self):
        """Reset error log before each test."""
        import os

        # Ensure error reporting is enabled for these tests
        os.environ.pop("DISABLE_ERROR_REPORTING", None)
        reset_error_log_for_testing()

    def test_reset_clears_state(self):
        """Test that reset clears all state."""
        # Add some errors
        log_error(ValueError("error 1"))
        log_mcp_error("server", ValueError("mcp error"))

        assert len(_in_memory_error_log) == 1
        assert len(_queue) == 2

        # Reset
        reset_error_log_for_testing()

        assert len(_in_memory_error_log) == 0
        assert len(_queue) == 0
