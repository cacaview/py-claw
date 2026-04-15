"""Tests for the commit service."""

from __future__ import annotations

import pytest

from py_claw.services.commit import (
    AttributionState,
    AttributionData,
    AttributionSummary,
    FileAttribution,
    FileAttributionState,
    ContentBaseline,
    CommitAnalysisResult,
    CommitPreparationResult,
    create_empty_attribution_state,
    track_file_modification,
    analyze_staged_changes,
    prepare_commit,
    build_commit_prompt,
    get_current_branch,
    get_recent_commits,
    is_git_transient_state,
)


class TestCreateEmptyAttributionState:
    """Tests for create_empty_attribution_state."""

    def test_returns_valid_state(self):
        """Test that it returns a valid AttributionState."""
        state = create_empty_attribution_state()
        assert isinstance(state, AttributionState)
        assert state.file_states == {}
        assert state.session_baselines == {}
        assert state.surface == "cli"
        assert state.starting_head_sha is None
        assert state.prompt_count == 0
        assert state.prompt_count_at_last_commit == 0
        assert state.permission_prompt_count == 0
        assert state.permission_prompt_count_at_last_commit == 0
        assert state.escape_count == 0
        assert state.escape_count_at_last_commit == 0


class TestTrackFileModification:
    """Tests for track_file_modification."""

    def test_new_file_tracking(self):
        """Test tracking a new file."""
        state = create_empty_attribution_state()
        new_state = track_file_modification(
            state,
            file_path="test.py",
            old_content="",
            new_content="hello world",
        )
        assert "test.py" in new_state.file_states
        assert new_state.file_states["test.py"].claude_contribution == 11

    def test_modified_file_tracking(self):
        """Test tracking file modifications."""
        state = create_empty_attribution_state()
        state = track_file_modification(
            state,
            file_path="test.py",
            old_content="",
            new_content="hello",
        )
        state = track_file_modification(
            state,
            file_path="test.py",
            old_content="hello",
            new_content="hello world",
        )
        assert state.file_states["test.py"].claude_contribution == 11

    def test_deleted_file_tracking(self):
        """Test tracking file deletion."""
        state = create_empty_attribution_state()
        state = track_file_modification(
            state,
            file_path="test.py",
            old_content="hello world",
            new_content="",
        )
        assert state.file_states["test.py"].claude_contribution == 11

    def test_preserves_other_files(self):
        """Test that tracking one file doesn't affect others."""
        state = create_empty_attribution_state()
        state = track_file_modification(
            state,
            file_path="file1.py",
            old_content="",
            new_content="content1",
        )
        state = track_file_modification(
            state,
            file_path="file2.py",
            old_content="",
            new_content="content2",
        )
        assert "file1.py" in state.file_states
        assert "file2.py" in state.file_states


class TestAttributionTypes:
    """Tests for attribution types."""

    def test_file_attribution_state(self):
        """Test FileAttributionState creation."""
        fas = FileAttributionState(
            content_hash="abc123",
            claude_contribution=100,
            mtime=1234567890.0,
        )
        assert fas.content_hash == "abc123"
        assert fas.claude_contribution == 100
        assert fas.mtime == 1234567890.0

    def test_content_baseline(self):
        """Test ContentBaseline creation."""
        cb = ContentBaseline(
            content_hash="def456",
            mtime=1234567890.0,
        )
        assert cb.content_hash == "def456"
        assert cb.mtime == 1234567890.0

    def test_file_attribution(self):
        """Test FileAttribution creation."""
        fa = FileAttribution(
            claude_chars=80,
            human_chars=20,
            percent=80,
            surface="cli",
        )
        assert fa.claude_chars == 80
        assert fa.human_chars == 20
        assert fa.percent == 80
        assert fa.surface == "cli"

    def test_attribution_summary(self):
        """Test AttributionSummary creation."""
        summary = AttributionSummary(
            claude_percent=75,
            claude_chars=750,
            human_chars=250,
            surfaces=["cli"],
        )
        assert summary.claude_percent == 75
        assert summary.claude_chars == 750
        assert summary.human_chars == 250
        assert summary.surfaces == ["cli"]

    def test_attribution_data(self):
        """Test AttributionData creation."""
        data = AttributionData(
            version=1,
            summary=AttributionSummary(
                claude_percent=60,
                claude_chars=600,
                human_chars=400,
                surfaces=["cli"],
            ),
            files={"test.py": FileAttribution(60, 40, 60, "cli")},
            excluded_generated=[],
            sessions=[],
        )
        assert data.version == 1
        assert data.summary.claude_percent == 60
        assert "test.py" in data.files


