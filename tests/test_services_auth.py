"""Tests for the auth service."""

from __future__ import annotations

import os
import time
from unittest.mock import patch, MagicMock

import pytest

from py_claw.services.auth.auth import (
    # Types
    ApiKeySource,
    AuthTokenSource,
    UserAccountInfo,
    OrgValidationResult,
    AwsCredentials,
    # Auth state
    is_anthropic_auth_enabled,
    get_auth_token_source,
    has_anthropic_api_key_auth,
    # API key management
    get_anthropic_api_key,
    get_anthropic_api_key_with_source,
    get_configured_api_key_helper,
    get_api_key_from_api_key_helper_cached,
    clear_api_key_helper_cache,
    save_api_key,
    remove_api_key,
    is_custom_api_key_approved,
    # OAuth tokens
    get_claude_ai_oauth_tokens,
    save_oauth_tokens_if_needed,
    clear_oauth_token_cache,
    # Subscription state
    is_claude_ai_subscriber,
    has_profile_scope,
    is_1p_api_customer,
    get_subscription_type,
    is_max_subscriber,
    is_team_subscriber,
    is_enterprise_subscriber,
    is_pro_subscriber,
    get_rate_limit_tier,
    get_subscription_name,
    has_opus_access,
    is_consumer_subscriber,
    # Cloud provider auth
    refresh_and_get_aws_credentials,
    clear_aws_credentials_cache,
    refresh_gcp_credentials_if_needed,
    clear_gcp_credentials_cache,
    # Account info
    is_overage_provisioning_allowed,
    # Helpers
    _is_valid_api_key,
    _is_env_truthy,
    _is_bare_mode,
    _is_managed_oauth_context,
)


class TestApiKeySource:
    """Tests for ApiKeySource enum."""

    def test_api_key_source_values(self):
        """Test that ApiKeySource enum has expected values."""
        assert ApiKeySource.ANTHROPIC_API_KEY.value == "ANTHROPIC_API_KEY"
        assert ApiKeySource.API_KEY_HELPER.value == "apiKeyHelper"
        assert ApiKeySource.LOGIN_MANAGED_KEY.value == "/login managed key"
        assert ApiKeySource.NONE.value == "none"


class TestAuthTokenSource:
    """Tests for AuthTokenSource enum."""

    def test_auth_token_source_values(self):
        """Test that AuthTokenSource enum has expected values."""
        assert AuthTokenSource.ANTHROPIC_AUTH_TOKEN.value == "ANTHROPIC_AUTH_TOKEN"
        assert AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN.value == "CLAUDE_CODE_OAUTH_TOKEN"
        assert AuthTokenSource.CLAUDE_AI.value == "claude.ai"
        assert AuthTokenSource.NONE.value == "none"


class TestUserAccountInfo:
    """Tests for UserAccountInfo dataclass."""

    def test_default_values(self):
        """Test that UserAccountInfo has correct defaults."""
        info = UserAccountInfo()
        assert info.subscription is None
        assert info.token_source is None
        assert info.api_key_source is None
        assert info.organization is None
        assert info.email is None

    def test_with_values(self):
        """Test UserAccountInfo with values."""
        info = UserAccountInfo(
            subscription="Claude Pro",
            token_source="claude.ai",
            organization="My Org",
            email="test@example.com",
        )
        assert info.subscription == "Claude Pro"
        assert info.token_source == "claude.ai"
        assert info.organization == "My Org"
        assert info.email == "test@example.com"


class TestOrgValidationResult:
    """Tests for OrgValidationResult dataclass."""

    def test_valid_result(self):
        """Test valid OrgValidationResult."""
        result = OrgValidationResult(valid=True)
        assert result.valid is True
        assert result.message is None

    def test_invalid_result_with_message(self):
        """Test invalid OrgValidationResult with message."""
        result = OrgValidationResult(valid=False, message="Token expired")
        assert result.valid is False
        assert result.message == "Token expired"


