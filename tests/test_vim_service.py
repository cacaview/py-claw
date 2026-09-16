"""Tests for the vim service — persistence and TUI publish contract.

The vim service persists to ~/.claude/vim.json and publishes mode changes to
the global TUI store. These tests pin that contract, including the "OFF"
sentinel that lets TUI widgets distinguish "vim disabled" from the enabled
insert sub-mode.
"""

from __future__ import annotations

import pytest

from py_claw.state import store as store_module
from py_claw.state.store import Store


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Point Path.home()-based vim storage at a temp dir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def fresh_store(monkeypatch):
    """Fresh global TUI store so publish assertions are hermetic."""
    Store.reset_instance()
    monkeypatch.setattr(store_module, "_store", None)
    yield store_module.get_global_store()
    Store.reset_instance()


class TestVimPersistence:
    def test_load_absent_file_returns_disabled_default(self, fake_home):
        from py_claw.services.vim import load_vim_config

        config = load_vim_config()
        assert config.enabled is False
        assert config.current_mode.value == "normal"

    def test_save_load_roundtrip(self, fake_home):
        from py_claw.services.vim import VimConfig, VimMode, load_vim_config, save_vim_config

        save_vim_config(VimConfig(enabled=True, current_mode=VimMode.VISUAL))

        config = load_vim_config()
        assert config.enabled is True
        assert config.current_mode is VimMode.VISUAL


class TestVimTuiPublish:
    def test_enable_publishes_current_mode(self, fake_home, fresh_store):
        from py_claw.services.vim import toggle_vim_mode

        result = toggle_vim_mode()

        assert result.success is True
        assert fresh_store.get_state().tui.vim_mode == "NORMAL"

    def test_disable_publishes_off_sentinel(self, fake_home, fresh_store):
        from py_claw.services.vim import (
            get_tui_vim_mode,
            is_vim_active_in_tui,
            toggle_vim_mode,
        )

        toggle_vim_mode()  # on
        assert get_tui_vim_mode() == "NORMAL"
        assert is_vim_active_in_tui() is True

        toggle_vim_mode()  # off
        # "OFF" in the store distinguishes disabled from insert sub-mode.
        assert fresh_store.get_state().tui.vim_mode == "OFF"
        # Public read API keeps its contract: not-in-vim reports as INSERT.
        assert get_tui_vim_mode() == "INSERT"
        assert is_vim_active_in_tui() is False

    def test_off_sentinel_maps_to_insert_in_reads(self, fake_home, fresh_store):
        from py_claw.services.vim import get_tui_vim_mode
        from py_claw.state.tui_state import update_tui_vim_mode

        update_tui_vim_mode("OFF")
        assert get_tui_vim_mode() == "INSERT"

        update_tui_vim_mode("VISUAL")
        assert get_tui_vim_mode() == "VISUAL"

    def test_get_tui_state_snapshot_reflects_store(self, fake_home, fresh_store):
        from py_claw.state.tui_state import get_tui_state_snapshot, update_tui_vim_mode

        update_tui_vim_mode("VISUAL")
        snapshot = get_tui_state_snapshot()
        assert snapshot.vim_mode == "VISUAL"


class TestVimSetMode:
    def test_set_mode_requires_enabled(self, fake_home, fresh_store):
        from py_claw.services.vim import VimMode, set_vim_mode

        result = set_vim_mode(VimMode.VISUAL)

        assert result.success is False
        assert "not enabled" in result.message

    def test_set_mode_persists_and_publishes(self, fake_home, fresh_store):
        from py_claw.services.vim import VimMode, load_vim_config, set_vim_mode, toggle_vim_mode

        toggle_vim_mode()  # on
        result = set_vim_mode(VimMode.VISUAL)

        assert result.success is True
        assert load_vim_config().current_mode is VimMode.VISUAL
        assert fresh_store.get_state().tui.vim_mode == "VISUAL"


class TestVimStatus:
    def test_status_enabled(self, fake_home, fresh_store):
        from py_claw.services.vim import get_vim_status_for_tui, toggle_vim_mode

        toggle_vim_mode()

        status = get_vim_status_for_tui()
        assert status["vim_enabled"] is True
        assert status["vim_mode"] == "NORMAL"
        assert status["short_label"] == "NOR"
        assert status["status_text"] == "VIM NORMAL"

    def test_status_disabled(self, fake_home, fresh_store):
        from py_claw.services.vim import get_vim_status_for_tui

        status = get_vim_status_for_tui()
        assert status["vim_enabled"] is False
        assert status["short_label"] == ""
        assert status["status_text"] == ""


class TestVimFormat:
    def test_format_enabled_shows_keybindings(self, fake_home, fresh_store):
        from py_claw.services.vim import format_vim_text, toggle_vim_mode

        text = format_vim_text(toggle_vim_mode())

        assert "Mode: normal" in text
        assert "i - Enter insert mode" in text
        assert "Escape - Return to normal mode" in text

    def test_format_disabled(self, fake_home, fresh_store):
        from py_claw.services.vim import format_vim_text, get_vim_info

        text = format_vim_text(get_vim_info())

        assert "Vim mode is disabled" in text
