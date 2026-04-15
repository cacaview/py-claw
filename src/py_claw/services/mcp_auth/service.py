"""
MCP Auth Service — MCP-specific OAuth/鉴权链.

Provides OAuth 2.0 + PKCE authentication for MCP servers,
with support for token refresh, XAA, and VSCode SDK integration.
"""
from __future__ import annotations

import http.server
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse

logger = logging.getLogger(__name__)

# Timeout for OAuth auth requests
AUTH_REQUEST_TIMEOUT_MS = 30000

# Sensitive OAuth params to redact from logs
SENSITIVE_OAUTH_PARAMS = {"state", "nonce", "code_challenge", "code_verifier", "code"}


# ─── Token Storage ──────────────────────────────────────────────────────────────


@dataclass
class SecureStorageEntry:
    """An entry in the secure token storage."""
    server_name: str
    server_url: str
    access_token: str = ""
    refresh_token: str | None = None
    expires_at: float = 0
    scope: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    step_up_scope: str | None = None
    discovery_state: dict[str, Any] | None = None


class SecureStorage:
    """In-memory secure storage for MCP OAuth tokens.

    In a production implementation, this would use the system keychain
    (Keyring on Linux, Keychain on macOS, Credential Manager on Windows).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, SecureStorageEntry] = {}

    def read(self) -> dict[str, SecureStorageEntry]:
        with self._lock:
            return dict(self._entries)

    def write(self, key: str, entry: SecureStorageEntry) -> None:
        with self._lock:
            self._entries[key] = entry

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# Global secure storage instance
_secure_storage = SecureStorage()


def get_secure_storage() -> SecureStorage:
    """Get the global secure storage instance."""
    return _secure_storage


def _make_server_key(server_name: str, server_url: str, headers: dict[str, str] | None = None) -> str:
    """Create a unique key for a server based on name and config hash."""
    import hashlib
    config_json = json.dumps({
        "url": server_url,
        "headers": headers or {},
    }, sort_keys=True)
    hash_val = hashlib.sha256(config_json.encode()).hexdigest()[:16]
    return f"{server_name}|{hash_val}"


# ─── OAuth Provider ──────────────────────────────────────────────────────────────


@dataclass
class McpAuthProvider:
    """OAuth provider for an MCP server.

    Implements RFC 7636 PKCE OAuth 2.0 flow.
    """
    server_name: str
    server_url: str
    client_id: str
    redirect_uri: str
    auth_url: str | None = None
    token_url: str | None = None
    scope: str | None = None
    # PKCE
    _code_verifier: str = field(default="")
    _state: str = field(default="")

    def __post_init__(self) -> None:
        self._code_verifier = secrets.token_urlsafe(64)
        self._state = secrets.token_urlsafe(32)

    def get_authorization_url(self, code_challenge: str) -> str:
        """Build the OAuth authorization URL."""
        if not self.auth_url:
            raise ValueError("No authorization URL configured")

        params: list[tuple[str, str]] = [
            ("response_type", "code"),
            ("client_id", self.client_id),
            ("redirect_uri", self.redirect_uri),
            ("code_challenge", code_challenge),
            ("code_challenge_method", "S256"),
            ("state", self._state),
        ]
        if self.scope:
            params.append(("scope", self.scope))

        return f"{self.auth_url}?{urlencode(params)}"

    def get_state(self) -> str:
        """Get the OAuth state parameter."""
        return self._state

    def exchange_code(self, authorization_code: str) -> dict[str, Any]:
        """Exchange authorization code for tokens.

        Returns the token response dict.
        """
        if not self.token_url:
            raise ValueError("No token URL configured")

        import hashlib
        import base64
        code_verifier = self._code_verifier
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()

        request_body = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": code_verifier,
        }

        body = json.dumps(request_body).encode("utf-8")
        req = http.client.HTTPSConnection(
            urlparse(self.server_url).netloc,
            timeout=30,
        )
        req.request(
            "POST",
            urlparse(self.token_url).path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        resp = req.getresponse()
        data = json.loads(resp.read().decode("utf-8"))

        if resp.status != 200:
            error = data.get("error", "unknown")
            error_desc = data.get("error_description", "")
            raise RuntimeError(f"Token exchange failed: {error} - {error_desc}")

        return data

    def refresh_tokens(self, refresh_token: str) -> dict[str, Any]:
        """Refresh the access token using a refresh token."""
        if not self.token_url:
            raise ValueError("No token URL configured")

        request_body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
        }

        body = json.dumps(request_body).encode("utf-8")
        req = http.client.HTTPSConnection(
            urlparse(self.server_url).netloc,
            timeout=30,
        )
        req.request(
            "POST",
            urlparse(self.token_url).path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        resp = req.getresponse()
        data = json.loads(resp.read().decode("utf-8"))

        if resp.status != 200:
            error = data.get("error", "unknown")
            error_desc = data.get("error_description", "")
            raise RuntimeError(f"Token refresh failed: {error} - {error_desc}")

        return data


# ─── Auth Callback Server ───────────────────────────────────────────────────────


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""

    handler_instance: "OAuthCallbackHandler | None" = None

    def do_GET(self) -> None:
        """Handle OAuth callback GET request."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]
        error_description = params.get("error_description", [None])[0]

        # Store callback data
        self.handler_instance = self

        if error:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<h1>Authentication Error</h1><p>{error}: {error_description}</p>".encode()
            )
            if OAuthCallbackServer._instance:
                OAuthCallbackServer._instance._error = error
                OAuthCallbackServer._instance._error_description = error_description
                OAuthCallbackServer._instance._event.set()
            return

        if code and state:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication Successful</h1><p>You can close this window.</p>")
            if OAuthCallbackServer._instance:
                OAuthCallbackServer._instance._code = code
                OAuthCallbackServer._instance._state = state
                OAuthCallbackServer._instance._event.set()
            return

        self.send_response(400)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Invalid Callback</h1><p>Missing code or state parameter.</p>")

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress log messages."""
        pass


class OAuthCallbackServer:
    """HTTP server to receive OAuth callbacks.

    Runs in a background thread and collects the authorization code.
    """

    _instance: "OAuthCallbackServer | None" = None

    def __init__(self, port: int | None = None):
        import socket
        if port is None:
            # Find available port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", 0))
                port = s.getsockname()[1]

        self._port = port
        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._event = threading.Event()
        self._code: str | None = None
        self._state: str | None = None
        self._error: str | None = None
        self._error_description: str | None = None

    def start(self) -> None:
        """Start the callback server in a background thread."""
        OAuthCallbackServer._instance = self
        OAuthCallbackHandler.handler_instance = None

        self._server = http.server.HTTPServer(
            ("127.0.0.1", self._port),
            OAuthCallbackHandler,
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()
        logger.debug("OAuth callback server started on port %d", self._port)

    def wait_for_callback(self, timeout: float = 300) -> tuple[str | None, str | None, str | None, str | None]:
        """Wait for the OAuth callback.

        Returns:
            tuple of (code, state, error, error_description)
        """
        self._event.wait(timeout=timeout)
        return self._code, self._state, self._error, self._error_description

    def stop(self) -> None:
        """Stop the callback server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        OAuthCallbackServer._instance = None

    @property
    def callback_url(self) -> str:
        """Get the callback URL for the OAuth flow."""
        return f"http://127.0.0.1:{self._port}/callback"


