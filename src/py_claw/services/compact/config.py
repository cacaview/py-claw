"""
Configuration for compact subsystem.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompactConfig:
    """Configuration for context compaction.

    These values control when and how compaction is triggered.
    """

    #: Token threshold below effective context window to trigger auto-compact.
    #  Effective threshold = context_window - compact_token_reserve
    compact_token_reserve: int = 13_000

    #: Maximum compact streaming retries before giving up.
    max_compact_streaming_retries: int = 2

    #: Maximum files to restore after compaction.
    post_compact_max_files_to_restore: int = 5

    #: Token budget for post-compact restoration.
    post_compact_token_budget: int = 50_000

    #: Maximum tokens per file in post-compact restoration.
    post_compact_max_tokens_per_file: int = 5_000

    #: Maximum tokens per skill in post-compact restoration.
    post_compact_max_tokens_per_skill: int = 5_000

    #: Token budget for skills after compaction.
    post_compact_skills_token_budget: int = 25_000

    #: Maximum PTL retries before giving up.
    max_ptl_retries: int = 3


# Default configuration values
DEFAULT_COMPACT_CONFIG = CompactConfig()

# Current compact configuration
_compact_config = CompactConfig()


def get_compact_config() -> CompactConfig:
    """Get the current compact configuration."""
    return CompactConfig(
        compact_token_reserve=_compact_config.compact_token_reserve,
        max_compact_streaming_retries=_compact_config.max_compact_streaming_retries,
        post_compact_max_files_to_restore=_compact_config.post_compact_max_files_to_restore,
        post_compact_token_budget=_compact_config.post_compact_token_budget,
        post_compact_max_tokens_per_file=_compact_config.post_compact_max_tokens_per_file,
        post_compact_max_tokens_per_skill=_compact_config.post_compact_max_tokens_per_skill,
        post_compact_skills_token_budget=_compact_config.post_compact_skills_token_budget,
        max_ptl_retries=_compact_config.max_ptl_retries,
    )


def set_compact_config(config: CompactConfig) -> None:
    """Set the compact configuration."""
    _compact_config.compact_token_reserve = config.compact_token_reserve
    _compact_config.max_compact_streaming_retries = config.max_compact_streaming_retries
    _compact_config.post_compact_max_files_to_restore = config.post_compact_max_files_to_restore
    _compact_config.post_compact_token_budget = config.post_compact_token_budget
    _compact_config.post_compact_max_tokens_per_file = config.post_compact_max_tokens_per_file
    _compact_config.post_compact_max_tokens_per_skill = config.post_compact_max_tokens_per_skill
    _compact_config.post_compact_skills_token_budget = config.post_compact_skills_token_budget
    _compact_config.max_ptl_retries = config.max_ptl_retries
