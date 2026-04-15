"""
XAA (Cross-App Access) support for MCP OAuth.

XAA allows reusing a single IdP login across all XAA-configured MCP servers:
1. Acquire an id_token from the IdP (cached in keychain)
2. Run RFC 8693 + RFC 7523 token exchange
3. Save tokens to the same keychain slot as normal OAuth

IdP connection details come from settings.xaaIdp (configured once via
`claude mcp xaa setup`). Per-server config is just `oauth.xaa: true`.
"""
from __future__ import annotations

import http.client
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# XAA Configuration
XAA_ENABLED_ENV = "CLAUDE_CODE_ENABLE_XAA"


def is_xaa_enabled() -> bool:
    """Check if XAA is enabled via environment variable."""
    import os
    return os.environ.get(XAA_ENABLED_ENV, "").lower() in ("1", "true", "yes")


# ─── XAA IdP Settings ─────────────────────────────────────────────────────────


@dataclass
class XaaIdpSettings:
    """XAA Identity Provider configuration."""
    issuer: str
    client_id: str
    client_secret: str | None = None
    callback_port: int | None = None


# In-memory XAA IdP settings (would be stored in settings)
_xaa_idp_settings: XaaIdpSettings | None = None


def get_xaa_idp_settings() -> XaaIdpSettings | None:
    """Get the XAA IdP settings.

    Returns None if XAA is not configured.
    """
    return _xaa_idp_settings


def set_xaa_idp_settings(settings: XaaIdpSettings | None) -> None:
    """Set the XAA IdP settings."""
    global _xaa_idp_settings
    _xaa_idp_settings = settings


# ─── XAA Token Cache ───────────────────────────────────────────────────────────


@dataclass
class XaaIdTokenCache:
    """Cached IdP id_token for XAA silent auth."""
    id_token: str
    expires_at: float  # Unix timestamp


_idp_token_cache: dict[str, XaaIdTokenCache] = {}
_idp_token_lock = threading.Lock()


def get_cached_idp_id_token(issuer: str) -> str | None:
    """Get cached IdP id_token if valid.

    Args:
        issuer: The IdP issuer URL

    Returns:
        id_token string if cached and not expired, None otherwise
    """
    with _idp_token_lock:
        cached = _idp_token_cache.get(issuer)
        if cached and cached.expires_at > time.time():
            return cached.id_token
        return None


def set_cached_idp_id_token(issuer: str, id_token: str, expires_in: int = 3600) -> None:
    """Cache an IdP id_token.

    Args:
        issuer: The IdP issuer URL
        id_token: The id_token to cache
        expires_in: Seconds until expiration
    """
    with _idp_token_lock:
        _idp_token_cache[issuer] = XaaIdTokenCache(
            id_token=id_token,
            expires_at=time.time() + expires_in,
        )


def clear_cached_idp_id_token(issuer: str) -> None:
    """Clear the cached IdP id_token.

    Args:
        issuer: The IdP issuer URL
    """
    with _idp_token_lock:
        _idp_token_cache.pop(issuer, None)


# ─── OIDC Discovery ────────────────────────────────────────────────────────────


@dataclass
class OidcDiscoveryResult:
    """Result of OIDC discovery."""
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str | None = None


async def discover_oidc(issuer: str) -> OidcDiscoveryResult:
    """Discover OIDC endpoints from the issuer.

    Args:
        issuer: The IdP issuer URL

    Returns:
        OidcDiscoveryResult with endpoint URLs
    """
    import urllib.request as urllib_request

    discovery_url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"

    try:
        req = urllib_request.Request(
            discovery_url,
            headers={"Accept": "application/json"},
        )
        with urllib_request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        return OidcDiscoveryResult(
            issuer=data.get("issuer", issuer),
            authorization_endpoint=data.get("authorization_endpoint", ""),
            token_endpoint=data.get("token_endpoint", ""),
            jwks_uri=data.get("jwks_uri"),
        )
    except Exception as e:
        logger.warning("OIDC discovery failed for %s: %s", issuer, e)
        raise


# ─── XAA Token Exchange ────────────────────────────────────────────────────────


@dataclass
class XaaTokenExchangeResult:
    """Result of XAA token exchange (RFC 8693)."""
    success: bool
    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    scope: str | None = None
    authorization_server_url: str | None = None
    error: str | None = None


class XaaTokenExchangeError(Exception):
    """Error during XAA token exchange."""
    def __init__(self, message: str, should_clear_id_token: bool = False):
        super().__init__(message)
        self.should_clear_id_token = should_clear_id_token


