"""
Tests for git operation tracking service.
"""
from __future__ import annotations

import pytest

from py_claw.services.git_operation_tracking import (
    CommitKind,
    BranchAction,
    PrAction,
    CommitInfo,
    PushInfo,
    BranchInfo,
    PrInfo,
    GitOperationResult,
    detect_git_operation,
    track_git_operations,
    is_curl_post_command,
    is_pr_endpoint_in_curl,
    get_operation_summary,
    parse_git_commit_id,
    parse_git_push_branch,
    parse_pr_url,
    find_pr_in_stdout,
    parse_pr_number_from_text,
    parse_ref_from_command,
    git_cmd_re,
)


class TestGitCmdRe:
    """Tests for git command regex builder."""

    def test_simple_subcmd(self) -> None:
        re = git_cmd_re("commit")
        assert re.search("git commit")
        assert re.search("git commit -m 'test'")
        # With global options
        assert re.search("git -c commit.gpgsign=false commit")

    def test_with_suffix(self) -> None:
        re = git_cmd_re("merge", "(?!-)")
        assert re.search("git merge")
        # Negative lookahead should prevent matching "merge-"

    def test_complex_options(self) -> None:
        re = git_cmd_re("push")
        assert re.search("git -C /path/to/repo push")
        assert re.search("git --git-dir=/path push")
        assert re.search("git -c user.name=test push")


class TestParseGitCommitId:
    """Tests for commit ID parsing."""

    def test_simple_commit(self) -> None:
        stdout = "[main abc1234] fix: a bug"
        assert parse_git_commit_id(stdout) == "abc1234"

    def test_root_commit(self) -> None:
        stdout = "[main (root-commit) abc1234] Initial commit"
        assert parse_git_commit_id(stdout) == "abc1234"

    def test_feature_branch(self) -> None:
        stdout = "[feature/my-branch abc1234] add feature"
        assert parse_git_commit_id(stdout) == "abc1234"

    def test_no_match(self) -> None:
        assert parse_git_commit_id("some random output") is None
        assert parse_git_commit_id("") is None


class TestParseGitPushBranch:
    """Tests for push branch parsing."""

    def test_new_branch(self) -> None:
        output = "* [new branch]         main -> main"
        assert parse_git_push_branch(output) == "main"

    def test_existing_branch_update(self) -> None:
        output = "abc1234..def5678  main -> main"
        assert parse_git_push_branch(output) == "main"

    def test_forced_update(self) -> None:
        output = " + abc...def  feature -> feature (forced update)"
        assert parse_git_push_branch(output) == "feature"

    def test_no_match(self) -> None:
        assert parse_git_push_branch("") is None
        assert parse_git_push_branch("random output") is None


class TestParsePrUrl:
    """Tests for PR URL parsing."""

    def test_github_pr_url(self) -> None:
        url = "https://github.com/owner/repo/pull/123"
        result = parse_pr_url(url)
        assert result == {
            "prNumber": 123,
            "prUrl": url,
            "prRepository": "owner/repo",
        }

    def test_github_pr_url_with_slashes(self) -> None:
        url = "https://github.com/anthropics/claude-code/pull/456"
        result = parse_pr_url(url)
        assert result == {
            "prNumber": 456,
            "prUrl": url,
            "prRepository": "anthropics/claude-code",
        }

    def test_invalid_url(self) -> None:
        assert parse_pr_url("https://github.com/owner/repo/issues/123") is None
        assert parse_pr_url("https://gitlab.com/owner/repo/pull/123") is None


class TestFindPrInStdout:
    """Tests for PR URL discovery in stdout."""

    def test_finds_pr_url(self) -> None:
        stdout = "Creating PR... https://github.com/owner/repo/pull/123"
        result = find_pr_in_stdout(stdout)
        assert result["prNumber"] == 123

    def test_no_pr_url(self) -> None:
        assert find_pr_in_stdout("No PR here") is None
        assert find_pr_in_stdout("") is None


class TestParsePrNumberFromText:
    """Tests for PR number parsing from text."""

    def test_merged_pr(self) -> None:
        stdout = "✓ Merged pull request owner/repo#123"
        assert parse_pr_number_from_text(stdout) == 123

    def test_closed_pr(self) -> None:
        stdout = "✓ Closed pull request #456"
        assert parse_pr_number_from_text(stdout) == 456

    def test_no_match(self) -> None:
        assert parse_pr_number_from_text("") is None
        assert parse_pr_number_from_text("random text") is None


class TestParseRefFromCommand:
    """Tests for ref extraction from merge/rebase commands."""

    def test_merge_branch(self) -> None:
        cmd = "git merge feature-branch"
        assert parse_ref_from_command(cmd, "merge") == "feature-branch"

    def test_merge_tag(self) -> None:
        cmd = "git merge v1.0.0"
        assert parse_ref_from_command(cmd, "merge") == "v1.0.0"

    def test_rebase_branch(self) -> None:
        cmd = "git rebase main"
        assert parse_ref_from_command(cmd, "rebase") == "main"

    def test_merge_with_flags(self) -> None:
        cmd = "git merge --no-ff feature-branch"
        # The function skips flags starting with -, so it returns the branch name
        assert parse_ref_from_command(cmd, "merge") == "feature-branch"


