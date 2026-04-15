"""Tests for notifier service."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


class TestNotificationChannel:
    """Tests for NotificationChannel enum."""

    def test_channel_values(self) -> None:
        """Test NotificationChannel enum has expected values."""
        from py_claw.services.notifier import NotificationChannel

        assert NotificationChannel.AUTO.value == "auto"
        assert NotificationChannel.ITERM2.value == "iterm2"
        assert NotificationChannel.ITERM2_WITH_BELL.value == "iterm2_with_bell"
        assert NotificationChannel.KITTY.value == "kitty"
        assert NotificationChannel.GHOSTTY.value == "ghostty"
        assert NotificationChannel.TERMINAL_BELL.value == "terminal_bell"
        assert NotificationChannel.NOTIFICATIONS_DISABLED.value == "notifications_disabled"


class TestNotificationOptions:
    """Tests for NotificationOptions."""

    def test_default_values(self) -> None:
        """Test NotificationOptions default values."""
        from py_claw.services.notifier import NotificationOptions

        opts = NotificationOptions(message="Test message")
        assert opts.message == "Test message"
        assert opts.title is None
        assert opts.notification_type == "general"

    def test_custom_values(self) -> None:
        """Test NotificationOptions with custom values."""
        from py_claw.services.notifier import NotificationOptions

        opts = NotificationOptions(
            message="Hello",
            title="My Title",
            notification_type="custom",
        )
        assert opts.message == "Hello"
        assert opts.title == "My Title"
        assert opts.notification_type == "custom"


class TestTerminalBackends:
    """Tests for terminal notification backends."""

    def test_iterm2_backend_send(self) -> None:
        """Test iTerm2 backend sends OSC sequence."""
        from py_claw.services.notifier import NotificationOptions
        from py_claw.services.notifier.terminals import ITerm2Backend

        backend = ITerm2Backend()
        opts = NotificationOptions(message="Test", title="Title")

        with patch.object(backend, "write") as mock_write:
            result = backend.send_notification(opts)
            assert result is True
            mock_write.assert_called_once()
            # Check OSC 9 sequence was written
            call_args = mock_write.call_args[0][0]
            assert "\x1b]9;0;" in call_args

    def test_kitty_backend_send(self) -> None:
        """Test Kitty backend sends OSC 99 sequence."""
        from py_claw.services.notifier import NotificationOptions
        from py_claw.services.notifier.terminals import KittyBackend

        backend = KittyBackend()
        opts = NotificationOptions(message="Test", title="Title")

        with patch.object(backend, "write") as mock_write:
            result = backend.send_notification(opts)
            assert result is True
            # All 3 sequences are written in a single call
            assert mock_write.call_count == 1
            call_args = mock_write.call_args[0][0]
            assert "Test" in call_args
            assert "Title" in call_args

    def test_ghostty_backend_send(self) -> None:
        """Test Ghostty backend sends OSC 777 sequence."""
        from py_claw.services.notifier import NotificationOptions
        from py_claw.services.notifier.terminals import GhosttyBackend

        backend = GhosttyBackend()
        opts = NotificationOptions(message="Test", title="Title")

        with patch.object(backend, "write") as mock_write:
            result = backend.send_notification(opts)
            assert result is True
            mock_write.assert_called_once()
            call_args = mock_write.call_args[0][0]
            assert "\x1b]777;notify;Title;Test" in call_args

    def test_bell_backend_send(self) -> None:
        """Test bell backend sends BEL character."""
        from py_claw.services.notifier import NotificationOptions
        from py_claw.services.notifier.terminals import BellBackend

        backend = BellBackend()
        opts = NotificationOptions(message="Test")

        with patch.object(backend, "write") as mock_write:
            result = backend.send_notification(opts)
            assert result is True
            mock_write.assert_called_once_with("\x07")


class TestNotifierService:
    """Tests for NotifierService."""

    @pytest.mark.asyncio
    async def test_send_notification(self) -> None:
        """Test send_notification sends to correct channel."""
        from py_claw.services.notifier import NotificationOptions, send_notification

        opts = NotificationOptions(message="Test message")

        with patch("py_claw.services.notifier.service._execute_notification_hooks"):
            with patch("py_claw.services.notifier.service._send_to_channel") as mock_send:
                mock_send.return_value = "terminal_bell"
                result = await send_notification(opts)
                assert result is True
                mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_disabled(self) -> None:
        """Test send_notification returns False when disabled."""
        from py_claw.services.notifier import NotificationOptions
        from py_claw.services.notifier.service import _get_configured_channel

        with patch("py_claw.services.notifier.service._get_configured_channel", return_value="notifications_disabled"):
            from py_claw.services.notifier import send_notification

            opts = NotificationOptions(message="Test")
            result = await send_notification(opts)
            assert result is False


class TestSendToChannel:
    """Tests for _send_to_channel function."""

    @pytest.mark.asyncio
    async def test_auto_channel_routes_correctly(self) -> None:
        """Test auto channel uses _send_auto."""
        from py_claw.services.notifier import NotificationOptions
        from py_claw.services.notifier.service import _send_to_channel

        opts = NotificationOptions(message="Test")

        with patch("py_claw.services.notifier.service._send_auto") as mock_auto:
            mock_auto.return_value = "iterm2"
            result = await _send_to_channel("auto", opts, "iTerm.app")
            assert result == "iterm2"
            mock_auto.assert_called_once()

    @pytest.mark.asyncio
    async def test_iterm2_channel(self) -> None:
        """Test explicit iTerm2 channel."""
        from py_claw.services.notifier import NotificationOptions
        from py_claw.services.notifier.service import _send_to_channel

        opts = NotificationOptions(message="Test")

        with patch("py_claw.services.notifier.terminals.ITerm2Backend") as mock:
            mock.return_value.send_notification.return_value = True
            result = await _send_to_channel("iterm2", opts, "iTerm.app")
            assert result == "iterm2"


class TestDetectTerminal:
    """Tests for terminal detection."""

    def test_detect_iterm2(self) -> None:
        """Test detection of iTerm2."""
        from py_claw.services.notifier.service import _detect_terminal

        with patch.dict(os.environ, {"TERM_PROGRAM": "iTerm.app"}):
            result = _detect_terminal()
            assert result == "iTerm.app"

    def test_detect_kitty(self) -> None:
        """Test detection of Kitty."""
        from py_claw.services.notifier.service import _detect_terminal

        with patch.dict(os.environ, {"TERM": "xterm-kitty"}):
            result = _detect_terminal()
            assert result == "kitty"

    def test_detect_ghostty(self) -> None:
        """Test detection of Ghostty."""
        from py_claw.services.notifier.service import _detect_terminal

        with patch.dict(os.environ, {"TERM": "xterm-ghostty"}):
            result = _detect_terminal()
            assert "ghostty" in result.lower()


class TestNotifierModuleFunctions:
    """Tests for module-level notifier functions."""

    @pytest.mark.asyncio
    async def test_notify_function(self) -> None:
        """Test notify module function."""
        from unittest.mock import AsyncMock

        from py_claw.services.notifier import notify

        with patch("py_claw.services.notifier.service.get_notifier_service") as mock_get:
            mock_service = MagicMock()
            # send() is async, so use AsyncMock
            mock_service.send = AsyncMock(return_value=True)
            mock_get.return_value = mock_service

            result = await notify("Test message", "Test Title")
            assert result is True
            mock_service.send.assert_called_once()

    def test_get_notifier_service_returns_singleton(self) -> None:
        """Test get_notifier_service returns singleton."""
        from py_claw.services.notifier import (
            NotifierService,
            get_notifier_service,
        )

        service = get_notifier_service()
        assert isinstance(service, NotifierService)
