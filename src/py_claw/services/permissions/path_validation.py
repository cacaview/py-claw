"""Path validation utilities for permission checks."""

from __future__ import annotations

import os
import re
from pathlib import Path

# Patterns that represent safety-sensitive paths
SENSITIVE_PATH_PATTERNS = [
    r"\.git/",
    r"\.git$",
    r"\.claude/",
    r"\.claude$",
    r"\.vscode/",
    r"\.vscode$",
    r"\.ssh/",
    r"\.ssh$",
    r"\.aws/",
    r"\.aws$",
    r"\.config/",
    r"\.config$",
    # Shell configuration files
    r"\.bashrc$",
    r"\.bash_profile$",
    r"\.zshrc$",
    r"\.profile$",
    r"\.fishrc$",
    # System files
    r"\.netrc$",
    r"\.npmrc$",
    r"\.gitconfig$",
    # Docker/Kubernetes
    r"\.docker/",
    r"\.docker$",
    r"\.kube/",
    r"\.kube$",
]


def _is_path_in_working_directory(path: str, working_dirs: list[str]) -> bool:
    """Check if path is within any of the allowed working directories."""
    try:
        path_obj = Path(path).resolve()
        for working_dir in working_dirs:
            working_obj = Path(working_dir).resolve()
            # Check if path is the same as or a child of working_dir
            try:
                path_obj.relative_to(working_obj)
                return True
            except ValueError:
                continue
        return False
    except Exception:
        return False


def path_in_allowed_working_path(path: str, allowed_paths: list[str]) -> bool:
    """
    Check if a path is within an allowed working path.

    Args:
        path: The path to check
        allowed_paths: List of allowed base paths

    Returns:
        True if path is within an allowed path
    """
    if not allowed_paths:
        return False

    # Normalize the path
    try:
        path_obj = Path(path).resolve()
    except Exception:
        return False

    for allowed in allowed_paths:
        try:
            allowed_obj = Path(allowed).resolve()
            # Check if path starts with allowed prefix
            try:
                path_obj.relative_to(allowed_obj)
                return True
            except ValueError:
                continue
        except Exception:
            continue

    return False


def check_path_safety_for_auto_edit(path: str) -> tuple[bool, str | None]:
    """
    Check if a path is safety-sensitive for auto-edit operations.

    Returns:
        Tuple of (is_safe, reason_if_unsafe)
    """
    path_lower = path.lower()

    # Check against sensitive patterns
    for pattern in SENSITIVE_PATH_PATTERNS:
        if re.search(pattern, path_lower):
            return False, f"Path matches sensitive pattern: {pattern}"

    # Check for hidden files/directories (starting with .)
    basename = os.path.basename(path)
    if basename.startswith(".") and basename not in (".gitignore", ".dockerignore"):
        # Allow .gitignore and .dockerignore but flag other hidden files
        pass  # Will be handled by pattern matching above

    return True, None


def is_protected_namespace(path: str) -> bool:
    """
    Check if path is in a protected namespace.

    Protected namespaces include system directories and sensitive user directories.
    """
    protected_prefixes = [
        "/System",
        "/Library",
        "/Applications",
        "/usr",
        "/bin",
        "/sbin",
        "/etc",
        "/var",
        # Windows equivalents
        "C:\\Windows",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
    ]

    path_obj = Path(path).resolve()
    for prefix in protected_prefixes:
        prefix_obj = Path(prefix)
        try:
            path_obj.relative_to(prefix_obj)
            return True
        except ValueError:
            continue

    return False
