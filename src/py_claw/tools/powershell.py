from __future__ import annotations

import shutil
import subprocess
import sys
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from py_claw.tasks import TaskRuntime
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

PowerShellSeverity = Literal["critical", "high", "medium", "low", "safe"]

# PowerShell-specific security patterns
_POWER_SHELL_SECURITY_PATTERNS: list[tuple[re.Pattern[str], str, PowerShellSeverity]] = [
    # critical
    (re.compile(r"Remove-Item\s+-Recurse\s+-Force\s+/\s*"), "ps_remove_root_recursive", "critical"),
    (re.compile(r"Format-Volume\s+-DriveLetter"), "ps_format_volume", "critical"),
    (re.compile(r"Clear-Disk\s+-Number"), "ps_clear_disk", "critical"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}"), "fork_bomb", "critical"),
    # high
    (re.compile(r"Invoke-Expression\s+.*\$"), "ps_iex_variable", "high"),
    (re.compile(r"IEX\s+"), "ps_alias_iex", "high"),
    (re.compile(r"Invoke-WebRequest?\s+.*\|\s*Invoke-Expression"), "ps_web_iex", "high"),
    (re.compile(r"Invoke-RestMethod?\s+.*\|\s*Invoke-Expression"), "ps_rest_iex", "high"),
    (re.compile(r"Start-Process\s+.*-Verb\s+RunAs"), "ps_runas_elevate", "high"),
    (re.compile(r"Start-Process\s+.*-WindowStyle\s+Hidden"), "ps_hidden_window", "high"),
    (re.compile(r"New-PSDrive\s+.*-PSProvider\s+Registry"), "ps_psdrive_registry", "high"),
    (re.compile(r"Set-ExecutionPolicy\s+Bypass"), "ps_bypass_execution_policy", "high"),
    (re.compile(r"bitsadmin\s+/transfer"), "ps_bitsadmin_download", "high"),
    (re.compile(r"certutil\s+.*-urlcache"), "ps_certutil_urlcache", "high"),
    (re.compile(r"\[System.Diagnostics.Process\]::Start"), "ps_dotnet_process_start", "high"),
    (re.compile(r"DownloadFile\("), "ps_download_file", "high"),
    (re.compile(r"DownloadString\("), "ps_download_string", "high"),
    # medium
    (re.compile(r"New-Service\s+.*-StartupType\s+Automatic"), "ps_auto_service", "medium"),
    (re.compile(r"schtasks\s+/Create"), "ps_scheduled_task_create", "medium"),
    (re.compile(r"Register-ScheduledTask"), "ps_scheduled_task_ps", "medium"),
    (re.compile(r"New-Item\s+.*-ItemType\s+SymbolicLink"), "ps_symlink_create", "medium"),
    (re.compile(r"cmd\s+/c\s+"), "ps_cmd_execution", "medium"),
    # low
    (re.compile(r"Set-ExecutionPolicy\s+Unrestricted"), "ps_unrestricted_policy", "low"),
]

