"""JWT utilities for bridge authentication."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

# Token refresh buffer: request a new token 5 minutes before expiry
TOKEN_REFRESH_BUFFER_SECONDS = 5 * 60

# Fallback refresh interval when the new token's expiry is unknown (30 minutes)
FALLBACK_REFRESH_INTERVAL_SECONDS = 30 * 60

# Max consecutive failures before giving up on the refresh chain
MAX_REFRESH_FAILURES = 3

# Retry delay when getAccessToken returns undefined (60 seconds)
REFRESH_RETRY_DELAY_SECONDS = 60


def decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode a JWT's payload segment without verifying the signature.

    Strips the 'sk-ant-si-' session-ingress prefix if present.
    Returns the parsed JSON payload as a dict, or None if the
    token is malformed or the payload is not valid JSON.

    Args:
        token: JWT token string (with or without 'sk-ant-si-' prefix)

    Returns:
        Decoded payload dict, or None if unparseable.
    """
    jwt = token
    if token.startswith("sk-ant-si-"):
        jwt = token[len("sk-ant-si-") :]

    parts = jwt.split(".")
    if len(parts) != 3 or not parts[1]:
        return None

    try:
        payload_str = base64.urlsafe_b64decode(parts[1] + "==").decode("utf-8")
        return json.loads(payload_str)
    except (ValueError, json.JSONDecodeError):
        return None


def decode_jwt_expiry(token: str) -> int | None:
    """Decode the 'exp' (expiry) claim from a JWT without verifying the signature.

    Args:
        token: JWT token string

    Returns:
        The 'exp' value in Unix seconds, or None if unparseable.
    """
    payload = decode_jwt_payload(token)
    if payload is not None and isinstance(payload, dict) and "exp" in payload:
        exp = payload["exp"]
        if isinstance(exp, (int, float)):
            return int(exp)
    return None


@dataclass
class TokenRefreshScheduler:
    """Scheduler for proactive token refresh before expiry.

    When a token is about to expire, the scheduler calls `on_refresh` with the
    session ID and the bridge's OAuth access token. The caller is responsible
    for delivering the token to the appropriate transport.
    """

    schedule: Callable[[str, str], None]
    schedule_from_expires_in: Callable[[str, int], None]
    cancel: Callable[[str], None]
    cancel_all: Callable[[], None]


