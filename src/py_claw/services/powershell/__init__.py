"""PowerShell utilities - parser, dangerous cmdlets, and static prefix analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .parser import (
    parse_powershell_command,
    parse_powershell_command_impl,
    ParsedPowerShellCommand,
    ParsedCommandElement,
    ParsedStatement,
    ParsedRedirection,
    MAX_COMMAND_LENGTH,
    COMMON_ALIASES,
    get_all_command_names,
    get_file_redirections,
    has_directory_change,
    derive_security_flags,
)
from .dangerous_cmdlets import (
    DANGEROUS_CMDLETS,
    NEVER_SUGGEST_CMDLETS,
    is_dangerous_cmdlet,
    is_never_suggest_cmdlet,
)

__all__ = [
    "parse_powershell_command",
    "parse_powershell_command_impl",
    "ParsedPowerShellCommand",
    "ParsedCommandElement",
    "ParsedStatement",
    "ParsedRedirection",
    "MAX_COMMAND_LENGTH",
    "COMMON_ALIASES",
    "get_all_command_names",
    "get_file_redirections",
    "has_directory_change",
    "derive_security_flags",
    "DANGEROUS_CMDLETS",
    "NEVER_SUGGEST_CMDLETS",
    "is_dangerous_cmdlet",
    "is_never_suggest_cmdlet",
]
