"""Tests for agent tracing service."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from py_claw.services.agent.tracing import (
    PERFETTO_ENABLED_ENV,
    PerfettoTracingService,
    TraceSpan,
    _datetime_to_us,
    _get_trace_dir,
    _is_tracing_enabled,
    _write_trace_file,
)


class TestIsTracingEnabled:
    """Test tracing enablement check."""

    def test_disabled_by_default(self):
        # Ensure env is not set
        env_backup = os.environ.pop(PERFETTO_ENABLED_ENV, None)
        try:
            assert _is_tracing_enabled() is False
        finally:
            if env_backup is not None:
                os.environ[PERFETTO_ENABLED_ENV] = env_backup

    def test_enabled_with_true(self):
        with patch.dict(os.environ, {PERFETTO_ENABLED_ENV: "true"}):
            assert _is_tracing_enabled() is True

    def test_enabled_with_1(self):
        with patch.dict(os.environ, {PERFETTO_ENABLED_ENV: "1"}):
            assert _is_tracing_enabled() is True

    def test_enabled_with_yes(self):
        with patch.dict(os.environ, {PERFETTO_ENABLED_ENV: "yes"}):
            assert _is_tracing_enabled() is True

    def test_disabled_with_false(self):
        with patch.dict(os.environ, {PERFETTO_ENABLED_ENV: "false"}):
            assert _is_tracing_enabled() is False


class TestGetTraceDir:
    """Test trace directory resolution."""

    def test_default_trace_dir(self, tmp_path: Path):
        with patch.object(Path, "home", return_value=tmp_path):
            trace_dir = _get_trace_dir()
            assert trace_dir == tmp_path / ".claude" / "traces"

    def test_custom_trace_dir(self, tmp_path: Path):
        with patch.dict(os.environ, {"PY_CLAW_PERFETTO_TRACE_DIR": str(tmp_path / "custom")}):
            trace_dir = _get_trace_dir()
            assert trace_dir == tmp_path / "custom"


class TestDatetimeToUs:
    """Test datetime to microseconds conversion."""

    def test_convert(self):
        from datetime import datetime, timezone

        dt = datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc)
        us = _datetime_to_us(dt)
        # Verify it returns a positive integer (microseconds since epoch)
        assert isinstance(us, int)
        assert us > 0


class TestTraceSpan:
    """Test TraceSpan dataclass."""

    def test_trace_span_creation(self):
        span = TraceSpan(
            agent_id="agent-123",
            agent_type="Explore",
            parent_id="session-456",
        )
        assert span.agent_id == "agent-123"
        assert span.agent_type == "Explore"
        assert span.parent_id == "session-456"
        assert span.end_time is None

    def test_trace_span_with_metadata(self):
        span = TraceSpan(
            agent_id="agent-123",
            agent_type="Plan",
            parent_id="session-456",
            metadata={"turns": 5, "tools_used": ["Read", "Edit"]},
        )
        assert span.metadata["turns"] == 5
        assert span.metadata["tools_used"] == ["Read", "Edit"]

    def test_to_dict(self):
        span = TraceSpan(
            agent_id="agent-123",
            agent_type="Explore",
            parent_id="session-456",
        )
        d = span.to_dict()
        assert d["agent_id"] == "agent-123"
        assert d["agent_type"] == "Explore"
        assert d["parent_id"] == "session-456"
        assert "start_time" in d


class TestPerfettoTracingService:
    """Test PerfettoTracingService class."""

    def test_is_enabled_when_disabled(self):
        env_backup = os.environ.pop(PERFETTO_ENABLED_ENV, None)
        try:
            assert PerfettoTracingService.is_enabled() is False
        finally:
            if env_backup is not None:
                os.environ[PERFETTO_ENABLED_ENV] = env_backup

    def test_is_enabled_when_enabled(self):
        with patch.dict(os.environ, {PERFETTO_ENABLED_ENV: "true"}):
            assert PerfettoTracingService.is_enabled() is True

    def test_register_agent_disabled(self, tmp_path: Path):
        """When tracing is disabled, register_agent should not raise."""
        env_backup = os.environ.pop(PERFETTO_ENABLED_ENV, None)
        with patch.dict(os.environ, {PERFETTO_ENABLED_ENV: ""}):
            # Should not raise
            PerfettoTracingService.register_agent(
                agent_id="agent-123",
                agent_type="Explore",
                parent_id="session-456",
            )

    def test_register_agent_enabled(self, tmp_path: Path):
        """When tracing is enabled, register_agent should create trace file."""
        with patch.dict(os.environ, {
            PERFETTO_ENABLED_ENV: "true",
            "PY_CLAW_PERFETTO_TRACE_DIR": str(tmp_path / "traces"),
        }):
            PerfettoTracingService.register_agent(
                agent_id="agent-123",
                agent_type="Explore",
                parent_id="session-456",
            )

            # Check trace file was created
            trace_file = tmp_path / "traces" / "agent-123.json"
            assert trace_file.exists()

    def test_unregister_agent_disabled(self):
        """When tracing is disabled, unregister_agent should not raise."""
        env_backup = os.environ.pop(PERFETTO_ENABLED_ENV, None)
        try:
            with patch.dict(os.environ, {PERFETTO_ENABLED_ENV: ""}):
                PerfettoTracingService.unregister_agent("agent-123")
        finally:
            if env_backup is not None:
                os.environ[PERFETTO_ENABLED_ENV] = env_backup

    def test_update_metadata_disabled(self):
        """When tracing is disabled, update_metadata should not raise."""
        env_backup = os.environ.pop(PERFETTO_ENABLED_ENV, None)
        try:
            with patch.dict(os.environ, {PERFETTO_ENABLED_ENV: ""}):
                PerfettoTracingService.update_metadata(
                    "agent-123",
                    {"turns": 5},
                )
        finally:
            if env_backup is not None:
                os.environ[PERFETTO_ENABLED_ENV] = env_backup

    def test_get_active_traces(self):
        """get_active_traces returns list of active spans."""
        traces = PerfettoTracingService.get_active_traces()
        assert isinstance(traces, list)


class TestWriteTraceFile:
    """Test _write_trace_file function."""

    def test_write_trace_file(self, tmp_path: Path):
        span = TraceSpan(
            agent_id="agent-xyz",
            agent_type="Plan",
            parent_id="session-abc",
        )

        with patch("py_claw.services.agent.tracing._get_trace_dir", return_value=tmp_path / "traces"):
            _write_trace_file(span)

        trace_file = tmp_path / "traces" / "agent-xyz.json"
        assert trace_file.exists()

        import json
        data = json.loads(trace_file.read_text())
        assert "traceEvents" in data
        assert "metadata" in data
        assert data["metadata"]["agent_id"] == "agent-xyz"
        assert data["metadata"]["agent_type"] == "Plan"
