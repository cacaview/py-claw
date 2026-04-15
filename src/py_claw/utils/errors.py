"""
Error utilities for py_claw.

Provides common error handling patterns and error message extraction.
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any


@dataclass
class ErrorContext:
    """Context information for an error."""
    message: str
    error_type: str
    stack_trace: str | None = None
    cause: Any = None

    @classmethod
    def from_exception(cls, exc: BaseException) -> ErrorContext:
        """Create ErrorContext from an exception."""
        return cls(
            message=str(exc),
            error_type=type(exc).__name__,
            stack_trace=traceback.format_exc(),
            cause=exc.__cause__ if hasattr(exc, '__cause__') else None,
        )


def error_message(error: Any) -> str:
    """
    Extract a human-readable error message from any error object.

    Args:
        error: An exception, string, or other error object

    Returns:
        A string error message
    """
    if isinstance(error, Exception):
        return str(error)
    if isinstance(error, str):
        return error
    return repr(error)


def get_error_context(error: Any) -> ErrorContext:
    """
    Get detailed error context from any error object.

    Args:
        error: An exception, string, or other error object

    Returns:
        ErrorContext with details
    """
    if isinstance(error, Exception):
        return ErrorContext.from_exception(error)
    return ErrorContext(
        message=str(error) if error else "Unknown error",
        error_type=type(error).__name__ if error else "Unknown",
    )


class CliError(Exception):
    """Base exception for CLI-specific errors."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class ConfigError(CliError):
    """Configuration-related errors."""
    pass


class AuthError(CliError):
    """Authentication-related errors."""
    pass


class ToolError(CliError):
    """Tool execution errors."""
    pass


class PermissionError(CliError):
    """Permission-related errors."""
    pass


class NetworkError(CliError):
    """Network-related errors."""
    pass


class ValidationError(CliError):
    """Input validation errors."""
    pass


def is_user_facing_error(error: Exception) -> bool:
    """
    Determine if an error should be shown to the user.

    Args:
        error: The exception to check

    Returns:
        True if the error is user-facing
    """
    # Internal errors that shouldn't be shown directly
    internal_errors = (
        KeyboardInterrupt,
        SystemExit,
    )
    return not isinstance(error, internal_errors)


def format_error_for_display(error: Any, include_trace: bool = False) -> str:
    """
    Format an error for user-facing display.

    Args:
        error: The error to format
        include_trace: Whether to include stack trace

    Returns:
        Formatted error string
    """
    msg = error_message(error)

    if include_trace and isinstance(error, Exception):
        trace_str = traceback.format_exception(type(error), error, error.__traceback__)
        return f"{msg}\n\nStack trace:\n{''.join(trace_str)}"

    return msg
