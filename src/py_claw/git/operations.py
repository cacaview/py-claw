"""
Git operations for py-claw runtime.

Based on ClaudeCode-main/src/utils/git.ts
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from .types import (
    GitDiffResult,
    GitDiffStats,
    GitFileStatus,
    GitRepoState,
    NumstatResult,
    PerFileStats,
    PreservedGitState,
    StructuredPatchHunk,
)


# Constants
GIT_TIMEOUT_MS = 5000
MAX_FILES = 50
MAX_DIFF_SIZE_BYTES = 1_000_000
MAX_LINES_PER_FILE = 400
MAX_FILES_FOR_DETAILS = 500
SINGLE_FILE_DIFF_TIMEOUT_MS = 3000

# Size limits for untracked file capture
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500MB per file
MAX_TOTAL_SIZE_BYTES = 5 * 1024 * 1024 * 1024  # 5GB total
MAX_FILE_COUNT = 20000


def git_exe() -> str:
    """Get the git executable path, memoized."""
    import shutil
    return shutil.which("git") or "git"


def find_git_root(start_path: str) -> Optional[str]:
    """
    Find the git root by walking up the directory tree.

    Args:
        start_path: Directory to start searching from

    Returns:
        Directory containing .git, or None if not found
    """
    current = os.path.abspath(start_path)
    root = os.path.dirname(current)
    if not root:
        root = os.sep

    while current != root:
        git_path = os.path.join(current, ".git")
        if os.path.exists(git_path):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    # Check root directory as well
    git_path = os.path.join(root, ".git")
    if os.path.exists(git_path):
        return root

    return None


def get_is_git() -> bool:
    """Check if the current working directory is in a git repo."""
    cwd = os.getcwd()
    return find_git_root(cwd) is not None


def get_git_dir(cwd: str) -> Optional[str]:
    """Get the .git directory path for a given working directory."""
    git_root = find_git_root(cwd)
    if git_root:
        return os.path.join(git_root, ".git")
    return None


def is_at_git_root() -> bool:
    """Check if current working directory is at git root."""
    cwd = os.getcwd()
    git_root = find_git_root(cwd)
    if not git_root:
        return False
    return os.path.abspath(cwd) == os.path.abspath(git_root)


def dir_is_in_git_repo(cwd: str) -> bool:
    """Check if a directory is inside a git repository."""
    return find_git_root(cwd) is not None


def _run_git_command(
    args: list[str],
    cwd: Optional[str] = None,
    timeout_ms: int = GIT_TIMEOUT_MS,
    capture_output: bool = True,
) -> tuple[str, int]:
    """
    Run a git command and return stdout and return code.

    Args:
        args: Git command arguments
        cwd: Working directory
        timeout_ms: Command timeout in milliseconds
        capture_output: Whether to capture stdout

    Returns:
        Tuple of (stdout, return_code)
    """
    import subprocess

    try:
        timeout_sec = timeout_ms / 1000
        result = subprocess.run(
            [git_exe()] + args,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            timeout=timeout_sec,
        )
        stdout = result.stdout if capture_output else ""
        return stdout, result.returncode
    except subprocess.TimeoutExpired:
        return "", 1
    except Exception:
        return "", 1


def get_head() -> str:
    """Get current HEAD commit hash."""
    stdout, code = _run_git_command(["rev-parse", "HEAD"])
    if code == 0:
        return stdout.strip()
    return ""


def get_branch() -> str:
    """Get current branch name."""
    stdout, code = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
    if code == 0:
        return stdout.strip()
    return ""


def get_default_branch() -> str:
    """Get the default branch (main or master) of the remote."""
    # First try: get tracking branch
    stdout, code = _run_git_command(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
    )
    if code == 0 and stdout.strip():
        return stdout.strip()

    # Second try: check for common default branch names on origin
    for candidate in ["origin/main", "origin/staging", "origin/master"]:
        _, code = _run_git_command(["rev-parse", "--verify", candidate])
        if code == 0:
            return candidate

    return "main"


def get_remote_url() -> Optional[str]:
    """Get the remote URL for the current repo."""
    stdout, code = _run_git_command(["remote", "get-url", "origin"])
    if code == 0:
        return stdout.strip()
    return None


def get_is_head_on_remote() -> bool:
    """Check if HEAD is on a remote tracking branch."""
    _, code = _run_git_command(["rev-parse", "@{u}"])
    return code == 0


def has_unpushed_commits() -> bool:
    """Check if there are unpushed commits."""
    stdout, code = _run_git_command(["rev-list", "--count", "@{u}..HEAD"])
    if code == 0:
        try:
            return int(stdout.strip()) > 0
        except ValueError:
            pass
    return False


def get_is_clean(ignore_untracked: bool = False) -> bool:
    """
    Check if the working tree is clean.

    Args:
        ignore_untracked: If True, ignore untracked files

    Returns:
        True if clean (no changes)
    """
    args = ["status", "--porcelain"]
    if ignore_untracked:
        args.append("-uno")
    stdout, code = _run_git_command(args)
    return code == 0 and len(stdout.strip()) == 0


def get_changed_files() -> list[str]:
    """Get list of changed files."""
    stdout, code = _run_git_command(["status", "--porcelain"])
    if code != 0:
        return []

    files = []
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        # Remove status prefix (e.g., "M ", "A ", "??")
        parts = line.strip().split(" ", 1)
        if len(parts) > 1:
            files.append(parts[1].strip())
    return files


def get_file_status() -> GitFileStatus:
    """
    Get git file status.

    Returns:
        GitFileStatus with tracked and untracked file lists
    """
    stdout, code = _run_git_command(["status", "--porcelain"])
    tracked: list[str] = []
    untracked: list[str] = []

    if code != 0:
        return GitFileStatus(tracked=tracked, untracked=untracked)

    for line in stdout.strip().split("\n"):
        if not line:
            continue
        status = line[:2]
        filename = line[2:].strip()

        if status == "??":
            untracked.append(filename)
        elif filename:
            tracked.append(filename)

    return GitFileStatus(tracked=tracked, untracked=untracked)


def get_worktree_count() -> int:
    """Get the number of git worktrees."""
    stdout, code = _run_git_command(["worktree", "list", "--porcelain"])
    if code != 0:
        return 0

    count = 0
    for line in stdout.split("\n"):
        if line.startswith("worktree "):
            count += 1
    # Subtract 1 for the main worktree
    return max(0, count - 1)


def fetch_git_diff() -> Optional[GitDiffResult]:
    """
    Fetch git diff stats comparing working tree to HEAD.

    Returns None if not in a git repo or during transient states.
    """
    if not get_is_git():
        return None

    # Check for transient git states
    if _is_in_transient_git_state():
        return None

    # Quick probe with --shortstat
    stdout, code = _run_git_command(
        ["diff", "HEAD", "--shortstat"],
        timeout_ms=GIT_TIMEOUT_MS,
    )

    if code == 0:
        from .parsers import parse_shortstat

        quick_stats = parse_shortstat(stdout)
        if quick_stats and quick_stats.files_count > MAX_FILES_FOR_DETAILS:
            # Too many files - return stats only
            return GitDiffResult(
                stats=quick_stats,
                per_file_stats={},
                hunks={},
            )

    # Get stats via --numstat
    stdout, code = _run_git_command(
        ["diff", "HEAD", "--numstat"],
        timeout_ms=GIT_TIMEOUT_MS,
    )

    if code != 0:
        return None

    from .parsers import parse_git_numstat

    result = parse_git_numstat(stdout)

    # Include untracked files
    remaining_slots = MAX_FILES - len(result.per_file_stats)
    if remaining_slots > 0:
        untracked_stats = _fetch_untracked_files(remaining_slots)
        if untracked_stats:
            result.stats.files_count += len(untracked_stats)
            for path, file_stats in untracked_stats.items():
                result.per_file_stats[path] = file_stats

    return GitDiffResult(
        stats=result.stats,
        per_file_stats=result.per_file_stats,
        hunks={},
    )


def fetch_git_diff_hunks() -> dict[str, list[StructuredPatchHunk]]:
    """
    Fetch git diff hunks on-demand (for DiffDialog).

    Returns empty dict if not in git repo or during transient states.
    """
    if not get_is_git():
        return {}

    if _is_in_transient_git_state():
        return {}

    stdout, code = _run_git_command(
        ["diff", "HEAD"],
        timeout_ms=GIT_TIMEOUT_MS,
    )

    if code != 0:
        return {}

    from .parsers import parse_git_diff_hunks

    return parse_git_diff_hunks(stdout)


def _is_in_transient_git_state() -> bool:
    """Check if we're in a transient git state (merge, rebase, cherry-pick, revert)."""
    cwd = os.getcwd()
    git_dir = get_git_dir(cwd)
    if not git_dir:
        return False

    transient_files = [
        "MERGE_HEAD",
        "REBASE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
    ]

    for filename in transient_files:
        if os.path.exists(os.path.join(git_dir, filename)):
            return True
    return False


