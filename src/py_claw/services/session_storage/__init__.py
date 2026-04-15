"""Session storage utilities for session persistence and retrieval.

Re-implements ClaudeCode-main/src/utils/sessionStorage.ts and sessionStoragePortable.ts

This module provides:
- Session file path management (projects directory, session transcripts)
- Fast metadata extraction from session files (head/tail reading)
- JSON field extraction without full parsing
- Session search functionality
"""

from __future__ import annotations

from py_claw.services.session_storage.common import (
    LITE_READ_BUF_SIZE,
    MAX_SANITIZED_LENGTH,
    SKIP_PRECOMPACT_THRESHOLD,
    CanonicalizedSessionFile,
    LiteSessionFile,
    extract_first_prompt_from_head,
    extract_json_string_field,
    extract_last_json_string_field,
    find_project_dir,
    get_project_dir,
    get_projects_dir,
    read_head_and_tail,
    read_session_lite,
    resolve_session_file_path,
    sanitize_path,
    unescape_json_string,
    validate_uuid,
)

from py_claw.services.session_storage.storage import (
    SessionStorageEngine,
    get_session_storage_engine,
)

from py_claw.services.session_storage.search import (
    SessionSearchResult,
    search_sessions,
)

__all__ = [
    # Common utilities
    "LITE_READ_BUF_SIZE",
    "MAX_SANITIZED_LENGTH",
    "SKIP_PRECOMPACT_THRESHOLD",
    "LiteSessionFile",
    "CanonicalizedSessionFile",
    "validate_uuid",
    "unescape_json_string",
    "extract_json_string_field",
    "extract_last_json_string_field",
    "extract_first_prompt_from_head",
    "read_head_and_tail",
    "read_session_lite",
    "sanitize_path",
    "get_projects_dir",
    "get_project_dir",
    "find_project_dir",
    "resolve_session_file_path",
    # Storage engine
    "SessionStorageEngine",
    "get_session_storage_engine",
    # Search
    "SessionSearchResult",
    "search_sessions",
]
