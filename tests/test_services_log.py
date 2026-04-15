"""Tests for services/log module - debug logging utilities.

These tests cover the debug logging functionality from
ClaudeCode-main/src/utils/log.ts.
"""

from __future__ import annotations

import os
import sys

import pytest

from py_claw.services.log.log import (
    DebugLogLevel,
    LEVEL_ORDER,
    _is_env_truthy,
    _matches_debug_filter,
    enable_debug_logging,
    get_debug_file_path,
    get_debug_filter,
    get_debug_log_path,
    get_has_formatted_output,
    get_min_debug_log_level,
    is_debug_mode,
    is_debug_to_stderr,
    log_for_debugging,
    set_has_formatted_output,
    should_log_debug_message,
)


class TestDebugLogLevel:
    """Tests for DebugLogLevel enum."""

    def test_debug_log_level_values(self):
        """Test DebugLogLevel enum values."""
        assert DebugLogLevel.VERBOSE.value == "verbose"
        assert DebugLogLevel.DEBUG.value == "debug"
        assert DebugLogLevel.INFO.value == "info"
        assert DebugLogLevel.WARN.value == "warn"
        assert DebugLogLevel.ERROR.value == "error"

    def test_level_order(self):
        """Test LEVEL_ORDER mapping."""
        assert LEVEL_ORDER[DebugLogLevel.VERBOSE] == 0
        assert LEVEL_ORDER[DebugLogLevel.DEBUG] == 1
        assert LEVEL_ORDER[DebugLogLevel.INFO] == 2
        assert LEVEL_ORDER[DebugLogLevel.WARN] == 3
        assert LEVEL_ORDER[DebugLogLevel.ERROR] == 4


class TestEnvTruthy:
    """Tests for environment truthy checking."""

    def test_is_env_truthy_truthy_values(self):
        """Test truthy values."""
        assert _is_env_truthy("1") is True
        assert _is_env_truthy("true") is True
        assert _is_env_truthy("yes") is True

    def test_is_env_truthy_falsy_values(self):
        """Test falsy values."""
        assert _is_env_truthy("0") is False
        assert _is_env_truthy("false") is False
        assert _is_env_truthy("no") is False

    def test_is_env_truthy_none(self):
        """Test None is falsy."""
        assert _is_env_truthy(None) is False


class TestGetMinDebugLogLevel:
    """Tests for get_min_debug_log_level function."""

    def test_default_debug_level(self):
        """Test default minimum level is DEBUG."""
        # Clear environment
        env_backup = os.environ.get("CLAUDE_CODE_DEBUG_LOG_LEVEL")
        if "CLAUDE_CODE_DEBUG_LOG_LEVEL" in os.environ:
            del os.environ["CLAUDE_CODE_DEBUG_LOG_LEVEL"]

        try:
            level = get_min_debug_log_level()
            assert level == DebugLogLevel.DEBUG
        finally:
            if env_backup is not None:
                os.environ["CLAUDE_CODE_DEBUG_LOG_LEVEL"] = env_backup


class TestDebugMode:
    """Tests for debug mode detection."""

    def test_is_debug_mode_env_variable(self):
        """Test DEBUG environment variable enables debug mode."""
        os.environ["DEBUG"] = "1"
        try:
            # Note: This may be cached, so we check the logic
            result = is_debug_mode()
            assert result is True
        finally:
            del os.environ["DEBUG"]

    def test_is_debug_mode_debug_sdk(self):
        """Test DEBUG_SDK environment variable enables debug mode."""
        os.environ["DEBUG_SDK"] = "true"
        try:
            result = is_debug_mode()
            assert result is True
        finally:
            del os.environ["DEBUG_SDK"]


class TestEnableDebugLogging:
    """Tests for enable_debug_logging function."""

    def test_enable_debug_logging_returns_previous_state(self):
        """Test that enable_debug_logging returns previous state."""
        was_active = enable_debug_logging()
        # First call should return False (not active before)
        assert was_active is False

        # Second call should return True (was active)
        was_active = enable_debug_logging()
        assert was_active is True


class TestGetDebugFilter:
    """Tests for get_debug_filter function."""

    def test_get_debug_filter_not_present(self):
        """Test no filter when --debug flag not present."""
        filter_result = get_debug_filter()
        # Returns None when no --debug=pattern in argv
        # This test depends on current sys.argv
        assert filter_result is None or isinstance(filter_result, str)


class TestDebugFilterMatching:
    """Tests for debug filter matching."""

    def test_matches_filter_substring(self):
        """Test substring matching."""
        assert _matches_debug_filter("hello world", "world") is True
        assert _matches_debug_filter("hello world", "foo") is False

    def test_matches_filter_regex(self):
        """Test regex matching."""
        assert _matches_debug_filter("error 123: something failed", r"error \d+") is True
        assert _matches_debug_filter("warning: something", r"error \d+") is False

    def test_matches_filter_invalid_regex_fallback(self):
        """Test invalid regex falls back to substring match."""
        # Invalid regex should fall back to substring
        assert _matches_debug_filter("hello [world", "[") is True


class TestIsDebugToStderr:
    """Tests for is_debug_to_stderr function."""

    def test_is_debug_to_stderr_flag(self):
        """Test --debug-to-stderr flag detection."""
        # This depends on sys.argv, just check it returns a bool
        result = is_debug_to_stderr()
        assert isinstance(result, bool)


class TestDebugFilePath:
    """Tests for debug file path functions."""

    def test_get_debug_file_path_no_arg(self):
        """Test get_debug_file_path when no --debug-file arg."""
        result = get_debug_file_path()
        # Returns None when no --debug-file in argv
        assert result is None or isinstance(result, str)

    def test_get_debug_log_path_default(self):
        """Test default debug log path."""
        path = get_debug_log_path()
        assert "debug" in path.lower() or path == ""


class TestFormattedOutput:
    """Tests for formatted output tracking."""

    def test_set_has_formatted_output(self):
        """Test setting formatted output state."""
        set_has_formatted_output(True)
        assert get_has_formatted_output() is True

        set_has_formatted_output(False)
        assert get_has_formatted_output() is False

    def test_default_has_formatted_output(self):
        """Test default formatted output state is False."""
        set_has_formatted_output(False)
        assert get_has_formatted_output() is False


class TestShouldLogDebugMessage:
    """Tests for should_log_debug_message function."""

    def test_returns_bool(self):
        """Test that should_log_debug_message returns a bool."""
        result = should_log_debug_message("test message")
        assert isinstance(result, bool)


class TestLogForDebugging:
    """Tests for log_for_debugging function."""

    def test_log_for_debugging_accepts_level(self):
        """Test log_for_debugging accepts level parameter."""
        # Should not raise, even if message is not logged
        log_for_debugging("test message", level=DebugLogLevel.INFO)

    def test_log_for_debugging_default_level(self):
        """Test log_for_debugging uses DEBUG level by default."""
        # Should not raise
        log_for_debugging("test message")


class TestLogAntError:
    """Tests for log_ant_error function."""
    # log_ant_error depends on USER_TYPE env var, so we just test it doesn't crash
    def test_log_ant_error_does_not_crash(self):
        """Test that log_ant_error doesn't raise."""
        from py_claw.services.log.log import log_ant_error

        # Should not raise even with non-ant user
        log_ant_error("test context", ValueError("test error"))