def _fetch_untracked_files(max_files: int) -> Optional[dict[str, PerFileStats]]:
    """
    Fetch untracked file names.

    Args:
        max_files: Maximum number of untracked files to include

    Returns:
        Dict mapping file paths to PerFileStats, or None if failed
    """
    stdout, code = _run_git_command(
        ["ls-files", "--others", "--exclude-standard"],
        timeout_ms=GIT_TIMEOUT_MS,
    )

    if code != 0 or not stdout.strip():
        return None

    untracked_paths = [p for p in stdout.strip().split("\n") if p]
    if not untracked_paths:
        return None

    per_file_stats: dict[str, PerFileStats] = {}
    for file_path in untracked_paths[:max_files]:
        per_file_stats[file_path] = PerFileStats(
            added=0,
            removed=0,
            is_binary=False,
            is_untracked=True,
        )

    return per_file_stats


def stash_to_clean_state(message: Optional[str] = None) -> bool:
    """
    Stash all changes (including untracked files) to return git to clean state.

    Args:
        message: Optional custom message for the stash

    Returns:
        True if stash was successful, False otherwise
    """
    try:
        stash_message = message or f"Claude Code auto-stash - {__import__('datetime').datetime.now().isoformat()}"

        # Check for untracked files
        file_status = get_file_status()

        # If we have untracked files, add them to the index first
        if file_status.untracked:
            _, code = _run_git_command(
                ["add"] + file_status.untracked,
                timeout_ms=GIT_TIMEOUT_MS,
            )
            if code != 0:
                return False

        # Now stash everything
        _, code = _run_git_command(
            ["stash", "push", "--message", stash_message],
            timeout_ms=GIT_TIMEOUT_MS,
        )
        return code == 0
    except Exception:
        return False