class TestCommitAnalysisResult:
    """Tests for CommitAnalysisResult."""

    def test_creation(self):
        """Test CommitAnalysisResult creation."""
        result = CommitAnalysisResult(
            staged_files=["a.py", "b.py"],
            modified_files=["a.py"],
            new_files=["b.py"],
            deleted_files=[],
            total_changes=2,
            has_staged_changes=True,
            current_branch="main",
            recent_commits=["abc123 feat: add stuff"],
            is_in_transient_state=False,
        )
        assert result.staged_files == ["a.py", "b.py"]
        assert result.modified_files == ["a.py"]
        assert result.new_files == ["b.py"]
        assert result.deleted_files == []
        assert result.total_changes == 2
        assert result.has_staged_changes is True
        assert result.current_branch == "main"
        assert result.is_in_transient_state is False

    def test_no_staged_changes(self):
        """Test result for no staged changes."""
        result = CommitAnalysisResult(
            staged_files=[],
            modified_files=[],
            new_files=[],
            deleted_files=[],
            total_changes=0,
            has_staged_changes=False,
            current_branch="main",
            recent_commits=[],
            is_in_transient_state=False,
        )
        assert result.has_staged_changes is False
        assert result.total_changes == 0


class TestCommitPreparationResult:
    """Tests for CommitPreparationResult."""

    def test_not_ready_result(self):
        """Test CommitPreparationResult when not ready."""
        result = CommitPreparationResult(
            ready=False,
            staged_files=[],
            error_message="No staged changes to commit",
        )
        assert result.ready is False
        assert result.error_message == "No staged changes to commit"
        assert result.attribution_data is None

    def test_ready_result(self):
        """Test CommitPreparationResult when ready."""
        result = CommitPreparationResult(
            ready=True,
            staged_files=["test.py"],
            analysis=CommitAnalysisResult(
                staged_files=["test.py"],
                modified_files=["test.py"],
                new_files=[],
                deleted_files=[],
                total_changes=1,
                has_staged_changes=True,
                current_branch="main",
                recent_commits=[],
                is_in_transient_state=False,
            ),
            attribution_data=AttributionData(
                version=1,
                summary=AttributionSummary(50, 50, 50, ["cli"]),
            ),
        )
        assert result.ready is True
        assert result.error_message is None
        assert result.attribution_data is not None


class TestAnalyzeStagedChanges:
    """Tests for analyze_staged_changes."""

    def test_returns_analysis_result(self):
        """Test that analyze_staged_changes returns CommitAnalysisResult."""
        result = analyze_staged_changes()
        assert isinstance(result, CommitAnalysisResult)
        assert isinstance(result.staged_files, list)
        assert isinstance(result.modified_files, list)
        assert isinstance(result.new_files, list)
        assert isinstance(result.deleted_files, list)
        assert isinstance(result.current_branch, str)
        assert isinstance(result.recent_commits, list)
        assert isinstance(result.has_staged_changes, bool)
        assert isinstance(result.is_in_transient_state, bool)


class TestPrepareCommit:
    """Tests for prepare_commit."""

    def test_returns_preparation_result(self):
        """Test that prepare_commit returns CommitPreparationResult."""
        result = prepare_commit()
        assert isinstance(result, CommitPreparationResult)

    def test_no_staged_changes(self):
        """Test prepare_commit when nothing is staged."""
        result = prepare_commit()
        if not result.ready:
            assert "No staged changes" in (result.error_message or "")


class TestBuildCommitPrompt:
    """Tests for build_commit_prompt."""

    def test_returns_string(self):
        """Test that build_commit_prompt returns a string."""
        prompt = build_commit_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_contains_git_safety_protocol(self):
        """Test that prompt contains Git Safety Protocol."""
        prompt = build_commit_prompt()
        assert "Git Safety Protocol" in prompt
        assert "NEVER update the git config" in prompt
        assert "ALWAYS create NEW commits" in prompt
        assert "Never use git commands with the -i flag" in prompt

    def test_contains_context_section(self):
        """Test that prompt contains Context section."""
        prompt = build_commit_prompt()
        assert "## Context" in prompt

    def test_contains_task_section(self):
        """Test that prompt contains Your task section."""
        prompt = build_commit_prompt()
        assert "## Your task" in prompt


class TestGitOperations:
    """Tests for git utility operations."""

    def test_get_current_branch_returns_string(self):
        """Test that get_current_branch returns a string."""
        branch = get_current_branch()
        assert isinstance(branch, str)

    def test_get_recent_commits_returns_list(self):
        """Test that get_recent_commits returns a list."""
        commits = get_recent_commits(count=5)
        assert isinstance(commits, list)
        for commit in commits:
            assert isinstance(commit, str)

    def test_is_git_transient_state_returns_bool(self):
        """Test that is_git_transient_state returns a boolean."""
        result = is_git_transient_state()
        assert isinstance(result, bool)
