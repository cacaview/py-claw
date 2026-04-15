"""
Environment utilities for py_claw.

Provides environment variable handling and detection.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class EnvInfo:
    """Information about the current environment."""
    is_ci: bool
    is_test: bool
    is_production: bool
    is_development: bool
    platform: str
    is_windows: bool
    is_macos: bool
    is_linux: bool


def get_env_info() -> EnvInfo:
    """
    Get information about the current environment.

    Returns:
        EnvInfo with environment details
    """
    return EnvInfo(
        is_ci=is_ci(),
        is_test=is_test(),
        is_production=is_production(),
        is_development=is_development(),
        platform=sys.platform,
        is_windows=sys.platform == "win32",
        is_macos=sys.platform == "darwin",
        is_linux=sys.platform == "linux",
    )


def is_ci() -> bool:
    """
    Check if running in a CI environment.

    Returns:
        True if CI environment detected
    """
    return (
        os.environ.get("CI") is not None
        or os.environ.get("GITHUB_ACTIONS") is not None
        or os.environ.get("GITLAB_CI") is not None
        or os.environ.get("JENKINS_URL") is not None
        or os.environ.get("TF_BUILD") is not None
    )


def is_test() -> bool:
    """
    Check if running in test mode.

    Returns:
        True if test mode detected
    """
    return (
        os.environ.get("PYTEST_CURRENT_TEST") is not None
        or os.environ.get("NODE_ENV") == "test"
        or "pytest" in sys.modules
    )


def is_production() -> bool:
    """
    Check if running in production mode.

    Returns:
        True if production mode detected
    """
    env = os.environ.get("NODE_ENV", os.environ.get("PY_ENV", ""))
    return env.lower() in ("production", "prod")


def is_development() -> bool:
    """
    Check if running in development mode.

    Returns:
        True if development mode detected
    """
    env = os.environ.get("NODE_ENV", os.environ.get("PY_ENV", ""))
    return env.lower() in ("development", "dev") or (not env and not is_production())


def get_env_bool(key: str, default: bool = False) -> bool:
    """
    Get an environment variable as a boolean.

    Truthy values: "1", "true", "yes", "on"
    Falsy values: "0", "false", "no", "off"

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        Boolean value
    """
    value = os.environ.get(key)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def get_env_int(key: str, default: int | None = None) -> int | None:
    """
    Get an environment variable as an integer.

    Args:
        key: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Integer value or default
    """
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_env_str(key: str, default: str = "") -> str:
    """
    Get an environment variable as a string.

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        String value
    """
    return os.environ.get(key, default)


def is_env_truthy(key: str | None) -> bool:
    """
    Check if an environment variable is truthy.

    Returns True for "1", "true" (case-insensitive).

    Args:
        key: Environment variable name, or None

    Returns:
        True if the value is truthy
    """
    if key is None:
        return False
    value = os.environ.get(key, "")
    return value.lower() in ("1", "true")


def get_required_env(key: str) -> str:
    """
    Get a required environment variable.

    Args:
        key: Environment variable name

    Returns:
        Value

    Raises:
        RuntimeError: If the variable is not set
    """
    value = os.environ.get(key)
    if value is None:
        raise RuntimeError(f"Required environment variable not set: {key}")
    return value


def get_claude_config_dir() -> str:
    """
    Get the Claude configuration directory.

    Returns:
        Config directory path
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
        return os.path.join(base, "claude")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/claude")
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return os.path.join(xdg_config, "claude")


def get_claude_data_dir() -> str:
    """
    Get the Claude data directory.

    Returns:
        Data directory path
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        return os.path.join(base, "claude")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/claude")
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        return os.path.join(xdg_data, "claude")
