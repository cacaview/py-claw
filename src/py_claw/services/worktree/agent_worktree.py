"""
Agent worktree management service.

Provides lightweight worktree creation/removal for subagents, independent of
the global session state. This enables worktree isolation for forked agents
without affecting the parent session's working directory or state.

Ephemeral worktree patterns:
- agent-a<7hex>: AgentTool subagents
- wf_<runId>-<idx>: WorkflowTool
- bridge-<safeFilenameId>: Bridge sessions
- job-<templateName>-<8hex>: Template job worktrees
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .types import AgentWorktreeResult

if TYPE_CHECKING:
    from py_claw.settings.loader import SettingsWithSources


# Ephemeral worktree slug patterns - these leak when parent process is killed
EPHEMERAL_WORKTREE_PATTERNS = [
    re.compile(r"^agent-a[0-9a-f]{7}$"),
    re.compile(r"^wf_[0-9a-f]{8}-[0-9a-f]{3}-\d+$"),
    # Legacy wf-<idx> slugs
    re.compile(r"^wf-\d+$"),
    # Bridge slugs: bridge-<safeFilenameId>
    re.compile(r"^bridge-[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$"),
    # Template job worktrees: job-<templateName>-<8hex>
    re.compile(r"^job-[a-zA-Z0-9._-]{1,55}-[0-9a-f]{8}$"),
]

# Max age for stale worktree cleanup (30 days)
STALE_WORKTREE_MAX_AGE_DAYS = 30


def is_ephemeral_slug(slug: str) -> bool:
    """Check if a worktree slug matches an ephemeral pattern."""
    return any(pattern.match(slug) for pattern in EPHEMERAL_WORKTREE_PATTERNS)


def validate_worktree_slug(slug: str) -> None:
    """
    Validates a worktree slug to prevent path traversal and directory escape.

    Each "/"-separated segment may contain only letters, digits, dots,
    underscores, and dashes; max 64 chars total.
    """
    if len(slug) > 64:
        raise ValueError(
            f"Invalid worktree name: must be 64 characters or fewer (got {len(slug)})"
        )

    segment_pattern = re.compile(r"^[a-zA-Z0-9._-]+$")
    for segment in slug.split("/"):
        if segment in (".", ".."):
            raise ValueError(
                f'Invalid worktree name "{slug}": must not contain "." or ".." path segments'
            )
        if not segment_pattern.match(segment):
            raise ValueError(
                f"Invalid worktree name: each \"/\"-separated segment must be "
                f"non-empty and contain only letters, digits, dots, underscores, and dashes"
            )


def flatten_slug(slug: str) -> str:
    """Flatten nested slugs (user/feature -> user+feature) for git branch name."""
    return slug.replace("/", "+")


def worktree_branch_name(slug: str) -> str:
    """Generate git branch name for a worktree."""
    return f"worktree-{flatten_slug(slug)}"


def worktree_path_for(repo_root: str, slug: str) -> str:
    """Get the worktree directory path for a slug."""
    return str(Path(repo_root) / ".claude" / "worktrees" / flatten_slug(slug))


def _git_repo_root(cwd: str) -> str | None:
    """Find the canonical git repository root."""
    completed = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    root = completed.stdout.strip()
    return str(Path(root).resolve()) if root else None


def _find_canonical_git_root(cwd: str) -> str | None:
    """Find canonical git root (resolves through worktrees to main repo)."""
    # Try to find git root first
    root = _git_repo_root(cwd)
    if root is None:
        return None

    # Check if we're in a worktree and find the canonical root
    git_dir_completed = subprocess.run(
        ["git", "-C", root, "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    if git_dir_completed.returncode != 0:
        return root

    git_dir = git_dir_completed.stdout.strip()
    # If git-dir is .git, we're in the main repo
    if git_dir == ".git":
        return root

    # We're in a worktree, find the main repo
    # The worktree's .git is a file pointing to the main repo's .git/worktrees/<name>
    try:
        with open(Path(root) / ".git", "r") as f:
            git_path = f.read().strip()
        if git_path.startswith("gitdir:"):
            git_path = git_path[7:].strip()
            # The worktree ref is in git_dir/worktrees/<name>
            if "/worktrees/" in git_path:
                main_git_dir = git_path.split("/worktrees/")[0]
                # Find the actual repo root by resolving the gitdir
                result = subprocess.run(
                    ["git", "-C", main_git_dir, "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass

    return root


def _get_default_branch(repo_root: str) -> str:
    """Get the default branch of a repository."""
    # Try main first, then master
    for branch in ["main", "master"]:
        result = subprocess.run(
            ["git", "-C", repo_root, "rev-parse", "--verify", f"origin/{branch}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return branch
    return "HEAD"


def _resolve_ref(repo_root: str, ref: str) -> str | None:
    """Resolve a git ref to a SHA."""
    result = subprocess.run(
        ["git", "-C", repo_root, "rev-parse", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _read_worktree_head_sha(worktree_path: str) -> str | None:
    """Read the HEAD SHA of an existing worktree (fast path without subprocess)."""
    head_file = Path(worktree_path) / ".git"
    if not head_file.exists():
        return None

    try:
        # Worktree .git is a file containing "gitdir: <path>"
        with open(head_file, "r") as f:
            content = f.read().strip()

        if content.startswith("gitdir:"):
            gitdir = content[7:].strip()
            head_sha_file = Path(gitdir) / "HEAD"
            if head_sha_file.exists():
                with open(head_sha_file, "r") as f:
                    sha = f.read().strip()
                # Could be direct SHA or ref
                if len(sha) == 40:
                    return sha
                elif sha.startswith("ref:"):
                    ref_file = Path(gitdir) / sha[5:].strip()
                    if ref_file.exists():
                        with open(ref_file, "r") as f:
                            return f.read().strip()
    except (OSError, subprocess.CalledProcessError):
        pass

    return None


def _exec_git_no_throw(
    args: list[str],
    cwd: str,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Execute git command and return (code, stdout, stderr)."""
    # Prevent git from prompting for credentials
    git_env = {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
    }
    if env:
        git_env.update(env)

    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, **git_env},
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


