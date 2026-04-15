"""
Commit attribution utility for tracking model usage in git commits.

Provides functionality to attribute commits to specific AI models and
sanitize model names for public display in git commit trailers.

Reference: ClaudeCode-main/src/utils/commitAttribution.ts
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Literal

# Allowlist of repos where internal model names are allowed in trailers
# Both SSH and HTTPS URL formats
INTERNAL_MODEL_REPOS: set[str] = {
    "github.com:anthropics/claude-cli-internal",
    "github.com/anthropics/claude-cli-internal",
    "github.com:anthropics/anthropic",
    "github.com/anthropics/anthropic",
    "github.com:anthropics/apps",
    "github.com/anthropics/apps",
    "github.com:anthropics/casino",
    "github.com/anthropics/casino",
    "github.com:anthropics/dbt",
    "github.com/anthropics/dbt",
    "github.com:anthropics/dotfiles",
    "github.com/anthropics/dotfiles",
    "github.com:anthropics/terraform-config",
    "github.com/anthropics/terraform-config",
    "github.com:anthropics/hex-export",
    "github.com/anthropics/hex-export",
    "github.com:anthropics/feedback-v2",
    "github.com/anthropics/feedback-v2",
    "github.com:anthropics/labs",
    "github.com/anthropics/labs",
    "github.com:anthropics/argo-rollouts",
    "github.com/anthropics/argo-rollouts",
    "github.com:anthropics/starling-configs",
    "github.com/anthropics/starling-configs",
    "github.com:anthropics/ts-tools",
    "github.com/anthropics/ts-tools",
    "github.com:anthropics/ts-capsules",
    "github.com/anthropics/ts-capsules",
    "github.com:anthropics/feldspar-testing",
    "github.com/anthropics/feldspar-testing",
    "github.com:anthropics/trellis",
    "github.com/anthropics/trellis",
    "github.com:anthropics/claude-for-hiring",
    "github.com/anthropics/claude-for-hiring",
    "github.com:anthropics/forge-web",
    "github.com/anthropics/forge-web",
    "github.com:anthropics/infra-manifests",
    "github.com/anthropics/infra-manifests",
    "github.com:anthropics/mycro_manifests",
    "github.com/anthropics/mycro_manifests",
    "github.com:anthropics/mycro_configs",
    "github.com/anthropics/mycro_configs",
    "github.com:anthropics/mobile-apps",
    "github.com/anthropics/mobile-apps",
}

# Cache for repo classification result
# 'internal' = remote matches INTERNAL_MODEL_REPOS allowlist
# 'external' = has a remote, not on allowlist (public/open-source repo)
# 'none' = no remote URL (not a git repo, or no remote configured)
_repo_class_cache: Literal["internal", "external", "none"] | None = None


def _get_cwd() -> str:
    """Get current working directory."""
    try:
        return os.getcwd()
    except OSError:
        return ""


def _get_original_cwd() -> str:
    """Get original working directory from bootstrap state."""
    try:
        from py_claw.bootstrap import get_original_cwd
        return get_original_cwd()
    except (ImportError, Exception):
        return os.getcwd()


def _find_git_root(path: str) -> str | None:
    """
    Find the git root directory for a given path.

    Args:
        path: Directory path to search from

    Returns:
        Path to git root or None if not in a git repo
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _get_remote_url(path: str) -> str | None:
    """
    Get the remote URL for a git repository.

    Args:
        path: Directory path within the git repo

    Returns:
        Remote URL or None if no remote configured
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def get_attribution_repo_root() -> str:
    """
    Get the repo root for attribution operations.

    Uses current working directory which respects agent worktree overrides,
    then resolves to git root to handle `cd subdir` case.
    Falls back to original cwd if git root can't be determined.
    """
    cwd = _get_cwd()
    git_root = _find_git_root(cwd)
    return git_root if git_root else _get_original_cwd()


def get_repo_class_cached() -> Literal["internal", "external", "none"] | None:
    """
    Synchronously return the cached repo classification.

    Returns None if the async check hasn't run yet.
    """
    return _repo_class_cache


def is_internal_model_repo_cached() -> bool:
    """
    Synchronously return the cached result of is_internal_model_repo().

    Returns False if the check hasn't run yet (safe default: don't leak).
    """
    return _repo_class_cache == "internal"


async def is_internal_model_repo() -> bool:
    """
    Check if the current repo is in the allowlist for internal model names.

    Memoized - only checks once per process.

    Returns:
        True if the repo is an internal model repo
    """
    global _repo_class_cache

    if _repo_class_cache is not None:
        return _repo_class_cache == "internal"

    cwd = get_attribution_repo_root()
    remote_url = _get_remote_url(cwd)

    if not remote_url:
        _repo_class_cache = "none"
        return False

    is_internal = any(repo in remote_url for repo in INTERNAL_MODEL_REPOS)
    _repo_class_cache = "internal" if is_internal else "external"
    return is_internal


def sanitize_model_name(short_name: str) -> str:
    """
    Sanitize a model name to its public equivalent.

    Maps internal variants to their public names based on model family.

    Args:
        short_name: Internal model name

    Returns:
        Public model name
    """
    # Map internal variants to public equivalents based on model family
    if "opus-4-6" in short_name:
        return "claude-opus-4-6"
    if "opus-4-5" in short_name:
        return "claude-opus-4-5"
    if "opus-4-1" in short_name:
        return "claude-opus-4-1"
    if "opus-4" in short_name:
        return "claude-opus-4"
    if "sonnet-4-6" in short_name:
        return "claude-sonnet-4-6"
    if "sonnet-4-5" in short_name:
        return "claude-sonnet-4-5"
    if "sonnet-4" in short_name:
        return "claude-sonnet-4"
    if "sonnet-3-7" in short_name:
        return "claude-sonnet-3-7"
    if "haiku-4-5" in short_name:
        return "claude-haiku-4-5"
    if "haiku-3-5" in short_name:
        return "claude-haiku-3-5"
    # Unknown models get a generic name
    return "claude"


def sanitize_surface_key(surface_key: str) -> str:
    """
    Sanitize a surface key to use public model names.

    Converts internal model variants to their public equivalents.

    Args:
        surface_key: Surface key (e.g., "cli/opus-4-5-fast")

    Returns:
        Sanitized surface key with public model name
    """
    # Split surface key into surface and model parts
    slash_index = surface_key.rfind("/")
    if slash_index == -1:
        return surface_key

    surface = surface_key[:slash_index]
    model = surface_key[slash_index + 1:]
    sanitized_model = sanitize_model_name(model)

    return f"{surface}/{sanitized_model}"


def reset_repo_class_cache() -> None:
    """Reset the repo classification cache. Used for testing."""
    global _repo_class_cache
    _repo_class_cache = None
