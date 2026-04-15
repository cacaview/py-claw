"""Message constants for the Python Claude Code runtime.

Based on ClaudeCode-main/src/utils/messages.ts
"""
from __future__ import annotations

# Synthetic messages - these are system-generated messages
INTERRUPT_MESSAGE = "[Request interrupted by user]"
INTERRUPT_MESSAGE_FOR_TOOL_USE = "[Request interrupted by user for tool use]"
CANCEL_MESSAGE = (
    "The user doesn't want to take this action right now. "
    "STOP what you are doing and wait for the user to tell you how to proceed."
)
REJECT_MESSAGE = (
    "The user doesn't want to proceed with this tool use. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "STOP what you are doing and wait for the user to tell you how to proceed."
)
REJECT_MESSAGE_WITH_REASON_PREFIX = (
    "The user doesn't want to proceed with this tool use. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "To tell you how to proceed, the user said:\n"
)
SUBAGENT_REJECT_MESSAGE = (
    "Permission for this tool use was denied. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "Try a different approach or report the limitation to complete your task."
)
SUBAGENT_REJECT_MESSAGE_WITH_REASON_PREFIX = (
    "Permission for this tool use was denied. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "The user said:\n"
)
PLAN_REJECTION_PREFIX = (
    "The agent proposed a plan that was rejected by the user. "
    "The user chose to stay in plan mode rather than proceed with implementation.\n\n"
    "Rejected plan:\n"
)

# Shared guidance for permission denials
DENIAL_WORKAROUND_GUIDANCE = (
    "IMPORTANT: You *may* attempt to accomplish this action using other tools that might "
    "naturally be used to accomplish this goal, e.g. using head instead of cat. "
    "But you *should not* attempt to work around this denial in malicious ways, "
    "e.g. do not use your ability to run tests to execute non-test actions. "
    "You should only try to work around this restriction in reasonable ways that do not attempt "
    "to bypass the intent behind this denial. "
    "If you believe this capability is essential to complete the user's request, "
    "STOP and explain to the user what you were trying to do and why you need this permission. "
    "Let the user decide how to proceed."
)

# Synthetic tool result placeholder when tool result is missing
SYNTHETIC_TOOL_RESULT_PLACEHOLDER = "[Tool result missing due to internal error]"

# Special markers
NO_RESPONSE_REQUESTED = "No response requested."
SYNTHETIC_MODEL = "<synthetic>"
TOOL_REFERENCE_TURN_BOUNDARY = "Tool loaded."

# Memory correction hint
MEMORY_CORRECTION_HINT = (
    "\n\nNote: The user's next message may contain a correction or preference. "
    "Pay close attention — if they explain what went wrong or how they'd prefer you to work, "
    "consider saving that to memory for future sessions."
)

# Auto mode rejection prefix
AUTO_MODE_REJECTION_PREFIX = "Permission for this action has been denied. Reason: "

# No content marker
NO_CONTENT_MESSAGE = "(no content)"

# Synthetic message set - used for quick lookup
SYNTHETIC_MESSAGES: frozenset[str] = frozenset({
    INTERRUPT_MESSAGE,
    INTERRUPT_MESSAGE_FOR_TOOL_USE,
    CANCEL_MESSAGE,
    REJECT_MESSAGE,
    NO_RESPONSE_REQUESTED,
})