def get_git_state() -> Optional[GitRepoState]:
    """
    Get complete git repository state snapshot.

    Returns:
        GitRepoState or None if not in a git repo
    """
    try:
        commit_hash = get_head()
        branch_name = get_branch()
        remote_url = get_remote_url()
        is_head_on_remote = get_is_head_on_remote()
        is_clean = get_is_clean()
        worktree_count = get_worktree_count()

        return GitRepoState(
            commit_hash=commit_hash,
            branch_name=branch_name,
            remote_url=remote_url,
            is_head_on_remote=is_head_on_remote,
            is_clean=is_clean,
            worktree_count=worktree_count,
        )
    except Exception:
        return None


def get_repo_remote_hash() -> Optional[str]:
    """
    Returns SHA256 hash (first 16 chars) of the normalized git remote URL.

    This provides a globally unique identifier for the repository.
    """
    import hashlib

    remote_url = get_remote_url()
    if not remote_url:
        return None

    normalized = _normalize_git_remote_url(remote_url)
    if not normalized:
        return None

    hash_obj = hashlib.sha256(normalized.encode())
    return hash_obj.hexdigest()[:16]


def _normalize_git_remote_url(url: str) -> Optional[str]:
    """
    Normalizes a git remote URL to canonical form: host/owner/repo.

    Handles SSH and HTTPS URLs, and CCR git proxy URLs.
    """
    trimmed = url.strip()
    if not trimmed:
        return None

    # Handle SSH format: git@host:owner/repo.git
    import re

    ssh_match = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", trimmed)
    if ssh_match and ssh_match.group(1) and ssh_match.group(2):
        return f"{ssh_match.group(1)}/{ssh_match.group(2)}".lower()

    # Handle HTTPS/SSH URL format
    url_match = re.match(
        r"^(?:https?|ssh)://(?:[^@]+@)?([^/]+)/(.+?)(?:\.git)?$",
        trimmed,
    )
    if url_match and url_match.group(1) and url_match.group(2):
        host = url_match.group(1)
        path = url_match.group(2)

        # CCR git proxy URLs
        if _is_local_host(host) and path.startswith("git/"):
            proxy_path = path[4:]  # Remove "git/" prefix
            segments = proxy_path.split("/")
            # 3+ segments where first contains a dot -> host/owner/repo
            if len(segments) >= 3 and "." in segments[0]:
                return proxy_path.lower()
            # 2 segments -> owner/repo (legacy format, assume github.com)
            return f"github.com/{proxy_path}".lower()

        return f"{host}/{path}".lower()

    return None