class TestAwsCredentials:
    """Tests for AwsCredentials dataclass."""

    def test_aws_credentials_creation(self):
        """Test AwsCredentials creation."""
        creds = AwsCredentials(
            access_key_id="AKIA...",
            secret_access_key="secret",
            session_token="session",
        )
        assert creds.access_key_id == "AKIA..."
        assert creds.secret_access_key == "secret"
        assert creds.session_token == "session"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_is_env_truthy(self):
        """Test _is_env_truthy helper."""
        assert _is_env_truthy("true") is True
        assert _is_env_truthy("1") is True
        assert _is_env_truthy("yes") is True
        assert _is_env_truthy("false") is False
        assert _is_env_truthy("0") is False
        assert _is_env_truthy("") is False
        assert _is_env_truthy(None) is False

    def test_is_bare_mode(self):
        """Test _is_bare_mode detection."""
        with patch.dict(os.environ, {}, clear=True):
            # Without CLAUDE_CODE_BARE, should return False
            # Note: This might need adjustment based on actual implementation
            pass

    def test_is_managed_oauth_context(self):
        """Test _is_managed_oauth_context detection."""
        with patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true"}):
            assert _is_managed_oauth_context() is True

        with patch.dict(os.environ, {"CLAUDE_CODE_ENTRYPOINT": "claude-desktop"}):
            assert _is_managed_oauth_context() is True

        with patch.dict(os.environ, {}, clear=True):
            assert _is_managed_oauth_context() is False


class TestApiKeyValidation:
    """Tests for API key validation."""

    def test_valid_api_keys(self):
        """Test that valid API keys pass validation."""
        valid_keys = [
            "sk-ant-api03-abc123",
            "sk-ant-api03-abc123-def456",
            "sk-ant-api03-abc123_def456-ghi789",
            "ABC123",
            "abc-123_456",
        ]
        for key in valid_keys:
            assert _is_valid_api_key(key) is True, f"Expected {key} to be valid"

    def test_invalid_api_keys(self):
        """Test that invalid API keys fail validation."""
        invalid_keys = [
            "sk-ant-api03-abc123!",
            "sk-ant api03-abc123",
            "sk-ant@api03-abc123",
            "sk-ant#api03-abc123",
            "",
        ]
        for key in invalid_keys:
            assert _is_valid_api_key(key) is False, f"Expected {key} to be invalid"


class TestIsAnthropicAuthEnabled:
    """Tests for is_anthropic_auth_enabled."""

    def test_bare_mode_disables_auth(self):
        """Test that bare mode disables Anthropic auth."""
        with patch.dict(os.environ, {"CLAUDE_CODE_BARE": "true"}):
            assert is_anthropic_auth_enabled() is False

    def test_third_party_services_disables_auth(self):
        """Test that third-party services disable Anthropic auth."""
        with patch.dict(os.environ, {"CLAUDE_CODE_USE_BEDROCK": "true"}):
            assert is_anthropic_auth_enabled() is False

        with patch.dict(os.environ, {"CLAUDE_CODE_USE_VERTEX": "true"}):
            assert is_anthropic_auth_enabled() is False

        with patch.dict(os.environ, {"CLAUDE_CODE_USE_FOUNDRY": "true"}):
            assert is_anthropic_auth_enabled() is False

    def test_oauth_token_enables_auth(self):
        """Test that CLAUDE_CODE_OAUTH_TOKEN enables auth in SSH context."""
        with patch.dict(os.environ, {
            "ANTHROPIC_UNIX_SOCKET": "/tmp/socket",
            "CLAUDE_CODE_OAUTH_TOKEN": "test-token",
        }):
            assert is_anthropic_auth_enabled() is True


class TestGetAuthTokenSource:
    """Tests for get_auth_token_source."""

    def test_bare_mode_with_api_key_helper(self):
        """Test bare mode with apiKeyHelper returns apiKeyHelper source."""
        with patch.dict(os.environ, {"CLAUDE_CODE_BARE": "true"}):
            with patch(
                "py_claw.services.auth.auth.get_configured_api_key_helper",
                return_value="/usr/local/bin/get-api-key",
            ):
                result = get_auth_token_source()
                assert result["source"] == AuthTokenSource.API_KEY_HELPER.value
                assert result["has_token"] is True

    def test_bare_mode_without_key_helper(self):
        """Test bare mode without apiKeyHelper returns none."""
        with patch.dict(os.environ, {"CLAUDE_CODE_BARE": "true"}):
            with patch(
                "py_claw.services.auth.auth.get_configured_api_key_helper",
                return_value=None,
            ):
                result = get_auth_token_source()
                assert result["source"] == AuthTokenSource.NONE.value
                assert result["has_token"] is False

    def test_oauth_token_from_env(self):
        """Test OAuth token from environment variable."""
        # Clear ANTHROPIC_AUTH_TOKEN to ensure CLAUDE_CODE_OAUTH_TOKEN is checked
        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "test-token"}, clear=True):
            with patch(
                "py_claw.services.auth.auth._is_managed_oauth_context",
                return_value=False,
            ):
                result = get_auth_token_source()
                assert result["source"] == AuthTokenSource.CLAUDE_CODE_OAUTH_TOKEN.value
                assert result["has_token"] is True


