"""
Session memory extraction logic.

Handles building extraction prompts and determining when
to trigger session memory extraction.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from py_claw.services.api import MessageCreateParams, MessageParam

from .config import get_session_memory_config
from .memory_file import (
    get_default_update_prompt,
    load_session_memory_template,
)
from .state import (
    get_last_summarized_message_id,
    has_met_initialization_threshold,
    record_extraction_token_count,
    set_last_summarized_message_id,
)

if TYPE_CHECKING:
    from pathlib import Path


# Maximum section length in tokens
MAX_SECTION_LENGTH = 2000

# Maximum total session memory tokens
MAX_TOTAL_SESSION_MEMORY_TOKENS = 12000


def _analyze_section_sizes(content: str) -> dict[str, int]:
    """Parse the session memory file and analyze section sizes."""
    sections: dict[str, int] = {}
    lines = content.split("\n")
    current_section = ""
    current_content: list[str] = []

    for line in lines:
        if line.startswith("# "):
            if current_section and current_content:
                section_content = "\n".join(current_content).strip()
                sections[current_section] = _rough_token_count(section_content)
            current_section = line
            current_content = []
        else:
            current_content.append(line)

    if current_section and current_content:
        section_content = "\n".join(current_content).strip()
        sections[current_section] = _rough_token_count(section_content)

    return sections


def _rough_token_count(text: str) -> int:
    """Rough token count estimation (chars / 4)."""
    return len(text) // 4


def _generate_section_reminders(
    section_sizes: dict[str, int],
    total_tokens: int,
) -> str:
    """Generate reminders for sections that are too long."""
    over_budget = total_tokens > MAX_TOTAL_SESSION_MEMORY_TOKENS
    oversized_sections = [
        (section, tokens)
        for section, tokens in section_sizes.items()
        if tokens > MAX_SECTION_LENGTH
    ]
    oversized_sections.sort(key=lambda x: x[1], reverse=True)

    if not oversized_sections and not over_budget:
        return ""

    parts: list[str] = []

    if over_budget:
        parts.append(
            f"\n\nCRITICAL: The session memory file is currently ~{total_tokens} tokens, "
            f"which exceeds the maximum of {MAX_TOTAL_SESSION_MEMORY_TOKENS} tokens. "
            "You MUST condense the file to fit within this budget."
        )

    if oversized_sections:
        parts.append(
            f"\n\nOversized sections to condense:\n"
            + "\n".join(
                f'- "{section}" is ~{tokens} tokens (limit: {MAX_SECTION_LENGTH})'
                for section, tokens in oversized_sections
            )
        )

    return "".join(parts)


def _substitute_variables(template: str, variables: dict[str, str]) -> str:
    """Substitute {{variable}} placeholders in the template."""
    import re

    def replacer(match: re.Match) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))

    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


def _extract_text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
            elif isinstance(block, dict):
                block_text = block.get("text")
                if isinstance(block_text, str) and block_text:
                    parts.append(block_text)
        return "".join(parts)
    return ""


async def build_session_memory_update_prompt(
    current_notes: str,
    notes_path: Path,
) -> str:
    """Build the prompt for updating session memory.

    Loads the custom prompt template (if exists) and substitutes
    variables with current content and path.
    """
    # Try to load custom prompt, fall back to default
    try:
        prompt_template = load_session_memory_template()
    except Exception:
        prompt_template = get_default_update_prompt()

    # Analyze section sizes and generate reminders
    section_sizes = _analyze_section_sizes(current_notes)
    total_tokens = _rough_token_count(current_notes)
    section_reminders = _generate_section_reminders(section_sizes, total_tokens)

    # Substitute variables
    variables = {
        "currentNotes": current_notes,
        "notesPath": str(notes_path),
    }

    base_prompt = _substitute_variables(prompt_template, variables)

    # Add section size reminders
    return base_prompt + section_reminders


def should_extract_memory(
    token_count: int,
    tool_call_count: int,
) -> tuple[bool, str]:
    """Determine if session memory extraction should be triggered.

    Returns a tuple of (should_extract, reason).

    Extraction is triggered when:
    1. Not initialized: token_count >= minimum_message_tokens_to_init
    2. Initialized: token_growth >= minimum_tokens_between_update
       AND tool_call_count >= tool_calls_between_updates
    """
    config = get_session_memory_config()

    if not has_met_initialization_threshold(token_count):
        return False, "not_yet_initialized"

    last_summarized = get_last_summarized_message_id()

    # If no extraction has been done yet, check initialization threshold
    if last_summarized is None:
        if token_count >= config.minimum_message_tokens_to_init:
            return True, "initialization_threshold_met"
        return False, "not_yet_initialized"

    # Check update threshold: token growth since last extraction
    # Note: We need to track tokens_at_last_extraction properly
    from .state import get_state

    state = get_state()
    token_growth = token_count - state.tokens_at_last_extraction

    if token_growth < config.minimum_tokens_between_update:
        return False, "token_growth_insufficient"

    # Token threshold met, check if we're at a good trigger point
    if tool_call_count >= config.tool_calls_between_updates:
        return True, "update_threshold_met_with_tool_calls"

    # Also trigger if significantly over threshold
    if token_growth >= config.minimum_tokens_between_update * 2:
        return True, "update_threshold_significantly_exceeded"

    return False, "token_growth_insufficient"


async def extract_session_memory(
    messages: list[Any],
    token_count: int,
    api_client: Any = None,
) -> dict[str, Any]:
    """Extract session memory from conversation messages.

    This updates the session memory markdown file using the configured API
    client when one is provided. If no client is available, the function still
    records state so callers can keep existing behavior during tests.

    Args:
        messages: List of conversation messages
        token_count: Current token count
        api_client: Optional API client for making extraction calls

    Returns:
        Dictionary with extraction result metadata
    """
    from .memory_file import get_memory_path, setup_session_memory_file
    from .state import (
        mark_extraction_completed,
        mark_extraction_started,
        mark_session_memory_initialized,
        record_extraction_token_count,
        set_last_summarized_message_id,
    )

    # Set up the memory file if needed
    memory_path = await setup_session_memory_file()

    # Mark extraction as started
    mark_extraction_started()

    try:
        # Get current memory content
        from .memory_file import get_session_memory_content

        current_content = await get_session_memory_content() or ""

        # Build the update prompt
        prompt = await build_session_memory_update_prompt(current_content, memory_path)

        extracted_content = current_content
        api_used = False

        if api_client is not None:
            response = api_client.create_message(
                MessageCreateParams(
                    model="claude-sonnet-4-20250514",
                    messages=[MessageParam(role="user", content=prompt)],
                    max_tokens=4096,
                )
            )
            if hasattr(response, "__await__"):
                response = await response
            extracted_content = _extract_text_from_content(getattr(response, "content", []))
            if extracted_content:
                memory_path.write_text(extracted_content, encoding="utf-8")
                api_used = True

        # Update state
        last_message_id = None
        if messages:
            last_message = messages[-1]
            last_message_id = getattr(last_message, "id", None)

        set_last_summarized_message_id(last_message_id)
        record_extraction_token_count(token_count)
        mark_session_memory_initialized()

        return {
            "success": True,
            "memory_path": str(get_memory_path()),
            "last_message_id": last_message_id,
            "token_count": token_count,
            "prompt_length": len(prompt),
            "api_used": api_used,
            "memory_written": bool(api_used),
            "content_length": len(extracted_content),
        }

    finally:
        mark_extraction_completed()


def truncate_session_memory_for_compact(content: str) -> tuple[str, bool]:
    """Truncate session memory content for compact operation.

    When inserting session memory into compact messages, we need to
    ensure it doesn't exceed the per-section token budget.

    Returns:
        Tuple of (truncated_content, was_truncated)
    """
    lines = content.split("\n")
    max_chars_per_section = MAX_SECTION_LENGTH * 4  # roughTokenCountEstimation uses length/4
    output_lines: list[str] = []
    current_section_lines: list[str] = []
    current_section_header = ""
    was_truncated = False

    for line in lines:
        if line.startswith("# "):
            result = _flush_session_section(
                current_section_header,
                current_section_lines,
                max_chars_per_section,
            )
            output_lines.extend(result["lines"])
            was_truncated = was_truncated or result["was_truncated"]
            current_section_header = line
            current_section_lines = []
        else:
            current_section_lines.append(line)

    # Flush the last section
    result = _flush_session_section(
        current_section_header,
        current_section_lines,
        max_chars_per_section,
    )
    output_lines.extend(result["lines"])
    was_truncated = was_truncated or result["was_truncated"]

    return "\n".join(output_lines), was_truncated


def _flush_session_section(
    section_header: str,
    section_lines: list[str],
    max_chars_per_section: int,
) -> dict[str, Any]:
    """Flush a session section, truncating if necessary."""
    if not section_header:
        return {"lines": section_lines, "was_truncated": False}

    section_content = "\n".join(section_lines)
    if len(section_content) <= max_chars_per_section:
        return {"lines": [section_header] + section_lines, "was_truncated": False}

    # Truncate at a line boundary near the limit
    char_count = 0
    kept_lines = [section_header]
    for line in section_lines:
        if char_count + len(line) + 1 > max_chars_per_section:
            break
        kept_lines.append(line)
        char_count += len(line) + 1

    kept_lines.append("\n[... section truncated for length ...]")
    return {"lines": kept_lines, "was_truncated": True}

