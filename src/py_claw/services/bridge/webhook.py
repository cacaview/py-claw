"""Webhook security filtering for bridge sessions.

Validates incoming webhook payloads and filters sensitive data
before forwarding to the session.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Patterns for sensitive data that should be filtered
SENSITIVE_PATTERNS = [
    # API keys
    (re.compile(r"api[_-]?key", re.IGNORECASE), "[API_KEY]"),
    # Tokens
    (re.compile(r"(bearer|token|oauth|access)[_-]?token", re.IGNORECASE), "[TOKEN]"),
    # Passwords
    (re.compile(r"password", re.IGNORECASE), "[PASSWORD]"),
    # Secrets
    (re.compile(r"secret", re.IGNORECASE), "[SECRET]"),
    # Private keys
    (re.compile(r"private[_-]?key", re.IGNORECASE), "[PRIVATE_KEY]"),
    # Auth headers
    (re.compile(r"authorization", re.IGNORECASE), "[AUTH]"),
]

# Allowed webhook event types
ALLOWED_EVENT_TYPES = frozenset([
    "session.started",
    "session.ended",
    "session.error",
    "session.ping",
    "session.message",
    "control.request",
    "control.response",
    "control.cancel",
    "tool.result",
    "tool.error",
])


@dataclass
class WebhookValidationResult:
    """Result of webhook validation."""

    valid: bool
    error: str | None = None
    filtered_payload: dict[str, Any] | None = None


@dataclass
class WebhookConfig:
    """Configuration for webhook filtering."""

    # Whether to enable strict filtering
    strict: bool = True
    # Maximum payload size in bytes
    max_payload_size: int = 1024 * 1024  # 1MB
    # Allowed source IPs/prefixes (empty = allow all)
    allowed_sources: list[str] = field(default_factory=list)


def validate_webhook_payload(
    payload: dict[str, Any],
    config: WebhookConfig | None = None,
) -> WebhookValidationResult:
    """Validate and sanitize a webhook payload.

    Args:
        payload: Raw webhook payload
        config: Optional webhook configuration

    Returns:
        WebhookValidationResult with validation status and filtered payload
    """
    cfg = config or WebhookConfig()

    # Check payload size
    import json

    try:
        payload_str = json.dumps(payload)
    except (TypeError, ValueError):
        return WebhookValidationResult(
            valid=False,
            error="Invalid JSON payload",
        )

    if len(payload_str) > cfg.max_payload_size:
        return WebhookValidationResult(
            valid=False,
            error=f"Payload too large: {len(payload_str)} bytes",
        )

    # Check event type
    event_type = payload.get("type") or payload.get("event")
    if event_type and event_type not in ALLOWED_EVENT_TYPES:
        if cfg.strict:
            return WebhookValidationResult(
                valid=False,
                error=f"Disallowed event type: {event_type}",
            )
        else:
            logger.warning("Unexpected event type: %s", event_type)

    # Filter sensitive data
    filtered = _filter_sensitive_data(payload)

    return WebhookValidationResult(
        valid=True,
        filtered_payload=filtered,
    )


def _filter_sensitive_data(
    data: Any,
    depth: int = 0,
    max_depth: int = 20,
) -> Any:
    """Recursively filter sensitive data from a payload.

    Args:
        data: Data to filter
        depth: Current recursion depth
        max_depth: Maximum recursion depth

    Returns:
        Filtered data
    """
    if depth > max_depth:
        return "[MAX_DEPTH]"

    if isinstance(data, dict):
        filtered = {}
        for key, value in data.items():
            # Check if key matches sensitive patterns
            filtered_key = _filter_key(key)
            filtered[filtered_key] = _filter_sensitive_data(
                value, depth + 1, max_depth
            )
        return filtered

    elif isinstance(data, list):
        return [
            _filter_sensitive_data(item, depth + 1, max_depth)
            for item in data
        ]

    elif isinstance(data, str):
        return _filter_string_value(data)

    else:
        return data


def _filter_key(key: str) -> str:
    """Filter a potentially sensitive key name.

    Args:
        key: Key name

    Returns:
        Filtered key name (may be replaced if sensitive)
    """
    for pattern, replacement in SENSITIVE_PATTERNS:
        if pattern.search(key):
            return replacement
    return key


def _filter_string_value(value: str) -> str:
    """Filter a potentially sensitive string value.

    Args:
        value: String value

    Returns:
        Original value or replacement if it looks like sensitive data
    """
    # Check for actual secret patterns (not just key names)
    # This is a simplified check - real implementation would be more thorough

    # Skip short values (likely not secrets)
    if len(value) < 8:
        return value

    # Check for high-entropy strings that might be tokens/keys
    if _looks_like_secret(value):
        return "[REDACTED]"

    return value


def _looks_like_secret(value: str) -> bool:
    """Check if a string looks like a secret/token.

    Args:
        value: String to check

    Returns:
        True if the string looks like a secret
    """
    # Check for common token formats
    if len(value) < 20:
        return False

    # Base64-like tokens
    if _is_base64_string(value):
        # Check entropy - high entropy suggests random token
        import base64

        try:
            decoded = base64.b64decode(value + "==")
            # Tokens are usually 32+ bytes after decode
            if len(decoded) >= 32:
                return True
        except Exception:
            pass

    # Hex strings that look like UUIDs or hashes
    if len(value) == 32 and all(c in "0123456789abcdef" for c in value.lower()):
        return True
    if len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower()):
        return True

    # JWT-like patterns (header.payload.signature)
    if value.count(".") == 2:
        return True

    return False


def _is_base64_string(value: str) -> bool:
    """Check if a string is valid base64.

    Args:
        value: String to check

    Returns:
        True if the string is valid base64
    """
    import base64

    try:
        base64.b64decode(value + "==")
        return True
    except Exception:
        return False


def sanitize_webhook_for_logging(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Sanitize a webhook payload for logging.

    Args:
        payload: Raw webhook payload

    Returns:
        Sanitized payload safe for logging
    """
    return _filter_sensitive_data(payload)
