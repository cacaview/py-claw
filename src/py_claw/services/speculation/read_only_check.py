"""Bash read-only constraint checking for speculation.

Mirrors ClaudeCode-main/src/tools/BashTool/bashPermissions.ts and
readOnlyValidation.ts logic used in speculation's canUseTool callback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

from py_claw.services.speculation.constants import (
    READ_ONLY_COMMANDS,
    SAFE_READ_ONLY_TOOLS,
    WRITE_TOOLS,
)


@dataclass
class ReadOnlyCheckResult:
    """Result of a read-only constraint check.

    Mirrors the TypeScript BashSecurityCheckResult shape.
    """
    behavior: Literal["allow", "deny", "passthrough"]
    message: Optional[str] = None
    updated_input: Optional[dict] = None


def _extract_base_command(command: str) -> str:
    """Extract the base command (first word, no path) from a shell command.

    Args:
        command: Full shell command string

    Returns:
        Base command name without path
    """
    stripped = command.strip()

    # Handle compound commands - split on pipe, &&, ||
    for sep in (" | ", " || ", " && ", " > ", " >> ", " < ", " 2>", " & "):
        if sep in stripped:
            stripped = stripped.split(sep)[0].strip()

    tokens = stripped.split()
    if not tokens:
        return ""
    return tokens[0].split("/")[-1]


def _split_compound_command(command: str) -> list[str]:
    """Split a compound command by |, &&, || separators.

    Args:
        command: Shell command potentially containing compound operations

    Returns:
        List of individual command parts
    """
    parts = re.split(r"\|(?=(?:[^'\"]*'[^'\"]*')*[^'\"]*$)", command)
    result = []
    for part in parts:
        part = part.strip()
        if " && " in part:
            result.extend(part.split(" && "))
        elif " || " in part:
            result.extend(part.split(" || "))
        else:
            result.append(part)
    return [p.strip() for p in result if p.strip()]


def _is_read_only_subcommand(subcmd: str) -> bool:
    """Check if a subcommand is read-only.

    Args:
        subcmd: Single command component

    Returns:
        True if the subcommand is read-only
    """
    base = _extract_base_command(subcmd)
    if base in READ_ONLY_COMMANDS:
        return True
    if base == "git":
        return _is_read_only_git_command(subcmd)
    return False


def _is_read_only_git_command(command: str) -> bool:
    """Check if a git command is read-only.

    Args:
        command: Git command string

    Returns:
        True if the git command doesn't modify state
    """
    readonly_git = {
        "status",
        "diff",
        "log",
        "show",
        "ls-files",
        "ls-tree",
        "rev-parse",
        "describe",
        "branch",
        "tag",
        "stash list",
        "remote -v",
        "remote get-url",
        "config --get",
    }
    return any(cmd in command for cmd in readonly_git)


def check_read_only_constraints(
    command: str,
    cwd: str,
) -> ReadOnlyCheckResult:
    """Check if a bash command is read-only during speculation.

    Returns:
        - allow: command is read-only, safe to execute in speculation
        - deny: command is not read-only, should block speculation
        - passthrough: requires further permission checks (not a read-only concern)
    """
    if not command or not command.strip():
        return ReadOnlyCheckResult(behavior="allow")

    # Check for dangerous patterns via bash_security if available
    try:
        from py_claw.tools.bash_security import check_bash_security

        security_result = check_bash_security(command)
        if security_result.severity == "critical":
            return ReadOnlyCheckResult(
                behavior="deny",
                message=f"Critical security risk: {security_result.dangerous_patterns[0] if security_result.dangerous_patterns else 'unknown'}",
            )
    except ImportError:
        pass

    # Check path security
    try:
        from py_claw.tools.local_shell import check_path_security

        path_ok, path_reason = check_path_security(command, cwd)
        if not path_ok:
            return ReadOnlyCheckResult(
                behavior="deny",
                message=f"Path outside allowed scope: {path_reason}",
            )
    except ImportError:
        pass

    # Get base command
    base_cmd = _extract_base_command(command)

    # Check simple read-only command
    if base_cmd in READ_ONLY_COMMANDS:
        return ReadOnlyCheckResult(behavior="allow")

    # Check compound commands
    subcommands = _split_compound_command(command)
    if all(_is_read_only_subcommand(sc) for sc in subcommands):
        return ReadOnlyCheckResult(behavior="allow")

    return ReadOnlyCheckResult(
        behavior="passthrough",
        message="Command is not read-only",
    )


def check_tool_in_speculation(
    tool_name: str,
    arguments: dict,
    cwd: str,
    permission_mode: str = "ask",
    is_bypass_available: bool = False,
) -> tuple[bool, Optional[dict], Optional[dict]]:
    """Check if a tool is allowed during speculation with overlay redirection.

    This implements the speculation's canUseTool callback logic:
    - Write tools: only allowed in acceptEdits/bypassPermissions/plan+bypass modes
    - Read tools: always allowed, redirect to overlay if previously written
    - Bash: check read-only constraints
    - Other tools: deny

    Args:
        tool_name: Name of the tool
        arguments: Tool input arguments
        cwd: Current working directory
        permission_mode: Current permission mode ('ask', 'bypassPermissions', 'plan', etc.)
        is_bypass_available: Whether bypass permissions is available in plan mode

    Returns:
        (allowed, updated_arguments_or_none, boundary_dict_or_none)
        If allowed=False, boundary contains the stop reason.
    """
    import time

    is_write_tool = tool_name in WRITE_TOOLS
    is_safe_read_only = tool_name in SAFE_READ_ONLY_TOOLS

    # Determine if edits are allowed in current permission mode
    can_auto_accept_edits = (
        permission_mode in ("acceptEdits", "bypassPermissions")
        or (
            permission_mode == "plan"
            and is_bypass_available
        )
    )

    # Handle file path tools
    path_key: Optional[str] = None
    file_path: Optional[str] = None
    for key in ("notebook_path", "path", "file_path"):
        if key in arguments:
            path_key = key
            file_path = arguments[key]
            break

    if is_write_tool or is_safe_read_only:
        if file_path:
            try:
                rel = str(Path(file_path).relative_to(Path(cwd)))
            except ValueError:
                # Not relative to cwd - check if absolute or parent
                rel = file_path

            is_absolute_or_parent = (
                os.path.isabs(file_path) or rel.startswith("..")
            )

            # Write outside cwd is denied
            if is_absolute_or_parent and is_write_tool:
                return (
                    False,
                    {},
                    {
                        "type": "edit",
                        "toolName": tool_name,
                        "filePath": file_path or "",
                        "completedAt": int(time.time() * 1000),
                    },
                )

    # Handle write tools
    if is_write_tool:
        if not can_auto_accept_edits:
            # Edit boundary - speculation stops here
            return (
                False,
                {},
                {
                    "type": "edit",
                    "toolName": tool_name,
                    "filePath": file_path or "",
                    "completedAt": int(time.time() * 1000),
                },
            )

    # Handle Bash
    if tool_name == "Bash":
        command = arguments.get("command", "")
        check_result = check_read_only_constraints(command, cwd)
        if check_result.behavior != "allow":
            return (
                False,
                {},
                {
                    "type": "bash",
                    "command": command[:200],
                    "completedAt": int(time.time() * 1000),
                },
            )

    # Handle safe read-only tools - always allowed
    if is_safe_read_only:
        return (True, None, None)

    # Handle other tools - deny by default
    if tool_name not in WRITE_TOOLS and tool_name not in SAFE_READ_ONLY_TOOLS and tool_name != "Bash":
        detail = str(
            arguments.get("url", arguments.get("path", arguments.get("command", "")))
        )[:200]
        return (
            False,
            {},
            {
                "type": "denied_tool",
                "toolName": tool_name,
                "detail": detail,
                "completedAt": int(time.time() * 1000),
            },
        )

    return (True, None, None)


# Local import for Path
from pathlib import Path
import os
