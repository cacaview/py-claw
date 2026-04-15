from __future__ import annotations

import threading
import time
from typing import Callable

from py_claw.services.oauth.auth import AuthCodeListener, find_available_port
from py_claw.services.oauth.client import build_auth_url, exchange_code_for_tokens, fetch_profile_info, refresh_oauth_token
from py_claw.services.oauth.config import get_oauth_config
from py_claw.services.oauth.crypto import generate_code_challenge, generate_code_verifier, generate_state
from py_claw.services.oauth.types import OAuthProfile, OAuthTokens


class OAuthService:
    """OAuth 2.0 authorization code flow service with PKCE support.

    Handles the complete OAuth flow:
    1. Generate PKCE code verifier and challenge
    2. Start local callback listener
    3. Open browser for user authentication
    4. Exchange authorization code for tokens
    5. Fetch user profile
    6. Support token refresh

    Supports two authentication flows:
    - Automatic: Opens browser, listens on localhost for redirect
    - Manual: Shows URL for manual code copy-paste (non-browser environments)
    """

    def __init__(self) -> None:
        self._code_verifier: str | None = None
        self._state: str | None = None
        self._listener: AuthCodeListener | None = None
        self._manual_code_resolver: Callable[[str], None] | None = None
        self._port: int | None = None
        self._tokens: OAuthTokens | None = None
        self._profile: OAuthProfile | None = None

    def start_flow(
        self,
        open_browser: Callable[[str], None] | None = None,
        *,
        login_with_claude_ai: bool = False,
        org_uuid: str | None = None,
        login_hint: str | None = None,
        login_method: str | None = None,
        expires_in: int | None = None,
        skip_browser_open: bool = False,
    ) -> OAuthTokens:
        """Start the OAuth authorization flow.

        Args:
            open_browser: Callback to open the browser with the auth URL.
                If None, only the manual URL is provided.
            login_with_claude_ai: Use claude.ai OAuth instead of console.
            org_uuid: Optional organization UUID to pre-select.
            login_hint: Optional email to pre-fill on login page.
            login_method: Optional specific login method (e.g., 'sso', 'google').
            expires_in: Optional token expiry override in seconds.
            skip_browser_open: If True, don't open browser; caller handles URL display.

        Returns:
            OAuthTokens with access/refresh tokens and profile info.

        Raises:
            ValueError: If OAuth flow fails (invalid state, error in callback, etc.)
            TimeoutError: If the OAuth callback times out.
        """
        # Generate PKCE values and state
        self._code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(self._code_verifier)
        self._state = generate_state()

        # Start auth code listener
        self._listener = AuthCodeListener()
        self._port = find_available_port()

        # Build auth URLs for manual and automatic flows
        opts = dict(
            code_challenge=code_challenge,
            state=self._state,
            port=self._port,
            login_with_claude_ai=login_with_claude_ai,
            org_uuid=org_uuid,
            login_hint=login_hint,
            login_method=login_method,
        )
        manual_url = build_auth_url(**opts, is_manual=True)
        automatic_url = build_auth_url(**opts, is_manual=False)

        # Open browser for automatic flow, show manual URL to user
        if open_browser and not skip_browser_open:
            open_browser(automatic_url)
        else:
            # Caller will handle displaying the URLs
            pass

        # Wait for callback on the automatic flow (localhost listener)
        authorization_code = self._wait_for_callback()

        # Determine if automatic flow was used (code received before manual)
        is_automatic = self._listener is not None

        # Exchange code for tokens
        try:
            tokens = exchange_code_for_tokens(
                authorization_code=authorization_code,
                state=self._state,
                code_verifier=self._code_verifier,
                port=self._port,
                use_manual_redirect=not is_automatic,
                expires_in=expires_in,
            )

            # Fetch profile info
            if tokens.access_token:
                profile = fetch_profile_info(tokens.access_token)
            else:
                profile = OAuthProfile()

            # Store tokens and profile for later retrieval
            self._tokens = tokens
            self._profile = profile

            return tokens

        finally:
            self._cleanup()

    def _wait_for_callback(self) -> str:
        """Wait for the OAuth callback and return the authorization code."""
        if self._listener is None or self._state is None:
            raise RuntimeError("OAuth flow not started")

        self._port = self._listener.start()
        state = self._state

        # Wait for callback
        import time
        for _ in range(300):  # 30 seconds
            if self._listener._authorization_code:
                if self._listener._state != state:
                    raise ValueError("State mismatch in OAuth callback")
                return self._listener._authorization_code
            if self._listener._error:
                raise ValueError(f"OAuth error: {self._listener._error}")
            time.sleep(0.1)

        raise TimeoutError("OAuth callback timeout")

    def handle_manual_code(self, authorization_code: str) -> None:
        """Handle manual auth code input when user pastes the code.

        This is called when the user manually copies and pastes the auth code
        instead of using the browser redirect flow.
        """
        if self._listener:
            self._listener._authorization_code = authorization_code

    def refresh_token(self, tokens: OAuthTokens, scopes: list[str] | None = None) -> OAuthTokens:
        """Refresh an access token using the refresh token.

        Args:
            tokens: The current OAuth tokens containing a refresh token.
            scopes: Optional specific scopes to request. Defaults to full Claude AI scopes.

        Returns:
            New OAuthTokens with refreshed access token.

        Raises:
            ValueError: If no refresh token is available.
            RuntimeError: If the refresh fails.
        """
        if not tokens.refresh_token:
            raise ValueError("No refresh token available")

        return refresh_oauth_token(tokens.refresh_token, scopes)

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self._listener:
            self._listener.close()
            self._listener = None
        self._code_verifier = None
        self._state = None
        self._port = None
        self._manual_code_resolver = None

    def get_tokens(self) -> OAuthTokens | None:
        """Get stored OAuth tokens.

        Returns tokens from the last successful authentication,
        or None if not authenticated.
        """
        return self._tokens

    def get_profile(self) -> OAuthProfile | None:
        """Get stored OAuth profile.

        Returns profile from the last successful authentication,
        or None if not authenticated.
        """
        return self._profile

    def is_authenticated(self) -> bool:
        """Check if authenticated with OAuth."""
        return self._tokens is not None and self._tokens.access_token is not None


# ============================================================================
# Global singleton
# ============================================================================

_oauth_service: OAuthService | None = None


def get_oauth_service() -> OAuthService:
    """Get the global OAuth service instance."""
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = OAuthService()
    return _oauth_service


def reset_oauth_service() -> None:
    """Reset the global OAuth service (for testing)."""
    global _oauth_service
    _oauth_service = None
