"""Tests for agent transcript service."""

import json
import tempfile
import asyncio
from pathlib import Path

import pytest

from py_claw.services.agent.transcript import (
    AgentMetadata,
    AgentTranscriptService,
    _get_agent_dir,
    _get_metadata_path,
    _get_transcript_path,
    clear_agent_transcript_subdir,
    get_last_recorded_uuid,
    read_agent_metadata,
    read_agent_transcript,
    record_sidechain_transcript,
    set_agent_transcript_subdir,
    write_agent_metadata,
)


class TestPathHelpers:
    """Test path helper functions."""

    def test_get_agent_dir(self):
        dir_path = _get_agent_dir("session-123", "agent-456")
        assert dir_path.name == "agent-456"
        assert dir_path.parent.name == "subagents"
        assert dir_path.parent.parent.name == "session-123"
        assert dir_path.parent.parent.parent.name == "sessions"

    def test_get_transcript_path(self):
        path = _get_transcript_path("session-123", "agent-456")
        assert path.name == "transcript.jsonl"
        assert path.parent.name == "agent-456"

    def test_get_metadata_path(self):
        path = _get_metadata_path("session-123", "agent-456")
        assert path.name == "metadata.json"
        assert path.parent.name == "agent-456"


class TestAgentMetadata:
    """Test AgentMetadata dataclass."""

    def test_metadata_defaults(self):
        metadata = AgentMetadata()
        assert metadata.agent_type == ""
        assert metadata.worktree_path is None
        assert metadata.description is None
        assert metadata.created_at is None

    def test_metadata_with_values(self):
        metadata = AgentMetadata(
            agent_type="Explore",
            worktree_path="/tmp/worktree",
            description="Test agent",
        )
        assert metadata.agent_type == "Explore"
        assert metadata.worktree_path == "/tmp/worktree"
        assert metadata.description == "Test agent"

    def test_to_dict(self):
        metadata = AgentMetadata(
            agent_type="Explore",
            description="Test agent",
        )
        d = metadata.to_dict()
        assert d["agent_type"] == "Explore"
        assert d["description"] == "Test agent"


