"""
Shared utilities for spawning teammates across different backends.

Based on ClaudeCode-main/src/utils/swarm/spawnUtils.ts

Handles:
- Getting teammate command path
- Building CLI flags to propagate to teammates
- Building environment variables to forward to teammates
"""
from __future__ import annotations

import os
import sys
from typing import Optional

# Team constants
TEAMMATE_COMMAND_ENV_VAR = "CLAUDE_CODE_TEAMMATE_COMMAND"

# Environment variables that must be forwarded to tmux-spawned teammates
TEAMMATE_ENV_VARS = [
    # API provider selection
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    # Custom API endpoint
    "ANTHROPIC_BASE_URL",
    # Config directory override
    "CLAUDE_CONFIG_DIR",
    # CCR marker
    "CLAUDE_CODE_REMOTE",
    # Remote memory
    "CLAUDE_CODE_REMOTE_MEMORY_DIR",
    # Proxy settings
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "NO_PROXY",
    "no_proxy",
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
]


def get_teammate_command() -> str:
    """
    Gets the command to use for spawning teammate processes.

    Uses TEAMMATE_COMMAND_ENV_VAR if set, otherwise falls back to the
    current process executable path.
    """
    env_val = os.environ.get(TEAMMATE_COMMAND_ENV_VAR)
    if env_val:
        return env_val

    # Check if running in bundled mode
    if getattr(sys, "frozen", False):
        return sys.executable
    return sys.executable


def _quote_arg(arg: str) -> str:
    """Quote an argument for shell passing."""
    # Simple quoting - wrap in single quotes and escape any embedded single quotes
    return "'" + arg.replace("'", "'\\''") + "'"


def build_inherited_cli_flags(
    plan_mode_required: bool = False,
    permission_mode: Optional[str] = None,
    model_override: Optional[str] = None,
    settings_path: Optional[str] = None,
    inline_plugins: Optional[list[str]] = None,
    teammate_mode: str = "auto",
    chrome_flag_override: Optional[bool] = None,
    session_bypass_permissions: bool = False,
) -> str:
    """
    Builds CLI flags to propagate from the current session to spawned teammates.

    This ensures teammates inherit important settings like permission mode,
    model selection, and plugin configuration from their parent.

    Args:
        plan_mode_required: If true, don't inherit bypass permissions
        permission_mode: Permission mode to propagate
        model_override: Model override from CLI
        settings_path: Settings path from CLI
        inline_plugins: List of inline plugin directories
        teammate_mode: Teammate mode to propagate
        chrome_flag_override: Chrome flag override (True/False/None)
        session_bypass_permissions: Whether session has bypass permissions

    Returns:
        String of CLI flags
    """
    flags: list[str] = []

    # Propagate permission mode to teammates, but NOT if plan mode is required
    # Plan mode takes precedence over bypass permissions for safety
    if plan_mode_required:
        pass  # Don't inherit bypass permissions
    elif permission_mode == "bypassPermissions" or session_bypass_permissions:
        flags.append("--dangerously-skip-permissions")
    elif permission_mode == "acceptEdits":
        flags.append("--permission-mode acceptEdits")

    # Propagate --model if explicitly set via CLI
    if model_override:
        flags.append(f"--model {_quote_arg(model_override)}")

    # Propagate --settings if set via CLI
    if settings_path:
        flags.append(f"--settings {_quote_arg(settings_path)}")

    # Propagate --plugin-dir for each inline plugin
    if inline_plugins:
        for plugin_dir in inline_plugins:
            flags.append(f"--plugin-dir {_quote_arg(plugin_dir)}")

    # Propagate --teammate-mode so tmux teammates use the same mode as leader
    flags.append(f"--teammate-mode {teammate_mode}")

    # Propagate --chrome / --no-chrome if explicitly set on the CLI
    if chrome_flag_override is True:
        flags.append("--chrome")
    elif chrome_flag_override is False:
        flags.append("--no-chrome")

    return " ".join(flags)


def build_inherited_env_vars() -> str:
    """
    Builds the `KEY=VALUE` string for teammate spawn commands.

    Always includes CLAUDECODE=1 and CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1,
    plus any provider/config env vars that are set in the current process.
    """
    env_vars = ["CLAUDECODE=1", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1"]

    for key in TEAMMATE_ENV_VARS:
        value = os.environ.get(key)
        if value is not None and value != "":
            env_vars.append(f"{key}={_quote_arg(value)}")

    return " ".join(env_vars)


__all__ = [
    "TEAMMATE_COMMAND_ENV_VAR",
    "TEAMMATE_ENV_VARS",
    "get_teammate_command",
    "build_inherited_cli_flags",
    "build_inherited_env_vars",
]
