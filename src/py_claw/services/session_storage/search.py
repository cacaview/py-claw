"""Session search functionality.

Re-implements ClaudeCode-main/src/utils/sessionStorage.ts session search.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    pass

from py_claw.services.session_storage.common import (
    LiteSessionFile,
    get_projects_dir,
    read_session_lite,
    resolve_session_file_path,
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SessionSearchResult:
    """A session search result."""

    session_id: str
    file_path: str
    project_path: str | None
    custom_title: str | None = None
    tag: str | None = None
    agent_name: str | None = None
    first_prompt: str | None = None
    size: int = 0
    mtime: float = 0.0

    @property
    def modified_date(self) -> datetime:
        """Get modified date as datetime."""
        return datetime.fromtimestamp(self.mtime)


# ---------------------------------------------------------------------------
# Session search
# ---------------------------------------------------------------------------


async def search_sessions(
    project_path: str | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SessionSearchResult]:
    """Search for sessions.

    Args:
        project_path: Optional project path to search within
        query: Optional search query (matches against title, tag, first prompt)
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of SessionSearchResult
    """
    results: list[SessionSearchResult] = []
    projects_to_scan: list[tuple[str | None, Path]] = []

    if project_path:
        # Scan specific project
        projects_to_scan.append((project_path, Path(project_path)))
    else:
        # Scan all projects
        projects_dir = Path(get_projects_dir())
        if projects_dir.exists():
            for entry in projects_dir.iterdir():
                if entry.is_dir():
                    projects_to_scan.append((str(entry), entry))

    for _, project_dir in projects_to_scan:
        if not project_dir.exists():
            continue

        # Find all .jsonl files in project
        try:
            for entry in project_dir.iterdir():
                if not entry.name.endswith(".jsonl"):
                    continue

                session_id = entry.name[: -len(".jsonl")]
                if not _is_valid_session_id(session_id):
                    continue

                # Load lite metadata
                lite = await read_session_lite(str(entry))
                if not lite:
                    continue

                # Extract metadata
                metadata = _extract_metadata_from_lite(lite)

                # Apply query filter
                if query and not _matches_query(metadata, query):
                    continue

                results.append(
                    SessionSearchResult(
                        session_id=session_id,
                        file_path=str(entry),
                        project_path=str(project_dir),
                        custom_title=metadata.get("custom_title"),
                        tag=metadata.get("tag"),
                        agent_name=metadata.get("agent_name"),
                        first_prompt=metadata.get("first_prompt"),
                        size=lite.size,
                        mtime=lite.mtime,
                    )
                )
        except OSError:
            continue

    # Sort by mtime descending
    results.sort(key=lambda r: r.mtime, reverse=True)

    # Apply pagination
    return results[offset : offset + limit]


async def get_session_info(
    session_id: str,
    project_path: str | None = None,
) -> SessionSearchResult | None:
    """Get information about a specific session.

    Args:
        session_id: Session UUID
        project_path: Optional project path to search within

    Returns:
        SessionSearchResult, or None if not found
    """
    resolved = await resolve_session_file_path(session_id, project_path)
    if not resolved:
        return None

    lite = await read_session_lite(resolved.file_path)
    if not lite:
        return None

    metadata = _extract_metadata_from_lite(lite)

    return SessionSearchResult(
        session_id=session_id,
        file_path=resolved.file_path,
        project_path=resolved.project_path,
        custom_title=metadata.get("custom_title"),
        tag=metadata.get("tag"),
        agent_name=metadata.get("agent_name"),
        first_prompt=metadata.get("first_prompt"),
        size=lite.size,
        mtime=lite.mtime,
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _is_valid_session_id(session_id: str) -> bool:
    """Check if a string is a valid session ID."""
    if len(session_id) != 36:
        return False
    parts = session_id.split("-")
    if len(parts) != 5:
        return False
    if parts[0].__len__() != 8:
        return False
    return True


def _extract_metadata_from_lite(lite: LiteSessionFile) -> dict[str, Any]:
    """Extract metadata from a LiteSessionFile.

    Combines head and tail for field extraction since fields
    may be in either location.
    """
    from py_claw.services.session_storage.common import (
        extract_first_prompt_from_head,
        extract_last_json_string_field,
    )

    combined = lite.head + "\n" + lite.tail

    return {
        "custom_title": extract_last_json_string_field(combined, "customTitle"),
        "tag": extract_last_json_string_field(combined, "tag"),
        "agent_name": extract_last_json_string_field(combined, "agentName"),
        "agent_color": extract_last_json_string_field(combined, "agentColor"),
        "first_prompt": extract_first_prompt_from_head(lite.head),
    }


def _matches_query(metadata: dict[str, Any], query: str) -> bool:
    """Check if metadata matches a search query.

    Args:
        metadata: Session metadata
        query: Search query (lowercase)

    Returns:
        True if matches
    """
    query_lower = query.lower()

    # Check custom title
    title = metadata.get("custom_title")
    if title and query_lower in title.lower():
        return True

    # Check tag
    tag = metadata.get("tag")
    if tag and query_lower in tag.lower():
        return True

    # Check agent name
    agent = metadata.get("agent_name")
    if agent and query_lower in agent.lower():
        return True

    # Check first prompt
    prompt = metadata.get("first_prompt")
    if prompt and query_lower in prompt.lower():
        return True

    return False


async def list_session_files(
    project_path: str | None = None,
    limit: int = 100,
) -> list[str]:
    """List session files for a project.

    Args:
        project_path: Optional project path
        limit: Maximum number of results

    Returns:
        List of session file paths
    """
    results: list[tuple[float, str]] = []

    if project_path:
        projects_to_scan = [(project_path, Path(project_path))]
    else:
        projects_dir = Path(get_projects_dir())
        if not projects_dir.exists():
            return []
        projects_to_scan = [(str(p), p) for p in projects_dir.iterdir() if p.is_dir()]

    for _, project_dir in projects_to_scan:
        if not project_dir.exists():
            continue

        try:
            for entry in project_dir.iterdir():
                if not entry.name.endswith(".jsonl"):
                    continue
                if not _is_valid_session_id(entry.name[: -len(".jsonl")]):
                    continue

                try:
                    mtime = entry.stat().st_mtime
                    results.append((mtime, str(entry)))
                except OSError:
                    continue
        except OSError:
            continue

    # Sort by mtime descending
    results.sort(key=lambda x: x[0], reverse=True)

    return [path for _, path in results[:limit]]