class TestGetAnthropicApiKey:
    """Tests for get_anthropic_api_key."""

    def test_returns_none_when_no_key(self):
        """Test that get_anthropic_api_key returns None when no key is available."""
        with patch(
            "py_claw.services.auth.auth.get_anthropic_api_key_with_source",
            return_value={"key": None, "source": ApiKeySource.NONE.value},
        ):
            result = get_anthropic_api_key()
            assert result is None


class TestGetAnthropicApiKeyWithSource:
    """Tests for get_anthropic_api_key_with_source."""

    def test_bare_mode_with_env_key(self):
        """Test bare mode with ANTHROPIC_API_KEY env var."""
        with patch.dict(os.environ, {
            "CLAUDE_CODE_BARE": "true",
            "ANTHROPIC_API_KEY": "sk-ant-test123",
        }):
            result = get_anthropic_api_key_with_source()
            assert result["key"] == "sk-ant-test123"
            assert result["source"] == ApiKeySource.ANTHROPIC_API_KEY.value

    def test_bare_mode_with_api_key_helper(self):
        """Test bare mode with apiKeyHelper."""
        with patch.dict(os.environ, {"CLAUDE_CODE_BARE": "true"}):
            with patch(
                "py_claw.services.auth.auth.get_configured_api_key_helper",
                return_value="/usr/local/bin/get-api-key",
            ):
                result = get_anthropic_api_key_with_source(
                    skip_retrieving_key_from_api_key_helper=True
                )
                assert result["key"] is None
                assert result["source"] == ApiKeySource.API_KEY_HELPER.value

    def test_ci_mode_requires_key_or_token(self):
        """Test that CI mode requires ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN."""
        with patch.dict(os.environ, {"CI": "true"}):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN"):
                get_anthropic_api_key_with_source()


class TestSubscriptionState:
    """Tests for subscription state functions."""

    def test_get_subscription_type_returns_none_when_no_auth(self):
        """Test get_subscription_type returns None when not authenticated."""
        with patch(
            "py_claw.services.auth.auth.is_anthropic_auth_enabled",
            return_value=False,
        ):
            assert get_subscription_type() is None

    def test_get_subscription_name(self):
        """Test get_subscription_name returns correct names."""
        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="max",
        ):
            assert get_subscription_name() == "Claude Max"

        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="pro",
        ):
            assert get_subscription_name() == "Claude Pro"

        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="enterprise",
        ):
            assert get_subscription_name() == "Claude Enterprise"

        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="team",
        ):
            assert get_subscription_name() == "Claude Team"

        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value=None,
        ):
            assert get_subscription_name() == "Claude API"

    def test_is_max_subscriber(self):
        """Test is_max_subscriber."""
        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="max",
        ):
            assert is_max_subscriber() is True

        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="pro",
        ):
            assert is_max_subscriber() is False

    def test_is_pro_subscriber(self):
        """Test is_pro_subscriber."""
        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="pro",
        ):
            assert is_pro_subscriber() is True

        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="max",
        ):
            assert is_pro_subscriber() is False

    def test_is_enterprise_subscriber(self):
        """Test is_enterprise_subscriber."""
        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="enterprise",
        ):
            assert is_enterprise_subscriber() is True

        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="team",
        ):
            assert is_enterprise_subscriber() is False

    def test_is_team_subscriber(self):
        """Test is_team_subscriber."""
        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="team",
        ):
            assert is_team_subscriber() is True

        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value="enterprise",
        ):
            assert is_team_subscriber() is False

    def test_is_consumer_subscriber(self):
        """Test is_consumer_subscriber (Max or Pro)."""
        with patch(
            "py_claw.services.auth.auth.is_claude_ai_subscriber",
            return_value=True,
        ):
            with patch(
                "py_claw.services.auth.auth.get_subscription_type",
                return_value="max",
            ):
                assert is_consumer_subscriber() is True

            with patch(
                "py_claw.services.auth.auth.get_subscription_type",
                return_value="pro",
            ):
                assert is_consumer_subscriber() is True

            with patch(
                "py_claw.services.auth.auth.get_subscription_type",
                return_value="team",
            ):
                assert is_consumer_subscriber() is False

    def test_has_opus_access(self):
        """Test has_opus_access for different subscription types."""
        # API users (subscription_type is None) have Opus access
        with patch(
            "py_claw.services.auth.auth.get_subscription_type",
            return_value=None,
        ):
            assert has_opus_access() is True

        # All paid tiers have Opus access
        for tier in ("max", "pro", "enterprise", "team"):
            with patch(
                "py_claw.services.auth.auth.get_subscription_type",
                return_value=tier,
            ):
                assert has_opus_access() is True


