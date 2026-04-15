from __future__ import annotations

import json
import time
from urllib import error as urllib_error
from urllib import request as urllib_request

from py_claw.services.oauth.config import get_oauth_config
from py_claw.services.oauth.types import OAuthProfile, OAuthTokens


def build_auth_url(
    *,
    code_challenge: str,
    state: str,
    port: int,
    is_manual: bool = False,
    login_with_claude_ai: bool = False,
    org_uuid: str | None = None,
    login_hint: str | None = None,
    login_method: str | None = None,
) -> str:
    """Build the OAuth authorization URL."""
    config = get_oauth_config()

    if login_with_claude_ai:
        base_url = "https://claude.com/cai/oauth/authorize"
    else:
        base_url = config.authorize_url

    params: list[tuple[str, str]] = [
        ("code", "true"),  # Tell login page to show Claude Max upsell
        ("client_id", config.client_id),
        ("response_type", "code"),
        ("redirect_uri", config.manual_redirect_url if is_manual else f"http://localhost:{port}/callback"),
        ("code_challenge", code_challenge),
        ("code_challenge_method", "S256"),
        ("state", state),
    ]

    if org_uuid:
        params.append(("orgUUID", org_uuid))
    if login_hint:
        params.append(("login_hint", login_hint))
    if login_method:
        params.append(("login_method", login_method))

    # Build URL with query params
    from urllib.parse import urlencode
    url = f"{base_url}?{urlencode(params)}"
    return url


def exchange_code_for_tokens(
    authorization_code: str,
    state: str,
    code_verifier: str,
    port: int,
    use_manual_redirect: bool = False,
    expires_in: int | None = None,
) -> OAuthTokens:
    """Exchange authorization code for OAuth tokens."""
    config = get_oauth_config()

    redirect_uri = config.manual_redirect_url if use_manual_redirect else f"http://localhost:{port}/callback"

    request_body: dict[str, str | int] = {
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": redirect_uri,
        "client_id": config.client_id,
        "code_verifier": code_verifier,
        "state": state,
    }

    if expires_in is not None:
        request_body["expires_in"] = expires_in

    request = urllib_request.Request(
        config.token_url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 401:
            raise ValueError("Authentication failed: Invalid authorization code")
        raise RuntimeError(f"Token exchange failed ({exc.code}): {body}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Token exchange failed: {exc.reason}") from exc

    tokens = OAuthTokens(
        access_token=data.get("access_token"),
        refresh_token=data.get("refresh_token"),
        token_type=data.get("token_type"),
        expires_in=data.get("expires_in"),
        scope=data.get("scope"),
        extra=data,
    )

    if data.get("expires_in"):
        tokens.expires_at = time.time() + data["expires_in"]

    return tokens


def refresh_oauth_token(
    refresh_token: str,
    scopes: list[str] | None = None,
) -> OAuthTokens:
    """Refresh an OAuth access token using a refresh token."""
    config = get_oauth_config()

    # Default to full Claude AI scopes
    if scopes is None:
        scopes = ["openid", "profile", "email", "offline_access", "https://auth.anthropic.com/scope/claude"]

    request_body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": config.client_id,
        "scope": " ".join(scopes),
    }

    request = urllib_request.Request(
        config.token_url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Token refresh failed ({exc.code}): {body}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Token refresh failed: {exc.reason}") from exc

    tokens = OAuthTokens(
        access_token=data.get("access_token"),
        refresh_token=data.get("refresh_token") or refresh_token,
        token_type=data.get("token_type"),
        expires_in=data.get("expires_in"),
        scope=data.get("scope"),
        extra=data,
    )

    if data.get("expires_in"):
        tokens.expires_at = time.time() + data["expires_in"]

    return tokens


def fetch_profile_info(access_token: str) -> OAuthProfile:
    """Fetch user profile information using an access token."""
    config = get_oauth_config()

    # The profile endpoint is the user's info endpoint
    request = urllib_request.Request(
        "https://api.anthropic.com/v1/oauth/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )

    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError:
        # If userinfo endpoint fails, return empty profile
        return OAuthProfile()
    except urllib_error.URLError:
        return OAuthProfile()

    return OAuthProfile.from_response(data)
