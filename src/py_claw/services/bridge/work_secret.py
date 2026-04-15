"""Work secret handling for CCR v2 bridge.

Provides work secret decoding, SDK URL building, and worker registration.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any


@dataclass
class WorkSecret:
    """Work secret containing session ingress credentials."""

    version: int
    session_ingress_token: str
    api_base_url: str


def decode_work_secret(secret: str) -> WorkSecret:
    """Decode a base64url-encoded work secret and validate its version.

    Args:
        secret: Base64url-encoded work secret string.

    Returns:
        Decoded WorkSecret.

    Raises:
        ValueError: If version is unsupported or required fields are missing.
    """
    try:
        # Handle base64url padding
        padded = secret + "=" * (4 - len(secret) % 4) if len(secret) % 4 else secret
        json_str = base64.urlsafe_b64decode(padded).decode("utf-8")
        parsed = json.loads(json_str)
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"Failed to decode work secret: {e}") from e

    if not isinstance(parsed, dict):
        raise ValueError("Work secret must be a JSON object")

    version = parsed.get("version")
    if version != 1:
        raise ValueError(f"Unsupported work secret version: {version}")

    session_ingress_token = parsed.get("session_ingress_token")
    if not session_ingress_token or not isinstance(session_ingress_token, str):
        raise ValueError("Invalid work secret: missing or empty session_ingress_token")

    api_base_url = parsed.get("api_base_url")
    if not isinstance(api_base_url, str):
        raise ValueError("Invalid work secret: missing api_base_url")

    return WorkSecret(
        version=version,
        session_ingress_token=session_ingress_token,
        api_base_url=api_base_url,
    )


def build_sdk_url(api_base_url: str, session_id: str) -> str:
    """Build a WebSocket SDK URL from API base URL and session ID.

    Uses /v2/ for localhost (direct to session-ingress) and /v1/ for
    production (Envoy rewrites /v1/ -> /v2/).

    Args:
        api_base_url: The API base URL (https://api.claude.ai or similar).
        session_id: The session ID.

    Returns:
        WebSocket SDK URL.
    """
    is_localhost = "localhost" in api_base_url or "127.0.0.1" in api_base_url
    protocol = "ws" if is_localhost else "wss"
    version = "v2" if is_localhost else "v1"

    # Strip protocol and trailing slashes
    host = re.sub(r"^https?://", "", api_base_url).rstrip("/")

    return f"{protocol}://{host}/{version}/session_ingress/ws/{session_id}"


def build_ccr_v2_sdk_url(api_base_url: str, session_id: str) -> str:
    """Build a CCR v2 session URL from API base URL and session ID.

    Returns an HTTP(S) URL pointing to /v1/code/sessions/{id}.

    Args:
        api_base_url: The API base URL.
        session_id: The session ID.

    Returns:
        CCR v2 SDK URL.
    """
    base = api_base_url.rstrip("/")
    return f"{base}/v1/code/sessions/{session_id}"


def same_session_id(a: str, b: str) -> bool:
    """Compare two session IDs regardless of tagged-ID prefix.

    Handles both {tag}_{body} and {tag}_staging_{body} formats.
    CCR v2 compat layer returns session_* but infrastructure uses cse_*.

    Args:
        a: First session ID.
        b: Second session ID.

    Returns:
        True if both IDs refer to the same session.
    """
    if a == b:
        return True

    # Body is everything after last underscore
    a_body = a[a.rfind("_") + 1:]
    b_body = b[b.rfind("_") + 1:]

    # Guard against bare UUIDs (no underscore)
    # Require minimum length to avoid accidental matches
    return len(a_body) >= 4 and a_body == b_body


async def register_worker(
    session_url: str,
    access_token: str,
    timeout_ms: int = 10_000,
) -> int:
    """Register this bridge as the worker for a CCR v2 session.

    Returns the worker_epoch, which must be passed to the child CC
    process so its CCRClient can include it in heartbeat/state/event requests.

    Args:
        session_url: The session URL (from POST /v1/code/sessions/{id}/bridge).
        access_token: OAuth access token.
        timeout_ms: Request timeout in milliseconds.

    Returns:
        The worker_epoch from the server.

    Raises:
        ValueError: If response is invalid.
    """
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{session_url}/worker/register",
            json={},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            timeout=timeout_ms / 1000,
        )
        response.raise_for_status()

        data = response.json()
        raw_epoch = data.get("worker_epoch")

        # protojson serializes int64 as string in JS
        epoch = int(raw_epoch) if isinstance(raw_epoch, str) else raw_epoch

        if not isinstance(epoch, int) or not isinstance(epoch, int):
            raise ValueError(f"register_worker: invalid worker_epoch in response: {data}")

        return epoch