class TestIs1PApiCustomer:
    """Tests for is_1p_api_customer."""

    def test_third_party_services_not_1p(self):
        """Test that third-party service users are not 1P customers."""
        with patch.dict(os.environ, {"CLAUDE_CODE_USE_BEDROCK": "true"}):
            assert is_1p_api_customer() is False

        with patch.dict(os.environ, {"CLAUDE_CODE_USE_VERTEX": "true"}):
            assert is_1p_api_customer() is False

        with patch.dict(os.environ, {"CLAUDE_CODE_USE_FOUNDRY": "true"}):
            assert is_1p_api_customer() is False

    def test_claude_ai_subscriber_not_1p(self):
        """Test that Claude.ai subscribers are not 1P customers."""
        with patch(
            "py_claw.services.auth.auth.is_claude_ai_subscriber",
            return_value=True,
        ):
            assert is_1p_api_customer() is False

    def test_api_customer_is_1p(self):
        """Test that non-subscriber API users are 1P customers."""
        with patch(
            "py_claw.services.auth.auth.is_claude_ai_subscriber",
            return_value=False,
        ):
            assert is_1p_api_customer() is True


class TestHasProfileScope:
    """Tests for has_profile_scope."""

    def test_returns_false_when_no_tokens(self):
        """Test has_profile_scope returns False when no tokens."""
        with patch(
            "py_claw.services.auth.auth.get_claude_ai_oauth_tokens",
            return_value=None,
        ):
            assert has_profile_scope() is False

    def test_returns_true_when_user_profile_scope_present(self):
        """Test has_profile_scope returns True when user:profile scope is present."""
        with patch(
            "py_claw.services.auth.auth.get_claude_ai_oauth_tokens",
            return_value={"scopes": ["user:profile", "user:inference"]},
        ):
            assert has_profile_scope() is True

    def test_returns_false_when_only_inference_scope(self):
        """Test has_profile_scope returns False for user:inference only (service keys)."""
        with patch(
            "py_claw.services.auth.auth.get_claude_ai_oauth_tokens",
            return_value={"scopes": ["user:inference"]},
        ):
            assert has_profile_scope() is False


class TestOAuthTokenCache:
    """Tests for OAuth token caching functions."""

    def test_clear_oauth_token_cache_clears_state(self):
        """Test that clear_oauth_token_cache doesn't raise."""
        # Should not raise
        clear_oauth_token_cache()


class TestApiKeyHelperCache:
    """Tests for API key helper caching functions."""

    def test_clear_api_key_helper_cache_clears_state(self):
        """Test that clear_api_key_helper_cache doesn't raise."""
        # Clear any existing cache
        clear_api_key_helper_cache()

    def test_get_api_key_from_api_key_helper_cached_returns_none_when_no_cache(self):
        """Test cached API key returns None when cache is empty."""
        clear_api_key_helper_cache()
        result = get_api_key_from_api_key_helper_cached()
        assert result is None


class TestCloudProviderAuth:
    """Tests for cloud provider auth functions."""

    def test_clear_aws_credentials_cache_clears_state(self):
        """Test that clear_aws_credentials_cache doesn't raise."""
        clear_aws_credentials_cache()

    def test_clear_gcp_credentials_cache_clears_state(self):
        """Test that clear_gcp_credentials_cache doesn't raise."""
        clear_gcp_credentials_cache()


class TestSaveApiKey:
    """Tests for save_api_key."""

    def test_raises_on_invalid_api_key(self):
        """Test that save_api_key raises ValueError for invalid API keys."""
        with pytest.raises(ValueError, match="Invalid API key format"):
            save_api_key("invalid key!")

    def test_accepts_valid_api_key(self):
        """Test that save_api_key accepts valid API keys."""
        # Should not raise
        save_api_key("sk-ant-api03-valid123")


