from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from py_claw.tools.bash_security import BashSecurityCheckResult, check_bash_security

PermissionMode = Literal["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"]
YoloDecision = Literal["allow", "deny", "ask"]


@dataclass(frozen=True, slots=True)
class YoloClassification:
    """Result of yolo classifier evaluation."""
    decision: YoloDecision
    reason: str
    severity: str | None = None


# Tools that are always safe to auto-allow in any mode
_ALWAYS_SAFE_TOOLS = frozenset({
    "Read", "Glob", "Grep", "TaskCreate", "TaskGet", "TaskList",
    "TaskOutput", "TaskUpdate", "TaskStop", "Config", "ConfigList",
})

# Bash commands that are safe to auto-allow in read-only contexts
_SAFE_BASH_READONLY = frozenset({
    "ls", "dir", "pwd", "echo", "cat", "head", "tail", "less", "more",
    "sort", "uniq", "wc", "cut", "paste", "column", "tr", "file",
    "stat", "diff", "awk", "strings", "hexdump", "od", "base64", "nl",
    "grep", "rg", "jq", "which", "type", "command", "builtin",
    "hostname", "whoami", "id", "date", "printf", "true", "false",
})

# Bash commands that are never auto-allowed (even in yolo mode)
_NEVER_SAFE_BASH = frozenset({
    "rm", "del", "erase", "rd", "format", "dd", "mkfs", "fdisk",
    "mount", "umount", "chmod", "chown", "chgrp", "setfacl",
    "shutdown", "reboot", "halt", "poweroff", "init",
    "kill", "killall", "pkill", "killall5",
    "curl", "wget", "fetch", "ssh", "scp", "sftp",
    "nc", "netcat", "ncat", "telnet", "ftp",
    "bash", "sh", "zsh", "fish", "pwsh", "powershell",
    "python", "python3", "ruby", "perl", "node", "npm", "yarn",
    "vim", "vi", "nano", "emacs", "sed", "awk",
    "git", "svn", "hg", "cvs",
    "docker", "kubectl", "helm", "terraform", "ansible",
    "curl", "wget", "fetch",
})

# PowerShell cmdlets that are safe to auto-allow in read-only contexts
_SAFE_POWERSHELL_READONLY = frozenset({
    "Get-Content", "Get-ChildItem", "Get-Item", "Get-Location", "Get-LocalGroupMember",
    "Get-Module", "Get-Process", "Get-Service", "Get-Date", "Get-Host", "Get-Variable",
    "Get-Command", "Get-Alias", "Get-Help", "Get-Member", "Get-PSDrive", "Get-PSProvider",
    "Test-Path", "Test-Connection", "Resolve-DnsName", "nslookup", "ping",
    "hostname", "whoami", "systeminfo",
    # Short aliases
    "gc", "gci", "gcm", "gal", "gl", "gm", "gp", "gs", "gt", "gv",
    "dir", "ls", "cd", "pwd",
})


def classify_yolo(
    tool_name: str,
    content: str | None,
    *,
    permission_mode: PermissionMode = "default",
) -> YoloClassification:
    """Classify a tool call using yolo (automatic) rules.

    The yolo classifier automatically allows or denies certain operations
    without prompting the user, based on patterns of known-safe or
    known-unsafe operations.

    This is useful for:
    - Auto-allowing read-only operations
    - Auto-denying clearly dangerous operations
    - Reducing permission prompts for common safe operations

    Args:
        tool_name: Name of the tool being called
        content: Content/target of the tool call (e.g., bash command)
        permission_mode: Current permission mode

    Returns:
        YoloClassification with decision, reason, and optional severity
    """
    # In bypassPermissions mode, everything is allowed
    if permission_mode == "bypassPermissions":
        return YoloClassification(
            decision="allow",
            reason="bypass_mode",
        )

    # Tools that are always safe to auto-allow
    if tool_name in _ALWAYS_SAFE_TOOLS:
        return YoloClassification(
            decision="allow",
            reason=f"tool_always_safe:{tool_name}",
        )

    # Bash-specific checks
    if tool_name == "Bash" and content:
        return _classify_bash_yolo(content, permission_mode)

    # PowerShell-specific checks
    if tool_name == "PowerShell" and content:
        return _classify_powershell_yolo(content, permission_mode)

    # Edit/Write tools - let them prompt in default mode
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        if permission_mode == "acceptEdits":
            return YoloClassification(
                decision="allow",
                reason="accept_edits_mode",
            )
        return YoloClassification(
            decision="ask",
            reason="modifying_tool",
        )

    # Agent/Skill tools - let them prompt
    if tool_name in ("Agent", "Skill"):
        return YoloClassification(
            decision="ask",
            reason="agent_or_skill",
        )

    # Default: ask
    return YoloClassification(
        decision="ask",
        reason="default",
    )


