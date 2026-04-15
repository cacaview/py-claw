"""
Agent transcript recording service.

Records forked agent conversation transcripts to disk for resume
and long-term storage, following the sessionStorage.ts pattern.

Transcripts are stored in:
  ~/.claude/sessions/<session_id>/subagents/<agent_id>/transcript.jsonl
Metadata is stored in:
  ~/.claude/sessions/<session_id>/subagents/<agent_id>/metadata.json
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Path Helpers ───────────────────────────────────────────────────────────────


def _get_claude_config_home() -> Path:
    """Get the Claude config home directory."""
    return Path.home() / ".claude"


def _get_sessions_dir() -> Path:
    """Get the sessions directory."""
    return _get_claude_config_home() / "sessions"


def _get_subagents_dir(session_id: str) -> Path:
    """Get the subagents directory for a session."""
    return _get_sessions_dir() / session_id / "subagents"


def _get_agent_dir(session_id: str, agent_id: str) -> Path:
    """Get the directory for a specific agent."""
    return _get_subagents_dir(session_id) / agent_id


def _get_transcript_path(session_id: str, agent_id: str) -> Path:
    """Get the transcript file path for an agent."""
    return _get_agent_dir(session_id, agent_id) / "transcript.jsonl"


def _get_metadata_path(session_id: str, agent_id: str) -> Path:
    """Get the metadata file path for an agent."""
    return _get_agent_dir(session_id, agent_id) / "metadata.json"


# ─── Transcript Subdir Routing ─────────────────────────────────────────────────


# In-memory mapping of agent_id → subdir for transcript grouping
_agent_subdir_map: dict[str, str] = {}


def set_agent_transcript_subdir(agent_id: str, subdir: str) -> None:
    """Route an agent's transcript to a grouping subdirectory.

    For example, workflow subagents can write to subagents/workflows/<runId>/.
    """
    _agent_subdir_map[agent_id] = subdir


def clear_agent_transcript_subdir(agent_id: str) -> None:
    """Clear the transcript subdir routing for an agent."""
    _agent_subdir_map.pop(agent_id, None)


# ─── Agent Metadata ─────────────────────────────────────────────────────────────


@dataclass
class AgentMetadata:
    """Metadata for a forked agent session."""

    agent_type: str = ""
    worktree_path: str | None = None
    description: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def write_agent_metadata(
    agent_id: str,
    session_id: str,
    metadata: AgentMetadata,
) -> None:
    """Write agent metadata to disk.

    Args:
        agent_id: Unique agent identifier
        session_id: Parent session identifier
        metadata: Agent metadata to write
    """
    metadata_path = _get_metadata_path(session_id, agent_id)
    try:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        if metadata.created_at is None:
            metadata.created_at = datetime.now(timezone.utc).isoformat()
        metadata_path.write_text(json.dumps(metadata.to_dict(), indent=2), encoding="utf-8")
    except OSError as exc:
        logger.debug("Failed to write agent metadata for %s: %s", agent_id, exc)


def read_agent_metadata(agent_id: str, session_id: str) -> AgentMetadata | None:
    """Read agent metadata from disk.

    Args:
        agent_id: Unique agent identifier
        session_id: Parent session identifier

    Returns:
        AgentMetadata if found, None otherwise
    """
    metadata_path = _get_metadata_path(session_id, agent_id)
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        return AgentMetadata(**data)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


# ─── Sidechain Transcript ────────────────────────────────────────────────────────


async def record_sidechain_transcript(
    messages: list[dict[str, Any]],
    agent_id: str,
    session_id: str,
    starting_parent_uuid: str | None = None,
) -> None:
    """Record messages to the agent's sidechain transcript file.

    Appends messages in NDJSON format to allow streaming reads.
    Uses parent_uuid chain for message continuity.

    Args:
        messages: List of message dicts to record
        agent_id: Unique agent identifier
        session_id: Parent session identifier
        starting_parent_uuid: UUID of the last message before the new batch
    """
    if not messages:
        return

    transcript_path = _get_transcript_path(session_id, agent_id)
    try:
        transcript_path.parent.mkdir(parents=True, exist_ok=True)

        last_uuid: str | None = starting_parent_uuid
        with transcript_path.open("a", encoding="utf-8") as f:
            for msg in messages:
                # Build message with parent chain
                record: dict[str, Any] = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **msg,
                }
                if last_uuid is not None:
                    record["_parent_uuid"] = last_uuid

                f.write(json.dumps(record, ensure_ascii=False) + "\n")

                # Track last non-progress message UUID
                if msg.get("type") != "progress":
                    last_uuid = msg.get("uuid")

    except OSError as exc:
        logger.debug("Failed to record sidechain transcript for %s: %s", agent_id, exc)


def get_last_recorded_uuid(
    agent_id: str,
    session_id: str,
) -> str | None:
    """Get the UUID of the last recorded message.

    Args:
        agent_id: Unique agent identifier
        session_id: Parent session identifier

    Returns:
        UUID string of last message, or None if transcript is empty/missing
    """
    transcript_path = _get_transcript_path(session_id, agent_id)
    try:
        with transcript_path.open("rb") as f:
            # Seek to last line
            f.seek(0, 2)
            file_size = f.tell()
            if file_size == 0:
                return None

            # Read last line
            f.seek(max(0, file_size - 512))
            last_lines = f.read().decode("utf-8").strip().split("\n")
            if last_lines:
                try:
                    last_record = json.loads(last_lines[-1])
                    return last_record.get("uuid")
                except json.JSONDecodeError:
                    pass
    except (FileNotFoundError, OSError):
        pass
    return None


# ─── Transcript Reading ─────────────────────────────────────────────────────────


def read_agent_transcript(
    agent_id: str,
    session_id: str,
) -> list[dict[str, Any]]:
    """Read the full transcript for an agent.

    Args:
        agent_id: Unique agent identifier
        session_id: Parent session identifier

    Returns:
        List of message dicts from the transcript
    """
    transcript_path = _get_transcript_path(session_id, agent_id)
    messages: list[dict[str, Any]] = []
    try:
        with transcript_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except (FileNotFoundError, OSError):
        pass
    return messages


# ─── Transcript Service ─────────────────────────────────────────────────────────


class AgentTranscriptService:
    """Service for managing agent transcript recording.

    Integrates with ForkedAgentProcess to record conversations
    to disk for resume and long-term storage.
    """

    def __init__(self, session_id: str):
        """Initialize the transcript service.

        Args:
            session_id: Parent session identifier
        """
        self._session_id = session_id
        self._agent_subdir_map: dict[str, str] = {}

    def set_subdir(self, agent_id: str, subdir: str) -> None:
        """Route an agent's transcript to a grouping subdirectory."""
        self._agent_subdir_map[agent_id] = subdir
        set_agent_transcript_subdir(agent_id, subdir)

    def clear_subdir(self, agent_id: str) -> None:
        """Clear the transcript subdir routing for an agent."""
        self._agent_subdir_map.pop(agent_id, None)
        clear_agent_transcript_subdir(agent_id)

    async def record_messages(
        self,
        messages: list[dict[str, Any]],
        agent_id: str,
        parent_uuid: str | None = None,
    ) -> None:
        """Record messages to the agent's transcript file.

        Args:
            messages: Messages to record
            agent_id: Agent identifier
            parent_uuid: UUID of last message before this batch
        """
        await record_sidechain_transcript(
            messages=messages,
            agent_id=agent_id,
            session_id=self._session_id,
            starting_parent_uuid=parent_uuid,
        )

    async def write_metadata(
        self,
        agent_id: str,
        metadata: AgentMetadata,
    ) -> None:
        """Write agent metadata to disk.

        Args:
            agent_id: Agent identifier
            metadata: Metadata to write
        """
        await write_agent_metadata(
            agent_id=agent_id,
            session_id=self._session_id,
            metadata=metadata,
        )

    def get_last_uuid(self, agent_id: str) -> str | None:
        """Get the last recorded message UUID for an agent."""
        return get_last_recorded_uuid(
            agent_id=agent_id,
            session_id=self._session_id,
        )

    def read_transcript(self, agent_id: str) -> list[dict[str, Any]]:
        """Read the full transcript for an agent."""
        return read_agent_transcript(
            agent_id=agent_id,
            session_id=self._session_id,
        )