class TestDetectGitOperation:
    """Tests for git operation detection."""

    def test_detect_commit(self) -> None:
        result = detect_git_operation(
            "git commit -m 'fix bug'",
            "[main abc1234] fix bug"
        )
        assert result.commit is not None
        assert result.commit.sha == "abc123"
        assert result.commit.kind == CommitKind.COMMITTED

    def test_detect_amend(self) -> None:
        result = detect_git_operation(
            "git commit --amend -m 'updated'",
            "[main def5678] updated"
        )
        assert result.commit is not None
        assert result.commit.kind == CommitKind.AMENDED

    def test_detect_cherry_pick(self) -> None:
        result = detect_git_operation(
            "git cherry-pick abc123",
            "[main abc123] picked commit"
        )
        assert result.commit is not None
        assert result.commit.kind == CommitKind.CHERRY_PICKED

    def test_detect_push(self) -> None:
        result = detect_git_operation(
            "git push origin main",
            "abc..def  main -> main"
        )
        assert result.push is not None
        assert result.push.branch == "main"

    def test_detect_merge(self) -> None:
        result = detect_git_operation(
            "git merge feature-branch",
            "Fast-forward"
        )
        assert result.branch is not None
        assert result.branch.ref == "feature-branch"
        assert result.branch.action == BranchAction.MERGED

    def test_detect_rebase(self) -> None:
        result = detect_git_operation(
            "git rebase main",
            "Successfully rebased and fast-forwarded."
        )
        assert result.branch is not None
        assert result.branch.action == BranchAction.REBASED

    def test_detect_gh_pr_create(self) -> None:
        result = detect_git_operation(
            "gh pr create --title 'Fix' --body ''",
            "https://github.com/owner/repo/pull/123"
        )
        assert result.pr is not None
        assert result.pr.number == 123
        assert result.pr.action == PrAction.CREATED

    def test_detect_gh_pr_merge(self) -> None:
        result = detect_git_operation(
            "gh pr merge --admin --squash",
            "✓ Merged pull request owner/repo#456"
        )
        assert result.pr is not None
        assert result.pr.number == 456
        assert result.pr.action == PrAction.MERGED

    def test_no_operation(self) -> None:
        result = detect_git_operation(
            "git log --oneline",
            "abc123 commit message"
        )
        assert result.commit is None
        assert result.push is None
        assert result.branch is None
        assert result.pr is None


class TestCurlPostDetection:
    """Tests for curl POST detection."""

    def test_curl_x_post(self) -> None:
        cmd = "curl -X POST https://api.example.com/data"
        assert is_curl_post_command(cmd) is True

    def test_curl_request_flag(self) -> None:
        cmd = "curl --request POST https://api.example.com/data"
        assert is_curl_post_command(cmd) is True

    def test_curl_d_flag(self) -> None:
        cmd = "curl -d '{\"title\":\"test\"}' https://api.example.com"
        assert is_curl_post_command(cmd) is True

    def test_curl_get(self) -> None:
        cmd = "curl https://api.example.com/data"
        assert is_curl_post_command(cmd) is False

    def test_curl_put(self) -> None:
        cmd = "curl -X PUT https://api.example.com/data"
        assert is_curl_post_command(cmd) is False


class TestPrEndpointDetection:
    """Tests for PR endpoint detection."""

    def test_github_pulls_endpoint(self) -> None:
        cmd = "curl https://api.github.com/repos/owner/repo/pulls"
        assert is_pr_endpoint_in_curl(cmd) is True

    def test_gitlab_pull_requests_endpoint(self) -> None:
        cmd = "curl https://gitlab.com/api/v4/projects/123/pull-requests"
        assert is_pr_endpoint_in_curl(cmd) is True

    def test_gitlab_merge_requests_endpoint(self) -> None:
        cmd = "curl https://gitlab.com/api/v4/projects/123/merge_requests"
        assert is_pr_endpoint_in_curl(cmd) is True

    def test_non_pr_endpoint(self) -> None:
        cmd = "curl https://api.github.com/repos/owner/repo/issues"
        assert is_pr_endpoint_in_curl(cmd) is False


class TestGetOperationSummary:
    """Tests for operation summary generation."""

    def test_single_commit(self) -> None:
        result = GitOperationResult(
            commit=CommitInfo(sha="abc123", kind=CommitKind.COMMITTED)
        )
        summary = get_operation_summary(result)
        assert "committed" in summary
        assert "abc123" in summary

    def test_multiple_operations(self) -> None:
        result = GitOperationResult(
            commit=CommitInfo(sha="abc123", kind=CommitKind.COMMITTED),
            push=PushInfo(branch="main"),
        )
        summary = get_operation_summary(result)
        assert "committed" in summary
        assert "pushed" in summary
        assert "main" in summary

    def test_empty_result(self) -> None:
        result = GitOperationResult()
        assert get_operation_summary(result) == ""


class TestTrackGitOperations:
    """Tests for tracking with analytics events."""

    def test_tracks_successful_commit(self) -> None:
        result = track_git_operations(
            "git commit -m 'fix'",
            0,
            stdout="[main abc123] fix",
        )
        assert result is not None
        assert result.commit is not None

    def test_ignores_failed_commands(self) -> None:
        result = track_git_operations(
            "git commit -m 'fix'",
            1,  # Exit code 1 = failure
            stdout="[main abc123] fix",
        )
        assert result is None

    def test_tracks_gh_pr_create(self) -> None:
        result = track_git_operations(
            "gh pr create --title 'Fix'",
            0,
            stdout="https://github.com/owner/repo/pull/123",
        )
        assert result is not None
        assert result.pr is not None
        assert result.pr.action == PrAction.CREATED
