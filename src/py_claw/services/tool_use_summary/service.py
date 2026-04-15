"""
Tool use summary service implementation.

Generates human-readable summaries of completed tool batches using Haiku.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .types import GenerateToolUseSummaryParams, ToolInfo

logger = logging.getLogger(__name__)

TOOL_USE_SUMMARY_SYSTEM_PROMPT = """Write a short summary label describing what these tool calls accomplished. It appears as a single-line row in a mobile app and truncates around 30 characters, so think git-commit-subject, not sentence.

Keep the verb in past tense and the most distinctive noun. Drop articles, connectors, and long location context first.

Examples:
- Searched in auth/
- Fixed NPE in UserService
- Created signup endpoint
- Read config.json
- Ran failing tests"""


def _truncate_json(value: Any, max_length: int) -> str:
    """
    Truncate a JSON value to a maximum length for the prompt.

    Args:
        value: The value to serialize and truncate
        max_length: Maximum length of the resulting string

    Returns:
        Truncated JSON string
    """
    try:
        # Use repr for more compact representation
        if isinstance(value, str):
            str_val = value
        else:
            str_val = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return "[unable to serialize]"

    if len(str_val) <= max_length:
        return str_val

    return str_val[: max_length - 3] + "..."


async def generate_tool_use_summary(
    params: GenerateToolUseSummaryParams,
) -> str | None:
    """
    Generate a human-readable summary of completed tools.

    Args:
        params: Parameters including tools executed and their results

    Returns:
        A brief summary string, or null if generation fails
    """
    if not params.tools:
        return None

    try:
        # Build a concise representation of what tools did
        tool_summaries = []
        for tool in params.tools:
            input_str = _truncate_json(tool.input, 300)
            output_str = _truncate_json(tool.output, 300)
            tool_summaries.append(f"Tool: {tool.name}\nInput: {input_str}\nOutput: {output_str}")

        tool_summary_text = "\n\n".join(tool_summaries)

        context_prefix = ""
        if params.last_assistant_text:
            context_prefix = (
                f"User's intent (from assistant's last message): "
                f"{params.last_assistant_text[:200]}\n\n"
            )

        # Build the prompt for Haiku
        user_prompt = (
            f"{context_prefix}"
            f"Tools completed:\n\n"
            f"{tool_summary_text}\n\n"
            f"Label:"
        )

        # TODO: Integrate with Haiku API when available
        # For now, generate a simple summary based on tool names
        summary = _generate_simple_summary(params.tools)

        return summary

    except Exception as error:
        logger.warning(f"Tool use summary generation failed: {error}")
        return None


def _generate_simple_summary(tools: list[ToolInfo]) -> str | None:
    """
    Generate a simple summary based on tool names when Haiku is not available.

    Args:
        tools: List of tools that were executed

    Returns:
        A simple summary string
    """
    if not tools:
        return None

    tool_names = [t.name for t in tools]

    # Simple heuristic summaries based on tool names
    if "Bash" in tool_names or "Shell" in tool_names:
        return "Ran shell commands"
    if "Read" in tool_names and "Edit" in tool_names:
        return "Read and edited files"
    if "Read" in tool_names:
        return "Read files"
    if "Edit" in tool_names:
        return "Edited files"
    if "Glob" in tool_names or "Grep" in tool_names:
        return "Searched codebase"
    if "Write" in tool_names:
        return "Wrote files"
    if len(tools) == 1:
        return f"Used {tools[0].name} tool"

    return f"Used {len(tools)} tools"