async def create_agent_worktree(
    slug: str,
    cwd: str | None = None,
) -> AgentWorktreeResult:
    """
    Create a lightweight worktree for a subagent.

    This does NOT touch global session state (currentWorktreeSession, process.chdir,
    project config). Falls back to hook-based creation if not in a git repository.

    Args:
        slug: Worktree slug (must match ephemeral pattern or be user-validated)
        cwd: Working directory to resolve git root from

    Returns:
        AgentWorktreeResult with worktree details

    Raises:
        ValueError: If slug is invalid
        RuntimeError: If git worktree creation fails
    """
    if cwd is None:
        cwd = os.getcwd()

    validate_worktree_slug(slug)

    # Try hook-based worktree creation first
    hook_result = _try_hook_worktree_create(slug, cwd)
    if hook_result is not None:
        return AgentWorktreeResult(
            worktree_path=hook_result["worktree_path"],
            worktree_branch=None,
            head_commit=None,
            git_root=None,
            hook_based=True,
        )

    # Fall back to git worktree
    git_root = _find_canonical_git_root(cwd)
    if git_root is None:
        raise RuntimeError(
            "Cannot create agent worktree: not in a git repository and no "
            "WorktreeCreate hooks are configured."
        )

    worktree_path = worktree_path_for(git_root, slug)
    worktree_branch = worktree_branch_name(slug)

    # Fast resume path: if worktree exists, skip creation
    existing_head = _read_worktree_head_sha(worktree_path)
    if existing_head:
        # Bump mtime so periodic cleanup doesn't consider this stale
        try:
            os.utime(worktree_path, None)
        except OSError:
            pass
        return AgentWorktreeResult(
            worktree_path=worktree_path,
            worktree_branch=worktree_branch,
            head_commit=existing_head,
            git_root=git_root,
            hook_based=False,
        )

    # Create worktree directory
    worktrees_dir = Path(git_root) / ".claude" / "worktrees"
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    # Get base branch
    default_branch = _get_default_branch(git_root)
    origin_ref = f"origin/{default_branch}"
    base_sha = _resolve_ref(git_root, origin_ref)
    base_branch = origin_ref if base_sha else "HEAD"

    # Fetch if needed
    if not base_sha:
        code, _, stderr = _exec_git_no_throw(
            ["fetch", "origin", default_branch],
            cwd=git_root,
        )
        if code == 0:
            base_sha = _resolve_ref(git_root, origin_ref)
            base_branch = origin_ref if base_sha else "HEAD"

    if not base_sha:
        base_sha = _resolve_ref(git_root, "HEAD") or "HEAD"
        base_branch = "HEAD"

    # Create worktree
    code, stdout, stderr = _exec_git_no_throw(
        ["worktree", "add", "-B", worktree_branch, worktree_path, base_branch],
        cwd=git_root,
    )

    if code != 0:
        raise RuntimeError(f"Failed to create worktree: {stderr or stdout}")

    # Get head commit
    head_commit = _resolve_ref(worktree_path, "HEAD") or base_sha

    # Perform post-creation setup (copy settings.local.json, configure hooks)
    _perform_post_creation_setup(git_root, worktree_path)

    return AgentWorktreeResult(
        worktree_path=worktree_path,
        worktree_branch=worktree_branch,
        head_commit=head_commit,
        git_root=git_root,
        hook_based=False,
    )


