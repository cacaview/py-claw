"""
Git operation tracking types.

Shell-agnostic git operation detection for usage metrics.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class CommitKind(str, Enum):
    """Kind of git commit operation."""
    COMMITTED = "committed"
    AMENDED = "amended"
    CHERRY_PICKED = "cherry-picked"


class BranchAction(str, Enum):
    """Action taken on a branch."""
    MERGED = "merged"
    REBASED = "rebased"


class PrAction(str, Enum):
    """GitHub/GitLab PR/MR action."""
    CREATED = "created"
    EDITED = "edited"
    MERGED = "merged"
    COMMENTED = "commented"
    CLOSED = "closed"
    READY = "ready"


@dataclass
class CommitInfo:
    """Git commit information."""
    sha: str
    kind: CommitKind


@dataclass
class PushInfo:
    """Git push information."""
    branch: str


@dataclass
class BranchInfo:
    """Branch operation information."""
    ref: str
    action: BranchAction


@dataclass
class PrInfo:
    """Pull request information."""
    number: int
    url: str | None = None
    action: PrAction | None = None


@dataclass
class GitOperationResult:
    """
    Result of git operation detection.

    All fields are optional - only present when the corresponding
    operation was detected in the command and output.
    """
    commit: CommitInfo | None = None
    push: PushInfo | None = None
    branch: BranchInfo | None = None
    pr: PrInfo | None = None


# Regex patterns for git command detection
# Tolerates git's global options between 'git' and subcommand
# e.g., git -c commit.gpgsign=false commit

GIT_COMMAND_RE = re.compile(
    r"\bgit(?:\s+-[cC]\s+\S+|\s+--\S+=\S+)*\s+{subcmd}\b"
)

GIT_COMMIT_RE = re.compile(
    r"\bgit(?:\s+-[cC]\s+\S+|\s+--\S+=\S+)*\s+commit\b"
)
GIT_PUSH_RE = re.compile(
    r"\bgit(?:\s+-[cC]\s+\S+|\s+--\S+=\S+)*\s+push\b"
)
GIT_CHERRY_PICK_RE = re.compile(
    r"\bgit(?:\s+-[cC]\s+\S+|\s+--\S+=\S+)*\s+cherry-pick\b"
)
GIT_MERGE_RE = re.compile(
    r"\bgit(?:\s+-[cC]\s+\S+|\s+--\S+=\S+)*\s+merge\b(?!-)"
)
GIT_REBASE_RE = re.compile(
    r"\bgit(?:\s+-[cC]\s+\S+|\s+--\S+=\S+)*\s+rebase\b"
)

# GitHub CLI PR actions
GH_PR_CREATE_RE = re.compile(r"\bgh\s+pr\s+create\b")
GH_PR_EDIT_RE = re.compile(r"\bgh\s+pr\s+edit\b")
GH_PR_MERGE_RE = re.compile(r"\bgh\s+pr\s+merge\b")
GH_PR_COMMENT_RE = re.compile(r"\bgh\s+pr\s+comment\b")
GH_PR_CLOSE_RE = re.compile(r"\bgh\s+pr\s+close\b")
GH_PR_READY_RE = re.compile(r"\bgh\s+pr\s+ready\b")

# GitLab CLI MR actions (glab)
GLAB_MR_CREATE_RE = re.compile(r"\bglab\s+mr\s+create\b")

# PR URL patterns
PR_URL_RE = re.compile(
    r"https?://[^\s'\"]+/(pulls|pull-requests|merge[-_]requests)(?!\/\d)"
)

GITHUB_PR_URL_RE = re.compile(
    r"https://github\.com/([^/]+\/[^/]+)/pull/(\d+)"
)


def git_cmd_re(subcmd: str, suffix: str = "") -> re.Pattern[str]:
    """
    Build a regex that matches `git <subcmd>` while tolerating git's global
    options between `git` and the subcommand.

    Args:
        subcmd: Git subcommand to match
        suffix: Additional pattern suffix

    Returns:
        Compiled regex pattern
    """
    return re.compile(
        rf"\bgit(?:\s+-[cC]\s+\S+|\s+--\S+=\S+)*\s+{re.escape(subcmd)}\b{suffix}"
    )


def parse_git_commit_id(stdout: str) -> str | None:
    """
    Parse git commit SHA from commit output.

    Output format: [branch abc1234] message
    or for root commit: [branch (root-commit) abc1234] message

    Args:
        stdout: Command output

    Returns:
        Commit SHA (first 6 chars) or None
    """
    match = re.search(
        r"\[[\w./-]+(?: \(root-commit\))? ([0-9a-f]+)\]",
        stdout
    )
    return match.group(1) if match else None


def parse_git_push_branch(output: str) -> str | None:
    """
    Parse branch name from git push output.

    Push writes ref update to stderr but we check both.
    Format: abc..def  branch -> branch or [new branch] branch -> branch

    Args:
        output: Combined stdout/stderr output

    Returns:
        Branch name or None
    """
    match = re.search(
        r"^\s*[+\-*!= ]?\s*(?:\[new branch\]|\S+\.\.+\S+)\s+\S+\s*->\s*(\S+)",
        output,
        re.MULTILINE,
    )
    return match.group(1) if match else None


def parse_pr_url(url: str) -> dict | None:
    """
    Parse PR info from a GitHub PR URL.

    Args:
        url: PR URL

    Returns:
        Dict with prNumber, prUrl, prRepository or None
    """
    match = GITHUB_PR_URL_RE.match(url)
    if match and match.group(1) and match.group(2):
        return {
            "prNumber": int(match.group(2)),
            "prUrl": url,
            "prRepository": match.group(1),
        }
    return None


def find_pr_in_stdout(stdout: str) -> dict | None:
    """
    Find a GitHub PR URL embedded in stdout and parse it.

    Args:
        stdout: Command stdout

    Returns:
        Parsed PR info or None
    """
    match = re.search(
        r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+",
        stdout,
    )
    if match:
        return parse_pr_url(match.group(0))
    return None


def parse_pr_number_from_text(stdout: str) -> int | None:
    """
    Parse PR number from gh pr merge/close/ready text output.

    These commands print "✓ <Verb> pull request owner/repo#1234"
    with no URL.

    Args:
        stdout: Command output

    Returns:
        PR number or None
    """
    match = re.search(r"[Pp]ull request (?:\S+#)?#?(\d+)", stdout)
    if match and match.group(1):
        return int(match.group(1))
    return None


def parse_ref_from_command(command: str, verb: str) -> str | None:
    """
    Extract target ref from `git merge <ref>` / `git rebase <ref>` command.

    Args:
        command: Full command string
        verb: Git verb (merge, rebase)

    Returns:
        Target ref or None
    """
    pattern = git_cmd_re(verb)
    match = pattern.search(command)
    if not match:
        return None
    after = command[match.end():]
    for token in after.strip().split():
        if re.match(r"^[&|;><]", token):
            break
        if token.startswith("-"):
            continue
        return token
    return None