async def perform_xaa_token_exchange(
    resource_url: str,
    client_id: str,
    client_secret: str | None,
    idp_client_id: str,
    idp_client_secret: str | None,
    idp_id_token: str,
    idp_token_endpoint: str,
    server_name: str,
    abort_signal: threading.Event | None = None,
) -> XaaTokenExchangeResult:
    """Perform XAA (Cross-App Access) token exchange.

    This implements RFC 8693 (Token Exchange) with RFC 7523 (JWT Bearer).

    Args:
        resource_url: The MCP server URL (resource)
        client_id: Authorization server client ID
        client_secret: Authorization server client secret
        idp_client_id: IdP client ID
        idp_client_secret: IdP client secret
        idp_id_token: IdP id_token
        idp_token_endpoint: IdP token endpoint URL
        server_name: Name of the MCP server (for logging)
        abort_signal: Optional abort signal

    Returns:
        XaaTokenExchangeResult with tokens or error
    """
    import urllib.request as urllib_request

    try:
        # Build the token exchange request (RFC 8693)
        exchange_params = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "resource": resource_url,
            "subject_token": idp_id_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
            "client_id": idp_client_id,
        }

        if client_secret:
            import base64
            credentials = f"{idp_client_id}:{client_secret}"
            encoded = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        if client_secret:
            headers["Authorization"] = f"Basic {encoded}"

        body = "&".join(f"{k}={v}" for k, v in exchange_params.items())

        req = urllib_request.Request(
            idp_token_endpoint,
            data=body.encode("utf-8"),
            headers=headers,
            method="POST",
        )

        if abort_signal and abort_signal.is_set():
            return XaaTokenExchangeResult(success=False, error="Aborted")

        with urllib_request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if resp.status != 200:
            return XaaTokenExchangeResult(
                success=False,
                error=data.get("error", "token_exchange_failed"),
            )

        return XaaTokenExchangeResult(
            success=True,
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope"),
            authorization_server_url=data.get("authorization_server_url"),
        )

    except Exception as e:
        logger.warning("XAA token exchange failed for %s: %s", server_name, e)
        return XaaTokenExchangeResult(success=False, error=str(e))


# ─── XAA Auth Flow ─────────────────────────────────────────────────────────────


async def perform_xaa_auth(
    server_name: str,
    server_url: str,
    client_id: str,
    client_secret: str | None,
    on_auth_url: Any | None = None,
    skip_browser_open: bool = False,
    abort_signal: threading.Event | None = None,
) -> XaaTokenExchangeResult:
    """Perform XAA auth flow for an MCP server.

    Args:
        server_name: Name of the MCP server
        server_url: URL of the MCP server
        client_id: AS client ID
        client_secret: AS client secret
        on_auth_url: Callback for authorization URL (not typically used for XAA)
        skip_browser_open: Skip browser open
        abort_signal: Abort signal

    Returns:
        XaaTokenExchangeResult with tokens or error
    """
    idp = get_xaa_idp_settings()
    if not idp:
        return XaaTokenExchangeResult(
            success=False,
            error="XAA: no IdP connection configured. Run 'claude mcp xaa setup --issuer <url> --client-id <id> --client-secret'.",
        )

    if not is_xaa_enabled():
        return XaaTokenExchangeResult(
            success=False,
            error="XAA is not enabled (set CLAUDE_CODE_ENABLE_XAA=1).",
        )

    # Check for cached id_token
    id_token_cache_hit = get_cached_idp_id_token(idp.issuer) is not None

    # Acquire id_token (cached or via OIDC flow)
    id_token = get_cached_idp_id_token(idp.issuer)
    if not id_token:
        # Would perform OIDC authorization code flow here
        # For now, return error indicating this needs browser interaction
        return XaaTokenExchangeResult(
            success=False,
            error="XAA: id_token not cached. Interactive login required.",
        )

    # Discover OIDC endpoints
    try:
        oidc = await discover_oidc(idp.issuer)
    except Exception as e:
        return XaaTokenExchangeResult(
            success=False,
            error=f"XAA: OIDC discovery failed: {e}",
        )

    # Perform token exchange
    result = await perform_xaa_token_exchange(
        resource_url=server_url,
        client_id=client_id,
        client_secret=client_secret,
        idp_client_id=idp.client_id,
        idp_client_secret=idp.client_secret,
        idp_id_token=id_token,
        idp_token_endpoint=oidc.token_endpoint,
        server_name=server_name,
        abort_signal=abort_signal,
    )

    if result.success:
        logger.debug("XAA auth successful for %s (cache hit: %s)", server_name, id_token_cache_hit)

    return result