def remove_agent_worktree(
    worktree_path: str,
    worktree_branch: str | None = None,
    git_root: str | None = None,
    hook_based: bool = False,
) -> bool:
    """
    Remove a worktree created by createAgentWorktree.

    Args:
        worktree_path: Path to the worktree directory
        worktree_branch: Optional branch name to delete
        git_root: Git root of the main repository (required for git-based removal)
        hook_based: Whether the worktree was created via hook

    Returns:
        True if removal was successful
    """
    if hook_based:
        return _try_hook_worktree_remove(worktree_path)

    if git_root is None:
        git_root = _git_repo_root(worktree_path)
        if git_root is None:
            return False

    # Run from main repo root, not the worktree (which we're deleting)
    code, stdout, stderr = _exec_git_no_throw(
        ["worktree", "remove", "--force", worktree_path],
        cwd=git_root,
    )

    if code != 0:
        # Log error but don't fail - worktree might already be partially removed
        return False

    # Delete the worktree branch
    if worktree_branch:
        _exec_git_no_throw(
            ["branch", "-D", worktree_branch],
            cwd=git_root,
        )

    return True


def has_worktree_changes(worktree_path: str, head_commit: str) -> bool:
    """
    Check if a worktree has uncommitted changes or new commits.

    Returns True if there are changes (fail-closed).
    """
    # Check for uncommitted changes
    code, stdout, _ = _exec_git_no_throw(
        ["status", "--porcelain"],
        cwd=worktree_path,
    )
    if code != 0 or stdout.strip():
        return True

    # Check for new commits
    code, stdout, _ = _exec_git_no_throw(
        ["rev-list", "--count", f"{head_commit}..HEAD"],
        cwd=worktree_path,
    )
    if code != 0:
        return True

    try:
        commits = int(stdout.strip() or "0")
        if commits > 0:
            return True
    except ValueError:
        return True

    return False


def cleanup_stale_agent_worktrees(
    cwd: str | None = None,
    cutoff_days: int = STALE_WORKTREE_MAX_AGE_DAYS,
) -> int:
    """
    Remove stale agent/workflow worktrees older than cutoff date.

    Safety:
    - Only touches slugs matching ephemeral patterns (never user-named worktrees)
    - Skips the current session's worktree
    - Fail-closed: skips if git status fails or shows tracked changes
    - Fail-closed: skips if any commits aren't reachable from a remote

    Args:
        cwd: Working directory to resolve git root from
        cutoff_days: Maximum age of worktrees to keep (default 30 days)

    Returns:
        Number of worktrees removed
    """
    if cwd is None:
        cwd = os.getcwd()

    git_root = _find_canonical_git_root(cwd)
    if git_root is None:
        return 0

    worktrees_dir = Path(git_root) / ".claude" / "worktrees"
    if not worktrees_dir.exists():
        return 0

    cutoff_time = time.time() - (cutoff_days * 24 * 60 * 60)
    cutoff_date = datetime.fromtimestamp(cutoff_time, tz=timezone.utc)

    removed = 0

    for entry in worktrees_dir.iterdir():
        if not entry.is_dir():
            continue

        slug = entry.name

        # Only clean up ephemeral patterns
        if not is_ephemeral_slug(slug):
            continue

        # Check mtime
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue

        if mtime >= cutoff_time:
            continue

        worktree_path = str(entry)

        # Check git status
        code, stdout, _ = _exec_git_no_throw(
            ["--no-optional-locks", "status", "--porcelain", "-uno"],
            cwd=worktree_path,
        )
        if code != 0 or stdout.strip():
            continue

        # Check for unpushed commits
        code, stdout, _ = _exec_git_no_throw(
            ["rev-list", "--max-count=1", "HEAD", "--not", "--remotes"],
            cwd=worktree_path,
        )
        if code != 0 or stdout.strip():
            continue

        # Get head commit for has_worktree_changes check
        head_commit = _read_worktree_head_sha(worktree_path) or "HEAD"

        # Final safety check for changes
        if has_worktree_changes(worktree_path, head_commit):
            continue

        # Remove the worktree
        branch = worktree_branch_name(slug)
        if remove_agent_worktree(
            worktree_path=worktree_path,
            worktree_branch=branch,
            git_root=git_root,
            hook_based=False,
        ):
            removed += 1

    # Prune any stale worktree references
    if removed > 0:
        _exec_git_no_throw(["worktree", "prune"], cwd=git_root)

    return removed


