"""
Message utility functions for py-claw runtime.

Based on ClaudeCode-main/src/utils/messages.ts
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from .constants import (
    NO_CONTENT_MESSAGE,
    PROMPT_XML_TAGS,
    SNIP_ID_TAG_FORMAT,
    SYSTEM_REMINDER_END_TAG,
    SYSTEM_REMINDER_TAG,
)


def derive_uuid(parent_uuid: str, index: int) -> str:
    """
    Derive a deterministic UUID from a parent UUID and index.

    This is used to generate stable UUIDs for synthetic messages.

    Args:
        parent_uuid: Parent message UUID
        index: Block index within the message

    Returns:
        Derived UUID string
    """
    combined = f"{parent_uuid}:{index}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, combined))


def derive_short_message_id(uuid: str) -> str:
    """
    Derive a short message ID for display.

    Takes first 10 hex chars of UUID, converts to base36, returns first 6 chars.

    Args:
        uuid: Full UUID string

    Returns:
        Short ID string
    """
    # First 10 hex chars
    hex_part = uuid.replace("-", "")[:10]
    # Convert to int then to base36
    int_val = int(hex_part, 16)
    base36 = base36_encode(int_val)
    return base36[:6].upper()


def base36_encode(n: int) -> str:
    """Encode an integer as base36 string."""
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    result = ""
    while n > 0:
        n, rem = divmod(n, 36)
        result = chars[rem] + result
    return result or "0"


def get_content_text(content: str | list[dict[str, Any]]) -> str:
    """
    Extract text from content (string or content block array).

    Args:
        content: String or content blocks

    Returns:
        Extracted text
    """
    if isinstance(content, str):
        return content

    # Content is a list of content blocks
    text_parts = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "thinking":
                # Include thinking content
                text_parts.append(f"[Thinking: {block.get('thinking', '')}]")
    return "".join(text_parts)


def extract_text_content(
    blocks: list[dict[str, Any]],
    separator: str = "\n",
) -> str:
    """
    Extract and join text content from blocks.

    Args:
        blocks: List of content blocks
        separator: Separator between text pieces

    Returns:
        Joined text content
    """
    texts = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if text:
                texts.append(text)
    return separator.join(texts)


def get_user_message_text(message: dict[str, Any]) -> str:
    """
    Extract text from a user message.

    Args:
        message: User message dict

    Returns:
        Message text
    """
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return get_content_text(content)


def get_assistant_message_text(message: dict[str, Any]) -> str:
    """
    Extract text from an assistant message.

    Args:
        message: Assistant message dict

    Returns:
        Message text
    """
    content = message.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return get_content_text(content)


def strip_prompt_xml_tags(content: str) -> str:
    """
    Strip XML tags used in prompts.

    Removes <commit_analysis>, <context>, <function_analysis>, <pr_analysis>,
    and <system-reminder> tags with their content.

    Args:
        content: Content to strip tags from

    Returns:
        Content with tags stripped
    """
    result = content
    for tag in PROMPT_XML_TAGS:
        # Handle paired tags with content between them
        pattern = re.escape(tag)
        if tag.startswith("</"):
            # Closing tag - remove everything after opening tag
            opening = tag.replace("</", "<")
            pattern = f"{re.escape(opening)}.*?{pattern}"
        result = re.sub(pattern, "", result, flags=re.DOTALL)
    return result


def wrap_in_system_reminder(content: str) -> str:
    """
    Wrap content in system reminder tags.

    Args:
        content: Content to wrap

    Returns:
        Wrapped content
    """
    return f"{SYSTEM_REMINDER_TAG}\n{content}\n{SYSTEM_REMINDER_END_TAG}"


def extract_tag(html: str, tag_name: str) -> str | None:
    """
    Extract content from an HTML/XML tag.

    Supports nested tags up to a depth of 10.

    Args:
        html: HTML content
        tag_name: Name of the tag to extract

    Returns:
        Content inside the tag, or None if not found
    """
    pattern = rf"<{tag_name}[^>]*>(.*?)</{tag_name}>"
    match = re.search(pattern, html, re.DOTALL)
    if match:
        return match.group(1)
    return None


def text_for_resubmit(message: dict[str, Any]) -> str:
    """
    Extract text suitable for resubmit from a user message.

    Looks for <bash-input> or <command-name>/<command-args> tags.

    Args:
        message: User message dict

    Returns:
        Resubmit text
    """
    content = message.get("content", "")
    if isinstance(content, str):
        # Try to extract bash-input
        bash_input = extract_tag(content, "bash-input")
        if bash_input:
            return bash_input.strip()

        # Try command-name and command-args
        cmd_name = extract_tag(content, "command-name")
        cmd_args = extract_tag(content, "command-args")
        if cmd_name:
            if cmd_args:
                return f"{cmd_name.strip()} {cmd_args.strip()}"
            return cmd_name.strip()

    return ""


def is_empty_message_text(text: str) -> bool:
    """
    Check if text is empty (whitespace only or equals NO_CONTENT_MESSAGE).

    Args:
        text: Text to check

    Returns:
        True if empty
    """
    stripped = strip_prompt_xml_tags(text).strip()
    return stripped == "" or stripped == NO_CONTENT_MESSAGE


def normalize_user_text_content(content: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize user text content to array form.

    Args:
        content: String or content array

    Returns:
        Content as array of text blocks
    """
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content


