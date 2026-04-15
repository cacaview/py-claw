"""
Export command - Export conversation to a text file.

This module provides the /export command that exports the current conversation
to a text file. When called with no arguments, it prompts for a filename.
When called with an argument, it writes directly to that file.

TS Reference: ClaudeCode-main/src/commands/export/
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.commands import CommandDefinition
    from py_claw.cli.runtime import RuntimeState
    from py_claw.settings.loader import SettingsLoadResult


def format_timestamp(dt: datetime) -> str:
    """Format datetime as YYYY-MM-DD-HHMMSS."""
    year = dt.year
    month = str(dt.month).zfill(2)
    day = str(dt.day).zfill(2)
    hours = str(dt.hour).zfill(2)
    minutes = str(dt.minute).zfill(2)
    seconds = str(dt.second).zfill(2)
    return f"{year}-{month}-{day}-{hours}{minutes}{seconds}"


def extract_first_prompt(messages: list[dict]) -> str:
    """Extract first user prompt from messages."""
    for msg in messages:
        if msg.get("type") == "user":
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str):
                result = content.strip()
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        result = block.get("text", "").strip()
                        break
                else:
                    result = ""
            else:
                result = ""
            # Take first line only, limit to 50 chars
            result = result.split("\n")[0] or ""
            if len(result) > 50:
                result = result[:49] + "…"
            return result
    return ""


def sanitize_filename(text: str) -> str:
    """Convert text to safe filename."""
    text = text.lower()
    # Remove special chars
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    # Replace spaces with hyphens
    text = re.sub(r"\s+", "-", text)
    # Replace multiple hyphens with single
    text = re.sub(r"-+", "-", text)
    # Remove leading/trailing hyphens
    text = text.strip("-")
    return text


def export_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry,  # CommandRegistry
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle /export command - export conversation to file."""
    args = arguments.strip()

    # Get messages from state/runtime if available
    messages = _get_messages(state)

    # Render conversation to text
    content = _render_messages_to_text(messages)

    # If filename provided, write directly
    if args:
        filename = args if args.endswith(".txt") else f"{args}.txt"
        filepath = Path(state.cwd) / filename
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Conversation exported to: {filepath}"
        except OSError as e:
            return f"Failed to export conversation: {e}"

    # Generate default filename
    first_prompt = extract_first_prompt(messages)
    timestamp = format_timestamp(datetime.now())

    if first_prompt:
        sanitized = sanitize_filename(first_prompt)
        if sanitized:
            filename = f"{timestamp}-{sanitized}.txt"
        else:
            filename = f"conversation-{timestamp}.txt"
    else:
        filename = f"conversation-{timestamp}.txt"

    filepath = Path(state.cwd) / filename
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Conversation exported to: {filepath}"
    except OSError as e:
        return f"Failed to export conversation: {e}"


def _get_messages(state: RuntimeState) -> list[dict]:
    """Get messages from state or return empty list."""
    # Try to get messages from query runtime
    if hasattr(state, "query_runtime") and state.query_runtime:
        try:
            if hasattr(state.query_runtime, "get_messages"):
                return state.query_runtime.get_messages()
        except Exception:
            pass
    return []


def _render_messages_to_text(messages: list[dict]) -> str:
    """Render messages to plain text for export."""
    lines = []
    for msg in messages:
        msg_type = msg.get("type", "unknown")
        if msg_type == "user":
            lines.append("--- User ---")
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str):
                lines.append(content)
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        lines.append(block.get("text", ""))
            lines.append("")
        elif msg_type == "assistant":
            lines.append("--- Assistant ---")
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        lines.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        lines.append(f"[{block.get('name', 'tool')}]")
            lines.append("")
        elif msg_type == "system":
            lines.append("--- System ---")
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str):
                lines.append(content)
            lines.append("")
    return "\n".join(lines)
