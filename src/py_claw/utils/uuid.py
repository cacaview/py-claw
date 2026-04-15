"""
UUID utilities for generating and validating UUIDs.

Reference: ClaudeCode-main/src/utils/uuid.ts
"""
from __future__ import annotations

import re
import uuid as uuid_module
from typing import Literal

# UUID regex pattern for validation
UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_uuid(maybe_uuid: object) -> str | None:
    """
    Validate if a value is a valid UUID string.

    Args:
        maybe_uuid: The value to check

    Returns:
        The UUID string if valid, None otherwise
    """
    if not isinstance(maybe_uuid, str):
        return None

    return maybe_uuid if UUID_REGEX.match(maybe_uuid) else None


def create_agent_id(label: str | None = None) -> str:
    """
    Generate a new agent ID with prefix for consistency with task IDs.

    Format: a{label-}{16 hex chars}
    Example: aa3f2c1b4d5e6f7a8, acompact-a3f2c1b4d5e6f7a8

    Args:
        label: Optional label to include in the ID

    Returns:
        Agent ID string
    """
    suffix = uuid_module.uuid4().bytes[:8].hex()
    if label:
        return f"a{label}-{suffix}"
    return f"a{suffix}"