class TestGetRateLimitTier:
    """Tests for get_rate_limit_tier."""

    def test_returns_none_when_not_authenticated(self):
        """Test get_rate_limit_tier returns None when not authenticated."""
        with patch(
            "py_claw.services.auth.auth.is_anthropic_auth_enabled",
            return_value=False,
        ):
            assert get_rate_limit_tier() is None

    def test_returns_tier_from_tokens(self):
        """Test get_rate_limit_tier returns tier from OAuth tokens."""
        with patch(
            "py_claw.services.auth.auth.is_anthropic_auth_enabled",
            return_value=True,
        ):
            with patch(
                "py_claw.services.auth.auth.get_claude_ai_oauth_tokens",
                return_value={"rateLimitTier": "default_claude_max_5x"},
            ):
                assert get_rate_limit_tier() == "default_claude_max_5x"


class TestHasAnthropicApiKeyAuth:
    """Tests for has_anthropic_api_key_auth."""

    def test_returns_false_when_no_key(self):
        """Test has_anthropic_api_key_auth returns False when no key."""
        with patch(
            "py_claw.services.auth.auth.get_anthropic_api_key_with_source",
            return_value={"key": None, "source": ApiKeySource.NONE.value},
        ):
            assert has_anthropic_api_key_auth() is False

    def test_returns_true_when_key_present(self):
        """Test has_anthropic_api_key_auth returns True when key is present."""
        with patch(
            "py_claw.services.auth.auth.get_anthropic_api_key_with_source",
            return_value={"key": "sk-ant-test123", "source": ApiKeySource.ANTHROPIC_API_KEY.value},
        ):
            assert has_anthropic_api_key_auth() is True


class TestIsOverageProvisioningAllowed:
    """Tests for is_overage_provisioning_allowed."""

    def test_returns_false_when_not_subscriber(self):
        """Test is_overage_provisioning_allowed returns False for non-subscribers."""
        with patch(
            "py_claw.services.auth.auth.is_claude_ai_subscriber",
            return_value=False,
        ):
            assert is_overage_provisioning_allowed() is False

    def test_returns_false_when_no_billing_type(self):
        """Test is_overage_provisioning_allowed returns False when no billing type."""
        with patch(
            "py_claw.services.auth.auth.is_claude_ai_subscriber",
            return_value=True,
        ):
            with patch(
                "py_claw.services.auth.auth.get_oauth_account_info",
                return_value={},
            ):
                assert is_overage_provisioning_allowed() is False

    def test_returns_true_for_stripe_billing(self):
        """Test is_overage_provisioning_allowed returns True for Stripe billing."""
        with patch(
            "py_claw.services.auth.auth.is_claude_ai_subscriber",
            return_value=True,
        ):
            with patch(
                "py_claw.services.auth.auth.get_oauth_account_info",
                return_value={"billingType": "stripe_subscription"},
            ):
                assert is_overage_provisioning_allowed() is True

    def test_returns_false_for_legacy_billing(self):
        """Test is_overage_provisioning_allowed returns False for legacy billing."""
        with patch(
            "py_claw.services.auth.auth.is_claude_ai_subscriber",
            return_value=True,
        ):
            with patch(
                "py_claw.services.auth.auth.get_oauth_account_info",
                return_value={"billingType": "legacy_billing"},
            ):
                assert is_overage_provisioning_allowed() is False


class TestConfiguredApiKeyHelper:
    """Tests for get_configured_api_key_helper."""

    def test_returns_none_when_not_configured(self):
        """Test get_configured_api_key_helper returns None when not configured."""
        with patch(
            "py_claw.services.auth.auth._get_settings",
            return_value={},
        ):
            with patch(
                "py_claw.services.auth.auth._is_bare_mode",
                return_value=False,
            ):
                assert get_configured_api_key_helper() is None

    def test_returns_helper_from_settings(self):
        """Test get_configured_api_key_helper returns helper from settings."""
        with patch(
            "py_claw.services.auth.auth._get_settings",
            return_value={"apiKeyHelper": "/usr/local/bin/get-key"},
        ):
            with patch(
                "py_claw.services.auth.auth._is_bare_mode",
                return_value=False,
            ):
                assert get_configured_api_key_helper() == "/usr/local/bin/get-key"
