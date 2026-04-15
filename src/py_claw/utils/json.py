"""
JSON utilities for py_claw.

Provides JSON parsing, serialization, and validation helpers.
"""
from __future__ import annotations

import json
from typing import Any, TypeVar

T = TypeVar("T")


def json_parse(text: str) -> Any:
    """
    Parse JSON text with better error messages.

    Args:
        text: JSON string to parse

    Returns:
        Parsed JSON object

    Raises:
        json.JSONDecodeError: If the JSON is invalid
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Invalid JSON: {e.msg} at position {e.pos}",
            e.doc,
            e.pos,
        ) from e


def json_stringify(obj: Any, indent: int | None = None) -> str:
    """
    Serialize an object to JSON string.

    Args:
        obj: Object to serialize
        indent: Optional indentation level

    Returns:
        JSON string
    """
    return json.dumps(obj, indent=indent, ensure_ascii=False)


def safe_json_parse(text: str, default: T | None = None) -> T | None:
    """
    Parse JSON text, returning a default value on failure.

    Args:
        text: JSON string to parse
        default: Value to return if parsing fails

    Returns:
        Parsed JSON or default value
    """
    try:
        return json_parse(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def is_json_string(value: str) -> bool:
    """
    Check if a string is valid JSON.

    Args:
        value: String to check

    Returns:
        True if the string is valid JSON
    """
    return safe_json_parse(value) is not None


def normalize_json_key(key: str) -> str:
    """
    Normalize a JSON config key for consistent lookup.

    Handles platform differences in path separators.

    Args:
        key: The key to normalize

    Returns:
        Normalized key
    """
    # Convert backslashes to forward slashes for cross-platform consistency
    return key.replace("\\", "/")
