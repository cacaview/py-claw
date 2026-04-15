"""
MCP Auth types — types for MCP-specific OAuth/鉴权.

Based on the TypeScript MCP auth.ts implementation.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any


# ─── MCP OAuth Token Types ───────────────────────────────────────────────────────


@dataclass
class McpOAuthTokens:
    """OAuth tokens for MCP server authentication."""
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: float | None = None  # Unix timestamp
    scope: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None  # Seconds until expiration
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if the access token is expired."""
        if self.expires_at is None:
            return False
        import time
        return time.time() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            **self.extra,
        }


# ─── MCP Auth Config ────────────────────────────────────────────────────────────


@dataclass
class McpOAuthClientConfig:
    """OAuth client configuration for an MCP server."""
    client_id: str
    client_secret: str | None = None
    auth_server_metadata_url: str | None = None  # RFC 8414 / RFC 9728


@dataclass
class McpOAuthSettings:
    """OAuth settings for an MCP server."""
    enabled: bool = False
    client_id: str | None = None
    client_secret: str | None = None  # Only used for confidential clients
    auth_server_metadata_url: str | None = None
    xaa: bool = False  # Cross-App Access
    scope: str | None = None
    # Callback configuration
    callback_port: int | None = None


# ─── MCP Auth Config for all servers ───────────────────────────────────────────


@dataclass
class McpAuthConfig:
    """MCP Auth service configuration."""
    enabled: bool = True
    # Secure storage path for tokens
    token_storage_path: str | None = None
    # OAuth callback settings
    default_callback_port: int = 19021
    callback_timeout_seconds: int = 300  # 5 minutes
    # XAA settings
    xaa_enabled: bool = False
    xaa_idp_issuer: str | None = None
    xaa_idp_client_id: str | None = None
    xaa_idp_client_secret: str | None = None
    xaa_callback_port: int | None = None


# ─── Server Key / Credential Storage ───────────────────────────────────────────


@dataclass
class McpServerCredentialEntry:
    """Stored credentials for an MCP server."""
    server_name: str
    server_url: str
    access_token: str = ""
    refresh_token: str | None = None
    expires_at: float = 0
    scope: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    # Step-up auth state
    step_up_scope: str | None = None
    # Discovery state
    discovery_state: dict[str, Any] | None = None


# ─── Auth Flow Types ────────────────────────────────────────────────────────────


@dataclass
class McpAuthResult:
    """Result of an MCP auth operation."""
    success: bool
    auth_url: str | None = None
    message: str = ""
    error: str | None = None


@dataclass
class McpAuthProviderInfo:
    """OAuth provider information discovered from metadata."""
    issuer: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    revocation_endpoint: str | None = None
    scopes_supported: list[str] | None = None
    token_endpoint_auth_methods_supported: list[str] | None = None


# ─── Token Refresh Result ──────────────────────────────────────────────────────


@dataclass
class McpTokenRefreshResult:
    """Result of a token refresh operation."""
    success: bool
    tokens: McpOAuthTokens | None = None
    error: str | None = None
    should_retry: bool = False


# ─── Server Auth State ─────────────────────────────────────────────────────────


class McpAuthState:
    """Enum-like class for MCP server auth states."""
    # Server has no stored credentials
    NEEDS_AUTH = "needs-auth"
    # Server has credentials but needs to refresh
    REFRESH_NEEDED = "refresh-needed"
    # Server is authenticated and ready
    AUTHENTICATED = "authenticated"
    # Server authentication failed
    AUTH_FAILED = "auth-failed"


# ─── XAA Types ─────────────────────────────────────────────────────────────────


@dataclass
class XaaTokenExchangeResult:
    """Result of XAA (Cross-App Access) token exchange."""
    success: bool
    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    scope: str | None = None
    authorization_server_url: str | None = None
    error: str | None = None


# ─── PKCE Helpers ───────────────────────────────────────────────────────────────


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code verifier and challenge.

    Returns:
        tuple of (code_verifier, code_challenge)
    """
    code_verifier = secrets.token_urlsafe(64)
    # SHA256 hash and base64url encode
    import hashlib
    import base64
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def generate_oauth_state() -> str:
    """Generate a random OAuth state parameter for CSRF protection."""
    return secrets.token_urlsafe(32)
