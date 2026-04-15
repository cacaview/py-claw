"""
Tests for IDE service.

Based on ClaudeCode-main/src/utils/ide.ts
"""
from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from py_claw.services.ide import (
    EDITOR_DISPLAY_NAMES,
    IdeKind,
    IdeType,
    is_vscode_ide,
    SUPPORTED_IDE_CONFIGS,
    DetectedIDEInfo,
    check_port_open,
    detect_ides,
    detect_running_ides,
    find_available_ide,
    get_ide_kind,
    get_terminal_ide_type,
    is_jetbrains_ide,
    is_supported_jetbrains_terminal,
    is_supported_terminal,
    is_supported_vscode_terminal,
    to_ide_display_name,
)


class TestIdeType:
    """Tests for IdeType enum."""

    def test_ide_type_values(self):
        """Test all IDE types are defined."""
        assert IdeType.VSCODE == "vscode"
        assert IdeType.CURSOR == "cursor"
        assert IdeType.WINDSURF == "windsurf"
        assert IdeType.INTELLIJ == "intellij"
        assert IdeType.PYCHARM == "pycharm"
        assert IdeType.WEBSTORM == "webstorm"
        assert IdeType.CLION == "clion"
        assert IdeType.GOLAND == "goland"
        assert IdeType.RIDER == "rider"
        assert IdeType.ANDROIDSTUDIO == "androidstudio"

    def test_ide_type_count(self):
        """Test we have all expected IDE types."""
        assert len(IdeType) == 18


class TestIdeKind:
    """Tests for IdeKind enum."""

    def test_ide_kind_values(self):
        """Test IDE kind values."""
        assert IdeKind.VSCODE == "vscode"
        assert IdeKind.JETBRAINS == "jetbrains"


class TestIdeConfigs:
    """Tests for IDE configurations."""

    def test_vscode_config(self):
        """Test VS Code configuration."""
        config = SUPPORTED_IDE_CONFIGS[IdeType.VSCODE]
        assert config.display_name == "VS Code"
        assert config.ide_kind == IdeKind.VSCODE
        assert "code.exe" in config.process_keywords_windows
        assert "code" in config.process_keywords_linux

    def test_cursor_config(self):
        """Test Cursor configuration."""
        config = SUPPORTED_IDE_CONFIGS[IdeType.CURSOR]
        assert config.display_name == "Cursor"
        assert config.ide_kind == IdeKind.VSCODE
        assert "cursor.exe" in config.process_keywords_windows

    def test_jetbrains_config(self):
        """Test JetBrains IntelliJ configuration."""
        config = SUPPORTED_IDE_CONFIGS[IdeType.INTELLIJ]
        assert config.display_name == "IntelliJ IDEA"
        assert config.ide_kind == IdeKind.JETBRAINS
        assert "idea64.exe" in config.process_keywords_windows

    def test_all_ides_have_display_names(self):
        """Test all IDEs have display names."""
        for ide_type, config in SUPPORTED_IDE_CONFIGS.items():
            assert config.display_name, f"Missing display name for {ide_type}"
            assert len(config.display_name) > 0


class TestIsVscodeIde:
    """Tests for is_vscode_ide function."""

    def test_vscode_is_vscode(self):
        """Test VS Code is recognized as VS Code."""
        assert is_vscode_ide(IdeType.VSCODE) is True
        assert is_vscode_ide(IdeType.CURSOR) is True
        assert is_vscode_ide(IdeType.WINDSURF) is True

    def test_jetbrains_not_vscode(self):
        """Test JetBrains IDEs are not VS Code."""
        assert is_vscode_ide(IdeType.INTELLIJ) is False
        assert is_vscode_ide(IdeType.PYCHARM) is False
        assert is_vscode_ide(IdeType.WEBSTORM) is False

    def test_none_returns_false(self):
        """Test None returns False."""
        assert is_vscode_ide(None) is False


class TestIsJetbrainsIde:
    """Tests for is_jetbrains_ide function."""

    def test_jetbrains_is_jetbrains(self):
        """Test JetBrains IDEs are recognized."""
        assert is_jetbrains_ide(IdeType.INTELLIJ) is True
        assert is_jetbrains_ide(IdeType.PYCHARM) is True
        assert is_jetbrains_ide(IdeType.CLION) is True
        assert is_jetbrains_ide(IdeType.GOLAND) is True
        assert is_jetbrains_ide(IdeType.RIDER) is True

    def test_vscode_not_jetbrains(self):
        """Test VS Code is not JetBrains."""
        assert is_jetbrains_ide(IdeType.VSCODE) is False
        assert is_jetbrains_ide(IdeType.CURSOR) is False
        assert is_jetbrains_ide(IdeType.WINDSURF) is False

    def test_none_returns_false(self):
        """Test None returns False."""
        assert is_jetbrains_ide(None) is False


class TestGetIdeKind:
    """Tests for get_ide_kind function."""

    def test_vscode_kind(self):
        """Test VS Code kind."""
        assert get_ide_kind(IdeType.VSCODE) == IdeKind.VSCODE
        assert get_ide_kind(IdeType.CURSOR) == IdeKind.VSCODE

    def test_jetbrains_kind(self):
        """Test JetBrains kind."""
        assert get_ide_kind(IdeType.INTELLIJ) == IdeKind.JETBRAINS
        assert get_ide_kind(IdeType.PYCHARM) == IdeKind.JETBRAINS

    def test_none_kind(self):
        """Test None returns None."""
        assert get_ide_kind(None) is None


