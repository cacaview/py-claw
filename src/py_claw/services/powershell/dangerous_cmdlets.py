"""Dangerous PowerShell cmdlets and security-related cmdlet lists."""

from __future__ import annotations

# Cmdlets that are never suggested in auto-complete
NEVER_SUGGEST_CMDLETS: frozenset[str] = frozenset([
    "Invoke-Expression",
    "Invoke-Command",
    "New-PSSession",
    "Enter-PSSession",
    "Remove-PSSession",
    "Start-Process",
    "Start-Job",
    "Invoke-WebRequest",
    "Invoke-RestMethod",
    "DownloadFile",
    "DownloadString",
    "UploadFile",
    "UploadString",
])

# Dangerous cmdlets that require special handling
DANGEROUS_CMDLETS: frozenset[str] = frozenset([
    # Code execution
    "Invoke-Expression",
    "Invoke-Command",
    "iex",
    "icm",
    # Remote sessions
    "New-PSSession",
    "Enter-PSSession",
    "Remove-PSSession",
    "nsn",
    "etsn",
    "rsn",
    # Process/Service control
    "Start-Process",
    "Start-Job",
    "Stop-Process",
    "Stop-Service",
    "Start-Service",
    # Network
    "Invoke-WebRequest",
    "Invoke-RestMethod",
    "iwr",
    "irm",
    # File operations
    "Remove-Item",
    "Remove-ItemProperty",
    "rm",
    "ri",
    "del",
    # Registry
    "Set-ItemProperty",
    "Remove-ItemProperty",
    "New-Item",
    # Download/Upload
    "DownloadFile",
    "DownloadString",
    "UploadFile",
])

# Safe output cmdlets that are commonly used
SAFE_OUTPUT_CMDLETS: frozenset[str] = frozenset([
    "Write-Output",
    "Write-Host",
    "Write-Verbose",
    "Write-Warning",
    "Write-Error",
    "Write-Debug",
    "Write-Information",
    "Out-Host",
    "Out-Null",
    "Out-String",
    "Out-File",
    "Tee-Object",
    "Format-Table",
    "Format-List",
    "Format-Wide",
    "Select-Object",
    "Where-Object",
    "ForEach-Object",
    "Sort-Object",
    "Measure-Object",
    "Compare-Object",
])

# Cmdlets that accept edits (safe for file modifications)
ACCEPT_EDITS_ALLOWED_CMDLETS: frozenset[str] = frozenset([
    "Add-Content",
    "Clear-Content",
    "Set-Content",
    "Out-File",
    "Tee-Object",
])


def is_dangerous_cmdlet(cmdlet_name: str) -> bool:
    """
    Check if a cmdlet is considered dangerous.

    Args:
        cmdlet_name: Name of the cmdlet (with or without module prefix)

    Returns:
        True if the cmdlet is dangerous
    """
    # Strip module prefix if present
    if "\\" in cmdlet_name:
        cmdlet_name = cmdlet_name.split("\\")[-1]

    # Check direct name
    if cmdlet_name in DANGEROUS_CMDLETS:
        return True

    # Check common aliases
    return cmdlet_name.lower() in DANGEROUS_CMDLETS


def is_never_suggest_cmdlet(cmdlet_name: str) -> bool:
    """
    Check if a cmdlet should never be suggested in auto-complete.

    Args:
        cmdlet_name: Name of the cmdlet

    Returns:
        True if the cmdlet should never be suggested
    """
    if "\\" in cmdlet_name:
        cmdlet_name = cmdlet_name.split("\\")[-1]

    return cmdlet_name in NEVER_SUGGEST_CMDLETS


def is_safe_output_cmdlet(cmdlet_name: str) -> bool:
    """
    Check if a cmdlet is a safe output cmdlet.

    Args:
        cmdlet_name: Name of the cmdlet

    Returns:
        True if the cmdlet is safe for output operations
    """
    if "\\" in cmdlet_name:
        cmdlet_name = cmdlet_name.split("\\")[-1]

    return cmdlet_name in SAFE_OUTPUT_CMDLETS


def is_accept_edits_allowed_cmdlet(cmdlet_name: str) -> bool:
    """
    Check if a cmdlet is allowed to accept edits.

    Args:
        cmdlet_name: Name of the cmdlet

    Returns:
        True if the cmdlet can accept edits
    """
    if "\\" in cmdlet_name:
        cmdlet_name = cmdlet_name.split("\\")[-1]

    return cmdlet_name in ACCEPT_EDITS_ALLOWED_CMDLETS