def _is_local_host(host: str) -> bool:
    """Check if host is localhost or a loopback IP."""
    import re

    host_without_port = host.split(":")[0]
    if host_without_port == "localhost":
        return True
    if re.match(r"^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host_without_port):
        return True
    return False


def find_remote_base() -> Optional[str]:
    """
    Find the best remote branch to use as a base.

    Priority:
    1. Tracking branch
    2. origin/HEAD -> origin/main (or similar)
    3. origin/main, origin/staging, origin/master
    """
    # First try: get the tracking branch
    stdout, code = _run_git_command(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
    )
    if code == 0 and stdout.strip():
        return stdout.strip()

    # Second try: check for common default branch names on origin
    for candidate in ["origin/main", "origin/staging", "origin/master"]:
        _, code = _run_git_command(["rev-parse", "--verify", candidate])
        if code == 0:
            return candidate

    return None


def _is_shallow_clone() -> bool:
    """Check if we're in a shallow clone."""
    cwd = os.getcwd()
    git_dir = get_git_dir(cwd)
    if not git_dir:
        return False
    return os.path.exists(os.path.join(git_dir, "shallow"))


def _capture_untracked_files() -> list[dict[str, str]]:
    """
    Capture untracked files with their contents.

    Respects size limits and skips binary files.
    """
    from .types import BINARY_EXTENSIONS

    stdout, code = _run_git_command(
        ["ls-files", "--others", "--exclude-standard"],
        timeout_ms=GIT_TIMEOUT_MS,
    )

    trimmed = stdout.strip()
    if code != 0 or not trimmed:
        return []

    files = [f for f in trimmed.split("\n") if f]
    result: list[dict[str, str]] = []
    total_size = 0

    for file_path in files:
        if len(result) >= MAX_FILE_COUNT:
            break

        # Skip binary files by extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext in BINARY_EXTENSIONS:
            continue

        try:
            full_path = os.path.join(os.getcwd(), file_path)
            stats = os.stat(full_path)
            file_size = stats.st_size

            # Skip files exceeding per-file limit
            if file_size > MAX_FILE_SIZE_BYTES:
                continue

            # Check total size limit
            if total_size + file_size > MAX_TOTAL_SIZE_BYTES:
                break

            # Empty file
            if file_size == 0:
                result.append({"path": file_path, "content": ""})
                total_size += file_size
                continue

            # Read file content
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                result.append({"path": file_path, "content": content})
                total_size += file_size

        except Exception:
            # Skip files we can't read
            pass

    return result


def is_current_directory_bare_git_repo() -> bool:
    """
    Check if the current working directory appears to be a bare git repository.

    SECURITY: A bare repo in cwd means git will execute hooks/pre-commit
    from the cwd, which could be an attack vector.

    Returns:
        True if cwd looks like a bare git repo
    """
    cwd = os.getcwd()
    git_path = os.path.join(cwd, ".git")

    try:
        stats = os.stat(git_path)
        if stats.is_file():
            # worktree/submodule - Git follows the gitdir reference
            return False
        if stats.is_directory():
            git_head_path = os.path.join(git_path, "HEAD")
            try:
                head_stats = os.stat(git_head_path)
                if head_stats.is_file():
                    # normal repo - .git/HEAD valid
                    return False
            except OSError:
                # .git exists but no HEAD - fall through
                pass
    except OSError:
        # no .git - fall through to bare-repo check
        pass

    # No valid .git/HEAD found. Check if cwd has bare git repo indicators.
    try:
        if os.stat(os.path.join(cwd, "HEAD")).is_file():
            return True
    except OSError:
        pass

    try:
        if os.path.isdir(os.path.join(cwd, "objects")):
            return True
    except OSError:
        pass

    try:
        if os.path.isdir(os.path.join(cwd, "refs")):
            return True
    except OSError:
        pass

    return False


def preserve_git_state_for_issue() -> Optional[PreservedGitState]:
    """
    Preserve git state for issue submission.

    Uses remote base for more stable replay capability.

    Returns:
        PreservedGitState or None if not in a git repo
    """
    try:
        if not get_is_git():
            return None

        # Check for shallow clone
        is_shallow = _is_shallow_clone()

        if is_shallow:
            stdout, _ = _run_git_command(["diff", "HEAD"])
            untracked_files = _capture_untracked_files()
            return PreservedGitState(
                remote_base_sha=None,
                remote_base=None,
                patch=stdout,
                untracked_files=untracked_files,
                format_patch=None,
                head_sha=None,
                branch_name=None,
            )

        # Find the best remote base
        remote_base = find_remote_base()

        if not remote_base:
            # No remote found
            stdout, _ = _run_git_command(["diff", "HEAD"])
            untracked_files = _capture_untracked_files()
            return PreservedGitState(
                remote_base_sha=None,
                remote_base=None,
                patch=stdout,
                untracked_files=untracked_files,
                format_patch=None,
                head_sha=None,
                branch_name=None,
            )

        # Get the merge-base with remote
        stdout, code = _run_git_command(
            ["merge-base", "HEAD", remote_base],
            timeout_ms=GIT_TIMEOUT_MS,
        )

        if code != 0 or not stdout.strip():
            # Merge-base failed
            stdout, _ = _run_git_command(["diff", "HEAD"])
            untracked_files = _capture_untracked_files()
            return PreservedGitState(
                remote_base_sha=None,
                remote_base=None,
                patch=stdout,
                untracked_files=untracked_files,
                format_patch=None,
                head_sha=None,
                branch_name=None,
            )

        remote_base_sha = stdout.strip()

        # Run parallel commands
        diff_out, _ = _run_git_command(["diff", remote_base_sha])
        untracked_files = _capture_untracked_files()
        format_out, format_code = _run_git_command(
            ["format-patch", f"{remote_base_sha}..HEAD", "--stdout"]
        )
        head_out, _ = _run_git_command(["rev-parse", "HEAD"])
        branch_out, _ = _run_git_command(
            ["rev-parse", "--abbrev-ref", "HEAD"]
        )

        format_patch = format_out if format_code == 0 and format_out.strip() else None
        trimmed_branch = branch_out.strip()

        return PreservedGitState(
            remote_base_sha=remote_base_sha,
            remote_base=remote_base,
            patch=diff_out,
            untracked_files=untracked_files,
            format_patch=format_patch,
            head_sha=head_out.strip() if head_out.strip() else None,
            branch_name=trimmed_branch if trimmed_branch and trimmed_branch != "HEAD" else None,
        )
    except Exception:
        return None
