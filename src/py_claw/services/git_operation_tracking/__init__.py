"""
Git operation tracking service.

Detects git operations (commit, push, merge, rebase, PR creation) in command strings
and fires analytics events. Shell-agnostic - works identically for Bash and PowerShell.

Basic usage:

    from py_claw.services.git_operation_tracking import detect_git_operation, track_git_operations

    # Detect operations without logging
    result = detect_git_operation("git commit -m 'fix bug'", "[main abc123] fix bug")
    if result.commit:
        print(f"Committed: {result.commit.sha}")

    # Detect and track with analytics events
    track_git_operations("gh pr create --title 'Fix'", 0, stdout="...")
"""
from __future__ import annotations

from .types import (
    CommitKind,
    BranchAction,
    PrAction,
    CommitInfo,
    PushInfo,
    BranchInfo,
    PrInfo,
    GitOperationResult,
    git_cmd_re,
    parse_git_commit_id,
    parse_git_push_branch,
    parse_pr_url,
    find_pr_in_stdout,
    parse_pr_number_from_text,
    parse_ref_from_command,
)
from .service import (
    detect_git_operation,
    track_git_operations,
    is_curl_post_command,
    is_pr_endpoint_in_curl,
    get_operation_summary,
)

__all__ = [
    # Types
    "CommitKind",
    "BranchAction",
    "PrAction",
    "CommitInfo",
    "PushInfo",
    "BranchInfo",
    "PrInfo",
    "GitOperationResult",
    # Functions
    "git_cmd_re",
    "parse_git_commit_id",
    "parse_git_push_branch",
    "parse_pr_url",
    "find_pr_in_stdout",
    "parse_pr_number_from_text",
    "parse_ref_from_command",
    "detect_git_operation",
    "track_git_operations",
    "is_curl_post_command",
    "is_pr_endpoint_in_curl",
    "get_operation_summary",
]
