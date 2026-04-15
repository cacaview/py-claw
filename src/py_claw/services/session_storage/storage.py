"""Session storage engine for reading and writing session transcripts.

Re-implements ClaudeCode-main/src/utils/sessionStorage.ts session file operations.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    pass

from py_claw.services.session_storage.common import (
    SKIP_PRECOMPACT_THRESHOLD,
    LiteSessionFile,
    get_claude_config_home_dir,
    get_project_dir,
    get_projects_dir,
    read_session_lite,
    sanitize_path,
)


# ---------------------------------------------------------------------------
# Session types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SessionMetadata:
    """Session metadata extracted from session file."""

    session_id: str
    custom_title: str | None = None
    tag: str | None = None
    agent_name: str | None = None
    agent_color: str | None = None
    first_prompt: str | None = None
    created_at: float | None = None
    modified_at: float | None = None


@dataclass
class SessionInfo:
    """Full session information."""

    session_id: str
    file_path: str
    project_path: str | None
    size: int
    mtime: float
    metadata: SessionMetadata


# ---------------------------------------------------------------------------
# Session storage engine
# ---------------------------------------------------------------------------


class SessionStorageEngine:
    """Engine for session file operations.

    Provides session persistence and retrieval with support for:
    - Session file creation and management
    - JSONL transcript appending
    - Metadata extraction and caching
    - Agent subdirectory support
    """

    def __init__(self) -> None:
        self._session_id: str | None = None
        self._session_file: str | None = None
        self._project_dir: str | None = None
        self._metadata_cache: dict[str, Any] = {}

    def set_session(self, session_id: str, project_dir: str | None = None) -> None:
        """Set the current session ID and project directory.

        Args:
            session_id: Session UUID
            project_dir: Optional project directory (defaults to cwd)
        """
        self._session_id = session_id
        if project_dir:
            self._project_dir = project_dir
        else:
            try:
                self._project_dir = get_project_dir(os.getcwd())
            except OSError:
                self._project_dir = None
        self._session_file = None

    def get_session_id(self) -> str | None:
        """Get the current session ID."""
        return self._session_id

    def get_session_file(self) -> str | None:
        """Get the current session file path.

        Creates the project directory and session file if needed.
        """
        if self._session_file:
            return self._session_file

        if not self._session_id or not self._project_dir:
            return None

        session_file = str(Path(self._project_dir) / f"{self._session_id}.jsonl")
        self._session_file = session_file
        return session_file

    def ensure_session_file(self) -> str | None:
        """Ensure the session file exists, creating if necessary.

        Returns:
            Session file path, or None if session not set
        """
        session_file = self.get_session_file()
        if not session_file:
            return None

        try:
            Path(session_file).parent.mkdir(parents=True, exist_ok=True)
            Path(session_file).touch(exist_ok=True)
        except OSError:
            pass

        return session_file

    def append_entry(self, entry: dict[str, Any]) -> None:
        """Append an entry to the session file.

        Args:
            entry: Entry to append (will be JSON serialized)
        """
        session_file = self.ensure_session_file()
        if not session_file:
            return

        try:
            with open(session_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    async def load_session_lite(self) -> LiteSessionFile | None:
        """Load lightweight session file metadata.

        Returns:
            LiteSessionFile with head/tail, or None if not found
        """
        session_file = self.get_session_file()
        if not session_file:
            return None

        return await read_session_lite(session_file)

    async def extract_metadata(self) -> SessionMetadata | None:
        """Extract metadata from the session file.

        Uses fast head/tail reading to extract:
        - customTitle
        - tag
        - agentName
        - agentColor
        - First user prompt

        Returns:
            SessionMetadata, or None if session not set
        """
        if not self._session_id:
            return None

        lite = await self.load_session_lite()
        if not lite:
            return SessionMetadata(session_id=self._session_id)

        # Import here to avoid circular
        from py_claw.services.session_storage.common import (
            extract_first_prompt_from_head,
            extract_json_string_field,
            extract_last_json_string_field,
        )

        custom_title = extract_last_json_string_field(lite.tail, "customTitle")
        tag = extract_last_json_string_field(lite.tail, "tag")
        agent_name = extract_last_json_string_field(lite.tail, "agentName")
        agent_color = extract_last_json_string_field(lite.tail, "agentColor")
        first_prompt = extract_first_prompt_from_head(lite.head)

        return SessionMetadata(
            session_id=self._session_id,
            custom_title=custom_title,
            tag=tag,
            agent_name=agent_name,
            agent_color=agent_color,
            first_prompt=first_prompt if first_prompt else None,
            created_at=None,
            modified_at=lite.mtime,
        )

    def cache_metadata(self, key: str, value: Any) -> None:
        """Cache metadata in memory.

        Args:
            key: Metadata key
            value: Metadata value
        """
        self._metadata_cache[key] = value

    def get_cached_metadata(self, key: str) -> Any:
        """Get cached metadata.

        Args:
            key: Metadata key

        Returns:
            Cached value, or None
        """
        return self._metadata_cache.get(key)

    def clear_metadata_cache(self) -> None:
        """Clear the metadata cache."""
        self._metadata_cache.clear()


# ---------------------------------------------------------------------------
# Global session storage engine
# ---------------------------------------------------------------------------

_session_storage_engine: SessionStorageEngine | None = None


def get_session_storage_engine() -> SessionStorageEngine:
    """Get the global session storage engine.

    Returns:
        The global SessionStorageEngine instance
    """
    global _session_storage_engine
    if _session_storage_engine is None:
        _session_storage_engine = SessionStorageEngine()
    return _session_storage_engine


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def get_current_session_id() -> str | None:
    """Get the current session ID from the global engine.

    Returns:
        Current session ID, or None
    """
    return get_session_storage_engine().get_session_id()


def get_current_session_file() -> str | None:
    """Get the current session file path.

    Returns:
        Session file path, or None
    """
    return get_session_storage_engine().get_session_file()


def set_current_session(session_id: str, project_dir: str | None = None) -> None:
    """Set the current session in the global engine.

    Args:
        session_id: Session UUID
        project_dir: Optional project directory
    """
    engine = get_session_storage_engine()
    engine.set_session(session_id, project_dir)


def append_to_session(entry: dict[str, Any]) -> None:
    """Append an entry to the current session file.

    Args:
        entry: Entry to append
    """
    get_session_storage_engine().append_entry(entry)


async def extract_current_session_metadata() -> SessionMetadata | None:
    """Extract metadata from the current session file.

    Returns:
        SessionMetadata, or None
    """
    return await get_session_storage_engine().extract_metadata()
