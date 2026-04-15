from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class APIError(Exception):
    """Base API error."""

    code: str
    message: str
    status_code: int | None = None
    retryable: bool = False
    should_fallback: bool = False

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class AuthenticationError(APIError):
    """Authentication failed (401)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            code="authentication_error",
            message=message,
            status_code=401,
            retryable=False,
        )


class RateLimitError(APIError):
    """Rate limit exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            code="rate_limit_error",
            message=message,
            status_code=429,
            retryable=True,
        )


class OverloadedError(APIError):
    """Server overloaded (529 or 429 with retry_after)."""

    def __init__(self, message: str = "Server overloaded"):
        super().__init__(
            code="overloaded_error",
            message=message,
            status_code=529,
            retryable=True,
        )


class PromptTooLongError(APIError):
    """Prompt is too long (400 with specific error)."""

    def __init__(
        self,
        message: str = "Prompt is too long",
        tokens_over: int | None = None,
    ):
        super().__init__(
            code="prompt_too_long",
            message=message,
            status_code=400,
            retryable=False,
        )
        self.tokens_over = tokens_over


class InvalidRequestError(APIError):
    """Invalid request (400)."""

    def __init__(self, message: str = "Invalid request"):
        super().__init__(
            code="invalid_request",
            message=message,
            status_code=400,
            retryable=False,
        )


class ForbiddenError(APIError):
    """Forbidden (403)."""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(
            code="forbidden_error",
            message=message,
            status_code=403,
            retryable=False,
        )


class NotFoundError(APIError):
    """Not found (404)."""

    def __init__(self, message: str = "Not found"):
        super().__init__(
            code="not_found_error",
            message=message,
            status_code=404,
            retryable=False,
        )


class InternalError(APIError):
    """Internal server error (500)."""

    def __init__(self, message: str = "Internal server error"):
        super().__init__(
            code="internal_error",
            message=message,
            status_code=500,
            retryable=True,
        )


class NetworkError(APIError):
    """Network connectivity error."""

    def __init__(self, message: str = "Network error"):
        super().__init__(
            code="network_error",
            message=message,
            status_code=None,
            retryable=True,
        )


def classify_error(
    status_code: int,
    response_body: str | None = None,
    error_data: dict[str, Any] | None = None,
) -> APIError:
    """Classify an HTTP error into a specific APIError type.

    Args:
        status_code: HTTP status code
        response_body: Raw response body text
        error_data: Parsed error response dict

    Returns:
        Appropriate APIError subclass
    """
    message = ""
    if error_data:
        message = error_data.get("error", {}).get("message", "")
    elif response_body:
        message = response_body[:200]

    normalized_message = message.lower()

    if status_code == 401:
        if "unauthorized" in normalized_message or "auth" in normalized_message:
            return AuthenticationError(message or "Unauthorized")
        return AuthenticationError(message or "Authentication failed")

    if status_code == 403:
        return ForbiddenError(message or "Forbidden")

    if status_code == 404:
        return NotFoundError(message or "Not found")

    if status_code == 400:
        # Check for prompt too long
        if "prompt" in normalized_message and "long" in normalized_message:
            tokens_over = None
            if error_data:
                # Try to extract token count from error
                type_str = error_data.get("type", "")
                if "token" in type_str:
                    # e.g., "token_limit_exceeded"
                    tokens_over = None  # Would need to parse from message
            return PromptTooLongError(message or "Prompt is too long", tokens_over)
        return InvalidRequestError(message or "Bad request")

    if status_code == 429:
        # Check for retry_after header or overloaded
        if "overloaded" in normalized_message or "retry" in normalized_message:
            return OverloadedError(message or "Server overloaded")
        return RateLimitError(message or "Rate limit exceeded")

    if status_code == 500:
        return InternalError(message or "Internal server error")

    if status_code == 529:
        return OverloadedError(message or "Server overloaded")

    # Generic error
    return APIError(
        code="unknown_error",
        message=message or f"HTTP {status_code}",
        status_code=status_code,
        retryable=status_code >= 500,
    )


# Error messages that indicate prompt too long
PROMPT_TOO_LONG_MESSAGES = frozenset({
    "prompt is too long",
    "maximum context length",
    "token limit",
    "too many tokens",
    "input too long",
    "context_length_exceeded",
    "token_limit_exceeded",
    "maximum tokens",
})


def is_prompt_too_long(error: APIError) -> bool:
    """Check if an error is a prompt-too-long error."""
    if isinstance(error, PromptTooLongError):
        return True
    if error.code == "invalid_request":
        return any(msg in error.message.lower() for msg in PROMPT_TOO_LONG_MESSAGES)
    return False
