"""
Session Memory module for extracting and maintaining long-term conversation memory.

This module periodically extracts high-value conversation information into
markdown files in ~/.claude/session-memory/, making it available for
/resume and compaction operations.
"""
from __future__ import annotations

from .config import (
    DEFAULT_SESSION_MEMORY_CONFIG,
    SessionMemoryConfig,
    get_session_memory_config,
    set_session_memory_config,
)
from .state import (
    SessionMemoryState,
    get_last_summarized_message_id,
    has_met_initialization_threshold,
    has_met_update_threshold,
    mark_extraction_completed,
    mark_extraction_started,
    mark_session_memory_initialized,
    record_extraction_token_count,
    reset_session_memory_state,
    set_last_summarized_message_id,
    should_trigger_update,
    get_state,
)
from .memory_file import (
    get_memory_dir,
    get_memory_path,
    get_session_memory_content,
    init_session_memory,
    is_session_memory_empty,
    setup_session_memory_file,
)
from .extractor import (
    build_session_memory_update_prompt,
    extract_session_memory,
    should_extract_memory,
    truncate_session_memory_for_compact,
)

__all__ = [
    # Config
    "DEFAULT_SESSION_MEMORY_CONFIG",
    "SessionMemoryConfig",
    "get_session_memory_config",
    "set_session_memory_config",
    # State
    "SessionMemoryState",
    "get_last_summarized_message_id",
    "has_met_initialization_threshold",
    "has_met_update_threshold",
    "mark_extraction_completed",
    "mark_extraction_started",
    "record_extraction_token_count",
    "reset_session_memory_state",
    "set_last_summarized_message_id",
    # Memory file
    "get_memory_path",
    "get_session_memory_content",
    "init_session_memory",
    "is_session_memory_empty",
    "setup_session_memory_file",
    # Extractor
    "build_session_memory_update_prompt",
    "extract_session_memory",
    "should_extract_memory",
]
