"""
SDK message mappers for py-claw runtime.

Based on ClaudeCode-main/src/utils/messages/mappers.ts
Handles translation between internal message format and SDK wire format.
"""
from __future__ import annotations

from typing import Any

from ..schemas.common import SDKMessage


def to_internal_messages(
    sdk_messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert SDK messages to internal message format.

    Args:
        sdk_messages: List of SDK messages

    Returns:
        List of internal messages
    """
    internal: list[dict[str, Any]] = []

    for sdk_msg in sdk_messages:
        msg_type = sdk_msg.get("type")
        msg = {"type": msg_type}

        if msg_type == "user":
            msg["content"] = sdk_msg.get("message", {})
            msg["uuid"] = sdk_msg.get("uuid")
            msg["session_id"] = sdk_msg.get("session_id")
            if sdk_msg.get("parent_tool_use_id"):
                msg["parent_uuid"] = sdk_msg["parent_tool_use_id"]
            if sdk_msg.get("isSynthetic"):
                msg["is_virtual"] = True
            if sdk_msg.get("tool_use_result"):
                msg["tool_use_result"] = sdk_msg["tool_use_result"]
            if sdk_msg.get("timestamp"):
                msg["timestamp"] = sdk_msg["timestamp"]

        elif msg_type == "assistant":
            msg["content"] = sdk_msg.get("message", {})
            msg["uuid"] = sdk_msg.get("uuid")
            msg["session_id"] = sdk_msg.get("session_id")
            if sdk_msg.get("error"):
                msg["error"] = sdk_msg["error"]
            if sdk_msg.get("parent_tool_use_id"):
                msg["parent_uuid"] = sdk_msg["parent_tool_use_id"]

        elif msg_type == "system":
            msg["subtype"] = sdk_msg.get("subtype", "informational")
            msg["content"] = sdk_msg.get("content", "")

            # Handle compact_boundary subtype
            if sdk_msg.get("subtype") == "compact_boundary":
                msg["compact_metadata"] = sdk_msg.get("compact_metadata", {})

        internal.append(msg)

    return internal


def to_sdk_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert internal messages to SDK message format.

    Args:
        messages: List of internal messages

    Returns:
        List of SDK messages
    """
    sdk: list[dict[str, Any]] = []

    for msg in messages:
        msg_type = msg.get("type")
        sdk_msg: dict[str, Any] = {"type": msg_type}

        if msg_type == "user":
            sdk_msg["message"] = msg.get("content", {})
            sdk_msg["uuid"] = msg.get("uuid")
            sdk_msg["session_id"] = msg.get("session_id")
            if msg.get("parent_uuid"):
                sdk_msg["parent_tool_use_id"] = msg["parent_uuid"]
            if msg.get("is_virtual"):
                sdk_msg["isSynthetic"] = True
            if msg.get("tool_use_result"):
                sdk_msg["tool_use_result"] = msg["tool_use_result"]

        elif msg_type == "assistant":
            sdk_msg["message"] = msg.get("content", {})
            sdk_msg["uuid"] = msg.get("uuid")
            sdk_msg["session_id"] = msg.get("session_id")
            if msg.get("error"):
                sdk_msg["error"] = msg["error"]
            if msg.get("parent_uuid"):
                sdk_msg["parent_tool_use_id"] = msg["parent_uuid"]

        elif msg_type == "system":
            sdk_msg["subtype"] = msg.get("subtype", "informational")
            sdk_msg["content"] = msg.get("content", "")

            # Handle compact_boundary
            if msg.get("subtype") == "compact_boundary":
                sdk_msg["compact_metadata"] = msg.get("compact_metadata", {})

            # Handle local_command_output
            if msg.get("subtype") == "local_command":
                sdk_msg["content"] = _strip_ansi(msg.get("content", ""))

        sdk.append(sdk_msg)

    return sdk


def _strip_ansi(text: str) -> str:
    """
    Strip ANSI escape codes from text.

    Args:
        text: Text that may contain ANSI codes

    Returns:
        Text with ANSI codes removed
    """
    import re
    ansi_pattern = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_pattern.sub("", text)


def normalize_assistant_message_for_sdk(
    message: dict[str, Any],
) -> dict[str, Any]:
    """
    Normalize assistant message for SDK consumption.

    Injects plan field into ExitPlanModeV2 tool inputs.

    Args:
        message: Assistant message dict

    Returns:
        Normalized message
    """
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_name = block.get("name")
                if tool_name == "ExitPlanModeV2":
                    # Inject plan field if not present
                    input_json = block.get("input_json", {})
                    if "plan" not in input_json:
                        input_json["plan"] = "Executing ExitPlanModeV2"
                        block["input_json"] = input_json

    return message


def local_command_output_to_sdk_assistant_message(
    raw_content: str,
    output_uuid: str,
    session_id: str,
) -> dict[str, Any]:
    """
    Convert local command output to SDK assistant message.

    Converts stdout/stderr XML tags to a synthetic assistant message.

    Args:
        raw_content: Raw command output with XML tags
        output_uuid: UUID for the output
        session_id: Session ID

    Returns:
        SDK assistant message
    """
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": raw_content}
            ]
        },
        "uuid": output_uuid,
        "session_id": session_id,
    }