_SEVERITY_ORDER: dict[PowerShellSeverity, int] = {
    "safe": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


@dataclass(frozen=True, slots=True)
class PowerShellSecurityCheckResult:
    is_safe: bool
    detected_shell: Literal["pwsh", "powershell", "unknown"]
    dangerous_patterns: list[str]
    warnings: list[str]
    severity: Literal["safe", "low", "medium", "high", "critical"]


def check_powershell_security(command: str) -> PowerShellSecurityCheckResult:
    """Analyze a PowerShell command for security risks.

    This is a pattern-based heuristic analyzer for PowerShell-specific risks.
    """
    cmd = command.strip()
    dangerous: list[str] = []
    max_severity: PowerShellSeverity = "safe"

    if not cmd:
        return PowerShellSecurityCheckResult(
            is_safe=True,
            detected_shell="unknown",
            dangerous_patterns=[],
            warnings=[],
            severity="safe",
        )

    for pattern, label, severity in _POWER_SHELL_SECURITY_PATTERNS:
        if pattern.search(cmd):
            dangerous.append(label)
            if _SEVERITY_ORDER.get(severity, 0) > _SEVERITY_ORDER.get(max_severity, 0):
                max_severity = severity

    warnings: list[str] = []
    detected_shell: Literal["pwsh", "powershell", "unknown"] = "unknown"

    # Detect pwsh (PowerShell 7+) vs Windows PowerShell (5.1)
    if re.search(r"\$PSVersionTable\.PSVersion\.Major", cmd):
        warnings.append("pwsh_version_check")
    if re.search(r"pwsh", cmd, re.IGNORECASE):
        detected_shell = "pwsh"
    elif re.search(r"powershell", cmd, re.IGNORECASE):
        detected_shell = "powershell"

    severity: Literal["safe", "low", "medium", "high", "critical"] = max_severity
    if severity == "safe" and warnings:
        severity = "low"

    return PowerShellSecurityCheckResult(
        is_safe=severity == "safe",
        detected_shell=detected_shell,
        dangerous_patterns=dangerous,
        warnings=warnings,
        severity=severity,
    )


class PowerShellToolInput(BaseModel):
    command: str
    timeout: int | None = Field(default=None, ge=1, le=600000)
    description: str | None = None
    run_in_background: bool = False
    dangerouslyDisableSandbox: bool = False


def _describe_security_result(result: PowerShellSecurityCheckResult) -> dict:
    return {
        "severity": result.severity,
        "shellType": result.detected_shell,
        "dangerousPatterns": result.dangerous_patterns,
        "warnings": result.warnings,
    }


def _get_powershell_executable() -> str:
    """Find PowerShell executable (prefers pwsh/7+ over Windows PowerShell)."""
    # Try pwsh first (PowerShell 7+)
    pwsh_path = shutil.which("pwsh")
    if pwsh_path is not None:
        return pwsh_path
    # Fall back to Windows PowerShell
    powershell_path = shutil.which("powershell")
    if powershell_path is not None:
        return powershell_path
    # Last resort
    if sys.platform == "win32":
        return "powershell.exe"
    return "pwsh"


class PowerShellTool:
    definition = ToolDefinition(name="PowerShell", input_model=PowerShellToolInput)

    def __init__(self, task_runtime: TaskRuntime | None = None) -> None:
        self._task_runtime = task_runtime

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        raw_value = payload.get("command")
        content = str(raw_value) if isinstance(raw_value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: PowerShellToolInput, *, cwd: str) -> dict[str, object]:
        output: dict[str, object] = {
            "command": arguments.command,
        }

        if not arguments.dangerouslyDisableSandbox:
            security = check_powershell_security(arguments.command)
            output["security"] = _describe_security_result(security)
            if security.severity == "critical":
                raise ToolError(
                    f"PowerShell command blocked due to critical security risk: {security.dangerous_patterns[0] if security.dangerous_patterns else security.severity}. "
                    "To bypass, set dangerouslyDisableSandbox: true."
                )

        if arguments.run_in_background:
            if self._task_runtime is None:
                raise ToolError("Background PowerShell execution requires task runtime")
            return self._execute_in_background(
                arguments,
                cwd=cwd,
                security_result=output.get("security"),
            )

        ps_path = _get_powershell_executable()
        timeout_ms = arguments.timeout or 120000

        # Use -Command for cross-platform PowerShell
        try:
            completed = subprocess.run(
                [ps_path, "-NoProfile", "-NonInteractive", "-Command", arguments.command],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(f"PowerShell command timed out after {timeout_ms}ms") from exc

        output.update({
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "exitCode": completed.returncode,
        })
        return output

    def _execute_in_background(
        self,
        arguments: PowerShellToolInput,
        *,
        cwd: str,
        security_result: dict | None = None,
    ) -> dict[str, object]:
        ps_path = _get_powershell_executable()
        timeout_ms = arguments.timeout or 120000

        from py_claw.tasks import TaskRecord
        task_record = self._task_runtime.create_task_record(
            label=f"PowerShell: {arguments.command[:50]}",
            is_shell=True,
        )

        def run_ps_task() -> None:
            try:
                completed = subprocess.run(
                    [ps_path, "-NoProfile", "-NonInteractive", "-Command", arguments.command],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_ms / 1000,
                    check=False,
                )
                self._task_runtime.update_task_output(
                    task_record.task_id,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    exit_code=completed.returncode,
                )
            except subprocess.TimeoutExpired:
                self._task_runtime.update_task_output(
                    task_record.task_id,
                    stdout="",
                    stderr=f"Command timed out after {timeout_ms}ms",
                    exit_code=124,
                )
            except Exception as exc:
                self._task_runtime.update_task_output(
                    task_record.task_id,
                    stdout="",
                    stderr=str(exc),
                    exit_code=1,
                )

        thread = threading.Thread(target=run_ps_task, daemon=True)
        thread.start()

        result: dict[str, object] = {
            "taskId": task_record.task_id,
            "security": security_result,
        }
        return result


# Read-only cmdlets that are considered safe
_READ_ONLY_CMDLETS = frozenset({
    "Get-Content", "Get-ChildItem", "Get-Item", "Get-Location", "Get-LocalGroupMember",
    "Get-Module", "Get-Process", "Get-Service", "Get-Date", "Get-Host", "Get-Variable",
    "Get-Command", "Get-Alias", "Get-Help", "Get-Member", "Get-PSDrive", "Get-PSProvider",
    "Get-PSReadLineOption", "Get-CimInstance", "Get-WmiObject", "Test-Path", "Test-Connection",
    "Resolve-DnsName", "nslookup", "ping", "hostname", "whoami", "systeminfo",
    # Short aliases
    "gc", "gci", "gcm", "gal", "gl", "gm", "gp", "gs", "gt", "gv",
    "dir", "ls", "cat", "type", "cd", "pwd", "select", "where", "?" ,
})

# Cmdlets that modify state (write/delete)
_WRITE_CMDLETS = frozenset({
    "Remove-Item", "Remove-ItemProperty", "Remove-PSDrive", "Remove-Module",
    "New-Item", "New-ItemProperty", "New-PSDrive", "New-Service",
    "Set-Content", "Set-Item", "Set-ItemProperty", "Set-Location",
    "Add-Content", "Clear-Content", "Clear-Item", "Clear-ItemProperty",
    "Copy-Item", "Copy-ItemProperty", "Move-Item", "Move-ItemProperty",
    "Rename-Item", "Rename-ItemProperty", "Invoke-Item",
    "Stop-Process", "Stop-Service", "Start-Service", "Restart-Service",
    "Set-Service", "Set-ExecutionPolicy", "Set-Alias", "Set-Variable",
    "Export-ModuleMember", "Import-Module", "Install-Module", "Update-Module",
    "Format-Volume", "Clear-Disk", "New-NetFirewallRule", "Disable-NetFirewallRule",
})


def check_powershell_path_security(command: str, cwd: str) -> tuple[bool, str | None]:
    """Check if a PowerShell command accesses paths outside the allowed scope.

    Returns (is_safe, reason). Read-only commands are permitted to access any path.
    Write/delete commands that target protected system paths are flagged.
    """
    import os
    from pathlib import Path

    resolved_cwd = Path(cwd).resolve()
    home = Path.home().resolve()

    cmd = _extract_powershell_command(command)
    if cmd in _READ_ONLY_CMDLETS:
        return True, None

    # Check for dangerous path access
    tokens = _extract_powershell_path_tokens(command)
    dangerous_paths = (
        "HKLM:\\", "HKCU:\\", "HKU:\\",  # Registry hives
        "/dev/sd", "/sys/", "/proc/", "/boot/",  # Unix-style
        "System32\\Config\\SAM", "System32\\Config\\SYSTEM",  # Windows registry
    )

    for token in tokens:
        if not token:
            continue
        expanded = os.path.expanduser(token)
        try:
            abs_path = Path(expanded).resolve()
        except (OSError, ValueError):
            continue

        abs_str = str(abs_path).replace("\\", "/")
        for dangerous in dangerous_paths:
            normalized = dangerous.replace("\\", "/")
            if abs_str.startswith(normalized):
                if cmd in _WRITE_CMDLETS:
                    return False, f"write to protected path: {token}"
                return False, f"access to protected path: {token}"

    # Check containment
    try:
        abs_path.relative_to(resolved_cwd)
    except ValueError:
        try:
            abs_path.relative_to(home)
        except ValueError:
            return False, f"path outside cwd/home: {abs_str}"

    return True, None


def _extract_powershell_command(command: str) -> str:
    """Extract the base cmdlet from a PowerShell command string."""
    stripped = command.strip()

    # Handle semicolon separated commands (take first)
    if ";" in stripped:
        stripped = stripped.split(";")[0].strip()

    # Handle pipeline (take first element)
    if " | " in stripped:
        stripped = stripped.split(" | ")[0].strip()

    # Handle common operators
    for sep in (" && ", " || ", " > ", " >> ", " < ", " 2>", " &"):
        if sep in stripped:
            stripped = stripped.split(sep)[0].strip()

    tokens = stripped.split()
    if not tokens:
        return ""

    # Handle common aliases
    first_word = tokens[0].lower()
    alias_map = {
        "rm": "Remove-Item", "del": "Remove-Item", "rmdir": "Remove-Item",
        "cp": "Copy-Item", "copy": "Copy-Item", "cpi": "Copy-Item",
        "mv": "Move-Item", "move": "Move-Item", "mi": "Move-Item",
        "mkdir": "New-Item", "md": "New-Item", "ni": "New-Item",
        "cat": "Get-Content", "gc": "Get-Content", "type": "Get-Content",
        "ls": "Get-ChildItem", "gci": "Get-ChildItem", "dir": "Get-ChildItem",
        "cd": "Set-Location", "sl": "Set-Location", "pwd": "Get-Location",
        "rmdir": "Remove-Item",
    }
    if first_word in alias_map:
        return alias_map[first_word]

    # Return first token, stripping common prefixes
    result = tokens[0]
    if result.startswith("-"):
        result = tokens[1] if len(tokens) > 1 else ""
    return result


_PATH_TOKEN_RE = re.compile(
    r"""
    (?P<quote>['"])(?P<quoted>(?:[^\\'"]|\\.)*)((?<!\\)\1)|
    (?:\s|^)(~[a-zA-Z_][a-zA-Z0-9_]*/?(?:[a-zA-Z0-9_./-]*)?)
    """,
    re.VERBOSE,
)


def _extract_powershell_path_tokens(command: str) -> list[str]:
    """Extract path-like tokens from a PowerShell command."""
    tokens: list[str] = []
    for m in _PATH_TOKEN_RE.finditer(command):
        if m.group("quote"):
            quoted = m.group("quoted")
            if quoted and ("/" in quoted or "\\" in quoted or "~" in quoted):
                tokens.append(quoted)
        elif m.group(4):
            tokens.append(m.group(4))

    # Find Windows absolute paths: X:\... or X:/...
    for token in command.split():
        if len(token) >= 3 and token[1] == ":" and token[0].isalpha():
            tokens.append(token)

    # Find PSDrive paths: HKLM:\, C:\, etc.
    psdrive_paths = re.findall(r'[a-zA-Z]+:[/\\][^\s]*', command)
    tokens.extend(psdrive_paths)

    # Find Unix-style absolute paths
    bare_paths = re.findall(r'(?<![a-zA-Z0-9_.-])(/[a-zA-Z0-9_./+-]+)', command)
    tokens.extend(bare_paths)

    return tokens
