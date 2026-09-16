"""Batch #6 P1 wiring regression tests.

Each test asserts that a formerly non-functional command now does what it
claims: it calls the real service, produces/persists real data, and reports
the real result.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from py_claw.commands import CommandDefinition
from py_claw.settings.loader import SettingsLoadResult


def _cmd(name: str) -> CommandDefinition:
    return CommandDefinition(name=name, description="test")


def _settings(effective: dict | None = None) -> SettingsLoadResult:
    return SettingsLoadResult(effective=effective or {}, sources=[])


def _call(handler, *, arguments: str = "", state=None, settings=None, session_id=None):
    return handler(
        command=_cmd("x"),
        arguments=arguments,
        state=state if state is not None else MagicMock(),
        settings=settings if settings is not None else _settings(),
        registry=MagicMock(),
        session_id=session_id,
        transcript_size=0,
    )


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Point Path.home()-based storage (theme/keybindings/global config) at tmp."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Session storage + global config resolve via CLAUDE_CONFIG_DIR first.
    config_dir = tmp_path / ".claude"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    # Reset the global-config in-memory cache so we always read the fake home.
    from py_claw.services.config import service as config_service

    monkeypatch.setattr(config_service, "_global_config_cache", None, raising=False)
    return tmp_path


@pytest.fixture
def clean_mock_limits(monkeypatch):
    """Ensure mock rate-limit state never leaks between tests."""
    from py_claw.services import rate_limits_mocking

    monkeypatch.delenv("USER_TYPE", raising=False)
    yield
    rate_limits_mocking.reset_mock_limits()


@pytest.fixture
def fresh_store(monkeypatch):
    """Fresh global TUI store so vim publish assertions are hermetic."""
    from py_claw.state import store as store_module
    from py_claw.state.store import Store

    Store.reset_instance()
    monkeypatch.setattr(store_module, "_store", None)
    yield store_module.get_global_store()
    Store.reset_instance()


# ---------------------------------------------------------------------------
# 1. /heapdump
# ---------------------------------------------------------------------------


class TestHeapdumpWiring:
    def test_heapdump_writes_real_files(self, tmp_path):
        from py_claw.commands import _heapdump_handler

        dump_dir = tmp_path / "dumps"
        result = _call(
            _heapdump_handler,
            arguments=str(dump_dir),
        )

        assert "Heap dump complete." in result
        heap_files = list(dump_dir.glob("*.heapsnapshot"))
        diag_files = list(dump_dir.glob("*-diagnostics.json"))
        assert len(heap_files) == 1
        assert len(diag_files) == 1
        assert str(heap_files[0]) in result
        assert str(diag_files[0]) in result
        # Diagnostics must be valid JSON with the expected shape.
        diag = json.loads(diag_files[0].read_text(encoding="utf-8"))
        assert diag["trigger"] == "manual"
        assert "memoryUsage" in diag


# ---------------------------------------------------------------------------
# 2. /theme
# ---------------------------------------------------------------------------


class TestThemeWiring:
    def test_theme_list_uses_service(self, fake_home):
        from py_claw.commands import _theme_handler

        result = _call(_theme_handler)

        # Service-backed names (BUILT_IN_THEMES), not the old static list.
        assert "default" in result
        assert "dracula" in result
        assert "monokai" in result
        assert "Current theme: default" in result

    def test_theme_set_persists(self, fake_home):
        from py_claw.commands import _theme_handler
        from py_claw.services.theme import service as theme_service

        result = _call(_theme_handler, arguments="dracula")

        assert "dracula" in result
        assert "read-only" not in result.lower()
        assert theme_service.get_current_theme_name() == "dracula"
        stored = json.loads((fake_home / ".claude" / "themes.json").read_text())
        assert stored == {"current": "dracula"}

    def test_theme_set_unknown_reports_service_error(self, fake_home):
        from py_claw.commands import _theme_handler

        result = _call(_theme_handler, arguments="does-not-exist")

        assert "Unknown theme" in result
        assert "Available" in result

    def test_tui_get_theme_reads_persisted_theme(self, fake_home):
        import py_claw.ui.theme as ui_theme
        from py_claw.commands import _theme_handler

        # No storage file yet -> dark default.
        ui_theme._theme_disk_cache = None
        assert ui_theme.get_theme() is ui_theme.DEFAULT_THEME

        _call(_theme_handler, arguments="solarized-light")
        ui_theme._theme_disk_cache = None
        assert ui_theme.get_theme() is ui_theme.LIGHT_THEME

        _call(_theme_handler, arguments="dracula")
        ui_theme._theme_disk_cache = None
        assert ui_theme.get_theme() is ui_theme.DEFAULT_THEME


# ---------------------------------------------------------------------------
# 3. /keybindings
# ---------------------------------------------------------------------------


class TestKeybindingsWiring:
    def test_keybindings_list_reads_service(self, fake_home):
        from py_claw.commands import _keybindings_handler

        result = _call(_keybindings_handler)

        assert "enter → submit" in result
        assert str(fake_home / ".claude" / "keybindings.json") in result

    def test_keybindings_set_persists(self, fake_home):
        from py_claw.commands import _keybindings_handler
        from py_claw.services.keybindings import service as kb_service

        result = _call(_keybindings_handler, arguments="set ctrl+z save-file")

        assert "ctrl+z" in result and "save-file" in result
        data = json.loads((fake_home / ".claude" / "keybindings.json").read_text())
        binding = {kb["key"]: kb["command"] for kb in data["keybindings"]}
        assert binding["ctrl+z"] == "save-file"
        loaded = {kb.key: kb.command for kb in kb_service.load_keybindings()}
        assert loaded["ctrl+z"] == "save-file"

    def test_keybindings_remove_persists(self, fake_home):
        from py_claw.commands import _keybindings_handler
        from py_claw.services.keybindings import service as kb_service

        _call(_keybindings_handler, arguments="set ctrl+z save-file")
        result = _call(_keybindings_handler, arguments="remove ctrl+z")

        assert "removed" in result
        loaded = {kb.key: kb.command for kb in kb_service.load_keybindings()}
        assert "ctrl+z" not in loaded

    def test_keybindings_remove_unknown_key(self, fake_home):
        from py_claw.commands import _keybindings_handler

        result = _call(_keybindings_handler, arguments="remove ctrl+doesnotexist")

        assert "No keybinding found" in result


# ---------------------------------------------------------------------------
# 4. /mobile
# ---------------------------------------------------------------------------


class TestMobileWiring:
    def test_mobile_prints_ascii_qr_and_url(self):
        from py_claw.commands import _mobile_handler

        result = _call(_mobile_handler)

        assert "██" in result  # real ASCII QR blocks, not a discarded base64 PNG
        assert "apps.apple.com" in result
        assert "play.google.com" in result
        assert "doesn't scan" in result

    def test_mobile_single_platform(self):
        from py_claw.commands import _mobile_handler

        result = _call(_mobile_handler, arguments="ios")

        assert "apps.apple.com" in result
        assert "play.google.com" not in result
        assert "██" in result


# ---------------------------------------------------------------------------
# 5. /voice
# ---------------------------------------------------------------------------


class TestVoiceWiring:
    def test_voice_on_writes_config(self, fake_home):
        from py_claw.commands import _voice_handler

        with patch("shutil.which", return_value="/usr/bin/sox"):
            result = _call(_voice_handler, arguments="on")

        assert "enabled" in result.lower()
        config = json.loads((fake_home / ".claude" / "settings.json").read_text())
        assert config["voiceEnabled"] is True

    def test_voice_off_writes_config_and_stops(self, fake_home):
        from py_claw.commands import _voice_handler

        stop = AsyncMock()
        with patch("shutil.which", return_value="/usr/bin/sox"), patch(
            "py_claw.services.voice.service.stop_voice", stop
        ):
            result = _call(_voice_handler, arguments="off")

        assert "disabled" in result.lower()
        config = json.loads((fake_home / ".claude" / "settings.json").read_text())
        assert config["voiceEnabled"] is False
        stop.assert_awaited_once()

    def test_voice_on_requires_sox(self, fake_home):
        from py_claw.commands import _voice_handler

        with patch("shutil.which", return_value=None):
            result = _call(_voice_handler, arguments="on")

        assert "SoX" in result
        assert not (fake_home / ".claude" / "settings.json").exists()


# ---------------------------------------------------------------------------
# 6. /rename
# ---------------------------------------------------------------------------


class TestRenameWiring:
    def test_rename_persists_agent_name_to_session_jsonl(self, tmp_path):
        from py_claw.commands import _rename_handler
        from py_claw.services.session_storage.common import (
            extract_last_json_string_field,
            get_project_dir,
        )

        session_id = "11111111-2222-3333-4444-555555555555"
        state = SimpleNamespace(cwd=str(tmp_path))
        result = _call(
            _rename_handler,
            arguments="My Cool Session!",
            state=state,
            session_id=session_id,
        )

        assert "my-cool-session" in result
        assert state.agent_name == "my-cool-session"

        # The name must be persisted into the session JSONL, where the
        # metadata reader (last-value semantics) can find it.
        session_file = Path(get_project_dir(str(tmp_path))) / f"{session_id}.jsonl"
        assert session_file.exists()
        tail = session_file.read_text(encoding="utf-8")
        assert extract_last_json_string_field(tail, "agentName") == "my-cool-session"

    def test_rename_without_session_is_in_memory_only(self, tmp_path):
        from py_claw.commands import _rename_handler

        state = SimpleNamespace(cwd=str(tmp_path))
        result = _call(_rename_handler, arguments="solo", state=state, session_id=None)

        assert "in-memory only" in result
        assert state.agent_name == "solo"


# ---------------------------------------------------------------------------
# 7. /agents
# ---------------------------------------------------------------------------


class TestAgentsWiring:
    def test_agents_lists_builtin_sessions_and_tasks(self):
        from py_claw.commands import _agents_handler
        from py_claw.schemas.common import AgentDefinition
        from py_claw.tasks import TaskRuntime

        rt = TaskRuntime()
        state = SimpleNamespace(initialized_agents={}, task_runtime=rt)
        result = _call(_agents_handler, state=state)

        assert "Built-in agents:" in result
        assert "general-purpose" in result
        assert "Session agents (initialized this session):" in result
        assert "(none)" in result

        # Session agent + running agent task show up.
        state = SimpleNamespace(
            initialized_agents={"helper": AgentDefinition(description="helps", prompt="p")},
            task_runtime=rt,
        )
        result = _call(_agents_handler, state=state)
        assert "helper" in result
        assert "helps" in result


# ---------------------------------------------------------------------------
# 8. /team list
# ---------------------------------------------------------------------------


class TestTeamWiring:
    def test_team_list_shows_teams_and_members(self):
        from py_claw.commands import _team_handler
        from py_claw.tasks import TaskRuntime

        rt = TaskRuntime()
        rt.register_team_member("alpha", "agent-1", member_name="worker-1")
        rt.create_team("beta", description="the beta team")
        state = SimpleNamespace(task_runtime=rt)

        result = _call(_team_handler, arguments="list", state=state)

        assert "alpha" in result
        assert "worker-1" in result
        assert "beta" in result
        assert "the beta team" in result
        # The listing must warn that listed teammates may not be running.
        assert "may not have started running" in result

    def test_team_list_empty(self):
        from py_claw.commands import _team_handler
        from py_claw.tasks import TaskRuntime

        result = _call(_team_handler, state=SimpleNamespace(task_runtime=TaskRuntime()))
        assert "No teams found" in result

    def test_team_unsupported_actions_explain(self):
        from py_claw.commands import _team_handler
        from py_claw.tasks import TaskRuntime

        result = _call(_team_handler, arguments="create gamma", state=SimpleNamespace(task_runtime=TaskRuntime()))
        assert "list" in result


# ---------------------------------------------------------------------------
# 9. /desktop
# ---------------------------------------------------------------------------


class TestDesktopWiring:
    def test_desktop_status_reports_service(self):
        from py_claw.commands import _desktop_handler
        from py_claw.services.desktop_deep_link import DesktopInstallStatus

        with patch(
            "py_claw.services.desktop_deep_link.get_desktop_install_status",
            return_value=DesktopInstallStatus(status="ready", version="1.2.3"),
        ):
            result = _call(_desktop_handler, arguments="status")

        assert "Status: ready" in result
        assert "Version: 1.2.3" in result

    def test_desktop_install_opens_download_url(self):
        from py_claw.commands import _desktop_handler

        with patch("webbrowser.open", return_value=True) as open_mock:
            result = _call(_desktop_handler, arguments="install")

        assert "Download:" in result
        assert "claude.ai" in result
        open_mock.assert_called_once()
        assert "claude.ai" in open_mock.call_args.args[0]

    def test_desktop_unknown_action_shows_usage(self):
        from py_claw.commands import _desktop_handler

        result = _call(_desktop_handler, arguments="fly")
        assert "Usage: /desktop" in result


# ---------------------------------------------------------------------------
# 10. /usage
# ---------------------------------------------------------------------------


class TestUsageWiring:
    def test_usage_shows_real_session_usage_not_fake_limits(self, monkeypatch):
        from py_claw.commands import _usage_handler

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        state = SimpleNamespace(
            session_input_tokens=1200,
            session_output_tokens=300,
            session_cost_usd=0.0042,
            session_cache_read_tokens=250,
        )
        result = _call(_usage_handler, state=state, settings=_settings())

        # Real numbers from the same state fields /cost reports.
        assert "Input tokens: 1,200" in result
        assert "Output tokens: 300" in result
        assert "Total tokens: 1,500" in result
        assert "Cache read tokens: 250" in result
        assert "$0.0042" in result
        # The fabricated "Unlimited" claims are gone.
        assert "Unlimited" not in result


# ---------------------------------------------------------------------------
# 11. /mock-limits
# ---------------------------------------------------------------------------


class TestMockLimitsWiring:
    def test_mock_limits_activates_service(self, clean_mock_limits, monkeypatch):
        from py_claw.new_commands import _mock_limits_handler
        from py_claw.services import rate_limits_mocking as mocking

        monkeypatch.setenv("USER_TYPE", "ant")
        result = _call(_mock_limits_handler, arguments="rate_limit 30")

        assert "active for 30s" in result
        assert mocking.should_process_mock_limits() is True
        headers = mocking.get_mock_headers()
        assert headers is not None
        assert headers["anthropic-ratelimit-unified-reset"] == "30"

    def test_mock_limits_off_deactivates(self, clean_mock_limits, monkeypatch):
        from py_claw.new_commands import _mock_limits_handler
        from py_claw.services import rate_limits_mocking as mocking

        monkeypatch.setenv("USER_TYPE", "ant")
        _call(_mock_limits_handler, arguments="rate_limit 60")
        result = _call(_mock_limits_handler, arguments="off")

        assert "disabled" in result.lower()
        assert mocking.should_process_mock_limits() is False

    def test_mock_limits_rejects_unknown_type(self, clean_mock_limits):
        from py_claw.new_commands import _mock_limits_handler

        result = _call(_mock_limits_handler, arguments="bogus 30")
        assert "Unknown type" in result

    def test_engine_injects_429_when_mock_active(self, clean_mock_limits, monkeypatch, tmp_path):
        from py_claw.cli.runtime import RuntimeState
        from py_claw.query.backend import ApiRequestError, BackendTurnResult
        from py_claw.query.engine import (
            BackendTurnExecutor,
            PreparedTurn,
            QueryTurnContext,
            QueryTurnFailure,
        )
        from py_claw.services import rate_limits_mocking as mocking

        monkeypatch.setenv("USER_TYPE", "ant")
        mocking.set_mock_limits_active(True)
        mocking.set_mock_headers({"anthropic-ratelimit-unified-reset": "30"})

        calls = []

        class FakeBackend:
            def run_turn(self, prepared, context):
                calls.append(1)
                return BackendTurnResult(assistant_text="hello")

        executor = BackendTurnExecutor(FakeBackend())
        state = RuntimeState(cwd=str(tmp_path))
        context = QueryTurnContext(state=state, session_id="s1")
        prepared = PreparedTurn(query_text="hi", should_query=True)

        with pytest.raises(QueryTurnFailure) as exc_info:
            executor.execute(prepared, context)

        assert isinstance(exc_info.value.error, ApiRequestError)
        assert exc_info.value.error.kind == "rate_limit"
        assert exc_info.value.error.status == 429
        assert "mocked" in str(exc_info.value.error)
        assert "resets in 30s" in str(exc_info.value.error)
        # The real backend must never be called while the mock is active.
        assert calls == []

    def test_engine_unchanged_when_mock_inactive(self, clean_mock_limits, tmp_path):
        from py_claw.cli.runtime import RuntimeState
        from py_claw.query.backend import BackendTurnResult
        from py_claw.query.engine import (
            BackendTurnExecutor,
            PreparedTurn,
            QueryTurnContext,
        )

        class FakeBackend:
            def run_turn(self, prepared, context):
                return BackendTurnResult(assistant_text="real answer")

        executor = BackendTurnExecutor(FakeBackend())
        state = RuntimeState(cwd=str(tmp_path))
        context = QueryTurnContext(state=state, session_id="s1")
        prepared = PreparedTurn(query_text="hi", should_query=True)

        executed = executor.execute(prepared, context)
        assert executed.assistant_text == "real answer"


# ---------------------------------------------------------------------------
# 12. /thinkback-play
# ---------------------------------------------------------------------------


class TestThinkbackPlayWiring:
    def test_thinkback_play_not_installed_returns_guidance(self):
        from py_claw.new_commands import _thinkback_play_handler

        with patch(
            "py_claw.services.thinkback_play.service.find_thinkback_skill_dir",
            return_value=None,
        ):
            result = _call(_thinkback_play_handler)

        # Real service path -> install guidance (not the old canned text).
        assert "not installed" in result
        assert "/plugin install thinkback" in result

    def test_thinkback_play_success_reports_service_message(self):
        from py_claw.new_commands import _thinkback_play_handler
        from py_claw.services.thinkback_play.types import ThinkbackPlayResult

        fake_result = ThinkbackPlayResult(success=True, message="Animation complete")
        with patch(
            "py_claw.services.thinkback_play.service.play",
            return_value=fake_result,
        ):
            result = _call(_thinkback_play_handler)

        assert result == "Animation complete"


# ---------------------------------------------------------------------------
# 13. /remote-env set
# ---------------------------------------------------------------------------


class TestRemoteEnvWiring:
    def test_remote_env_set_writes_default_environment(self, fake_home):
        from py_claw.commands import _remote_env_handler

        settings = _settings(
            {"teleport": {"environments": [{"id": "env-1", "name": "One"}, "env-2"]}}
        )
        result = _call(_remote_env_handler, arguments="set env-2", settings=settings)

        assert "env-2" in result
        config = json.loads((fake_home / ".claude" / "settings.json").read_text())
        assert config["teleport"]["defaultEnvironment"] == "env-2"

    def test_remote_env_set_rejects_unknown_id(self, fake_home):
        from py_claw.commands import _remote_env_handler

        settings = _settings({"teleport": {"environments": [{"id": "env-1", "name": "One"}]}})
        result = _call(_remote_env_handler, arguments="set nope", settings=settings)

        assert "Unknown environment id" in result
        assert "env-1" in result
        assert not (fake_home / ".claude" / "settings.json").exists()

    def test_remote_env_list_shows_default(self, fake_home):
        from py_claw.commands import _remote_env_handler

        settings = _settings(
            {"teleport": {"environments": [{"id": "env-1", "name": "One"}], "defaultEnvironment": "env-1"}}
        )
        result = _call(_remote_env_handler, settings=settings)

        assert "Default environment: env-1" in result
        assert "One (env-1)" in result


# ---------------------------------------------------------------------------
# 14. /vim
# ---------------------------------------------------------------------------


class TestVimWiring:
    """/vim is backed by the vim service: real persistence + TUI publish."""

    def test_vim_toggle_enables_and_persists(self, fake_home, fresh_store):
        from py_claw.commands import _vim_handler
        from py_claw.services.vim import is_vim_enabled, load_vim_config

        result = _call(_vim_handler)

        assert "Keybindings" in result
        assert is_vim_enabled() is True
        stored = json.loads((fake_home / ".claude" / "vim.json").read_text())
        assert stored["enabled"] is True
        # A fresh load (as at restart) reads back the enabled state.
        assert load_vim_config().enabled is True
        # Published to the TUI store so the TUI can react.
        assert fresh_store.get_state().tui.vim_mode == "NORMAL"

    def test_vim_toggle_back_disables_and_persists(self, fake_home, fresh_store):
        from py_claw.commands import _vim_handler
        from py_claw.services.vim import is_vim_enabled, load_vim_config

        _call(_vim_handler)  # on
        result = _call(_vim_handler)  # off

        assert "Vim mode is disabled" in result
        assert is_vim_enabled() is False
        assert load_vim_config().enabled is False
        # The "OFF" sentinel distinguishes disabled from insert sub-mode.
        assert fresh_store.get_state().tui.vim_mode == "OFF"

    def test_vim_on_off_idempotent(self, fake_home, fresh_store):
        from py_claw.commands import _vim_handler
        from py_claw.services.vim import is_vim_enabled

        assert is_vim_enabled() is False

        result = _call(_vim_handler, arguments="on")
        assert is_vim_enabled() is True
        assert "Mode: normal" in result

        # /vim on while enabled: no-op, still enabled, reports current state.
        result = _call(_vim_handler, arguments="on")
        assert is_vim_enabled() is True
        assert "Mode: normal" in result

        result = _call(_vim_handler, arguments="off")
        assert is_vim_enabled() is False
        assert "Vim mode is disabled" in result

        # /vim off while disabled: no-op, file state unchanged.
        stored_before = (fake_home / ".claude" / "vim.json").read_text()
        result = _call(_vim_handler, arguments="off")
        assert "Vim mode is disabled" in result
        assert (fake_home / ".claude" / "vim.json").read_text() == stored_before

    def test_vim_status_reports_state(self, fake_home, fresh_store):
        from py_claw.commands import _vim_handler

        result = _call(_vim_handler, arguments="status")
        assert "enabled: no" in result
        assert "disabled" in result

        _call(_vim_handler)  # enable
        result = _call(_vim_handler, arguments="status")
        assert "enabled: yes" in result
        assert "VIM NORMAL" in result
        assert "Vim mode: normal" in result

    def test_vim_unknown_arg_shows_usage(self, fake_home, fresh_store):
        from py_claw.commands import _vim_handler

        result = _call(_vim_handler, arguments="banana")

        assert "Usage: /vim [on|off|status]" in result
        assert "/vim on" in result
        assert "/vim status" in result


# ---------------------------------------------------------------------------
# Extra: /rate-limit-options stale /upgrade text removed
# ---------------------------------------------------------------------------


class TestRateLimitOptionsText:
    def test_no_stale_upgrade_reference(self):
        from py_claw.commands import _rate_limit_options_handler

        result = _call(_rate_limit_options_handler)

        assert "/upgrade" not in result
        assert "/extra-usage" in result
