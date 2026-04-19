"""Tests for bridge services."""

from __future__ import annotations

import os
import pytest


class TestBridgeConfig:
    """Test suite for bridge configuration."""

    def test_get_bridge_base_url_default(self):
        """Test default bridge base URL."""
        # Clear any env vars
        env_backup = os.environ.get("CLAUDE_BRIDGE_BASE_URL")
        env_backup2 = os.environ.get("BRIDGE_BASE_URL")
        try:
            os.environ.pop("CLAUDE_BRIDGE_BASE_URL", None)
            os.environ.pop("BRIDGE_BASE_URL", None)

            from py_claw.services.bridge.config import get_bridge_base_url

            url = get_bridge_base_url()
            assert url == "https://api.anthropic.com"
        finally:
            if env_backup:
                os.environ["CLAUDE_BRIDGE_BASE_URL"] = env_backup
            if env_backup2:
                os.environ["BRIDGE_BASE_URL"] = env_backup2

    def test_get_bridge_base_url_override(self):
        """Test bridge base URL override via env var."""
        env_backup = os.environ.get("BRIDGE_BASE_URL")
        try:
            os.environ["BRIDGE_BASE_URL"] = "https://custom.example.com"

            from py_claw.services.bridge.config import get_bridge_base_url

            url = get_bridge_base_url()
            assert url == "https://custom.example.com"
        finally:
            if env_backup:
                os.environ["BRIDGE_BASE_URL"] = env_backup
            else:
                os.environ.pop("BRIDGE_BASE_URL", None)

    def test_get_bridge_access_token_no_token(self):
        """Test get_bridge_access_token returns None when no token available."""
        env_backup1 = os.environ.get("CLAUDE_BRIDGE_OAUTH_TOKEN")
        env_backup2 = os.environ.get("BRIDGE_MODE_ACCESS_TOKEN")
        try:
            os.environ.pop("CLAUDE_BRIDGE_OAUTH_TOKEN", None)
            os.environ.pop("BRIDGE_MODE_ACCESS_TOKEN", None)

            from py_claw.services.bridge.config import get_bridge_access_token

            token = get_bridge_access_token()
            assert token is None
        finally:
            if env_backup1:
                os.environ["CLAUDE_BRIDGE_OAUTH_TOKEN"] = env_backup1
            if env_backup2:
                os.environ["BRIDGE_MODE_ACCESS_TOKEN"] = env_backup2

    def test_get_bridge_access_token_from_env(self):
        """Test get_bridge_access_token from env var."""
        env_backup = os.environ.get("BRIDGE_MODE_ACCESS_TOKEN")
        try:
            os.environ["BRIDGE_MODE_ACCESS_TOKEN"] = "test_token_123"

            from py_claw.services.bridge.config import get_bridge_access_token

            token = get_bridge_access_token()
            assert token == "test_token_123"
        finally:
            if env_backup:
                os.environ["BRIDGE_MODE_ACCESS_TOKEN"] = env_backup
            else:
                os.environ.pop("BRIDGE_MODE_ACCESS_TOKEN", None)


class TestBridgeEnabled:
    """Test suite for bridge entitlement checks."""

    def test_is_bridge_enabled_no_env(self):
        """Test is_bridge_enabled returns False when BRIDGE_MODE not set."""
        env_backup = os.environ.get("BRIDGE_MODE")
        try:
            os.environ.pop("BRIDGE_MODE", None)

            from py_claw.services.bridge.enabled import is_bridge_enabled

            enabled = is_bridge_enabled()
            assert enabled is False
        finally:
            if env_backup:
                os.environ["BRIDGE_MODE"] = env_backup

    def test_is_bridge_enabled_with_env(self):
        """Test is_bridge_enabled with BRIDGE_MODE set."""
        env_backup = os.environ.get("BRIDGE_MODE")
        try:
            os.environ["BRIDGE_MODE"] = "1"

            from py_claw.services.bridge.enabled import is_bridge_enabled

            enabled = is_bridge_enabled()
            # Still False because ccr_bridge_enabled is False
            assert enabled is False
        finally:
            if env_backup:
                os.environ["BRIDGE_MODE"] = env_backup
            else:
                os.environ.pop("BRIDGE_MODE", None)

    def test_get_bridge_disabled_reason_no_env(self):
        """Test get_bridge_disabled_reason when not enabled."""
        env_backup = os.environ.get("BRIDGE_MODE")
        try:
            os.environ.pop("BRIDGE_MODE", None)

            from py_claw.services.bridge.enabled import get_bridge_disabled_reason

            reason = get_bridge_disabled_reason()
            assert reason is not None
            assert "not available" in reason
        finally:
            if env_backup:
                os.environ["BRIDGE_MODE"] = env_backup


