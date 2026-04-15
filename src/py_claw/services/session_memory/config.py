"""
Configuration for session memory extraction thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionMemoryConfig:
    """Configuration for session memory extraction thresholds.

    These thresholds determine when to trigger session memory extraction.
    They use the same token counting as autocompact to ensure consistent
    behavior between the two features.
    """

    #: Minimum context window tokens before initializing session memory.
    minimum_message_tokens_to_init: int = 10_000

    #: Minimum context window growth (in tokens) between session memory updates.
    # Uses the same token counting as autocompact to measure actual context
    # growth, not cumulative API usage.
    minimum_tokens_between_update: int = 5_000

    #: Number of tool calls between session memory updates.
    tool_calls_between_updates: int = 3


# Default configuration values
DEFAULT_SESSION_MEMORY_CONFIG = SessionMemoryConfig()

# Current session memory configuration
_session_memory_config = SessionMemoryConfig()


def get_session_memory_config() -> SessionMemoryConfig:
    """Get the current session memory configuration."""
    return SessionMemoryConfig(
        minimum_message_tokens_to_init=_session_memory_config.minimum_message_tokens_to_init,
        minimum_tokens_between_update=_session_memory_config.minimum_tokens_between_update,
        tool_calls_between_updates=_session_memory_config.tool_calls_between_updates,
    )


def set_session_memory_config(config: SessionMemoryConfig) -> None:
    """Set the session memory configuration."""
    _session_memory_config.minimum_message_tokens_to_init = (
        config.minimum_message_tokens_to_init
    )
    _session_memory_config.minimum_tokens_between_update = (
        config.minimum_tokens_between_update
    )
    _session_memory_config.tool_calls_between_updates = (
        config.tool_calls_between_updates
    )
