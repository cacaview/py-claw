"""Classifier-based permission decisions for auto mode."""

from __future__ import annotations

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


def classify_yolo_action(
    messages: list,
    action: str,
    tools: list,
    permission_context: dict,
    abort_signal: any = None,
) -> dict:
    """
    Classify an action for auto mode permission decision.

    Uses the real YOLO classifier from py_claw.permissions.yolo_classifier
    to evaluate the action. Fail-open: block only on high-confidence deny.

    Args:
        messages: Conversation message history
        action: Tool/action name being evaluated
        tools: List of available tools
        permission_context: Dict with 'mode' key (PermissionMode string)
        abort_signal: Optional abort signal

    Returns:
        dict with:
        - should_block: bool (True = block, False = allow/ask)
        - reason: str (explanation)
        - unavailable: bool (True if classifier unavailable -> fail open)
        - error_dump_path: str | None
    """
    try:
        from py_claw.permissions.yolo_classifier import classify_yolo

        # Extract permission mode from context
        mode = "default"
        if permission_context and isinstance(permission_context, dict):
            mode = permission_context.get("mode", "default")

        # Call the real YOLO classifier
        # Note: messages and tools are not used by classify_yolo but could be
        # passed in a future enhancement for context-aware classification
        result = classify_yolo(
            tool_name=action,
            content=None,  # classifier_decision doesn't receive content; tool-level only
            permission_mode=mode,
        )

        # Fail-open: block only on high-confidence deny (critical/high severity)
        should_block = result.decision == "deny" and result.severity in ("critical", "high")

        return {
            "should_block": should_block,
            "reason": result.reason,
            "unavailable": False,
            "error_dump_path": None,
        }

    except Exception:
        # Fail-open: if classifier is unavailable, don't block
        return {
            "should_block": False,
            "reason": "classifier_unavailable",
            "unavailable": True,
            "error_dump_path": None,
        }