def create_token_refresh_scheduler(
    get_access_token: Callable[[], str | None | Awaitable[str | None]],
    on_refresh: Callable[[str, str], None],
    label: str,
    refresh_buffer_seconds: float = TOKEN_REFRESH_BUFFER_SECONDS,
) -> TokenRefreshScheduler:
    """Create a token refresh scheduler that proactively refreshes session tokens.

    Args:
        get_access_token: Async or sync function that returns the current OAuth token.
        on_refresh: Callback(session_id, oauth_token) called when refresh is needed.
        label: Label for logging/debugging.
        refresh_buffer_seconds: How long before expiry to fire refresh. Default 5 min.

    Returns:
        TokenRefreshScheduler with schedule/cancel/cancel_all methods.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    timers: dict[str, object] = {}  # session_id -> timer
    failure_counts: dict[str, int] = {}
    generations: dict[str, int] = {}  # session_id -> generation counter
    _executor = ThreadPoolExecutor(max_workers=4)

    def _next_generation(session_id: str) -> int:
        gen = generations.get(session_id, 0) + 1
        generations[session_id] = gen
        return gen

    def _clear_timer(session_id: str) -> None:
        timer = timers.pop(session_id, None)
        if timer is not None:
            # Cancel is handled by asyncio handling in _do_refresh
            pass

    def _run_async(coro: Awaitable[Any]) -> None:
        """Run coroutine in a way that works for both sync and async contexts."""
        try:
            loop = asyncio.get_running_loop()
            # Already running in async context
            asyncio.create_task(coro)
        except RuntimeError:
            # No running loop, use executor
            def _sync_wrapper() -> None:
                asyncio.run(coro)
            _executor.submit(_sync_wrapper)

    async def _do_refresh(session_id: str, gen: int) -> None:
        """Async refresh logic with retry handling."""
        oauth_token: str | None = None
        try:
            result = get_access_token()
            if asyncio.iscoroutine(result):
                oauth_token = await result
            else:
                oauth_token = result
        except Exception:
            oauth_token = None

        # Check if session was cancelled or rescheduled
        if generations.get(session_id) != gen:
            return

        if oauth_token is None:
            failures = failure_counts.get(session_id, 0) + 1
            failure_counts[session_id] = failures
            if failures < MAX_REFRESH_FAILURES:
                # Schedule retry
                await asyncio.sleep(REFRESH_RETRY_DELAY_SECONDS)
                if generations.get(session_id) == gen:
                    asyncio.create_task(_do_refresh(session_id, gen))
            return

        # Reset failure counter on success
        failure_counts.pop(session_id, None)
        on_refresh(session_id, oauth_token)

        # Schedule follow-up refresh
        await asyncio.sleep(FALLBACK_REFRESH_INTERVAL_SECONDS)
        if generations.get(session_id) == gen:
            asyncio.create_task(_do_refresh(session_id, gen))

    def schedule(session_id: str, token: str) -> None:
        """Schedule refresh based on JWT expiry."""
        expiry = decode_jwt_expiry(token)
        if expiry is None:
            # Token is not a decodable JWT (e.g. an OAuth token).
            # Keep any existing timer.
            return

        _clear_timer(session_id)
        gen = _next_generation(session_id)

        delay_seconds = expiry - time.time() - refresh_buffer_seconds
        if delay_seconds <= 0:
            # Already expired or within buffer, refresh immediately
            _run_async(_do_refresh(session_id, gen))
            return

        # Schedule timer
        async def _scheduled_refresh() -> None:
            await asyncio.sleep(delay_seconds)
            if generations.get(session_id) == gen:
                await _do_refresh(session_id, gen)

        timers[session_id] = _scheduled_refresh
        _run_async(_scheduled_refresh)

    def schedule_from_expires_in(session_id: str, expires_in_seconds: int) -> None:
        """Schedule refresh using an explicit TTL rather than decoding JWT."""
        _clear_timer(session_id)
        gen = _next_generation(session_id)

        # Clamp to 30s floor
        delay_seconds = max(expires_in_seconds - refresh_buffer_seconds, 30)

        async def _scheduled_refresh() -> None:
            await asyncio.sleep(delay_seconds)
            if generations.get(session_id) == gen:
                await _do_refresh(session_id, gen)

        timers[session_id] = _scheduled_refresh
        _run_async(_scheduled_refresh)

    def cancel(session_id: str) -> None:
        """Cancel refresh for a session."""
        _next_generation(session_id)
        _clear_timer(session_id)
        failure_counts.pop(session_id, None)

    def cancel_all() -> None:
        """Cancel all refresh timers."""
        for session_id in list(generations.keys()):
            _next_generation(session_id)
        timers.clear()
        failure_counts.clear()

    return TokenRefreshScheduler(
        schedule=schedule,
        schedule_from_expires_in=schedule_from_expires_in,
        cancel=cancel,
        cancel_all=cancel_all,
    )


def sign_jwt_payload(
    payload: dict[str, Any],
    secret: str,
    algorithm: str = "HS256",
    expires_in_seconds: int | None = None,
) -> str:
    """Sign a payload to create a JWT token.

    Args:
        payload: The payload to sign.
        secret: The secret key for signing.
        algorithm: The signing algorithm (default HS256).
        expires_in_seconds: Optional expiry time in seconds from now.

    Returns:
        The signed JWT token string.
    """
    import hmac
    import hashlib
    import json as json_lib

    if expires_in_seconds is not None:
        payload = dict(payload)
        payload["exp"] = int(time.time() + expires_in_seconds)

    header = {"alg": algorithm, "typ": "JWT"}
    header_encoded = base64.urlsafe_b64encode(
        json_lib.dumps(header).encode()
    ).rstrip(b"=").decode()
    payload_encoded = base64.urlsafe_b64encode(
        json_lib.dumps(payload).encode()
    ).rstrip(b"=").decode()

    signature = hmac.new(
        secret.encode(),
        f"{header_encoded}.{payload_encoded}".encode(),
        hashlib.sha256,
    ).digest()
    signature_encoded = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

    return f"{header_encoded}.{payload_encoded}.{signature_encoded}"


def verify_jwt_signature(
    token: str,
    secret: str,
    algorithms: tuple[str, ...] = ("HS256",),
) -> bool:
    """Verify a JWT signature.

    Args:
        token: The JWT token to verify.
        secret: The secret key for verification.
        algorithms: Acceptable signing algorithms.

    Returns:
        True if signature is valid, False otherwise.
    """
    import hmac
    import hashlib
    import json as json_lib

    parts = token.split(".")
    if len(parts) != 3:
        return False

    header_encoded, payload_encoded, signature_encoded = parts

    # Decode and check header
    try:
        header = json_lib.loads(
            base64.urlsafe_b64decode(header_encoded + "==").decode()
        )
    except (ValueError, json_lib.JSONDecodeError):
        return False

    algorithm = header.get("alg", "")
    if algorithm not in algorithms:
        return False

    # Compute expected signature
    expected = hmac.new(
        secret.encode(),
        f"{header_encoded}.{payload_encoded}".encode(),
        hashlib.sha256,
    ).digest()
    expected_encoded = base64.urlsafe_b64encode(expected).rstrip(b"=").decode()

    return hmac.compare_digest(signature_encoded, expected_encoded)
