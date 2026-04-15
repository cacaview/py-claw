"""
Path utilities for py_claw.

Provides cross-platform path manipulation helpers.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Union


# Use pathlib for modern path operations
PathLike = Union[str, Path]


def normalize_path(path: PathLike) -> Path:
    """
    Normalize a path to a Path object.

    Args:
        path: Path to normalize

    Returns:
        Normalized Path object
    """
    return Path(path).expanduser().resolve()


def is_absolute_path(path: PathLike) -> bool:
    """
    Check if a path is absolute.

    Args:
        path: Path to check

    Returns:
        True if path is absolute
    """
    return Path(path).is_absolute()


def join_paths(*parts: PathLike) -> Path:
    """
    Join path components.

    Args:
        *parts: Path components to join

    Returns:
        Joined Path object
    """
    result = Path(parts[0]) if parts else Path(".")
    for part in parts[1:]:
        result = result / part
    return result


def get_home_dir() -> Path:
    """
    Get the user's home directory.

    Returns:
        Home directory path
    """
    return Path.home()


def get_config_home() -> Path:
    """
    Get the platform-specific config directory.

    On Windows: %APPDATA%
    On macOS: ~/Library/Application Support
    On Linux: ~/.config

    Returns:
        Config directory path
    """
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", get_home_dir() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        return get_home_dir() / "Library" / "Application Support"
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config)
        return get_home_dir() / ".config"


def get_cache_dir() -> Path:
    """
    Get the platform-specific cache directory.

    Returns:
        Cache directory path
    """
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", get_home_dir() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        return get_home_dir() / "Library" / "Caches"
    else:
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            return Path(xdg_cache)
        return get_home_dir() / ".cache"


def ensure_dir_exists(path: PathLike) -> Path:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path

    Returns:
        The directory path
    """
    dir_path = normalize_path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def is_subpath(child: PathLike, parent: PathLike) -> bool:
    """
    Check if child is a subpath of parent.

    Args:
        child: Potential child path
        parent: Potential parent path

    Returns:
        True if child is under parent
    """
    try:
        child_path = normalize_path(child)
        parent_path = normalize_path(parent)
        child_path.relative_to(parent_path)
        return True
    except ValueError:
        return False


def windows_to_posix_path(path: PathLike) -> str:
    """
    Convert a Windows path to POSIX format.

    Args:
        path: Path to convert

    Returns:
        POSIX-formatted path string
    """
    return str(Path(path)).replace("\\", "/")


def posix_to_windows_path(path: PathLike) -> str:
    """
    Convert a POSIX path to Windows format.

    Args:
        path: Path to convert

    Returns:
        Windows-formatted path string
    """
    return str(Path(path)).replace("/", "\\")


def get_relative_path(path: PathLike, base: PathLike) -> Path:
    """
    Get path relative to base.

    Args:
        path: Target path
        base: Base path

    Returns:
        Relative path
    """
    return normalize_path(path).relative_to(normalize_path(base))


def path_to_uri(path: PathLike) -> str:
    """
    Convert a file path to a file:// URI.

    Args:
        path: File path

    Returns:
        file:// URI
    """
    import urllib.parse

    path_str = normalize_path(path).as_uri()
    return path_str


def uri_to_path(uri: str) -> Path:
    """
    Convert a file:// URI to a file path.

    Args:
        uri: file:// URI

    Returns:
        File path
    """
    import urllib.parse

    if not uri.startswith("file://"):
        raise ValueError(f"Not a file URI: {uri}")

    # On Windows, file:///C:/... format
    # On Unix, file:///home/... format
    parsed = urllib.parse.urlparse(uri)
    if parsed.netloc:
        # Windows with network location
        path = "/" + parsed.netloc + parsed.path
    else:
        path = parsed.path

    return Path(urllib.parse.unquote(path))
