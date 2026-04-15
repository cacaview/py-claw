"""AwaySummary service types and configuration."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AwaySummaryConfig:
    """Configuration for the away summary service.

    Attributes:
        recent_message_window: Number of recent messages to include in the
            summary prompt. Helps avoid 'prompt too long' on large sessions.
        max_summary_length: Maximum length of the generated summary in characters.
    """

    # Recap only needs recent context — 30 messages ≈ ~15 exchanges.
    recent_message_window: int = 30

    # Maximum length of generated summary in characters.
    max_summary_length: int = 500