@pytest.mark.asyncio
class TestWriteAgentMetadata:
    """Test write_agent_metadata function."""

    async def test_write_and_read_metadata(self, tmp_path: Path, monkeypatch):
        # Patch the config home to tmp_path
        def mock_home():
            return tmp_path

        monkeypatch.setattr("pathlib.Path.home", mock_home)

        agent_id = "test-agent-123"
        session_id = "test-session-456"

        metadata = AgentMetadata(
            agent_type="Explore",
            description="Test exploration agent",
            worktree_path="/tmp/test-worktree",
        )

        await write_agent_metadata(agent_id, session_id, metadata)

        # Read it back
        read_back = read_agent_metadata(agent_id, session_id)
        assert read_back is not None
        assert read_back.agent_type == "Explore"
        assert read_back.description == "Test exploration agent"
        assert read_back.worktree_path == "/tmp/test-worktree"
        assert read_back.created_at is not None

    async def test_read_nonexistent_metadata(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = read_agent_metadata("nonexistent", "nonexistent-session")
        assert result is None


@pytest.mark.asyncio
class TestRecordSidechainTranscript:
    """Test record_sidechain_transcript function."""

    async def test_record_and_read_transcript(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        agent_id = "test-agent-abc"
        session_id = "test-session-xyz"

        messages = [
            {"type": "user", "uuid": "msg-001", "role": "user", "content": "Hello"},
            {"type": "assistant", "uuid": "msg-002", "role": "assistant", "content": "Hi there"},
        ]

        await record_sidechain_transcript(
            messages=messages,
            agent_id=agent_id,
            session_id=session_id,
        )

        # Read it back
        transcript = read_agent_transcript(agent_id, session_id)
        assert len(transcript) == 2
        assert transcript[0]["uuid"] == "msg-001"
        assert transcript[0]["role"] == "user"
        assert transcript[1]["uuid"] == "msg-002"
        assert transcript[1]["role"] == "assistant"

    async def test_record_empty_messages(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        await record_sidechain_transcript(
            messages=[],
            agent_id="test-agent",
            session_id="test-session",
        )

        # Should not raise and transcript should be empty
        transcript = read_agent_transcript("test-agent", "test-session")
        assert transcript == []

    async def test_record_with_parent_uuid(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        agent_id = "test-agent"
        session_id = "test-session"

        messages = [
            {"type": "user", "uuid": "msg-001", "role": "user", "content": "Hello"},
        ]

        await record_sidechain_transcript(
            messages=messages,
            agent_id=agent_id,
            session_id=session_id,
            starting_parent_uuid="parent-msg-000",
        )

        transcript = read_agent_transcript(agent_id, session_id)
        assert transcript[0]["_parent_uuid"] == "parent-msg-000"


class TestGetLastRecordedUuid:
    """Test get_last_recorded_uuid function."""

    def test_get_last_uuid(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        agent_id = "test-agent"
        session_id = "test-session"

        messages = [
            {"type": "user", "uuid": "msg-001", "role": "user", "content": "Hello"},
            {"type": "assistant", "uuid": "msg-002", "role": "assistant", "content": "Hi"},
            {"type": "progress", "uuid": "msg-003", "role": "assistant", "content": "..."},
            {"type": "user", "uuid": "msg-004", "role": "user", "content": "World"},
        ]

        asyncio.run(record_sidechain_transcript(
            messages=messages,
            agent_id=agent_id,
            session_id=session_id,
        ))

        last_uuid = get_last_recorded_uuid(agent_id, session_id)
        # Last non-progress message is msg-004
        assert last_uuid == "msg-004"

    def test_empty_transcript(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = get_last_recorded_uuid("nonexistent", "nonexistent-session")
        assert result is None


class TestTranscriptSubdirRouting:
    """Test transcript subdirectory routing."""

    def test_set_and_clear_subdir(self):
        agent_id = "test-agent-xyz"

        set_agent_transcript_subdir(agent_id, "workflows/run-123")
        clear_agent_transcript_subdir(agent_id)

        # Should not raise - just tests the functions exist and work

    def test_subdir_map_is_global(self):
        agent_id_1 = "agent-001"
        agent_id_2 = "agent-002"

        set_agent_transcript_subdir(agent_id_1, "workflows/run-1")
        set_agent_transcript_subdir(agent_id_2, "workflows/run-2")

        clear_agent_transcript_subdir(agent_id_1)
        clear_agent_transcript_subdir(agent_id_2)


class TestAgentTranscriptService:
    """Test AgentTranscriptService class."""

    @pytest.mark.asyncio
    async def test_service_record_messages(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        service = AgentTranscriptService(session_id="test-session")
        agent_id = "test-agent"

        messages = [
            {"type": "user", "uuid": "msg-001", "content": "Test"},
        ]

        await service.record_messages(messages, agent_id)

        transcript = service.read_transcript(agent_id)
        assert len(transcript) == 1
        assert transcript[0]["uuid"] == "msg-001"

    @pytest.mark.asyncio
    async def test_service_write_metadata(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        service = AgentTranscriptService(session_id="test-session")
        agent_id = "test-agent"

        metadata = AgentMetadata(agent_type="Plan")
        await service.write_metadata(agent_id, metadata)

        read_back = read_agent_metadata(agent_id, "test-session")
        assert read_back is not None
        assert read_back.agent_type == "Plan"

    def test_service_set_and_clear_subdir(self):
        service = AgentTranscriptService(session_id="test-session")
        agent_id = "test-agent"

        service.set_subdir(agent_id, "workflows/run-123")
        service.clear_subdir(agent_id)

        # Should not raise