def get_tool_use_id(message: dict[str, Any]) -> str | None:
    """
    Extract tool_use_id from any message type.

    Args:
        message: Message dict

    Returns:
        Tool use ID if present
    """
    # Check various locations where tool_use_id might be
    if "tool_use_id" in message:
        return message["tool_use_id"]

    # Check content blocks for tool_use
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return block.get("id")

    # Check progress messages
    if message.get("type") == "progress":
        progress = message.get("progress", {})
        return progress.get("tool_use_id")

    return None


def is_tool_use_request_message(message: dict[str, Any]) -> bool:
    """
    Check if message is a tool use request.

    Args:
        message: Message dict

    Returns:
        True if assistant message with tool_use block
    """
    if message.get("type") != "assistant":
        return False
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return True
    return False


def is_tool_use_result_message(message: dict[str, Any]) -> bool:
    """
    Check if message is a tool use result.

    Args:
        message: Message dict

    Returns:
        True if user message with tool_result block
    """
    if message.get("type") != "user":
        return False
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                return True
    return False


def is_synthetic_message(message: dict[str, Any]) -> bool:
    """
    Check if message is synthetic (generated by the system).

    Args:
        message: Message dict

    Returns:
        True if synthetic
    """
    content = message.get("content", "")
    if isinstance(content, str):
        from .constants import SYNTHETIC_MESSAGES
        return content in SYNTHETIC_MESSAGES
    return False


def is_human_turn(message: dict[str, Any]) -> bool:
    """
    Check if message is a human turn (actual user message, not tool result).

    Args:
        message: Message dict

    Returns:
        True if human turn
    """
    return (
        message.get("type") == "user"
        and not message.get("is_meta", False)
        and message.get("tool_use_result") is None
    )


def is_thinking_message(message: dict[str, Any]) -> bool:
    """
    Check if assistant message contains thinking.

    Args:
        message: Message dict

    Returns:
        True if thinking content present
    """
    if message.get("type") != "assistant":
        return False
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                return True
    return False


def is_compact_boundary_message(message: dict[str, Any]) -> bool:
    """
    Check if message is a compact boundary.

    Args:
        message: Message dict

    Returns:
        True if compact boundary
    """
    return (
        message.get("type") == "system"
        and message.get("subtype") == "compact_boundary"
    )


def has_successful_tool_call(
    messages: list[dict[str, Any]],
    tool_name: str,
) -> bool:
    """
    Check if there's a successful (non-error) tool call of a given name.

    Args:
        messages: List of messages
        tool_name: Tool name to search for

    Returns:
        True if found
    """
    for message in messages:
        if message.get("type") != "assistant":
            continue
        content = message.get("content", [])
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == tool_name
                ):
                    # Check for corresponding non-error result
                    tool_use_id = block.get("id")
                    if tool_use_id:
                        for msg in messages:
                            if msg.get("type") == "user":
                                result_content = msg.get("content", [])
                                if isinstance(result_content, list):
                                    for result in result_content:
                                                                if (
                                                                    isinstance(result, dict)
                                                                    and result.get("type") == "tool_result"
                                                                    and result.get("tool_use_id") == tool_use_id
                                                                    and not result.get("is_error", False)
                                                                ):
                                                                    return True
    return False


def count_tool_calls(messages: list[dict[str, Any]]) -> dict[str, int]:
    """
    Count tool calls by tool name.

    Args:
        messages: List of messages

    Returns:
        Dict mapping tool name to call count
    """
    counts: dict[str, int] = {}
    for message in messages:
        if message.get("type") != "assistant":
            continue
        content = message.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name", "unknown")
                    counts[name] = counts.get(name, 0) + 1
    return counts


def get_last_assistant_message(
    messages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Get the last assistant message from a list.

    Args:
        messages: List of messages

    Returns:
        Last assistant message or None
    """
    for message in reversed(messages):
        if message.get("type") == "assistant":
            return message
    return None


def has_tool_calls_in_last_assistant_turn(
    messages: list[dict[str, Any]],
) -> bool:
    """
    Check if the last assistant message has tool calls.

    Args:
        messages: List of messages

    Returns:
        True if last assistant has tool calls
    """
    last_assistant = get_last_assistant_message(messages)
    if not last_assistant:
        return False
    return is_tool_use_request_message(last_assistant)
