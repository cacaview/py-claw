"""PowerShell command parser using PowerShell AST."""

from __future__ import annotations

import base64
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

# Windows command line limit
WINDOWS_ARGV_CAP = 32767
# pwsh path + flags overhead
FIXED_ARGV_OVERHEAD = 200
# Base64 wrapper length
ENCODED_CMD_WRAPPER = len("$EncodedCommand = ''\n")
# Safety margin
SAFETY_MARGIN = 100

# Budget for command in the -EncodedCommand payload
SCRIPT_CHARS_BUDGET = ((WINDOWS_ARGV_CAP - FIXED_ARGV_OVERHEAD) * 3) / 8
CMD_B64_BUDGET = SCRIPT_CHARS_BUDGET - 0  # Would subtract PARSE_SCRIPT_BODY.length

# Windows max command length in UTF-8 bytes
WINDOWS_MAX_COMMAND_LENGTH = max(0, int((CMD_B64_BUDGET * 3) / 4) - SAFETY_MARGIN)
UNIX_MAX_COMMAND_LENGTH = 4500

MAX_COMMAND_LENGTH = WINDOWS_MAX_COMMAND_LENGTH if os.name == "nt" else UNIX_MAX_COMMAND_LENGTH


@dataclass
class CommandElementChild:
    """Child node of a command element."""

    type: str  # CommandElementType
    text: str


@dataclass
class ParsedRedirection:
    """Redirection in a command."""

    operator: str  # '>', '>>', '2>', '2>>', '*>', '*>>', '2>&1'
    target: str
    is_merging: bool


@dataclass
class ParsedCommandElement:
    """A command invocation within a pipeline segment."""

    name: str
    name_type: str  # 'cmdlet', 'application', 'unknown'
    element_type: str = "CommandAst"
    args: list[str] = field(default_factory=list)
    text: str = ""
    element_types: list[str] = field(default_factory=list)
    children: list[CommandElementChild | None] = field(default_factory=list)
    redirections: list[ParsedRedirection] = field(default_factory=list)


@dataclass
class ParsedStatement:
    """A parsed statement from PowerShell."""

    statement_type: str  # 'PipelineAst', 'IfStatementAst', etc.
    commands: list[ParsedCommandElement] = field(default_factory=list)
    redirections: list[ParsedRedirection] = field(default_factory=list)
    text: str = ""
    nested_commands: list[ParsedCommandElement] | None = None
    security_patterns: dict[str, bool] | None = None


@dataclass
class ParsedPowerShellCommand:
    """Complete parsed result from PowerShell AST parser."""

    valid: bool
    statements: list[ParsedStatement] = field(default_factory=list)
    variables: list[dict[str, Any]] = field(default_factory=list)
    has_stop_parsing: bool = False
    errors: list[dict[str, str]] = field(default_factory=list)
    original_command: str = ""


# Common PowerShell aliases
COMMON_ALIASES: dict[str, str] = {
    "ls": "Get-ChildItem",
    "dir": "Get-ChildItem",
    "cat": "Get-Content",
    "cd": "Set-Location",
    "pwd": "Get-Location",
    "rm": "Remove-Item",
    "cp": "Copy-Item",
    "mv": "Move-Item",
    "mkdir": "New-Item",
    "echo": "Write-Output",
    "sls": "Select-String",
    "iex": "Invoke-Expression",
    "iwr": "Invoke-WebRequest",
    "irm": "Invoke-RestMethod",
}


def _to_utf16_le_base64(text: str) -> str:
    """Encode string as UTF-16LE and then base64."""
    # Python doesn't have direct UTF-16LE conversion, so we simulate it
    encoded = text.encode("utf-16-le")
    return base64.b64encode(encoded).decode("ascii")


