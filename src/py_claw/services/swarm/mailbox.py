"""
Mailbox system for inter-agent communication.

Provides file-based mailbox for communication between team lead and teammates.
Reference: ClaudeCode-main/src/utils/teammateMailbox.ts
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import MAILBOX_DIR_NAME, MAILBOX_POLL_INTERVAL_MS
from .types import MailboxEntry, SwarmMessage


def _get_mailbox_dir(team_name: str | None = None) -> Path:
    """
    Get the mailbox directory path.

    Args:
        team_name: Optional team name for team-specific mailbox

    Returns:
        Path to mailbox directory
    """
    if team_name:
        mailbox_path = Path.home() / MAILBOX_DIR_NAME / team_name
    else:
        mailbox_path = Path.home() / MAILBOX_DIR_NAME
    return mailbox_path


def _ensure_mailbox_dir(team_name: str | None = None) -> Path:
    """
    Ensure mailbox directory exists.

    Args:
        team_name: Optional team name

    Returns:
        Path to mailbox directory
    """
    mailbox_dir = _get_mailbox_dir(team_name)
    mailbox_dir.mkdir(parents=True, exist_ok=True)
    return mailbox_dir


def write_to_mailbox(
    recipient: str,
    message: SwarmMessage | dict[str, Any],
    team_name: str | None = None,
) -> None:
    """
    Write a message to a recipient's mailbox.

    Args:
        recipient: The recipient's agent name
        message: The message to write
        team_name: Optional team name
    """
    mailbox_dir = _ensure_mailbox_dir(team_name)
    mailbox_file = mailbox_dir / f"{recipient}.json"

    # Load existing messages
    messages = read_mailbox(recipient, team_name)

    # Add new message
    if isinstance(message, dict):
        # Ensure read flag is False for new messages
        message["read"] = False
        messages.append(message)
    else:
        messages.append(message)

    # Write back
    with open(mailbox_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False)


def read_mailbox(
    agent_name: str,
    team_name: str | None = None,
) -> list[MailboxEntry]:
    """
    Read all messages from an agent's mailbox.

    Args:
        agent_name: The agent's name
        team_name: Optional team name

    Returns:
        List of mailbox entries
    """
    mailbox_dir = _get_mailbox_dir(team_name)
    mailbox_file = mailbox_dir / f"{agent_name}.json"

    if not mailbox_file.exists():
        return []

    try:
        with open(mailbox_file, "r", encoding="utf-8") as f:
            messages = json.load(f)
            return messages
    except (json.JSONDecodeError, IOError):
        return []


def mark_message_as_read(
    agent_name: str,
    message_index: int,
    team_name: str | None = None,
) -> bool:
    """
    Mark a specific message as read.

    Args:
        agent_name: The agent's name
        message_index: Index of the message to mark as read
        team_name: Optional team name

    Returns:
        True if successful, False otherwise
    """
    mailbox_dir = _get_mailbox_dir(team_name)
    mailbox_file = mailbox_dir / f"{agent_name}.json"

    if not mailbox_file.exists():
        return False

    try:
        with open(mailbox_file, "r", encoding="utf-8") as f:
            messages = json.load(f)

        if 0 <= message_index < len(messages):
            messages[message_index]["read"] = True
            with open(mailbox_file, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False)
            return True
    except (json.JSONDecodeError, IOError, IndexError):
        pass

    return False


def clear_mailbox(
    agent_name: str,
    team_name: str | None = None,
) -> None:
    """
    Clear an agent's mailbox.

    Args:
        agent_name: The agent's name
        team_name: Optional team name
    """
    mailbox_dir = _get_mailbox_dir(team_name)
    mailbox_file = mailbox_dir / f"{agent_name}.json"

    if mailbox_file.exists():
        mailbox_file.unlink()


def create_idle_notification(
    from_agent: str,
    idle_reason: str = "available",
    summary: str | None = None,
    completed_task_id: str | None = None,
    completed_status: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """
    Create an idle notification message.

    Args:
        from_agent: The agent sending the notification
        idle_reason: Reason for idle (available, interrupted, failed)
        summary: Optional summary of recent activity
        completed_task_id: Optional completed task ID
        completed_status: Optional completion status
        failure_reason: Optional failure reason

    Returns:
        Idle notification dictionary
    """
    return {
        "type": "idle",
        "from": from_agent,
        "idle_reason": idle_reason,
        "summary": summary,
        "completed_task_id": completed_task_id,
        "completed_status": completed_status,
        "failure_reason": failure_reason,
    }


def create_permission_request(
    tool_name: str,
    tool_use_id: str,
    input_data: dict[str, Any],
    description: str,
    worker_id: str,
    worker_name: str,
    worker_color: str | None,
    team_name: str,
    suggestions: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create a permission request message.

    Args:
        tool_name: Name of the tool
        tool_use_id: Unique ID for this tool use
        input_data: Tool input data
        description: Human-readable description
        worker_id: ID of the requesting worker
        worker_name: Name of the requesting worker
        worker_color: Color of the requesting worker
        team_name: Team name
        suggestions: Optional permission suggestions

    Returns:
        Permission request dictionary
    """
    return {
        "type": "permission_request",
        "id": str(uuid.uuid4()),
        "tool_name": tool_name,
        "tool_use_id": tool_use_id,
        "input": input_data,
        "description": description,
        "permission_suggestions": suggestions or [],
        "worker_id": worker_id,
        "worker_name": worker_name,
        "worker_color": worker_color,
        "team_name": team_name,
    }


def is_permission_response(text: str) -> dict[str, Any] | None:
    """
    Parse and validate a permission response message.

    Args:
        text: JSON string of the message

    Returns:
        Parsed message or None if invalid
    """
    try:
        msg = json.loads(text)
        if msg.get("type") == "permission_response":
            return msg
    except json.JSONDecodeError:
        pass
    return None


def is_shutdown_request(text: str) -> dict[str, Any] | None:
    """
    Parse and validate a shutdown request message.

    Args:
        text: JSON string of the message

    Returns:
        Parsed message or None if invalid
    """
    try:
        msg = json.loads(text)
        if msg.get("type") == "shutdown":
            return msg
    except json.JSONDecodeError:
        pass
    return None
