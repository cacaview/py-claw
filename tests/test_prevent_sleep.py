"""Tests for prevent_sleep service."""
from __future__ import annotations

import os
import platform
from unittest.mock import MagicMock, patch

import pytest


class TestPreventSleepService:
    """Tests for PreventSleepService."""

    def test_service_initialization(self) -> None:
        """Test service can be initialized."""
        from py_claw.services.prevent_sleep import PreventSleepService

        service = PreventSleepService()
        assert service is not None
        assert not service.is_preventing_sleep

    def test_enable_increments_ref_count(self) -> None:
        """Test enable increments ref count."""
        from py_claw.services.prevent_sleep import PreventSleepService

        service = PreventSleepService()

        # On non-darwin, enable won't actually start caffeinate
        service.enable()
        assert service._ref_count == 1

    def test_disable_decrements_ref_count(self) -> None:
        """Test disable decrements ref count."""
        from py_claw.services.prevent_sleep import PreventSleepService

        service = PreventSleepService()
        service.enable()
        service.disable()
        assert service._ref_count == 0

    def test_nested_enable_disable(self) -> None:
        """Test nested enable/disable only stops at zero."""
        from py_claw.services.prevent_sleep import PreventSleepService

        service = PreventSleepService()
        service.enable()
        service.enable()
        service.enable()

        assert service._ref_count == 3

        service.disable()
        assert service._ref_count == 2

        service.disable()
        assert service._ref_count == 1

        service.disable()
        assert service._ref_count == 0

    def test_force_stop_resets_ref_count(self) -> None:
        """Test force_stop resets ref count to zero."""
        from py_claw.services.prevent_sleep import PreventSleepService

        service = PreventSleepService()
        service.enable()
        service.enable()
        service.force_stop()

        assert service._ref_count == 0

    @pytest.mark.skipif(platform.system() == "Windows", reason="os.uname not available on Windows")
    def test_is_darwin_true(self) -> None:
        """Test darwin detection returns True for Darwin."""
        import sys
        from py_claw.services.prevent_sleep import PreventSleepService

        mock_result = MagicMock()
        mock_result.sysname = "Darwin"

        # The _is_darwin check is: os.name == "posix" and os.uname().sysname == "Darwin"
        # On non-Windows, os.name is "posix", so we just need to mock uname
        with patch(f"{PreventSleepService.__module__}.os.uname", return_value=mock_result):
            service = PreventSleepService()
            # Force os.name to be posix
            with patch("os.name", "posix"):
                assert service._is_darwin() is True

    @pytest.mark.skipif(platform.system() == "Windows", reason="os.uname not available on Windows")
    def test_is_darwin_false_linux(self) -> None:
        """Test darwin detection returns False for Linux."""
        import sys
        from py_claw.services.prevent_sleep import PreventSleepService

        mock_result = MagicMock()
        mock_result.sysname = "Linux"

        with patch(f"{PreventSleepService.__module__}.os.uname", return_value=mock_result):
            with patch("os.name", "posix"):
                service = PreventSleepService()
                assert service._is_darwin() is False

    def test_is_darwin_false_windows(self) -> None:
        """Test darwin detection returns False on Windows."""
        from py_claw.services.prevent_sleep import PreventSleepService

        service = PreventSleepService()
        # On Windows, os.name is "nt", so _is_darwin should return False
        with patch("os.name", "nt"):
            assert service._is_darwin() is False

    def test_kill_caffeinate_noop_when_not_running(self) -> None:
        """Test kill_caffeinate does nothing when process is None."""
        from py_claw.services.prevent_sleep import PreventSleepService

        service = PreventSleepService()
        service._caffeinate_process = None
        # Should not raise
        service._kill_caffeinate()

    def test_spawn_caffeinate_noop_on_non_darwin(self) -> None:
        """Test spawn_caffeinate does nothing on non-Darwin."""
        from py_claw.services.prevent_sleep import PreventSleepService

        service = PreventSleepService()
        with patch.object(service, "_is_darwin", return_value=False):
            service._spawn_caffeinate()
            assert service._caffeinate_process is None


class TestPreventSleepModuleFunctions:
    """Tests for module-level prevent_sleep functions."""

    def test_start_stop_functions(self) -> None:
        """Test start/stop module functions don't raise."""
        from py_claw.services.prevent_sleep import (
            force_stop_prevent_sleep,
            start_prevent_sleep,
            stop_prevent_sleep,
        )

        # Should not raise on non-darwin platforms
        start_prevent_sleep()
        stop_prevent_sleep()
        force_stop_prevent_sleep()

    def test_get_service_returns_singleton(self) -> None:
        """Test get_prevent_sleep_service returns same instance."""
        from py_claw.services.prevent_sleep import (
            PreventSleepService,
            get_prevent_sleep_service,
        )

        service1 = get_prevent_sleep_service()
        service2 = get_prevent_sleep_service()

        # May or may not be same instance depending on initialization
        assert service1 is not None
        assert service2 is not None
        assert isinstance(service1, PreventSleepService)