def _try_hook_worktree_create(slug: str, cwd: str) -> dict | None:
    """
    Try to create worktree via WorktreeCreate hook.

    Returns hook result dict if hook exists and succeeds, None otherwise.
    """
    # Import here to avoid circular dependency
    from py_claw.hooks.runtime import get_hook_runtime

    try:
        hook_runtime = get_hook_runtime()
    except RuntimeError:
        return None

    if hook_runtime is None:
        return None

    # Check if hook exists
    hook_names = hook_runtime.list_hooks()
    if "WorktreeCreate" not in hook_names:
        return None

    try:
        from py_claw.settings.loader import get_settings_with_sources

        settings = get_settings_with_sources(cwd=cwd, home_dir=None)

        result = hook_runtime.run_worktree_create(
            settings=settings,
            cwd=cwd,
            name=slug,
            permission_mode="default",
        )

        if result.continue_ and isinstance(result.content, dict):
            worktree_path = result.content.get("worktreePath")
            if worktree_path:
                return {"worktree_path": worktree_path}
    except Exception:
        pass

    return None


def _try_hook_worktree_remove(worktree_path: str) -> bool:
    """Try to remove worktree via WorktreeRemove hook."""
    from py_claw.hooks.runtime import get_hook_runtime

    try:
        hook_runtime = get_hook_runtime()
    except RuntimeError:
        return False

    if hook_runtime is None:
        return False

    hook_names = hook_runtime.list_hooks()
    if "WorktreeRemove" not in hook_names:
        return False

    try:
        from py_claw.settings.loader import get_settings_with_sources

        cwd = os.getcwd()
        settings = get_settings_with_sources(cwd=cwd, home_dir=None)

        result = hook_runtime.run_worktree_remove(
            settings=settings,
            cwd=cwd,
            worktree_path=worktree_path,
            permission_mode="default",
        )

        return result.continue_
    except Exception:
        return False


def _perform_post_creation_setup(repo_root: str, worktree_path: str) -> None:
    """
    Post-creation setup for a newly created worktree.

    Propagates settings.local.json, configures git hooks.
    """
    # Copy settings.local.json to the worktree's .claude directory
    try:
        local_settings = Path(repo_root) / ".claude" / "settings.local.json"
        if local_settings.exists():
            dest_dir = Path(worktree_path) / ".claude"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_settings, dest_dir / "settings.local.json")
    except (OSError, shutil.Error):
        pass

    # Configure the worktree to use hooks from the main repository
    # This solves issues with .husky and other git hooks that use relative paths
    for hooks_candidate in [
        Path(repo_root) / ".husky",
        Path(repo_root) / ".git" / "hooks",
    ]:
        if hooks_candidate.exists() and hooks_candidate.is_dir():
            # Check if hooks are configured
            code, stdout, _ = _exec_git_no_throw(
                ["config", "--get", "core.hooksPath"],
                cwd=worktree_path,
            )
            current_hooks = stdout.strip()

            if str(hooks_candidate) != current_hooks:
                _exec_git_no_throw(
                    ["config", "core.hooksPath", str(hooks_candidate)],
                    cwd=worktree_path,
                )
            break
