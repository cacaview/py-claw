"""
Conversation recovery utility for session resume functionality.

Handles deserializing messages from log files, filtering invalid states,
and detecting turn interruptions for proper conversation recovery.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

# Message type constants
MESSAGE_TYPE_USER = "user"
MESSAGE_TYPE_ASSISTANT = "assistant"
MESSAGE_TYPE_SYSTEM = "system"
MESSAGE_TYPE_PROGRESS = "progress"

# Sentinel for no response requested
NO_RESPONSE_REQUESTED = "No response requested."


@dataclass
class TurnInterruptionState:
    """Turn interruption state."""
    kind: Literal["none", "interrupted_prompt"]
    message: Optional[dict] = None


@dataclass
class DeserializeResult:
    """Result of deserializing messages."""
    messages: list[dict]
    turn_interruption_state: TurnInterruptionState


def migrate_legacy_attachment_types(message: dict) -> dict:
    """
    Transforms legacy attachment types to current types for backward compatibility.
    """
    if message.get("type") != "attachment":
        return message

    attachment = message.get("attachment", {})

    # Transform legacy attachment types
    if attachment.get("type") == "new_file":
        filename = attachment.get("filename", "")
        return {
            **message,
            "attachment": {
                **attachment,
                "type": "file",
                "displayPath": _relative_path(filename),
            },
        }

    if attachment.get("type") == "new_directory":
        path = attachment.get("path", "")
        return {
            **message,
            "attachment": {
                **attachment,
                "type": "directory",
                "displayPath": _relative_path(path),
            },
        }

    # Backfill displayPath for attachments from old sessions
    if "displayPath" not in attachment:
        path = (
            attachment.get("filename")
            or attachment.get("path")
            or attachment.get("skillDir")
        )
        if path:
            return {
                **message,
                "attachment": {
                    **attachment,
                    "displayPath": _relative_path(path),
                },
            }

    return message


def _relative_path(path: str) -> str:
    """Get relative path from current working directory."""
    import os
    try:
        cwd = os.getcwd()
        if path.startswith(cwd):
            return path[len(cwd):].lstrip("/\\")
        return path
    except OSError:
        return path


# Valid permission modes
PERMISSION_MODES = {
    "default", "local", "auto", "ask", "deny",
    "bypassPermissions", "bypass-prompt",
}


def _filter_unresolved_tool_uses(messages: list[dict]) -> list[dict]:
    """
    Filter out unresolved tool uses and any synthetic messages that follow them.
    """
    filtered: list[dict] = []
    skip_until_user = False

    for msg in messages:
        msg_type = msg.get("type")

        if skip_until_user and msg_type != MESSAGE_TYPE_USER:
            continue

        if msg_type == "user":
            skip_until_user = False

        # Check for unresolved tool use
        if msg_type == "tool_use":
            tool_use_error = msg.get("tool_use_result", {}).get("error")
            is_error_result = tool_use_error is not None
            # Skip if tool use resulted in error and no subsequent user message
            if is_error_result:
                skip_until_user = True
                continue

        filtered.append(msg)

    return filtered


def _filter_orphaned_thinking_only_messages(messages: list[dict]) -> list[dict]:
    """
    Filter out orphaned thinking-only assistant messages that can cause API errors
    during resume.
    """
    filtered: list[dict] = []
    prev_was_thinking_only_assistant = False

    for msg in messages:
        msg_type = msg.get("type")

        # Check if this is a thinking-only assistant message
        is_thinking_only = (
            msg_type == MESSAGE_TYPE_ASSISTANT
            and msg.get("thinking", "") != ""
            and msg.get("content", "") == ""
        )

        if prev_was_thinking_only_assistant and msg_type == MESSAGE_TYPE_ASSISTANT:
            # Skip orphaned thinking-only message
            prev_was_thinking_only_assistant = is_thinking_only
            continue

        prev_was_thinking_only_assistant = is_thinking_only
        filtered.append(msg)

    return filtered


def _filter_whitespace_only_assistant_messages(messages: list[dict]) -> list[dict]:
    """
    Filter out assistant messages with only whitespace text content.
    """
    filtered: list[dict] = []

    for msg in messages:
        if msg.get("type") == MESSAGE_TYPE_ASSISTANT:
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip() == "":
                # Skip whitespace-only assistant messages
                continue
        filtered.append(msg)

    return filtered


def _detect_turn_interruption(messages: list[dict]) -> TurnInterruptionState:
    """
    Determines whether the conversation was interrupted mid-turn based on the
    last message after filtering.
    """
    if not messages:
        return TurnInterruptionState(kind="none")

    # Find the last turn-relevant message
    last_relevant_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        msg_type = msg.get("type")
        is_api_error = (
            msg_type == MESSAGE_TYPE_ASSISTANT
            and msg.get("isApiErrorMessage", False)
        )
        if (
            msg_type not in (MESSAGE_TYPE_SYSTEM, MESSAGE_TYPE_PROGRESS)
            and not is_api_error
        ):
            last_relevant_idx = i
            break

    if last_relevant_idx == -1:
        return TurnInterruptionState(kind="none")

    last_message = messages[last_relevant_idx]
    last_type = last_message.get("type")

    if last_type == MESSAGE_TYPE_ASSISTANT:
        # Assistant as last message is treated as completed turn
        # (stop_reason is always null on persisted messages in streaming path)
        return TurnInterruptionState(kind="none")

    if last_type == MESSAGE_TYPE_USER:
        return TurnInterruptionState(
            kind="interrupted_prompt",
            message={
                "type": MESSAGE_TYPE_USER,
                "content": "Continue from where you left off.",
                "isMeta": True,
            },
        )

    return TurnInterruptionState(kind="none")


def deserialize_messages(serialized_messages: list[dict]) -> list[dict]:
    """
    Deserializes messages from a log file into the format expected by the REPL.
    Filters unresolved tool uses, orphaned thinking messages, and appends a
    synthetic assistant sentinel when the last message is from the user.
    """
    result = deserialize_messages_with_interrupt_detection(serialized_messages)
    return result.messages


def deserialize_messages_with_interrupt_detection(
    serialized_messages: list[dict],
) -> DeserializeResult:
    """
    Like deserializeMessages, but also detects whether the session was
    interrupted mid-turn. Used by the SDK resume path to auto-continue
    interrupted turns after a gateway-triggered restart.
    """
    try:
        # Transform legacy attachment types before processing
        migrated_messages = [
            migrate_legacy_attachment_types(msg)
            for msg in serialized_messages
        ]

        # Strip invalid permissionMode values from deserialized user messages
        valid_modes = set(PERMISSION_MODES)
        for msg in migrated_messages:
            if msg.get("type") == MESSAGE_TYPE_USER:
                permission_mode = msg.get("permissionMode")
                if permission_mode is not None and permission_mode not in valid_modes:
                    msg["permissionMode"] = None

        # Filter out unresolved tool uses
        filtered_tool_uses = _filter_unresolved_tool_uses(migrated_messages)

        # Filter out orphaned thinking-only assistant messages
        filtered_thinking = _filter_orphaned_thinking_only_messages(filtered_tool_uses)

        # Filter out whitespace-only assistant messages
        filtered_messages = _filter_whitespace_only_assistant_messages(filtered_thinking)

        # Detect turn interruption
        interruption = _detect_turn_interruption(filtered_messages)

        # Handle interrupted turns
        turn_interruption_state = interruption
        if interruption.kind == "interrupted_prompt":
            # Already has the continuation message
            pass
        elif interruption.kind == "none":
            # Check if we need to add a synthetic assistant sentinel
            last_relevant_idx = -1
            for i in range(len(filtered_messages) - 1, -1, -1):
                msg_type = filtered_messages[i].get("type")
                if msg_type not in (MESSAGE_TYPE_SYSTEM, MESSAGE_TYPE_PROGRESS):
                    last_relevant_idx = i
                    break

            if (
                last_relevant_idx != -1
                and filtered_messages[last_relevant_idx].get("type") == MESSAGE_TYPE_USER
            ):
                # Append synthetic assistant sentinel
                filtered_messages.append({
                    "type": MESSAGE_TYPE_ASSISTANT,
                    "content": NO_RESPONSE_REQUESTED,
                })

        return DeserializeResult(
            messages=filtered_messages,
            turn_interruption_state=turn_interruption_state,
        )

    except Exception as e:
        # Log error and re-raise
        import traceback
        traceback.print_exc()
        raise