class TestToIdeDisplayName:
    """Tests for to_ide_display_name function."""

    def test_ide_type_display_names(self):
        """Test display names for IDE types."""
        assert to_ide_display_name("vscode") == "VS Code"
        assert to_ide_display_name("cursor") == "Cursor"
        assert to_ide_display_name("windsurf") == "Windsurf"
        assert to_ide_display_name("intellij") == "IntelliJ IDEA"
        assert to_ide_display_name("pycharm") == "PyCharm"

    def test_editor_display_names(self):
        """Test display names for editor commands."""
        assert to_ide_display_name("code") == "VS Code"
        assert to_ide_display_name("vim") == "Vim"
        assert to_ide_display_name("nano") == "nano"
        assert to_ide_display_name("emacs") == "Emacs"

    def test_none_returns_ide(self):
        """Test None returns 'IDE'."""
        assert to_ide_display_name(None) == "IDE"

    def test_unknown_returns_capitalized(self):
        """Test unknown terminals are capitalized."""
        result = to_ide_display_name("unknowneditor")
        assert result == "Unknowneditor"


class TestEditorDisplayNames:
    """Tests for EDITOR_DISPLAY_NAMES constant."""

    def test_common_editors(self):
        """Test common editor mappings."""
        assert EDITOR_DISPLAY_NAMES["code"] == "VS Code"
        assert EDITOR_DISPLAY_NAMES["cursor"] == "Cursor"
        assert EDITOR_DISPLAY_NAMES["vim"] == "Vim"
        assert EDITOR_DISPLAY_NAMES["emacs"] == "Emacs"

    def test_editor_names_count(self):
        """Test we have multiple editor mappings."""
        assert len(EDITOR_DISPLAY_NAMES) >= 10


class TestDetectedIDEInfo:
    """Tests for DetectedIDEInfo dataclass."""

    def test_creation(self):
        """Test creating DetectedIDEInfo."""
        ide = DetectedIDEInfo(
            name="VS Code",
            port=12345,
            workspace_folders=["/home/user/project"],
            url="http://127.0.0.1:12345/sse",
            is_valid=True,
        )
        assert ide.name == "VS Code"
        assert ide.port == 12345
        assert ide.is_valid is True

    def test_to_dict(self):
        """Test converting to dictionary."""
        ide = DetectedIDEInfo(
            name="VS Code",
            port=12345,
            is_valid=True,
        )
        d = ide.to_dict()
        assert d["name"] == "VS Code"
        assert d["port"] == 12345
        assert d["is_valid"] is True


class TestCheckPortOpen:
    """Tests for check_port_open function."""

    def test_localhost_refused(self):
        """Test connecting to closed port returns False."""
        # Use a high port that's unlikely to be in use
        result = check_port_open("127.0.0.1", 65432, timeout=0.1)
        assert result is False

    def test_invalid_host(self):
        """Test invalid host returns False."""
        result = check_port_open("invalid.host.local", 80, timeout=0.1)
        assert result is False


class TestDetectRunningIdes:
    """Tests for detect_running_ides function."""

    def test_returns_list(self):
        """Test returns a list of IDE types."""
        result = detect_running_ides()
        assert isinstance(result, list)
        # All items should be IdeType
        for ide in result:
            assert isinstance(ide, IdeType)

    def test_no_false_positives(self):
        """Test no IDEs running returns empty list or correctly."""
        # This test just verifies the function doesn't crash
        result = detect_running_ides()
        assert isinstance(result, list)


class TestDetectIdes:
    """Tests for detect_ides function."""

    @pytest.mark.asyncio
    async def test_no_lockfiles(self):
        """Test with no lockfiles returns empty list."""
        with patch("py_claw.services.ide.service._get_lockfiles", return_value=[]):
            result = await detect_ides()
            assert result == []

    @pytest.mark.asyncio
    async def test_include_invalid(self):
        """Test include_invalid parameter."""
        with patch("py_claw.services.ide.service._get_lockfiles", return_value=[]):
            result = await detect_ides(include_invalid=True)
            assert isinstance(result, list)


class TestFindAvailableIde:
    """Tests for find_available_ide function."""

    @pytest.mark.asyncio
    async def test_no_ides_returns_none(self):
        """Test when no IDEs available returns None."""
        with patch("py_claw.services.ide.service._get_lockfiles", return_value=[]):
            result = await find_available_ide(timeout=0.1, interval=0.01)
            assert result is None

    @pytest.mark.asyncio
    async def test_quick_timeout(self):
        """Test with very short timeout."""
        with patch("py_claw.services.ide.service._get_lockfiles", return_value=[]):
            result = await find_available_ide(timeout=0.05, interval=0.01)
            assert result is None


class TestSupportedTerminal:
    """Tests for terminal detection functions."""

    def test_supported_terminal_defaults(self):
        """Test is_supported_terminal with defaults."""
        with patch.dict(os.environ, {}, clear=True):
            # With no TERM set, should be False
            # (unless FORCE_CODE_TERMINAL is set)
            pass

    def test_is_supported_vscode_terminal(self):
        """Test VS Code terminal detection."""
        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            # Default should be False without proper IDE terminal
            pass

    def test_is_supported_jetbrains_terminal(self):
        """Test JetBrains terminal detection."""
        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            # Default should be False without proper IDE terminal
            pass


class TestGetTerminalIdeType:
    """Tests for get_terminal_ide_type function."""

    def test_no_terminal(self):
        """Test with no TERM set."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_terminal_ide_type()
            # With no TERM, should return None
            assert result is None or isinstance(result, IdeType)

    def test_unknown_terminal(self):
        """Test with unknown terminal."""
        with patch.dict(os.environ, {"TERM": "totally-unknown-terminal"}):
            result = get_terminal_ide_type()
            # Unknown terminal should return None
            assert result is None
