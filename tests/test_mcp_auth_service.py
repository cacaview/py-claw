"""
Tests for the MCP Auth Service.
"""
from __future__ import annotations

import pytest

from py_claw.services.mcp_auth.types import (
    McpOAuthTokens,
    McpOAuthSettings,
    McpAuthConfig,
    McpAuthResult,
    McpTokenRefreshResult,
    McpAuthState,
    generate_pkce_pair,
    generate_oauth_state,
)


class TestMcpOAuthTokens:
    """Tests for McpOAuthTokens."""

    def test_create_tokens(self) -> None:
        tokens = McpOAuthTokens(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_in=3600,
        )
        assert tokens.access_token == "test_access_token"
        assert tokens.refresh_token == "test_refresh_token"
        assert tokens.expires_in == 3600

    def test_tokens_expired_no_expiry(self) -> None:
        tokens = McpOAuthTokens(access_token="token")
        assert not tokens.is_expired

    def test_tokens_to_dict(self) -> None:
        tokens = McpOAuthTokens(
            access_token="token",
            refresh_token="refresh",
            scope="read write",
        )
        d = tokens.to_dict()
        assert d["access_token"] == "token"
        assert d["refresh_token"] == "refresh"
        assert d["scope"] == "read write"


class TestMcpOAuthSettings:
    """Tests for McpOAuthSettings."""

    def test_default_settings(self) -> None:
        settings = McpOAuthSettings()
        assert not settings.enabled
        assert settings.client_id is None
        assert not settings.xaa

    def test_xaa_settings(self) -> None:
        settings = McpOAuthSettings(enabled=True, xaa=True, scope="mcp")
        assert settings.enabled
        assert settings.xaa
        assert settings.scope == "mcp"


class TestMcpAuthConfig:
    """Tests for McpAuthConfig."""

    def test_default_config(self) -> None:
        config = McpAuthConfig()
        assert config.enabled
        assert config.default_callback_port == 19021
        assert config.callback_timeout_seconds == 300
        assert not config.xaa_enabled


class TestMcpAuthResult:
    """Tests for McpAuthResult."""

    def test_success_result(self) -> None:
        result = McpAuthResult(success=True, message="OK")
        assert result.success
        assert result.message == "OK"

    def test_error_result(self) -> None:
        result = McpAuthResult(success=False, error="timeout", message="Timed out")
        assert not result.success
        assert result.error == "timeout"


class TestMcpTokenRefreshResult:
    """Tests for McpTokenRefreshResult."""

    def test_success_refresh(self) -> None:
        tokens = McpOAuthTokens(access_token="new_token")
        result = McpTokenRefreshResult(success=True, tokens=tokens)
        assert result.success
        assert result.tokens is not None

    def test_failed_refresh(self) -> None:
        result = McpTokenRefreshResult(success=False, error="Invalid token", should_retry=True)
        assert not result.success
        assert result.should_retry


class TestMcpAuthState:
    """Tests for McpAuthState enum-like."""

    def test_auth_states(self) -> None:
        assert McpAuthState.NEEDS_AUTH == "needs-auth"
        assert McpAuthState.REFRESH_NEEDED == "refresh-needed"
        assert McpAuthState.AUTHENTICATED == "authenticated"
        assert McpAuthState.AUTH_FAILED == "auth-failed"


class TestGeneratePkcePair:
    """Tests for PKCE pair generation."""

    def test_pkce_pair_format(self) -> None:
        verifier, challenge = generate_pkce_pair()
        # Verifier should be URL-safe base64 string
        assert len(verifier) > 0
        # Challenge should be URL-safe base64 without padding
        assert len(challenge) > 0
        # Challenge should not have padding
        assert "=" not in challenge

    def test_pkce_pair_unique(self) -> None:
        pairs = [generate_pkce_pair() for _ in range(10)]
        # All verifiers should be unique
        verifiers = [p[0] for p in pairs]
        assert len(verifiers) == len(set(verifiers))


class TestGenerateOAuthState:
    """Tests for OAuth state generation."""

    def test_oauth_state_format(self) -> None:
        state = generate_oauth_state()
        assert len(state) > 0

    def test_oauth_state_unique(self) -> None:
        states = [generate_oauth_state() for _ in range(10)]
        assert len(states) == len(set(states))
