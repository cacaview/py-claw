"""Tests for agent worktree management."""
from __future__ import annotations

import pytest

from py_claw.services.worktree import (
    is_ephemeral_slug,
    validate_worktree_slug,
    flatten_slug,
    worktree_branch_name,
)


class TestEphemeralSlugPatterns:
    """Test ephemeral worktree slug pattern matching."""

    def test_agent_slug_pattern(self):
        """AgentTool subagents use agent-a<7hex> pattern."""
        assert is_ephemeral_slug("agent-a1b2c3d4")  # 7 hex chars
        assert is_ephemeral_slug("agent-a1234567")  # 7 hex chars
        assert not is_ephemeral_slug("agent-a123456")  # too short (6 chars)
        assert not is_ephemeral_slug("agent-a12345678")  # too long (8 chars)
        assert not is_ephemeral_slug("agent-b1b2c3d4")  # wrong prefix 'b' instead of 'a'

    def test_workflow_slug_pattern(self):
        """WorkflowTool uses wf_<runId>-<idx> pattern."""
        assert is_ephemeral_slug("wf_12345678-abc-0")
        assert is_ephemeral_slug("wf_1a2b3c4d-e5f-123")
        assert not is_ephemeral_slug("wf_12345678-ab-0")  # runId too short
        assert not is_ephemeral_slug("wf_123456789-abcd-0")  # runId too long

    def test_legacy_workflow_slug_pattern(self):
        """Legacy wf-<idx> pattern is also recognized."""
        assert is_ephemeral_slug("wf-0")
        assert is_ephemeral_slug("wf-12345")

    def test_bridge_slug_pattern(self):
        """Bridge sessions use bridge-<safeFilenameId> pattern."""
        assert is_ephemeral_slug("bridge-session_abc")
        assert is_ephemeral_slug("bridge-my-session")
        assert is_ephemeral_slug("bridge-abc_def")

    def test_job_slug_pattern(self):
        """Template job worktrees use job-<templateName>-<8hex> pattern."""
        assert is_ephemeral_slug("job-myjob-a1b2c3d4")
        assert is_ephemeral_slug("job-test_template-12345678")

    def test_user_worktree_slugs_not_ephemeral(self):
        """User-named worktrees should not be treated as ephemeral."""
        assert not is_ephemeral_slug("my-feature")
        assert not is_ephemeral_slug("user/feature")
        assert not is_ephemeral_slug("pr-123")


class TestWorktreeSlugValidation:
    """Test worktree slug validation."""

    def test_valid_simple_slug(self):
        """Simple slugs without slashes are valid."""
        validate_worktree_slug("my-feature")
        validate_worktree_slug("agent-a1b2c3d")
        validate_worktree_slug("wf-123")
        validate_worktree_slug("test.123_456")

    def test_valid_nested_slug(self):
        """Slash-separated slugs are valid if segments are valid."""
        validate_worktree_slug("user/feature")
        validate_worktree_slug("team/project/branch")

    def test_too_long_slug(self):
        """Slugs over 64 characters are invalid."""
        long_slug = "a" * 65
        with pytest.raises(ValueError, match="64 characters or fewer"):
            validate_worktree_slug(long_slug)

    def test_dot_segment_invalid(self):
        """Dot segments (. or ..) are invalid."""
        with pytest.raises(ValueError, match='must not contain "." or ".."'):
            validate_worktree_slug("foo/../bar")
        with pytest.raises(ValueError, match='must not contain "." or ".."'):
            validate_worktree_slug("foo/./bar")

    def test_invalid_characters(self):
        """Invalid characters in slug segments are rejected."""
        with pytest.raises(ValueError, match="contain only letters"):
            validate_worktree_slug("foo bar")
        with pytest.raises(ValueError, match="contain only letters"):
            validate_worktree_slug("foo@bar")
        with pytest.raises(ValueError, match="contain only letters"):
            validate_worktree_slug("foo#bar")

    def test_empty_segment_invalid(self):
        """Empty slug segments are invalid."""
        with pytest.raises(ValueError, match="contain only letters"):
            validate_worktree_slug("/foo")
        with pytest.raises(ValueError, match="contain only letters"):
            validate_worktree_slug("foo//bar")


class TestSlugFlattening:
    """Test slug flattening for git branch names."""

    def test_flatten_simple_slug(self):
        """Simple slugs are unchanged."""
        assert flatten_slug("my-feature") == "my-feature"
        assert flatten_slug("agent-a1b2c3d") == "agent-a1b2c3d"

    def test_flatten_nested_slug(self):
        """Nested slugs have / replaced with +."""
        assert flatten_slug("user/feature") == "user+feature"
        assert flatten_slug("team/project/branch") == "team+project+branch"


class TestWorktreeBranchName:
    """Test worktree branch name generation."""

    def test_branch_name_format(self):
        """Branch name format is worktree-<flattened-slug>."""
        assert worktree_branch_name("my-feature") == "worktree-my-feature"
        assert worktree_branch_name("user/feature") == "worktree-user+feature"
        assert worktree_branch_name("agent-a1b2c3d") == "worktree-agent-a1b2c3d"
