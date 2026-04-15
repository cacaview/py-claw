"""
Tests for VCR service.
"""
from __future__ import annotations

import pytest

from py_claw.services.vcr.types import (
    VCRConfig,
    Recording,
    get_vcr_config,
    should_use_vcr,
)
from py_claw.services.vcr.service import (
    with_fixture,
    with_vcr,
    _normalize_path,
    _deep_dehydrate,
    reset_vcr_for_testing,
)


class TestVCRConfig:
    """Tests for VCRConfig."""

    def test_default_config(self) -> None:
        config = VCRConfig()
        assert config.enabled is False
        assert config.fixtures_root is None
        assert config.record_mode is False
        assert config.force_record is False
        assert config.cwd_placeholder == "[CWD]"
        assert config.config_home_placeholder == "[CONFIG_HOME]"


class TestVCRTypes:
    """Tests for VCR types."""

    def test_recording_creation(self) -> None:
        recording = Recording(
            input_data={"key": "value"},
            output_data={"result": "ok"},
            recorded_at="2026-04-13T12:00:00Z",
        )
        assert recording.input_data == {"key": "value"}
        assert recording.output_data == {"result": "ok"}


class TestShouldUseVCR:
    """Tests for VCR mode detection."""

    def test_default_disabled(self) -> None:
        import os
        # Save original values
        orig_env = os.environ.get("PYTHON_ENV")
        orig_vcr = os.environ.get("VCR_ENABLED")

        try:
            # Clear test env vars
            os.environ.pop("PYTHON_ENV", None)
            os.environ.pop("VCR_ENABLED", None)
            reset_vcr_for_testing()

            # Should be disabled without env vars
            assert should_use_vcr() is False
        finally:
            # Restore
            if orig_env:
                os.environ["PYTHON_ENV"] = orig_env
            elif "PYTHON_ENV" in os.environ:
                del os.environ["PYTHON_ENV"]
            if orig_vcr:
                os.environ["VCR_ENABLED"] = orig_vcr
            elif "VCR_ENABLED" in os.environ:
                del os.environ["VCR_ENABLED"]


class TestNormalizePath:
    """Tests for path normalization."""

    def test_normalize_basic_path(self) -> None:
        result = _normalize_path("C:\\Users\\test\\file.txt")
        # Should normalize backslashes
        assert "\\" not in result or result.count("\\") == 0

    def test_normalize_timestamp(self) -> None:
        result = _normalize_path("2026-04-13T12:00:00Z")
        assert "[TIMESTAMP]" in result

    def test_normalize_uuid(self) -> None:
        result = _normalize_path("12345678-1234-1234-1234-123456789012")
        assert "[UUID]" in result


class TestDeepDehydrate:
    """Tests for deep dehydration."""

    def test_dehydrate_string(self) -> None:
        result = _deep_dehydrate("2026-04-13T12:00:00Z")
        assert result == "[TIMESTAMP]"

    def test_dehydrate_dict(self) -> None:
        result = _deep_dehydrate({"key": "2026-04-13T12:00:00Z", "value": 123})
        assert result["key"] == "[TIMESTAMP]"
        assert result["value"] == 123

    def test_dehydrate_nested(self) -> None:
        result = _deep_dehydrate({"outer": {"inner": "value"}})
        assert result == {"outer": {"inner": "value"}}


class TestWithFixture:
    """Tests for with_fixture."""

    def test_with_fixture_disabled(self) -> None:
        """When VCR is disabled, should call the function directly."""
        import os
        # Ensure VCR is disabled
        os.environ.pop("PYTHON_ENV", None)
        os.environ.pop("VCR_ENABLED", None)
        reset_vcr_for_testing()

        called = False

        async def my_func():
            nonlocal called
            called = True
            return "result"

        result = with_fixture({"input": "data"}, "test", my_func)
        # Should return coroutine when VCR is disabled
        import asyncio
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)

        assert called
        assert result == "result"