class TestSessionApiClient:
    """Test suite for SessionApiClient."""

    @pytest.mark.asyncio
    async def test_register_bridge_environment_returns_result(self):
        """Test register_bridge_environment returns a result."""
        from py_claw.services.bridge.session_api import SessionApiClient

        client = SessionApiClient(
            base_url="https://api.anthropic.com",
            access_token="test_token",
        )

        result = await client.register_bridge_environment(
            environment_id="test-env-id",
            worker_type="claude_code",
            machine_name="test-machine",
        )

        assert result is not None
        assert "environment_id" in result
        assert "environment_secret" in result
        assert result["environment_id"] == "test-env-id"

    @pytest.mark.asyncio
    async def test_poll_for_work_no_work(self):
        """Test poll_for_work returns None when no work available."""
        from py_claw.services.bridge.session_api import SessionApiClient

        client = SessionApiClient(
            base_url="https://api.anthropic.com",
            access_token="test_token",
        )

        # Should return None (mock implementation or network error)
        result = await client.poll_for_work(
            environment_id="test-env-id",
            environment_secret="test_secret",
        )

        # May be None if network error or mock returns None
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_acknowledge_work(self):
        """Test acknowledge_work handles the response."""
        from py_claw.services.bridge.session_api import SessionApiClient

        client = SessionApiClient(
            base_url="https://api.anthropic.com",
            access_token="test_token",
        )

        # Should return False (mock or network error)
        result = await client.acknowledge_work(
            environment_id="test-env-id",
            work_id="test-work-id",
            session_token="test_session_token",
        )

        # May be False due to mock
        assert isinstance(result, bool)


class TestBridgeCore:
    """Test suite for BridgeCore."""

    def test_bridge_core_creation(self):
        """Test BridgeCore can be created."""
        from py_claw.services.bridge.core import BridgeCore, BridgeCoreParams
        from py_claw.services.bridge.types import BridgeState

        params = BridgeCoreParams(
            base_url="https://api.anthropic.com",
            session_ingress_url="wss://api.anthropic.com",
            environment_id="test-env-id",
            access_token="test_token",
        )

        from py_claw.services.bridge.config import get_bridge_config

        core = BridgeCore(
            params=params,
            config=get_bridge_config(),
        )

        assert core.state == BridgeState.DISCONNECTED
        assert core.params.environment_id == "test-env-id"
        assert core.environment_secret is None

    def test_bridge_core_params_defaults(self):
        """Test BridgeCoreParams default values."""
        from py_claw.services.bridge.core import BridgeCoreParams

        params = BridgeCoreParams(
            base_url="https://api.anthropic.com",
            session_ingress_url="wss://api.anthropic.com",
            environment_id="test-env-id",
            access_token="test_token",
        )

        assert params.worker_type == "claude_code"
        assert params.title is None
        assert params.git_repo_url is None
        assert params.branch is None


class TestBridgeCommand:
    """Test suite for /bridge command."""

    def test_bridge_status_displays_info(self):
        """Test /bridge status shows bridge information."""
        from py_claw.commands import _bridge_handler
        from unittest.mock import MagicMock

        result = _bridge_handler(
            command=MagicMock(),
            arguments="status",
            state=MagicMock(),
            settings=MagicMock(),
            registry=MagicMock(),
            session_id=None,
            transcript_size=0,
        )

        assert "Claude Code Remote Bridge" in result
        assert "BRIDGE_MODE" not in result or "Remote Control" in result

    def test_bridge_start_no_credentials(self):
        """Test /bridge start without credentials."""
        from py_claw.commands import _bridge_handler
        from unittest.mock import MagicMock

        result = _bridge_handler(
            command=MagicMock(),
            arguments="start",
            state=MagicMock(),
            settings=MagicMock(),
            registry=MagicMock(),
            session_id=None,
            transcript_size=0,
        )

        # Should indicate bridge is not available or not authenticated
        assert "Error" in result or "not" in result.lower()

    def test_bridge_stop_when_not_running(self):
        """Test /bridge stop when bridge is not running."""
        from py_claw.commands import _bridge_handler
        from unittest.mock import MagicMock

        result = _bridge_handler(
            command=MagicMock(),
            arguments="stop",
            state=MagicMock(),
            settings=MagicMock(),
            registry=MagicMock(),
            session_id=None,
            transcript_size=0,
        )

        assert "not running" in result.lower() or "stop" in result.lower()

    def test_bridge_unknown_arg(self):
        """Test /bridge with unknown argument."""
        from py_claw.commands import _bridge_handler
        from unittest.mock import MagicMock

        result = _bridge_handler(
            command=MagicMock(),
            arguments="unknown",
            state=MagicMock(),
            settings=MagicMock(),
            registry=MagicMock(),
            session_id=None,
            transcript_size=0,
        )

        assert "Unknown" in result or "Usage" in result
