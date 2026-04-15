"""Debug logging utilities for bridge.

Provides debug logging, secret redaction, and error formatting
for bridge operations.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Limit debug message size to 2000 chars
DEBUG_MSG_LIMIT = 2000

# Field names that contain secrets
SECRET_FIELD_NAMES = [
    "session_ingress_token",
    "environment_secret",
    "access_token",
    "secret",
    "token",
]

# Pattern to find secret fields in JSON strings
SECRET_PATTERN = re.compile(
    r'"(' + "|".join(SECRET_FIELD_NAMES) + r')"\s*:\s*"([^"]*)"',
    re.IGNORECASE,
)

# Minimum length for a value to be considered a secret
REDACT_MIN_LENGTH = 16


def redact_secrets(s: str) -> str:
    """Redact secret values from a string.

    Replaces secret field values with a partial redaction showing
    first 8 and last 4 characters.

    Args:
        s: String potentially containing secrets.

    Returns:
        String with secrets redacted.
    """
    def replacer(match: re.Match) -> str:
        field = match.group(1)
        value = match.group(2)
        if len(value) < REDACT_MIN_LENGTH:
            return f'"{field}":"[REDACTED]"'
        redacted = f"{value[:8]}...{value[-4:]}"
        return f'"{field}":"{redacted}"'

    return SECRET_PATTERN.sub(replacer, s)


def debug_truncate(s: str) -> str:
    """Truncate a string for debug logging.

    Collapses newlines and truncates to DEBUG_MSG_LIMIT.

    Args:
        s: String to truncate.

    Returns:
        Truncated string with length info if truncated.
    """
    flat = s.replace("\n", "\\n")
    if len(flat) <= DEBUG_MSG_LIMIT:
        return flat
    return flat[:DEBUG_MSG_LIMIT] + f"... ({len(flat)} chars)"


def debug_body(data: Any) -> str:
    """Truncate a JSON-serializable value for debug logging.

    Args:
        data: Value to serialize and truncate.

    Returns:
        Redacted and truncated string representation.
    """
    raw = json.dumps(data) if not isinstance(data, str) else data
    s = redact_secrets(raw)
    if len(s) <= DEBUG_MSG_LIMIT:
        return s
    return s[:DEBUG_MSG_LIMIT] + f"... ({len(s)} chars)"


def describe_axios_error(err: Exception) -> str:
    """Extract a descriptive error message from an axios error.

    For HTTP errors, appends the server's response body message if available.

    Args:
        err: Exception (potentially with response attribute).

    Returns:
        Error message with additional detail if available.
    """
    msg = str(err)

    # Check for response attribute (axios-style error)
    if hasattr(err, "response"):
        response = err.response
        if response and isinstance(response, dict):
            data = response.get("data")
            if data and isinstance(data, dict):
                detail = data.get("message") or data.get("error", {}).get("message")
                if detail:
                    return f"{msg}: {detail}"

    return msg


def extract_http_status(err: Exception) -> int | None:
    """Extract HTTP status code from an error.

    Args:
        err: Exception potentially with response.status.

    Returns:
        HTTP status code, or None if not found.
    """
    if hasattr(err, "response"):
        response = err.response
        if isinstance(response, dict):
            status = response.get("status")
            if isinstance(status, int):
                return status
    return None


def extract_error_detail(data: Any) -> str | None:
    """Pull a human-readable message from an API error response.

    Args:
        data: Response data to extract from.

    Returns:
        Error message, or None if not found.
    """
    if not isinstance(data, dict):
        return None

    if "message" in data and isinstance(data["message"], str):
        return data["message"]

    error = data.get("error")
    if error and isinstance(error, dict) and "message" in error:
        return error["message"]

    return None


def log_bridge_skip(reason: str, debug_msg: str | None = None, v2: bool = False) -> None:
    """Log a bridge init skip.

    Args:
        reason: Short reason code for analytics.
        debug_msg: Optional debug message to log.
        v2: Whether this is a v2 bridge skip.
    """
    import logging

    logger = logging.getLogger("py_claw.bridge")

    if debug_msg:
        logger.debug(debug_msg)

    # In a full implementation, would emit analytics event
    # log_event('tengu_bridge_repl_skipped', {reason, v2})
