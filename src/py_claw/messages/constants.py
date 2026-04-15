"""
Message constants for py-claw runtime.

Based on ClaudeCode-main/src/utils/messages.ts
"""
from __future__ import annotations


# Rejection and cancellation messages
INTERRUPT_MESSAGE = "[Request interrupted by user]"
CANCEL_MESSAGE = "[Cancelled by user]"
REJECT_MESSAGE = "[Tool use rejected by user]"
SUBAGENT_REJECT_MESSAGE = "[Permission denied for subagent tool use]"

# Synthetic message markers
SYNTHETIC_MODEL = "<synthetic>"
SYNTHETIC_TOOL_RESULT_PLACEHOLDER = "[Tool result not available]"
NO_CONTENT_MESSAGE = "[No content]"

# Synthetic message text values (set of strings that indicate synthetic messages)
SYNTHETIC_MESSAGES: set[str] = {
    INTERRUPT_MESSAGE,
    CANCEL_MESSAGE,
    REJECT_MESSAGE,
    SUBAGENT_REJECT_MESSAGE,
    SYNTHETIC_TOOL_RESULT_PLACEHOLDER,
}

# Denial/workaround guidance
DENIAL_WORKAROUND_GUIDANCE = (
    "The user's permission was denied for this tool use. "
    "Do not attempt to use the tool again. "
    "If you need to perform this action, ask the user to grant permission."
)

# Auto mode rejection prefix
AUTO_MODE_REJECTION_PREFIX = "AUTO_MODE_REJECTION:"

# System reminder tags
SYSTEM_REMINDER_TAG = "<system-reminder>"
SYSTEM_REMINDER_END_TAG = "</system-reminder>"

# Command input tags
LOCAL_COMMAND_CAVEAT_TAG = "<local-command-caveat>"
COMMAND_NAME_TAG = "<command-name>"
COMMAND_MESSAGE_TAG = "<command-message>"
COMMAND_ARGS_TAG = "<command-args>"

# XML prompt tags that can be stripped
PROMPT_XML_TAGS = (
    "<commit_analysis>",
    "<context>",
    "<function_analysis>",
    "<pr_analysis>",
    "<system-reminder>",
    "</system-reminder>",
)

# Stop reasons
STOP_REASON_END_TURN = "end_turn"
STOP_REASON_MAX_TOKENS = "max_tokens"
STOP_REASON_STOP_SEQUENCE = "stop_sequence"
STOP_REASON_TOOL_USE = "tool_use"

# Tool result prefixes
TOOL_RESULT_PREFIX = "[TOOL_RESULT]"
TOOL_REFERENCE_TURN_BOUNDARY = "[TOOL_REFERENCE_TURN_BOUNDARY]"

# Snip tool ID tag format
SNIP_ID_TAG_FORMAT = "[id:{short_id}]"
