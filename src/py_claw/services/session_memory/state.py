"""
Session memory state management.

Tracks extraction state, thresholds, and message IDs for
determining when to trigger session memory extraction.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .config import get_session_memory_config

# Timeout for waiting for extraction to complete (15 seconds)
EXTRACTION_WAIT_TIMEOUT_MS = 15000

# Threshold for considering an extraction stale (60 seconds)
EXTRACTION_STALE_THRESHOLD_MS = 60000


@dataclass
class SessionMemoryState:
    """Manages session memory extraction state."""

    #: Message ID up to which the session memory is current.
    last_summarized_message_id: str | None = None

    #: Context size at the time of last extraction (for minimumTokensBetweenUpdate).
    tokens_at_last_extraction: int = 0

    #: Whether session memory has been initialized (met minimumMessageTokensToInit).
    initialized: bool = False

    #: Timestamp when extraction started (None if not in progress).
    extraction_started_at: float | None = None

    def should_reset(self) -> bool:
        """Check if extraction should be considered stale and skipped."""
        if self.extraction_started_at is None:
            return False
        elapsed = (time.time() - self.extraction_started_at) * 1000
        return elapsed > EXTRACTION_STALE_THRESHOLD_MS


# Global state instance
_state = SessionMemoryState()


def get_last_summarized_message_id() -> str | None:
    """Get the message ID up to which the session memory is current."""
    return _state.last_summarized_message_id


def set_last_summarized_message_id(message_id: str | None) -> None:
    """Set the last summarized message ID."""
    _state.last_summarized_message_id = message_id


def mark_extraction_started() -> None:
    """Mark extraction as started."""
    _state.extraction_started_at = time.time()


def mark_extraction_completed() -> None:
    """Mark extraction as completed."""
    _state.extraction_started_at = None


def record_extraction_token_count(token_count: int) -> None:
    """Record the context size at the time of extraction.

    Used to measure context growth for minimumTokensBetweenUpdate threshold.
    """
    _state.tokens_at_last_extraction = token_count


def has_met_initialization_threshold(token_count: int) -> bool:
    """Check if the initialization threshold has been met.

    Initialization requires reaching a minimum token count.
    """
    config = get_session_memory_config()
    return token_count >= config.minimum_message_tokens_to_init


def has_met_update_threshold(token_count: int) -> bool:
    """Check if the update threshold has been met.

    Updates require both:
    - Token growth since last extraction >= minimum_tokens_between_update
    - Session memory has been initialized
    """
    if not _state.initialized:
        return False

    config = get_session_memory_config()
    token_growth = token_count - _state.tokens_at_last_extraction
    return token_growth >= config.minimum_tokens_between_update


def should_trigger_update(token_count: int, tool_call_count: int) -> bool:
    """Determine if a session memory update should be triggered.

    Token threshold is always required. Tool call threshold is an
    additional condition that can trigger updates at natural
    conversation breakpoints.
    """
    config = get_session_memory_config()

    # Token threshold must always be met first
    if not has_met_update_threshold(token_count):
        return False

    # Check if we're at a natural breakpoint (after tool calls)
    if tool_call_count >= config.tool_calls_between_updates:
        return True

    # Also trigger if token growth is significantly above threshold
    if not _state.initialized:
        return has_met_initialization_threshold(token_count)

    token_growth = token_count - _state.tokens_at_last_extraction
    if token_growth >= config.minimum_tokens_between_update * 2:
        return True

    return False


def reset_session_memory_state() -> None:
    """Reset all session memory state (for testing)."""
    _state.last_summarized_message_id = None
    _state.tokens_at_last_extraction = 0
    _state.initialized = False
    _state.extraction_started_at = None


def mark_session_memory_initialized() -> None:
    """Mark session memory as initialized after first successful extraction."""
    _state.initialized = True


def get_state() -> SessionMemoryState:
    """Get the current session memory state."""
    return _state
