"""
MCP Auth Service — MCP-specific OAuth/鉴权链.

Provides OAuth 2.0 + PKCE authentication for MCP servers,
with support for token refresh, XAA, VSCode SDK integration,
channel permissions, elicitation handling, and official registry.
"""
from __future__ import annotations

from py_claw.services.mcp_auth.types import (
    McpOAuthTokens,
    McpOAuthSettings,
    McpAuthConfig,
    McpServerCredentialEntry,
    McpAuthResult,
    McpAuthProviderInfo,
    McpTokenRefreshResult,
    McpAuthState,
    XaaTokenExchangeResult,
    generate_pkce_pair,
    generate_oauth_state,
)

from py_claw.services.mcp_auth.service import (
    SecureStorage,
    SecureStorageEntry,
    McpAuthProvider,
    OAuthCallbackHandler,
    OAuthCallbackServer,
    McpAuthService,
    get_mcp_auth_service,
    get_secure_storage,
)

from py_claw.services.mcp_auth.vscode import (
    McpAuthToolResult,
    McpAuthTool,
    create_auth_tool_for_server,
    get_needs_auth_servers,
)

from py_claw.services.mcp_auth.xaa import (
    is_xaa_enabled,
    XaaIdpSettings,
    get_xaa_idp_settings,
    set_xaa_idp_settings,
    XaaIdTokenCache,
    get_cached_idp_id_token,
    set_cached_idp_id_token,
    clear_cached_idp_id_token,
    OidcDiscoveryResult,
    discover_oidc,
    XaaTokenExchangeResult as XaaTokenExchangeResult2,
    perform_xaa_token_exchange,
    perform_xaa_auth,
)

from py_claw.services.mcp_auth.channel import (
    ChannelPermissionResponse,
    ChannelPermissionCallbacks,
    create_channel_permission_callbacks,
    filter_permission_relay_clients,
    ChannelGateResult,
    is_channel_permission_relay_enabled,
    gate_channel_server,
    wrap_channel_message,
    short_request_id,
    truncate_for_preview,
    PERMISSION_REPLY_RE,
)

from py_claw.services.mcp_auth.elicitation import (
    ElicitationWaitingState,
    ElicitationRequestEvent,
    ElicitationQueue,
    ElicitResult,
    get_elicitation_mode,
    ElicitationHandler,
    get_elicitation_handler,
    reset_elicitation_handler,
)

from py_claw.services.mcp_auth.registry import (
    is_official_mcp_url,
    prefetch_official_mcp_urls,
    reset_official_mcp_urls_for_testing,
    get_official_mcp_urls,
    check_url_in_registry,
)

__all__ = [
    # types
    "McpOAuthTokens",
    "McpOAuthSettings",
    "McpAuthConfig",
    "McpServerCredentialEntry",
    "McpAuthResult",
    "McpAuthProviderInfo",
    "McpTokenRefreshResult",
    "McpAuthState",
    "XaaTokenExchangeResult",
    "generate_pkce_pair",
    "generate_oauth_state",
    # service
    "SecureStorage",
    "SecureStorageEntry",
    "McpAuthProvider",
    "OAuthCallbackHandler",
    "OAuthCallbackServer",
    "McpAuthService",
    "get_mcp_auth_service",
    "get_secure_storage",
    # vscode
    "McpAuthToolResult",
    "McpAuthTool",
    "create_auth_tool_for_server",
    "get_needs_auth_servers",
    # xaa
    "is_xaa_enabled",
    "XaaIdpSettings",
    "get_xaa_idp_settings",
    "set_xaa_idp_settings",
    "XaaIdTokenCache",
    "get_cached_idp_id_token",
    "set_cached_idp_id_token",
    "clear_cached_idp_id_token",
    "OidcDiscoveryResult",
    "discover_oidc",
    "XaaTokenExchangeResult2",
    "perform_xaa_token_exchange",
    "perform_xaa_auth",
    # channel
    "ChannelPermissionResponse",
    "ChannelPermissionCallbacks",
    "create_channel_permission_callbacks",
    "filter_permission_relay_clients",
    "ChannelGateResult",
    "is_channel_permission_relay_enabled",
    "gate_channel_server",
    "wrap_channel_message",
    "short_request_id",
    "truncate_for_preview",
    "PERMISSION_REPLY_RE",
    # elicitation
    "ElicitationWaitingState",
    "ElicitationRequestEvent",
    "ElicitationQueue",
    "ElicitResult",
    "get_elicitation_mode",
    "ElicitationHandler",
    "get_elicitation_handler",
    "reset_elicitation_handler",
    # registry
    "is_official_mcp_url",
    "prefetch_official_mcp_urls",
    "reset_official_mcp_urls_for_testing",
    "get_official_mcp_urls",
    "check_url_in_registry",
]