# ─── MCP Auth Service ──────────────────────────────────────────────────────────


class McpAuthService:
    """Main service for MCP OAuth authentication.

    Provides:
    - OAuth 2.0 + PKCE authorization code flow
    - Token storage and refresh
    - XAA (Cross-App Access) support
    - VSCode SDK MCP integration
    """

    def __init__(self, config: McpAuthConfig | None = None):
        """Initialize the MCP auth service.

        Args:
            config: MCP auth service configuration
        """
        self._config = config or McpAuthConfig()
        self._storage = get_secure_storage()

    @staticmethod
    def get_server_key(
        server_name: str,
        server_url: str,
        headers: dict[str, str] | None = None,
    ) -> str:
        """Get the unique storage key for a server."""
        return _make_server_key(server_name, server_url, headers)

    def get_stored_tokens(self, server_key: str) -> McpOAuthTokens | None:
        """Get stored tokens for a server.

        Args:
            server_key: Unique server key

        Returns:
            McpOAuthTokens if found, None otherwise
        """
        entry = self._storage.read().get(server_key)
        if not entry:
            return None

        return McpOAuthTokens(
            access_token=entry.access_token or None,
            refresh_token=entry.refresh_token,
            expires_at=entry.expires_at if entry.expires_at > 0 else None,
            scope=entry.scope,
            expires_in=int(entry.expires_at - time.time()) if entry.expires_at > 0 else None,
        )

    def store_tokens(
        self,
        server_key: str,
        server_name: str,
        server_url: str,
        tokens: McpOAuthTokens,
    ) -> None:
        """Store OAuth tokens for a server.

        Args:
            server_key: Unique server key
            server_name: Server name
            server_url: Server URL
            tokens: OAuth tokens to store
        """
        entry = SecureStorageEntry(
            server_name=server_name,
            server_url=server_url,
            access_token=tokens.access_token or "",
            refresh_token=tokens.refresh_token,
            expires_at=tokens.expires_at or 0,
            scope=tokens.scope,
        )
        self._storage.write(server_key, entry)
        logger.debug("Stored tokens for server %s", server_name)

    def clear_tokens(self, server_key: str) -> None:
        """Clear stored tokens for a server.

        Args:
            server_key: Unique server key
        """
        self._storage.delete(server_key)
        logger.debug("Cleared tokens for server key %s", server_key)

    def has_discovery_but_no_token(self, server_key: str) -> bool:
        """Check if server has discovery state but no valid tokens.

        Args:
            server_key: Unique server key

        Returns:
            True if discovery exists but no tokens
        """
        entry = self._storage.read().get(server_key)
        if not entry:
            return False
        return bool(entry.discovery_state) and not entry.access_token and not entry.refresh_token

    async def perform_oauth_flow(
        self,
        server_name: str,
        server_url: str,
        oauth_settings: McpOAuthSettings,
        on_auth_url: Callable[[str], None] | None = None,
        skip_browser_open: bool = False,
        abort_signal: threading.Event | None = None,
    ) -> McpAuthResult:
        """Perform the OAuth authorization code flow.

        Args:
            server_name: Name of the MCP server
            server_url: Base URL of the MCP server
            oauth_settings: OAuth settings for the server
            on_auth_url: Callback to receive the authorization URL
            skip_browser_open: If True, don't open the browser automatically
            abort_signal: Optional event to abort the flow

        Returns:
            McpAuthResult with success status and auth URL if needed
        """
        try:
            # Generate PKCE pair
            code_verifier, code_challenge = self._generate_pkce_pair()

            # Get callback URL
            port = oauth_settings.callback_port or self._config.default_callback_port
            callback_server = OAuthCallbackServer(port=port)
            callback_server.start()
            redirect_uri = callback_server.callback_url

            # Create provider
            provider = McpAuthProvider(
                server_name=server_name,
                server_url=server_url,
                client_id=oauth_settings.client_id or "",
                redirect_uri=redirect_uri,
                scope=oauth_settings.scope,
            )

            # Get authorization URL
            auth_url = provider.get_authorization_url(code_challenge)

            if on_auth_url:
                on_auth_url(auth_url)

            # In production, would open browser here
            if not skip_browser_open:
                import webbrowser
                webbrowser.open(auth_url)

            # Wait for callback
            code, state, error, error_desc = callback_server.wait_for_callback(
                timeout=self._config.callback_timeout_seconds,
            )
            callback_server.stop()

            if error:
                return McpAuthResult(
                    success=False,
                    error=error,
                    message=f"OAuth error: {error} - {error_desc or ''}",
                )

            if not code:
                return McpAuthResult(
                    success=False,
                    error="timeout",
                    message="OAuth callback timeout",
                )

            # Validate state
            if state != provider.get_state():
                return McpAuthResult(
                    success=False,
                    error="state_mismatch",
                    message="OAuth state mismatch - possible CSRF attack",
                )

            # Exchange code for tokens
            try:
                token_response = provider.exchange_code(code)
            except RuntimeError as e:
                return McpAuthResult(
                    success=False,
                    error="token_exchange_failed",
                    message=str(e),
                )

            # Store tokens
            tokens = McpOAuthTokens(
                access_token=token_response.get("access_token"),
                refresh_token=token_response.get("refresh_token"),
                expires_in=token_response.get("expires_in"),
                scope=token_response.get("scope"),
                token_type=token_response.get("token_type", "Bearer"),
            )
            if tokens.expires_in:
                tokens.expires_at = time.time() + tokens.expires_in

            server_key = self.get_server_key(server_name, server_url)
            self.store_tokens(server_key, server_name, server_url, tokens)

            return McpAuthResult(
                success=True,
                message=f"Successfully authenticated {server_name}",
            )

        except Exception as e:
            logger.exception("OAuth flow failed for %s", server_name)
            return McpAuthResult(
                success=False,
                error="unknown",
                message=str(e),
            )

    def refresh_server_tokens(
        self,
        server_key: str,
        server_name: str,
        server_url: str,
        oauth_settings: McpOAuthSettings,
    ) -> McpTokenRefreshResult:
        """Refresh the tokens for an MCP server.

        Args:
            server_key: Unique server key
            server_name: Server name
            server_url: Server URL
            oauth_settings: OAuth settings

        Returns:
            McpTokenRefreshResult with refreshed tokens or error
        """
        entry = self._storage.read().get(server_key)
        if not entry or not entry.refresh_token:
            return McpTokenRefreshResult(
                success=False,
                error="No refresh token available",
            )

        try:
            provider = McpAuthProvider(
                server_name=server_name,
                server_url=server_url,
                client_id=oauth_settings.client_id or entry.client_id or "",
                redirect_uri="http://localhost",  # Not used for refresh
                scope=oauth_settings.scope,
            )

            token_response = provider.refresh_tokens(entry.refresh_token)

            tokens = McpOAuthTokens(
                access_token=token_response.get("access_token"),
                refresh_token=token_response.get("refresh_token"),
                expires_in=token_response.get("expires_in"),
                scope=token_response.get("scope"),
            )
            if tokens.expires_in:
                tokens.expires_at = time.time() + tokens.expires_in

            self.store_tokens(server_key, server_name, server_url, tokens)

            return McpTokenRefreshResult(success=True, tokens=tokens)

        except Exception as e:
            logger.warning("Token refresh failed for %s: %s", server_name, e)
            return McpTokenRefreshResult(
                success=False,
                error=str(e),
                should_retry=True,  # Could retry with new auth
            )

    @staticmethod
    def _generate_pkce_pair() -> tuple[str, str]:
        """Generate a PKCE code verifier and challenge."""
        import hashlib
        import base64

        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return code_verifier, code_challenge


# ─── Module-level Config ───────────────────────────────────────────────────────


_mcp_auth_config: McpAuthConfig | None = None


def get_mcp_auth_config() -> McpAuthConfig:
    """Get the MCP auth service configuration."""
    global _mcp_auth_config
    if _mcp_auth_config is None:
        _mcp_auth_config = McpAuthConfig()
    return _mcp_auth_config


def set_mcp_auth_config(config: McpAuthConfig) -> None:
    """Set the MCP auth service configuration."""
    global _mcp_auth_config
    _mcp_auth_config = config


def get_mcp_auth_service() -> McpAuthService:
    """Get the global MCP auth service instance."""
    return McpAuthService(config=get_mcp_auth_config())
