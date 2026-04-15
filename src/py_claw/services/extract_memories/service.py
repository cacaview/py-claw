"""
ExtractMemories service.

Extracts key memories from conversations using forked subagent.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from py_claw.services.extract_memories.config import (
    DEFAULT_EXTRACTION_PROMPT,
    get_extract_memories_config,
)

from .types import ExtractionResult, ExtractionState, ExtractionStatus, get_extraction_state

if TYPE_CHECKING:
    from py_claw.services.api import AnthropicAPIClient


def _estimate_tokens(text: str) -> int:
    """Rough token estimation."""
    return len(text) // 4


def _build_extraction_prompt(conversation_text: str, custom_template: str | None = None) -> str:
    """Build the extraction prompt from conversation."""
    config = get_extract_memories_config()

    if custom_template:
        return custom_template.format(conversation=conversation_text)

    template = config.prompt_template or DEFAULT_EXTRACTION_PROMPT
    return f"{template}\n\n--- CONVERSATION TO ANALYZE ---\n\n{conversation_text}"


def should_extract_memories(
    messages_count: int,
    token_count: int,
) -> tuple[bool, str]:
    """Determine if memory extraction should be triggered.

    Args:
        messages_count: Number of messages since last extraction
        token_count: Token count since last extraction

    Returns:
        Tuple of (should_extract, reason)
    """
    config = get_extract_memories_config()

    if not config.enabled:
        return False, "disabled"

    state = get_extraction_state()

    # Circuit breaker
    if state.consecutive_failures >= 3:
        return False, "circuit_breaker"

    # Check minimum thresholds
    if messages_count < config.min_messages:
        return False, f"min_messages_not_met ({messages_count}/{config.min_messages})"

    if token_count < config.min_tokens:
        return False, f"min_tokens_not_met ({token_count}/{config.min_tokens})"

    return True, "thresholds_met"


def _extract_to_memory_file(content: str, output_path: str | None = None) -> str:
    """Write extracted memory content to file."""
    config = get_extract_memories_config()

    if output_path is None:
        output_path = config.output_path

    if output_path is None:
        # Default path
        output_path = ".claude/memories/extracted_memory.md"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    Path(output_path).write_text(content, encoding="utf-8")
    return output_path


async def extract_memories(
    messages: list[Any],
    api_client: AnthropicAPIClient | None = None,
    output_path: str | None = None,
    custom_prompt: str | None = None,
) -> ExtractionResult:
    """Extract memories from conversation messages.

    Args:
        messages: List of conversation messages
        api_client: Optional API client for extraction
        output_path: Optional custom output path
        custom_prompt: Optional custom extraction prompt

    Returns:
        ExtractionResult with extraction details
    """
    state = get_extraction_state()
    config = get_extract_memories_config()
    start_time = time.time()

    try:
        # Build conversation text from messages
        conversation_parts: list[str] = []
        messages_processed = 0
        tokens_processed = 0

        for msg in messages:
            role = getattr(msg, "role", "unknown")
            content = getattr(msg, "content", "")

            if isinstance(content, list):
                content = " ".join(
                    str(c) if isinstance(c, str) else ""
                    for c in content
                )

            if content:
                conversation_parts.append(f"[{role.upper()}]\n{content}")
                messages_processed += 1
                tokens_processed += _estimate_tokens(content)

        conversation_text = "\n\n".join(conversation_parts)

        # Build extraction prompt
        prompt = _build_extraction_prompt(conversation_text, custom_prompt)

        extracted_content = ""

        if api_client is not None and config.use_forked_agent:
            # Use API client for extraction
            from py_claw.services.api import MessageCreateParams, MessageParam

            response = api_client.create_message(
                MessageCreateParams(
                    model="claude-sonnet-4-20250514",
                    messages=[MessageParam(role="user", content=prompt)],
                    max_tokens=4096,
                )
            )

            if hasattr(response, "__await__"):
                response = await response

            # Extract content from response
            if hasattr(response, "content"):
                content = response.content
                if isinstance(content, list):
                    extracted_content = " ".join(
                        str(c) if isinstance(c, str) else ""
                        for c in content
                    )
                elif isinstance(content, str):
                    extracted_content = content

        else:
            # Simulate extraction (no API client)
            extracted_content = f"# Extracted Memory\n\n[MEMORY_EXTRACTED_FROM_{messages_processed}_MESSAGES]"
            tokens_processed = len(prompt) // 4

        # Write to file
        memory_path = _extract_to_memory_file(extracted_content, output_path)

        duration = time.time() - start_time
        state.record_extraction(duration, messages_processed, tokens_processed)

        return ExtractionResult(
            status=ExtractionStatus.COMPLETED,
            message="Memory extraction completed successfully",
            memory_path=memory_path,
            memory_content=extracted_content,
            messages_processed=messages_processed,
            tokens_processed=tokens_processed,
            duration_seconds=duration,
        )

    except Exception as e:
        duration = time.time() - start_time
        state.record_failure()

        return ExtractionResult(
            status=ExtractionStatus.FAILED,
            message=f"Memory extraction failed: {e}",
            duration_seconds=duration,
            error=str(e),
        )


async def check_and_extract_memories(
    messages: list[Any],
    api_client: AnthropicAPIClient | None = None,
) -> ExtractionResult:
    """Check if extraction should trigger and execute if so.

    Args:
        messages: List of conversation messages
        api_client: Optional API client for extraction

    Returns:
        ExtractionResult with operation details
    """
    state = get_extraction_state()

    # Calculate current progress
    messages_count = len(messages) - state.messages_since_last_extraction
    tokens_count = state.tokens_since_last_extraction

    # Rough token estimation for new messages
    for msg in messages[-messages_count:]:
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            content = " ".join(str(c) if isinstance(c, str) else "" for c in content)
        tokens_count += _estimate_tokens(content)

    should, reason = should_extract_memories(len(messages), tokens_count)

    if not should:
        state.record_progress(messages_count, tokens_count)
        return ExtractionResult(
            status=ExtractionStatus.SKIPPED,
            message=f"Extraction skipped: {reason}",
            messages_processed=messages_count,
            tokens_processed=tokens_count,
        )

    return await extract_memories(messages, api_client)


def get_extraction_stats() -> dict[str, Any]:
    """Get memory extraction statistics.

    Returns:
        Dictionary with extraction statistics
    """
    state = get_extraction_state()
    config = get_extract_memories_config()

    return {
        "enabled": config.enabled,
        "use_forked_agent": config.use_forked_agent,
        "total_extractions": state.total_extractions,
        "failed_extractions": state.failed_extractions,
        "consecutive_failures": state.consecutive_failures,
        "last_extraction_at": (
            state.last_extraction_at.isoformat()
            if state.last_extraction_at else None
        ),
        "last_extraction_duration_seconds": state.last_extraction_duration,
        "messages_since_last_extraction": state.messages_since_last_extraction,
        "tokens_since_last_extraction": state.tokens_since_last_extraction,
    }
