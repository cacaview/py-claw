"""
Type definitions for compact subsystem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.schemas.common import Message

# Error messages
ERROR_MESSAGE_NOT_ENOUGH_MESSAGES = "Not enough messages to compact."
ERROR_MESSAGE_PROMPT_TOO_LONG = (
    "Conversation too long. Press esc twice to go up a few messages and try again."
)
ERROR_MESSAGE_USER_ABORT = "API Error: Request was aborted."
ERROR_MESSAGE_INCOMPLETE_RESPONSE = (
    "Compaction interrupted · This may be due to network issues — please try again."
)


@dataclass
class CompactionResult:
    """Result of a compaction operation.

    Contains the compacted conversation with boundary markers,
    summary messages, and metadata about the operation.
    """

    #: Boundary marker message indicating where compaction occurred.
    boundary_marker: Any  # SystemCompactBoundaryMessage

    #: Summary messages generated from the compacted content.
    summary_messages: list[Any]  # list[UserMessage]

    #: Attachments to be preserved after compaction.
    attachments: list[Any] = field(default_factory=list)

    #: Hook results from pre/post compact hooks.
    hook_results: list[Any] = field(default_factory=list)

    #: Messages to keep (tail of conversation after compaction).
    messages_to_keep: list[Any] | None = None  # list[Message] | None

    #: Optional user display message about the compaction.
    user_display_message: str | None = None

    #: Token count before compaction.
    pre_compact_token_count: int | None = None

    #: Token count after compaction.
    post_compact_token_count: int | None = None

    #: True token count after compaction (may differ from post_compact_token_count).
    true_post_compact_token_count: int | None = None

    #: Usage statistics from the compaction API call.
    compaction_usage: dict[str, Any] | None = None


@dataclass
class RecompactionInfo:
    """Information about recompaction in a chain.

    Passed from autoCompact to compactConversation to help
    analytics disambiguate different compaction scenarios.
    """

    #: Whether this is a recompaction in the same chain.
    is_recompaction_in_chain: bool = False

    #: Number of turns since previous compaction.
    turns_since_previous_compact: int = 0

    #: Turn ID of the previous compaction.
    previous_compact_turn_id: str | None = None

    #: Auto compact threshold that triggered this.
    auto_compact_threshold: int = 0

    #: Source of the query (startup, resume, etc.).
    query_source: str | None = None


@dataclass
class CompactTriggerReason:
    """Reason why compaction was triggered."""

    #: The trigger type.
    type: str  # "auto" | "manual" | "recompact"

    #: Human-readable description.
    description: str


@dataclass
class AutoCompactTrackingState:
    """Tracks auto-compact state across turns for circuit breaker.

    Tracks consecutive failures to prevent infinite retry loops when
    the context is irrecoverably over the token limit.
    """
    #: Whether a compaction has occurred in this session.
    compacted: bool = False

    #: Turn counter since session start.
    turn_counter: int = 0

    #: Unique ID for current turn.
    turn_id: str | None = None

    #: Consecutive auto-compact failures. Reset on success.
    #: Used as circuit breaker to stop retrying when context
    #: is irrecoverably over the limit (e.g., prompt_too_long).
    consecutive_failures: int = 0


@dataclass
class CompactThresholdInfo:
    """Information about compact threshold calculation."""

    #: Effective threshold (context_window - reserve).
    effective_threshold: int

    #: Context window size.
    context_window: int

    #: Reserve amount.
    reserve: int

    #: Whether auto compact is enabled.
    auto_compact_enabled: bool = True

    #: Whether blocking is enabled.
    blocking_enabled: bool = True
