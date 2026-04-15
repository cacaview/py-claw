"""Classifier-based permission decisions for auto mode."""

from __future__ import annotations

import os

# Safe tools that don't need YOLO classification in auto mode
SAFE_TOOL_ALLOWLIST = {
    "Read",
    "Glob",
    "Grep",
    "LS",
    "WebSearch",
    "WebFetch",
}


def is_auto_mode_allowlisted_tool(tool_name: str) -> bool:
    """Check if a tool is on the safe allowlist for auto mode."""
    return tool_name in SAFE_TOOL_ALLOWLIST


# Placeholder for YOLO classification
# In a full implementation, this would call the classifier API
def classify_yolo_action(
    messages: list,
    action: str,
    tools: list,
    permission_context: dict,
    abort_signal: any = None,
) -> dict:
    """
    Classify an action for auto mode permission decision.

    Returns a dict with:
    - should_block: bool
    - reason: str
    - unavailable: bool
    - error_dump_path: str | None
    """
    # Stub implementation - returns allowed
    return {
        "should_block": False,
        "reason": "stub",
        "unavailable": False,
        "error_dump_path": None,
    }
