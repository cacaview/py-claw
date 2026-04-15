"""
Tests for heap dump service.
"""
from __future__ import annotations

import pytest

from py_claw.services.heap_dump.types import (
    HeapDumpConfig,
    HeapDumpResult,
    MemoryDiagnostics,
)


class TestHeapDumpConfig:
    """Tests for HeapDumpConfig."""

    def test_default_config(self) -> None:
        config = HeapDumpConfig()
        assert config.enabled
        assert config.dump_dir is None
        assert config.auto_dump_threshold_gb == 1.5


class TestHeapDumpResult:
    """Tests for HeapDumpResult."""

    def test_success_result(self) -> None:
        result = HeapDumpResult(success=True, heap_path="/path/to/dump.heapsnapshot")
        assert result.success
        assert result.heap_path == "/path/to/dump.heapsnapshot"

    def test_error_result(self) -> None:
        result = HeapDumpResult(success=False, error="Out of memory")
        assert not result.success
        assert result.error == "Out of memory"


class TestMemoryDiagnostics:
    """Tests for MemoryDiagnostics."""

    def test_diagnostics_creation(self) -> None:
        diag = MemoryDiagnostics(
            timestamp="2026-04-13T12:00:00",
            session_id="test-session",
            trigger="manual",
            dump_number=0,
            uptime_seconds=3600.0,
            memory_usage={"heap_used": 1000000, "rss": 50000000},
            platform="Linux",
            python_version="3.13.0",
        )
        assert diag.session_id == "test-session"
        assert diag.trigger == "manual"
        assert diag.dump_number == 0
