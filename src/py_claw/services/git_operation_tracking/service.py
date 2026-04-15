"""
Git operation tracking service.

Detects git operations in command strings and fires analytics events.
Shell-agnostic - works identically for Bash and PowerShell.
"""
from __future__ import annotations

from .types import (
    GIT_COMMIT_RE,
    GIT_PUSH_RE,
    GIT_CHERRY_PICK_RE,
    GIT_MERGE_RE,
    GIT_REBASE_RE,
    GH_PR_CREATE_RE,
    GH_PR_EDIT_RE,
    GH_PR_MERGE_RE,
    GH_PR_COMMENT_RE,
    GH_PR_CLOSE_RE,
    GH_PR_READY_RE,
    GLAB_MR_CREATE_RE,
    CommitKind,
    BranchAction,
    PrAction,
    CommitInfo,
    PushInfo,
    BranchInfo,
    PrInfo,
    GitOperationResult,
    find_pr_in_stdout,
    parse_git_commit_id,
    parse_git_push_branch,
    parse_pr_number_from_text,
    parse_ref_from_command,
    PR_URL_RE,
)


# GH PR action mapping
GH_PR_ACTIONS = [
    (GH_PR_CREATE_RE, "created", "pr_create"),
    (GH_PR_EDIT_RE, "edited", "pr_edit"),
    (GH_PR_MERGE_RE, "merged", "pr_merge"),
    (GH_PR_COMMENT_RE, "commented", "pr_comment"),
    (GH_PR_CLOSE_RE, "closed", "pr_close"),
    (GH_PR_READY_RE, "ready", "pr_ready"),
]


def detect_git_operation(
    command: str,
    output: str,
) -> GitOperationResult:
    """
    Scan command + output for git operations.

    Checks the command to avoid matching SHAs/URLs that merely
    appear in unrelated output (e.g., `git log`).

    Pass stdout+stderr concatenated - git push writes ref update to stderr.

    Args:
        command: Command string to analyze
        output: Combined stdout/stderr output

    Returns:
        GitOperationResult with detected operations
    """
    result = GitOperationResult()

    # Commit and cherry-pick both produce "[branch sha] msg" output
    is_cherry_pick = GIT_CHERRY_PICK_RE.search(command) is not None
    if GIT_COMMIT_RE.search(command) or is_cherry_pick:
        sha = parse_git_commit_id(output)
        if sha:
            if is_cherry_pick:
                kind = CommitKind.CHERRY_PICKED
            elif "--amend" in command:
                kind = CommitKind.AMENDED
            else:
                kind = CommitKind.COMMITTED
            result.commit = CommitInfo(sha=sha[:6], kind=kind)

    if GIT_PUSH_RE.search(command):
        branch = parse_git_push_branch(output)
        if branch:
            result.push = PushInfo(branch=branch)

    if GIT_MERGE_RE.search(command) and ("Fast-forward" in output or "Merge made by" in output):
        ref = parse_ref_from_command(command, "merge")
        if ref:
            result.branch = BranchInfo(ref=ref, action=BranchAction.MERGED)

    if GIT_REBASE_RE.search(command) and "Successfully rebased" in output:
        ref = parse_ref_from_command(command, "rebase")
        if ref:
            result.branch = BranchInfo(ref=ref, action=BranchAction.REBASED)

    # Check for GitHub PR actions
    for regex, action, _ in GH_PR_ACTIONS:
        if regex.search(command):
            pr_info = find_pr_in_stdout(output)
            if pr_info:
                result.pr = PrInfo(
                    number=pr_info["prNumber"],
                    url=pr_info["prUrl"],
                    action=PrAction(action),
                )
            else:
                num = parse_pr_number_from_text(output)
                if num:
                    result.pr = PrInfo(number=num, action=PrAction(action))
            break

    return result


def is_curl_post_command(command: str) -> bool:
    """
    Check if command is a curl POST request.

    Detects:
    - curl -X POST
    - curl --request POST
    - curl with -d (defaults to POST)

    Args:
        command: Command string

    Returns:
        True if command appears to be a curl POST
    """
    if "curl" not in command.lower():
        return False

    if re.search(r"-X\s*POST\b", command, re.IGNORECASE):
        return True
    if re.search(r"--request\s*=?\s*POST\b", command, re.IGNORECASE):
        return True
    if re.search(r"\s-d\s", command):
        return True
    return False


def is_pr_endpoint_in_curl(command: str) -> bool:
    """
    Check if command contains a PR/MR endpoint URL.

    Matches endpoints like:
    - /pulls (GitHub)
    - /pull-requests (GitLab)
    - /merge_requests (GitLab)

    Args:
        command: Command string

    Returns:
        True if PR endpoint detected
    """
    # Require https?:// prefix to avoid matching text in POST body
    return bool(PR_URL_RE.search(command))


import re

from .types import (
    CommitKind,
    PrAction,
)


def track_git_operations(
    command: str,
    exit_code: int,
    stdout: str = "",
    stderr: str = "",
) -> GitOperationResult | None:
    """
    Track git operations from command execution.

    Logs analytics events for successful operations and returns
    the detection result.

    Args:
        command: Command that was executed
        exit_code: Process exit code
        stdout: Standard output
        stderr: Standard error

    Returns:
        GitOperationResult if operations detected, None if not applicable
    """
    # Only track successful operations
    if exit_code != 0:
        return None

    # Import here to avoid circular imports
    from ..analytics.service import log_analytics_event

    output = stdout + "\n" + stderr
    result = detect_git_operation(command, output)

    # Log commit event
    if result.commit:
        log_analytics_event("tengu_git_operation", {"operation": "commit"})
        if result.commit.kind == CommitKind.AMENDED:
            log_analytics_event("tengu_git_operation", {"operation": "commit_amend"})

    # Log push event
    if result.push:
        log_analytics_event("tengu_git_operation", {"operation": "push"})

    # Log PR actions from GitHub CLI
    for regex, action, op in GH_PR_ACTIONS:
        if regex.search(command):
            log_analytics_event("tengu_git_operation", {"operation": op})
            break

    # Log GitLab MR creation
    if GLAB_MR_CREATE_RE.search(command):
        log_analytics_event("tengu_git_operation", {"operation": "pr_create"})

    # Detect curl-based PR creation (Bitbucket, GitHub API, GitLab API)
    if is_curl_post_command(command) and is_pr_endpoint_in_curl(command):
        log_analytics_event("tengu_git_operation", {"operation": "pr_create"})

    return result if any([result.commit, result.push, result.branch, result.pr]) else None


def get_operation_summary(result: GitOperationResult) -> str:
    """
    Get a human-readable summary of detected git operations.

    Args:
        result: Detected git operation result

    Returns:
        Summary string like "committed abc123, pushed to main"
    """
    parts = []

    if result.commit:
        parts.append(f"{result.commit.kind.value} {result.commit.sha}")

    if result.push:
        parts.append(f"pushed to {result.push.branch}")

    if result.branch:
        parts.append(f"{result.branch.action.value} {result.branch.ref}")

    if result.pr:
        action_str = result.pr.action.value if result.pr.action else "created"
        parts.append(f"{action_str} PR #{result.pr.number}")

    return ", ".join(parts) if parts else ""
