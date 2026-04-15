"""Tests for services/debug module.

This module re-exports from services/log, so tests verify the re-export works.
"""

from __future__ import annotations

import pytest

from py_claw.services.debug.debug import (
    DebugLogLevel,
    enable_debug_logging,
    flush_debug_logs,
    get_debug_file_path,
    get_debug_filter,
    get_debug_log_path,
    get_has_formatted_output,
    get_min_debug_log_level,
    is_debug_mode,
    is_debug_to_stderr,
    log_ant_error,
    log_for_debugging,
    set_has_formatted_output,
    should_log_debug_message,
)


class TestReExports:
    """Tests that debug module re-exports correctly from log."""

    def test_debug_log_level_available(self):
        """Test DebugLogLevel is available."""
        assert DebugLogLevel is not None
        assert hasattr(DebugLogLevel, "DEBUG")

    def test_functions_available(self):
        """Test all functions are available."""
        assert callable(enable_debug_logging)
        assert callable(flush_debug_logs)
        assert callable(get_debug_file_path)
        assert callable(get_debug_filter)
        assert callable(get_debug_log_path)
        assert callable(get_has_formatted_output)
        assert callable(get_min_debug_log_level)
        assert callable(is_debug_mode)
        assert callable(is_debug_to_stderr)
        assert callable(log_ant_error)
        assert callable(log_for_debugging)
        assert callable(set_has_formatted_output)
        assert callable(should_log_debug_message)
