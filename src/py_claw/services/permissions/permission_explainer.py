"""Permission result explanation utilities."""

from __future__ import annotations

from enum import Enum


class PermissionBehavior(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"
    PASSTHROUGH = "passthrough"


def explain_permission_result(behavior: str, tool_name: str, reason: str | None = None) -> str:
    """
    Create a human-readable explanation for a permission result.

    Args:
        behavior: The permission behavior (allow, deny, ask, passthrough)
        tool_name: Name of the tool
        reason: Optional reason for the decision

    Returns:
        Human-readable explanation string
    """
    explanations = {
        "allow": f"{tool_name} is allowed to run.",
        "deny": f"{tool_name} is denied permission.",
        "ask": f"{tool_name} requires user permission to run.",
        "passthrough": f"{tool_name} permission check deferred.",
    }

    base = explanations.get(behavior, behavior)
    if reason:
        return f"{base} Reason: {reason}"
    return base


def format_permission_rule(tool_name: str, rule_content: str | None = None) -> str:
    """
    Format a permission rule as a string.

    Args:
        tool_name: Name of the tool
        rule_content: Optional content/pattern for the rule

    Returns:
        Formatted rule string (e.g., "Bash", "Bash(npm publish:*)")
    """
    if rule_content:
        return f"{tool_name}({rule_content})"
    return tool_name
