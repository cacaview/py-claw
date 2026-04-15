"""Tests for /session command."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from py_claw.settings.loader import SettingsLoadResult


class TestSessionCommand:
    """Test suite for /session command."""

    def test_session_handler_not_in_remote_mode(self):
        """Test /session when not in remote mode."""
        from py_claw.session import session_handler
        from py_claw.commands import CommandDefinition

        # Create mock state without remote URL
        state = MagicMock()
        state.cwd = "/test"
        state.remote_url = None

        # Mock bridge state to return disconnected
        with patch.object(state, 'remote_url', None):
            result = session_handler(
                command=CommandDefinition(name="session", description="Test"),
                arguments="",
                state=state,
                settings=MagicMock(),
                registry=MagicMock(),
                session_id="test-123",
                transcript_size=5,
            )

        assert "Not in remote mode" in result
        assert "--remote" in result

    def test_session_handler_in_remote_mode_with_qr(self):
        """Test /session when in remote mode with QR code."""
        from py_claw.session import session_handler, _generate_qr_code, _format_session_info
        from py_claw.commands import CommandDefinition

        test_url = "https://claude.ai/session/abc123"

        # Test QR code generation
        qr_art = _generate_qr_code(test_url)
        assert len(qr_art) > 0
        assert '██' in qr_art or '  ' in qr_art  # QR code should have filled/empty cells

        # Test session info formatting
        result = _format_session_info(test_url, qr_art)
        assert "Remote session" in result
        assert test_url in result

    def test_generate_qr_code_with_real_url(self):
        """Test QR code generation with a real URL."""
        from py_claw.session import _generate_qr_code

        url = "https://claude.ai/connect/session/test-session-id-12345"
        qr = _generate_qr_code(url)

        # Should return multi-line string with QR pattern
        lines = qr.strip().split('\n')
        assert len(lines) > 5  # Minimum size for a QR code

    def test_session_handler_returns_formatted_info(self):
        """Test that session handler returns properly formatted info."""
        from py_claw.session import _format_session_info

        test_url = "https://claude.ai/session/test123"
        qr_art = "██  ██  ██\n██  ██  ██\n"

        result = _format_session_info(test_url, qr_art)

        assert "Remote session" in result
        assert test_url in result
        assert "Open in browser" in result

    def test_session_handler_no_args(self):
        """Test /session with no arguments."""
        from py_claw.session import session_handler
        from py_claw.commands import CommandDefinition

        state = MagicMock()
        state.remote_url = None

        # Mock to return no remote URL
        with patch('py_claw.session._get_remote_session_url', return_value=None):
            result = session_handler(
                command=CommandDefinition(name="session", description="Test"),
                arguments="",
                state=state,
                settings=MagicMock(),
                registry=MagicMock(),
                session_id="test-123",
                transcript_size=5,
            )

        # Should show not in remote mode message
        assert "Not in remote mode" in result

    def test_get_remote_session_url_from_env(self):
        """Test getting remote URL from environment variable."""
        from py_claw.session import _get_remote_session_url

        state = MagicMock()
        state.remote_url = None

        with patch.dict('os.environ', {'CLAUDE_REMOTE_SESSION_URL': 'https://test.url/session'}):
            with patch('py_claw.services.bridge.state.get_bridge_state', side_effect=Exception("No bridge")):
                url = _get_remote_session_url(state)
                assert url == 'https://test.url/session'

    def test_get_remote_session_url_no_source(self):
        """Test getting remote URL when no source available."""
        from py_claw.session import _get_remote_session_url

        state = MagicMock()
        state.remote_url = None

        with patch.dict('os.environ', {}, clear=True):
            with patch('py_claw.services.bridge.state.get_bridge_state', side_effect=Exception("No bridge")):
                url = _get_remote_session_url(state)
                assert url is None

    def test_qr_code_fallback_without_qrcode_library(self):
        """Test QR code fallback when qrcode library not available."""
        from py_claw.session import _generate_simple_qr_placeholder

        url = "https://example.com/session/test"
        result = _generate_simple_qr_placeholder(url)

        assert "QR Code" in result
        assert url in result
        assert "install qrcode package" in result

    def test_session_command_not_hidden_when_no_remote(self):
        """Test session command is visible but shows not-in-remote-mode message."""
        from py_claw.session import session_handler
        from py_claw.commands import CommandDefinition

        state = MagicMock()
        state.remote_url = None

        with patch('py_claw.session._get_remote_session_url', return_value=None):
            result = session_handler(
                command=CommandDefinition(name="session", description="Show remote session"),
                arguments="",
                state=state,
                settings=MagicMock(),
                registry=MagicMock(),
                session_id=None,
                transcript_size=0,
            )

        # Should show guidance message
        assert "Not in remote mode" in result
        assert "--remote" in result


class TestNewCommandHandlers:
    """Test suite for lightweight command handlers that now have real behavior."""

    def test_oauth_refresh_status_reports_auth_state(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _oauth_refresh_handler
        from py_claw.services.oauth.types import OAuthProfile, OAuthTokens

        service = MagicMock()
        service.is_authenticated.return_value = True
        service.get_tokens.return_value = OAuthTokens(access_token="a", refresh_token="r")
        service.get_profile.return_value = OAuthProfile(raw={"email": "user@example.com"})

        with patch("py_claw.services.oauth.service.get_oauth_service", return_value=service):
            result = _oauth_refresh_handler(
                command=CommandDefinition(name="oauth-refresh", description="Refresh OAuth"),
                arguments="status",
                state=MagicMock(),
                settings=MagicMock(),
                registry=MagicMock(),
                session_id="s1",
                transcript_size=0,
            )

        assert "OAuth Status" in result
        assert "Authenticated: yes" in result
        assert "Refresh token: yes" in result
        assert "user@example.com" in result

    def test_oauth_refresh_requires_login_when_not_authenticated(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _oauth_refresh_handler

        service = MagicMock()
        service.is_authenticated.return_value = False

        with patch("py_claw.services.oauth.service.get_oauth_service", return_value=service):
            result = _oauth_refresh_handler(
                command=CommandDefinition(name="oauth-refresh", description="Refresh OAuth"),
                arguments="refresh",
                state=MagicMock(),
                settings=MagicMock(),
                registry=MagicMock(),
                session_id=None,
                transcript_size=0,
            )

        assert "Run /login first" in result

    def test_oauth_refresh_refreshes_existing_token(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _oauth_refresh_handler
        from py_claw.services.oauth.types import OAuthProfile, OAuthTokens

        tokens = OAuthTokens(access_token="old", refresh_token="refresh")
        refreshed = OAuthTokens(access_token="new", refresh_token="refresh")

        service = MagicMock()
        service.is_authenticated.return_value = True
        service.get_tokens.return_value = tokens
        service.get_profile.return_value = OAuthProfile(raw={"email": "user@example.com"})
        service.refresh_token.return_value = refreshed

        with patch("py_claw.services.oauth.service.get_oauth_service", return_value=service):
            result = _oauth_refresh_handler(
                command=CommandDefinition(name="oauth-refresh", description="Refresh OAuth"),
                arguments="refresh",
                state=MagicMock(),
                settings=MagicMock(),
                registry=MagicMock(),
                session_id=None,
                transcript_size=0,
            )

        service.refresh_token.assert_called_once_with(tokens)
        assert "OAuth token refreshed." in result
        assert "Access token present: yes" in result

    def test_ctx_viz_returns_runtime_summary(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _ctx_viz_handler

        state = MagicMock()
        state.cwd = "/repo"
        state.initialized_agents = {"a1": object(), "a2": object()}
        state.sdk_mcp_servers = ["m1"]
        state.todos = [{"id": 1}]
        state.scheduled_cron_jobs = [object(), object()]
        state._total_input_tokens = 120
        state._total_output_tokens = 30
        state.build_slash_command_usage.return_value = {"includedCommands": 12}
        state.build_skill_usage.return_value = {"includedSkills": 3}
        state.task_runtime.list.return_value = [MagicMock(status="in_progress"), MagicMock(status="completed")]

        registry = MagicMock()
        registry.list.return_value = []
        settings = SettingsLoadResult(effective={"skills": ["draft"]}, sources=[])

        result = _ctx_viz_handler(
            command=CommandDefinition(name="ctx_viz", description="Context viz"),
            arguments="",
            state=state,
            settings=settings,
            registry=registry,
            session_id="sess-1",
            transcript_size=8,
        )

        assert "=== Context Visualization ===" in result
        assert "Transcript messages: 8" in result
        assert "Commands: 12" in result
        assert "Skills: 3" in result
        assert "Agents: 2" in result
        assert "SDK MCP servers: 1" in result
        assert "Active tasks: 1" in result
        assert "Total: 150" in result

    def test_pr_comments_requires_pr_number(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _pr_comments_handler

        result = _pr_comments_handler(
            command=CommandDefinition(name="pr-comments", description="PR comments"),
            arguments="",
            state=MagicMock(),
            settings=MagicMock(),
            registry=MagicMock(),
            session_id=None,
            transcript_size=0,
        )

        assert "Usage: /pr-comments <pr-number>" in result

    def test_pr_comments_formats_comments_from_gh(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _pr_comments_handler

        def fake_run(args):
            if args[:3] == ["pr", "view", "123"]:
                return {
                    "number": 123,
                    "headRepository": {"name": "repo"},
                    "headRepositoryOwner": {"login": "owner"},
                }
            if args[:2] == ["api", "/repos/owner/repo/issues/123/comments"]:
                return [{"user": {"login": "alice"}, "body": "Looks good", "created_at": "2026-04-15T00:00:00Z"}]
            if args[:2] == ["api", "/repos/owner/repo/pulls/123/comments"]:
                return [{"user": {"login": "bob"}, "body": "Fix this", "path": "src/app.py", "line": 42, "diff_hunk": "-old\n+new", "created_at": "2026-04-15T00:00:01Z"}]
            raise AssertionError(args)

        with patch("py_claw.new_commands._run_gh_json", side_effect=fake_run):
            result = _pr_comments_handler(
                command=CommandDefinition(name="pr-comments", description="PR comments"),
                arguments="123",
                state=MagicMock(),
                settings=MagicMock(),
                registry=MagicMock(),
                session_id=None,
                transcript_size=0,
            )

        assert "## PR #123 Comments" in result
        assert "### PR comments" in result
        assert "### Review comments" in result
        assert "@alice" in result
        assert "@bob src/app.py#42" in result
        assert "```diff" in result

    def test_pr_comments_handles_no_comments(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _pr_comments_handler

        def fake_run(args):
            if args[:3] == ["pr", "view", "123"]:
                return {
                    "number": 123,
                    "headRepository": {"name": "repo"},
                    "headRepositoryOwner": {"login": "owner"},
                }
            return []

        with patch("py_claw.new_commands._run_gh_json", side_effect=fake_run):
            result = _pr_comments_handler(
                command=CommandDefinition(name="pr-comments", description="PR comments"),
                arguments="123",
                state=MagicMock(),
                settings=MagicMock(),
                registry=MagicMock(),
                session_id=None,
                transcript_size=0,
            )

        assert result == "No comments found."

    def test_remote_setup_reports_remote_settings_status(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _remote_setup_handler
        from py_claw.services.remote_settings.types import RemoteSettingsConfig

        service = MagicMock()
        service.initialized = True
        service.is_eligible.return_value = True
        service.get_config.return_value = RemoteSettingsConfig(api_url="https://settings.example.test/api", timeout_ms=5000, polling_interval_ms=120000)
        service.get_settings.return_value = {"policy": {"mode": "managed"}, "hooks": {}}
        service.get_checksum.return_value = "abc123"
        service._polling_interval_id = object()

        with patch("py_claw.services.remote_settings.service.get_remote_settings_service", return_value=service):
            result = _remote_setup_handler(
                command=CommandDefinition(name="remote-setup", description="Remote setup"),
                arguments="status",
                state=MagicMock(),
                settings=MagicMock(),
                registry=MagicMock(),
                session_id=None,
                transcript_size=0,
            )

        assert "Remote Setup" in result
        assert "Eligible: yes" in result
        assert "Polling active: yes" in result
        assert "Checksum: abc123" in result
        assert "Cached keys: hooks, policy" in result

    def test_remote_setup_can_clear_cache(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _remote_setup_handler

        service = MagicMock()
        service.initialized = True

        with patch("py_claw.services.remote_settings.service.get_remote_settings_service", return_value=service):
            result = _remote_setup_handler(
                command=CommandDefinition(name="remote-setup", description="Remote setup"),
                arguments="clear-cache",
                state=MagicMock(),
                settings=MagicMock(),
                registry=MagicMock(),
                session_id=None,
                transcript_size=0,
            )

        service.clear_cache.assert_called_once_with()
        assert result == "Remote managed settings cache cleared."

    def test_debug_tool_call_returns_diagnostic_snapshot(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _debug_tool_call_handler
        from py_claw.services.diagnostic_tracking.types import DiagnosticReport

        summary = {
            "enabled": True,
            "total_tracked": 4,
            "fixed_total": 1,
            "max_tracked": 100,
            "auto_fix_suggestions": False,
        }
        report = DiagnosticReport(
            total_diagnostics=4,
            by_severity={"error": 2, "warning": 2},
            by_source={"lsp": 3, "mypy": 1},
            most_recent=None,
            newly_introduced=2,
            newly_fixed=1,
        )

        with patch("py_claw.services.diagnostic_tracking.get_diagnostics_summary", return_value=summary):
            with patch("py_claw.services.diagnostic_tracking.generate_report", return_value=report):
                result = _debug_tool_call_handler(
                    command=CommandDefinition(name="debug-tool-call", description="Debug tool call"),
                    arguments="Read",
                    state=MagicMock(),
                    settings=MagicMock(),
                    registry=MagicMock(),
                    session_id=None,
                    transcript_size=0,
                )

        assert "=== Tool Debug: Read ===" in result
        assert "Total tracked: 4" in result
        assert "error: 2" in result
        assert "lsp: 3" in result
        assert "Newly introduced (1h): 2" in result

    def test_issue_list_formats_issues_from_gh(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _issue_handler

        fake_issues = [
            {
                "number": 12,
                "title": "Fix login redirect",
                "state": "OPEN",
                "author": {"login": "alice"},
                "assignees": [{"login": "bob"}],
                "labels": [{"name": "bug"}, {"name": "auth"}],
            }
        ]

        with patch("py_claw.new_commands._run_gh_json", return_value=fake_issues):
            result = _issue_handler(
                command=CommandDefinition(name="issue", description="Issue"),
                arguments="list open",
                state=MagicMock(),
                settings=MagicMock(),
                registry=MagicMock(),
                session_id=None,
                transcript_size=0,
            )

        assert "## Issues (open)" in result
        assert "#12 [OPEN] Fix login redirect" in result
        assert "author: @alice" in result
        assert "assignees: @bob" in result
        assert "labels: bug, auth" in result

    def test_issue_show_formats_issue_details(self):
        from py_claw.commands import CommandDefinition
        from py_claw.new_commands import _issue_handler

        fake_issue = {
            "number": 34,
            "title": "Crash on startup",
            "state": "CLOSED",
            "body": "Resolved by warming cache.",
            "author": {"login": "carol"},
            "assignees": [],
            "labels": [{"name": "infra"}],
            "url": "https://github.com/example/repo/issues/34",
        }

        with patch("py_claw.new_commands._run_gh_json", return_value=fake_issue):
            result = _issue_handler(
                command=CommandDefinition(name="issue", description="Issue"),
                arguments="show 34",
                state=MagicMock(),
                settings=MagicMock(),
                registry=MagicMock(),
                session_id=None,
                transcript_size=0,
            )

        assert "## Issue #34: Crash on startup" in result
        assert "State: CLOSED" in result
        assert "Author: @carol" in result
        assert "Labels: infra" in result
        assert "Resolved by warming cache." in result
    def test_install_status_reports_real_install_state(self):
        from py_claw.commands import CommandDefinition, _install_handler
        from py_claw.services.config.types import GlobalConfig

        with patch("py_claw.services.config.service.get_global_config", return_value=GlobalConfig(auto_updates=True, auto_updates_channel="stable")):
            with patch("py_claw.services.native_installer.check_install", return_value={"installed": True, "install_dir": "/tmp/claude", "executable": "/tmp/claude/claude"}):
                result = _install_handler(
                    command=CommandDefinition(name="install", description="Install"),
                    arguments="",
                    state=MagicMock(),
                    settings=MagicMock(),
                    registry=MagicMock(),
                    session_id=None,
                    transcript_size=0,
                )

        assert "=== Claude Code Install ===" in result
        assert "Installed: yes" in result
        assert "Configured update channel: stable" in result
        assert "Auto-updates: enabled" in result
        assert "/install latest" in result

    def test_install_latest_runs_installer_and_persists_channel(self):
        from py_claw.commands import CommandDefinition, _install_handler
        from py_claw.services.config.types import GlobalConfig
        from py_claw.services.native_installer.installer import SetupMessage

        saved = {}

        async def fake_install_latest():
            return SetupMessage(type="success", message="installed")

        async def fake_cleanup_npm_installations():
            return SetupMessage(type="info", message="no npm")

        async def fake_cleanup_shell_aliases():
            return SetupMessage(type="success", message="aliases cleaned")

        def fake_save_global_config(updater):
            saved["config"] = updater(GlobalConfig())

        with patch("py_claw.services.config.service.get_global_config", return_value=GlobalConfig()):
            with patch("py_claw.services.config.service.save_global_config", side_effect=fake_save_global_config):
                with patch("py_claw.services.native_installer.check_install", return_value={"installed": True, "install_dir": "/tmp/claude", "executable": "/tmp/claude/claude"}):
                    with patch("py_claw.services.native_installer.install_latest", side_effect=fake_install_latest):
                        with patch("py_claw.services.native_installer.cleanup_npm_installations", side_effect=fake_cleanup_npm_installations):
                            with patch("py_claw.services.native_installer.cleanup_shell_aliases", side_effect=fake_cleanup_shell_aliases):
                                result = _install_handler(
                                    command=CommandDefinition(name="install", description="Install"),
                                    arguments="latest",
                                    state=MagicMock(),
                                    settings=MagicMock(),
                                    registry=MagicMock(),
                                    session_id=None,
                                    transcript_size=0,
                                )

        assert "Requested channel: latest" in result
        assert "Install result [success]: installed" in result
        assert "npm cleanup [info]: no npm" in result
        assert "shell cleanup [success]: aliases cleaned" in result
        assert saved["config"].install_method == "native"
        assert saved["config"].auto_updates is True
        assert saved["config"].auto_updates_channel == "latest"

    def test_install_version_records_pinned_preference(self):
        from py_claw.commands import CommandDefinition, _install_handler
        from py_claw.services.config.types import GlobalConfig

        saved = {}

        def fake_save_global_config(updater):
            saved["config"] = updater(GlobalConfig())

        with patch("py_claw.services.config.service.get_global_config", return_value=GlobalConfig()):
            with patch("py_claw.services.config.service.save_global_config", side_effect=fake_save_global_config):
                result = _install_handler(
                    command=CommandDefinition(name="install", description="Install"),
                    arguments="version:1.2.3",
                    state=MagicMock(),
                    settings=MagicMock(),
                    registry=MagicMock(),
                    session_id=None,
                    transcript_size=0,
                )

        assert "Pinned install preference to version '1.2.3'." in result
        assert "does not download arbitrary versions yet" in result
        assert saved["config"].auto_updates is False
        assert saved["config"].auto_updates_channel == "1.2.3"


class TestSessionCommandIntegration:
    """Integration tests for session command with bridge service."""

    def test_get_remote_session_url_from_bridge_state(self):
        """Test getting remote URL from bridge state when connected."""
        from py_claw.session import _get_remote_session_url
        from py_claw.services.bridge.types import BridgeState, BridgeSession
        from unittest.mock import MagicMock, patch

        state = MagicMock()
        state.remote_url = None

        # Create mock bridge session with URL
        mock_session = MagicMock(spec=BridgeSession)
        mock_session.session_url = "https://claude.ai/session/bridge-123"

        mock_bridge_state = MagicMock()
        mock_bridge_state.get_global_state.return_value = BridgeState.CONNECTED
        mock_bridge_state.list_sessions.return_value = [mock_session]

        with patch('py_claw.services.bridge.state.get_bridge_state', return_value=mock_bridge_state):
            with patch.dict('os.environ', {}, clear=True):
                url = _get_remote_session_url(state)
                assert url == "https://claude.ai/session/bridge-123"

    def test_get_remote_session_url_bridge_disconnected(self):
        """Test getting remote URL when bridge is disconnected."""
        from py_claw.session import _get_remote_session_url
        from py_claw.services.bridge.types import BridgeState
        from unittest.mock import MagicMock, patch

        state = MagicMock()
        state.remote_url = None

        mock_bridge_state = MagicMock()
        mock_bridge_state.get_global_state.return_value = BridgeState.DISCONNECTED
        mock_bridge_state.list_sessions.return_value = []

        with patch('py_claw.services.bridge.state.get_bridge_state', return_value=mock_bridge_state):
            with patch.dict('os.environ', {}, clear=True):
                url = _get_remote_session_url(state)
                assert url is None
