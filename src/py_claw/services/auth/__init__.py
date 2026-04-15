"""Auth utilities module for token management and authentication state."""

from __future__ import annotations

from py_claw.services.auth.auth import (
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
    get_claude_ai_oauth_tokens_async,
    save_oauth_tokens_if_needed,
    clear_oauth_token_cache,
    handle_oauth_401_error,
    check_and_refresh_oauth_token_if_needed,
    # Subscription state
    is_claude_ai_subscriber,
    has_profile_scope,
    is_1p_api_customer,
    get_subscription_type,
    is_max_subscriber,
    is_team_subscriber,
    is_team_premium_subscriber,
    is_enterprise_subscriber,
    is_pro_subscriber,
    get_rate_limit_tier,
    get_subscription_name,
    has_opus_access,
    is_consumer_subscriber,
    # Account info
    get_account_information,
    get_oauth_account_info,
    is_overage_provisioning_allowed,
    # Validation
    validate_force_login_org,
    # Cloud provider auth helpers
    refresh_and_get_aws_credentials,
    clear_aws_credentials_cache,
    refresh_gcp_credentials_if_needed,
    clear_gcp_credentials_cache,
    prefetch_aws_credentials_if_safe,
    prefetch_gcp_credentials_if_safe,
    # OTel headers
    get_otel_headers_from_helper,
    # Types
    ApiKeySource,
    AuthTokenSource,
    UserAccountInfo,
    OrgValidationResult,
)

__all__ = [
    # Auth state
    "is_anthropic_auth_enabled",
    "get_auth_token_source",
    "has_anthropic_api_key_auth",
    # API key management
    "get_anthropic_api_key",
    "get_anthropic_api_key_with_source",
    "get_configured_api_key_helper",
    "get_api_key_from_api_key_helper_cached",
    "clear_api_key_helper_cache",
    "save_api_key",
    "remove_api_key",
    "is_custom_api_key_approved",
    # OAuth tokens
    "get_claude_ai_oauth_tokens",
    "get_claude_ai_oauth_tokens_async",
    "save_oauth_tokens_if_needed",
    "clear_oauth_token_cache",
    "handle_oauth_401_error",
    "check_and_refresh_oauth_token_if_needed",
    # Subscription state
    "is_claude_ai_subscriber",
    "has_profile_scope",
    "is_1p_api_customer",
    "get_subscription_type",
    "is_max_subscriber",
    "is_team_subscriber",
    "is_team_premium_subscriber",
    "is_enterprise_subscriber",
    "is_pro_subscriber",
    "get_rate_limit_tier",
    "get_subscription_name",
    "has_opus_access",
    "is_consumer_subscriber",
    # Account info
    "get_account_information",
    "get_oauth_account_info",
    "is_overage_provisioning_allowed",
    # Validation
    "validate_force_login_org",
    # Cloud provider auth helpers
    "refresh_and_get_aws_credentials",
    "clear_aws_credentials_cache",
    "refresh_gcp_credentials_if_needed",
    "clear_gcp_credentials_cache",
    "prefetch_aws_credentials_if_safe",
    "prefetch_gcp_credentials_if_safe",
    # OTel headers
    "get_otel_headers_from_helper",
    # Types
    "ApiKeySource",
    "AuthTokenSource",
    "UserAccountInfo",
    "OrgValidationResult",
]