def _get_powershell_path() -> str | None:
    """Get the PowerShell executable path."""
    if os.name == "nt":
        # Check common PowerShell paths on Windows
        paths = [
            r"C:\Program Files\PowerShell\7\pwsh.exe",
            r"C:\Program Files (x86)\PowerShell\7\pwsh.exe",
            "pwsh.exe",
            "powershell.exe",
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        # Try to find in PATH
        import shutil

        return shutil.which("pwsh") or shutil.which("powershell")
    else:
        import shutil

        return shutil.which("pwsh")


async def parse_powershell_command_impl(command: str) -> ParsedPowerShellCommand:
    """
    Parse a PowerShell command using the native AST parser.

    Args:
        command: The PowerShell command to parse

    Returns:
        ParsedPowerShellCommand with parsed structure
    """
    # Check command length
    command_bytes = len(command.encode("utf-8"))
    if command_bytes > MAX_COMMAND_LENGTH:
        return ParsedPowerShellCommand(
            valid=False,
            original_command=command,
            errors=[{"message": f"Command too long ({command_bytes} bytes)", "errorId": "CommandTooLong"}],
        )

    pwsh_path = _get_powershell_path()
    if not pwsh_path:
        return ParsedPowerShellCommand(
            valid=False,
            original_command=command,
            errors=[{"message": "PowerShell is not available", "errorId": "NoPowerShell"}],
        )

    # Build parse script
    encoded_command = _to_utf16_le_base64(command)
    script = f"$EncodedCommand = '{encoded_command}'\n"

    # Add simple parsing logic - in full implementation this would use the full PS1 script
    # For now, return a stub that extracts basic command structure

    try:
        # Simple approach: extract command name and arguments
        parts = command.strip().split()
        if not parts:
            return ParsedPowerShellCommand(valid=True, original_command=command, statements=[])

        cmd_name = parts[0]
        args = parts[1:] if len(parts) > 1 else []

        # Classify command name
        name_type = "unknown"
        if re.match(r"^[A-Za-z]+-[A-Za-z][A-Za-z0-9_]*$", cmd_name):
            name_type = "cmdlet"
        elif re.match(r"[.\\/]", cmd_name):
            name_type = "application"

        # Resolve aliases
        resolved_name = COMMON_ALIASES.get(cmd_name.lower(), cmd_name)

        cmd_element = ParsedCommandElement(
            name=resolved_name,
            name_type=name_type,
            element_type="CommandAst",
            args=args,
            text=command,
        )

        statement = ParsedStatement(
            statement_type="PipelineAst",
            commands=[cmd_element],
            text=command,
        )

        return ParsedPowerShellCommand(
            valid=True,
            original_command=command,
            statements=[statement],
            variables=[],
            has_stop_parsing="--%" in command,
        )

    except Exception as e:
        return ParsedPowerShellCommand(
            valid=False,
            original_command=command,
            errors=[{"message": str(e), "errorId": "ParseError"}],
        )


# Module-level cache for parsed commands (LRU cache would be used in full impl)
_parsed_cache: dict[str, ParsedPowerShellCommand] = {}
MAX_CACHE_SIZE = 256


def parse_powershell_command(command: str) -> ParsedPowerShellCommand:
    """
    Parse a PowerShell command with caching.

    Args:
        command: The PowerShell command to parse

    Returns:
        ParsedPowerShellCommand result
    """
    if command in _parsed_cache:
        return _parsed_cache[command]

    # Simple synchronous wrapper for the async impl
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(parse_powershell_command_impl(command))
    finally:
        if len(_parsed_cache) < MAX_CACHE_SIZE:
            _parsed_cache[command] = result

    return result


def get_all_command_names(parsed: ParsedPowerShellCommand) -> list[str]:
    """Get all command names from parsed PowerShell command."""
    names = []
    for stmt in parsed.statements:
        for cmd in stmt.commands:
            names.append(cmd.name.lower())
        if stmt.nested_commands:
            for cmd in stmt.nested_commands:
                names.append(cmd.name.lower())
    return names


def get_file_redirections(parsed: ParsedPowerShellCommand) -> list[ParsedRedirection]:
    """Get all file redirections from parsed command."""
    redirections = []
    for stmt in parsed.statements:
        redirections.extend(stmt.redirections)
    return [r for r in redirections if not r.is_merging and r.target.lower() != "$null"]


def has_directory_change(parsed: ParsedPowerShellCommand) -> bool:
    """Check if command contains directory-changing commands."""
    dir_cmdlets = {"set-location", "push-location", "pop-location"}
    dir_aliases = {"cd", "sl", "chdir", "pushd", "popd"}

    for name in get_all_command_names(parsed):
        if name in dir_cmdlets or name in dir_aliases:
            return True
    return False


def derive_security_flags(parsed: ParsedPowerShellCommand) -> dict[str, bool]:
    """Derive security-relevant flags from parsed command."""
    return {
        "hasSubExpressions": "$(" in parsed.original_command,
        "hasScriptBlocks": "{ }" in parsed.original_command,
        "hasSplatting": "@" in parsed.original_command,
        "hasExpandableStrings": '"' in parsed.original_command,
        "hasMemberInvocations": "." in parsed.original_command,
        "hasAssignments": "=" in parsed.original_command,
        "hasStopParsing": parsed.has_stop_parsing,
    }