def _classify_bash_yolo(command: str, permission_mode: PermissionMode) -> YoloClassification:
    """Classify a bash command using yolo rules."""
    cmd = command.strip()

    # Empty command - ask
    if not cmd:
        return YoloClassification(decision="ask", reason="empty_command")

    # Check for dangerous patterns
    security = check_bash_security(cmd)

    if not security.is_safe:
        severity = security.severity
        if severity in ("critical", "high"):
            return YoloClassification(
                decision="deny",
                reason=f"bash_dangerous:{security.dangerous_patterns[0] if security.dangerous_patterns else severity}",
                severity=severity,
            )
        # medium/low severity - still ask
        return YoloClassification(
            decision="ask",
            reason=f"bash_suspicious:{security.dangerous_patterns[0] if security.dangerous_patterns else severity}",
            severity=severity,
        )

    # Extract the base command
    base_cmd = _extract_base_command(cmd)

    # Never safe bash commands
    if base_cmd in _NEVER_SAFE_BASH:
        return YoloClassification(
            decision="ask",
            reason=f"bash_command_requires_review:{base_cmd}",
        )

    # Always safe bash commands
    if base_cmd in _SAFE_BASH_READONLY:
        if permission_mode == "acceptEdits":
            return YoloClassification(
                decision="allow",
                reason=f"bash_safe_readonly:{base_cmd}",
            )
        return YoloClassification(
            decision="ask",
            reason="bash_readonly_command",
        )

    # Default: ask for unknown bash commands
    return YoloClassification(
        decision="ask",
        reason=f"bash_unknown_command:{base_cmd}",
    )


def _classify_powershell_yolo(command: str, permission_mode: PermissionMode) -> YoloClassification:
    """Classify a PowerShell command using yolo rules."""
    cmd = command.strip()

    # Empty command - ask
    if not cmd:
        return YoloClassification(decision="ask", reason="empty_command")

    # Extract the base cmdlet
    base_cmdlet = _extract_powershell_base_command(cmd)

    # Check for dangerous patterns
    dangerous_patterns = [
        "Invoke-Expression", "IEX", "Invoke-WebRequest", "Invoke-RestMethod",
        "Start-Process -Verb RunAs", "Start-Process -WindowStyle Hidden",
        "New-PSDrive -PSProvider Registry", "Set-ExecutionPolicy Bypass",
        "bitsadmin", "certutil -urlcache", "[System.Diagnostics.Process]::Start",
        "DownloadFile", "DownloadString",
    ]
    for pattern in dangerous_patterns:
        if pattern.lower() in cmd.lower():
            return YoloClassification(
                decision="deny",
                reason=f"ps_dangerous_pattern:{pattern}",
                severity="high",
            )

    # Safe PowerShell cmdlets
    if base_cmdlet in _SAFE_POWERSHELL_READONLY:
        if permission_mode == "acceptEdits":
            return YoloClassification(
                decision="allow",
                reason=f"ps_safe_readonly:{base_cmdlet}",
            )
        return YoloClassification(
            decision="ask",
            reason="ps_readonly_command",
        )

    # Default: ask
    return YoloClassification(
        decision="ask",
        reason=f"ps_unknown_command:{base_cmdlet}",
    )


def _extract_base_command(command: str) -> str:
    """Extract the base command from a shell command."""
    cmd = command.strip()

    # Handle shebang
    if cmd.startswith("#!"):
        lines = cmd.splitlines()
        if lines:
            shebang = lines[0]
            for shell in ("bash", "sh", "zsh", "fish", "pwsh", "powershell"):
                if shell in shebang:
                    return shell
            return "unknown"

    # Handle semicolon-separated commands (take first)
    if ";" in cmd:
        cmd = cmd.split(";")[0].strip()

    # Handle && and || (take first part)
    for sep in (" && ", " || "):
        if sep in cmd:
            cmd = cmd.split(sep)[0].strip()

    # Handle pipe (take first part)
    if " | " in cmd:
        cmd = cmd.split(" | ")[0].strip()

    # Handle redirects (take first part)
    for sep in (" > ", " >> ", " < ", " 2> "):
        if sep in cmd:
            cmd = cmd.split(sep)[0].strip()

    # Split on whitespace
    tokens = cmd.split()
    if not tokens:
        return "unknown"

    base = tokens[0]

    # Remove path components
    if "/" in base:
        base = base.split("/")[-1]
    if "\\" in base:
        base = base.split("\\")[-1]

    return base.lower()


def _extract_powershell_base_command(command: str) -> str:
    """Extract the base cmdlet from a PowerShell command."""
    cmd = command.strip()

    # Handle semicolon-separated commands (take first)
    if ";" in cmd:
        cmd = cmd.split(";")[0].strip()

    # Handle pipeline (take first part)
    if " | " in cmd:
        cmd = cmd.split(" | ")[0].strip()

    # Common aliases mapping
    alias_map = {
        "rm": "Remove-Item", "del": "Remove-Item", "rmdir": "Remove-Item",
        "cp": "Copy-Item", "copy": "Copy-Item", "cpi": "Copy-Item",
        "mv": "Move-Item", "move": "Move-Item", "mi": "Move-Item",
        "mkdir": "New-Item", "md": "New-Item", "ni": "New-Item",
        "cat": "Get-Content", "gc": "Get-Content", "type": "Get-Content",
        "ls": "Get-ChildItem", "gci": "Get-ChildItem", "dir": "Get-ChildItem",
        "cd": "Set-Location", "sl": "Set-Location", "pwd": "Get-Location",
        "rm": "Remove-Item",
    }

    # Split on whitespace
    tokens = cmd.split()
    if not tokens:
        return "unknown"

    first_word = tokens[0].lower()
    if first_word in alias_map:
        return alias_map[first_word]

    return tokens[0]
