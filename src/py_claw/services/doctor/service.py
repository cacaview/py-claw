"""
Doctor diagnostic service.

Provides system diagnostics for Claude Code installation:
- Installation type detection
- Environment validation
- Settings validation
- MCP status
- Context warnings

Based on ClaudeCode-main/src/utils/doctorDiagnostic.ts and doctorContextWarnings.ts
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from .types import (
    ContextWarning,
    ContextWarnings,
    DiagnosticInfo,
    DoctorCheckResult,
    InstallationType,
    RipgrepStatus,
)


def _get_claude_config_home() -> Path:
    """Get the Claude config home directory."""
    return Path.home() / ".claude"


def _get_cwd() -> str:
    """Get current working directory."""
    return os.getcwd()


def _which(cmd: str) -> str | None:
    """Find executable path."""
    return shutil.which(cmd)


def _is_in_bundled_mode() -> bool:
    """Check if running in bundled mode."""
    return getattr(sys, "frozen", False) or bool(os.environ.get("CLAUDE_CODE_BUNDLED"))


def _get_version() -> str:
    """Get py-claw version."""
    try:
        from py_claw import __version__

        return __version__
    except ImportError:
        return "unknown"


def _get_python_version() -> str:
    """Get Python version string."""
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _get_installation_type() -> InstallationType:
    """Detect the installation type."""
    # Check for development mode
    if os.environ.get("NODE_ENV") == "development":
        return InstallationType.DEVELOPMENT

    if _is_in_bundled_mode():
        # Check for package manager installations
        if _which("brew") is not None:
            return InstallationType.PACKAGE_MANAGER
        if _which("winget") is not None:
            return InstallationType.PACKAGE_MANAGER
        if _which("mise") is not None:
            return InstallationType.PACKAGE_MANAGER
        return InstallationType.NATIVE

    # Check if installed via pip/npm
    try:
        import importlib.metadata

        dist = importlib.metadata.distribution("py-claw")
        location = dist.files[0].locations[0] if dist.files else ""
        if "site-packages" in str(location):
            return InstallationType.NPM_GLOBAL
    except Exception:
        pass

    return InstallationType.UNKNOWN


def _check_python_version() -> DoctorCheckResult:
    """Check Python version."""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 11:
        return DoctorCheckResult(
            name="Python version",
            status="ok",
            message=f"Python {version.major}.{version.minor}.{version.micro} is supported",
        )
    elif version.major >= 3 and version.minor >= 8:
        return DoctorCheckResult(
            name="Python version",
            status="warning",
            message=f"Python {version.major}.{version.minor}.{version.micro} - recommended 3.11+",
        )
    else:
        return DoctorCheckResult(
            name="Python version",
            status="error",
            message=f"Python {version.major}.{version.minor}.{version.micro} - requires 3.8+",
        )


def _check_platform() -> DoctorCheckResult:
    """Check platform compatibility."""
    system = platform.system()
    if system in ("Windows", "Darwin", "Linux"):
        return DoctorCheckResult(
            name="Platform",
            status="ok",
            message=f"Platform: {system} ({platform.release()})",
        )
    else:
        return DoctorCheckResult(
            name="Platform",
            status="warning",
            message=f"Platform: {system} - some features may not work",
        )


def _check_api_key() -> DoctorCheckResult:
    """Check for API key configuration."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        masked = f"{api_key[:8]}..." if len(api_key) > 8 else "***"
        return DoctorCheckResult(
            name="API key",
            status="ok",
            message=f"ANTHROPIC_API_KEY: set ({masked})",
        )
    else:
        return DoctorCheckResult(
            name="API key",
            status="error",
            message="ANTHROPIC_API_KEY: not set",
        )


def _check_git() -> DoctorCheckResult:
    """Check for git installation."""
    git_path = _which("git")
    if git_path:
        try:
            result = shutil.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            version = result.stdout.strip() if result.stdout else "found"
            return DoctorCheckResult(
                name="Git",
                status="ok",
                message=f"Git: {version}",
            )
        except Exception:
            return DoctorCheckResult(
                name="Git",
                status="ok",
                message=f"Git: found at {git_path}",
            )
    else:
        return DoctorCheckResult(
            name="Git",
            status="warning",
            message="Git: NOT FOUND",
        )


def _check_shell() -> DoctorCheckResult:
    """Check for shell availability."""
    shells = []
    for shell in ["bash", "zsh", "sh"]:
        if _which(shell):
            shells.append(shell)

    if shells:
        return DoctorCheckResult(
            name="Shell",
            status="ok",
            message=f"Available shells: {', '.join(shells)}",
        )
    else:
        return DoctorCheckResult(
            name="Shell",
            status="warning",
            message="No common shells found (bash/zsh/sh)",
        )


def _check_config_dir() -> DoctorCheckResult:
    """Check configuration directory."""
    config_home = _get_claude_config_home()
    if config_home.exists():
        return DoctorCheckResult(
            name="Config directory",
            status="ok",
            message=f"Config directory exists: {config_home}",
        )
    else:
        return DoctorCheckResult(
            name="Config directory",
            status="warning",
            message=f"Config directory not found: {config_home}",
        )


def _check_settings() -> DoctorCheckResult:
    """Check settings files."""
    config_home = _get_claude_config_home()
    settings_files = [
        config_home / "settings.json",
        config_home / "settings.local.json",
    ]

    found = []
    for f in settings_files:
        if f.exists():
            found.append(str(f))

    if found:
        return DoctorCheckResult(
            name="Settings files",
            status="ok",
            message=f"Found: {', '.join(found)}",
        )
    else:
        return DoctorCheckResult(
            name="Settings files",
            status="warning",
            message="No settings files found",
        )


def _check_rg_status() -> DoctorCheckResult:
    """Check ripgrep status."""
    rg_path = _which("rg")
    if rg_path:
        try:
            result = shutil.run(
                ["rg", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return DoctorCheckResult(
                    name="Ripgrep",
                    status="ok",
                    message=f"Ripgrep: {result.stdout.split()[1] if result.stdout else 'found'}",
                )
        except Exception:
            pass
        return DoctorCheckResult(
            name="Ripgrep",
            status="ok",
            message=f"Ripgrep: found at {rg_path}",
        )
    else:
        return DoctorCheckResult(
            name="Ripgrep",
            status="warning",
            message="Ripgrep: not found (will use slower fallback)",
        )


def _check_package_managers() -> list[DoctorCheckResult]:
    """Check for package managers."""
    results = []
    managers = [
        ("brew", "Homebrew"),
        ("pip", "pip"),
        ("npm", "npm"),
        ("yarn", "yarn"),
    ]

    for cmd, name in managers:
        path = _which(cmd)
        if path:
            results.append(
                DoctorCheckResult(
                    name=f"{name} package manager",
                    status="ok",
                    message=f"{name}: found at {path}",
                )
            )
        else:
            results.append(
                DoctorCheckResult(
                    name=f"{name} package manager",
                    status="warning",
                    message=f"{name}: not found",
                )
            )

    return results


def run_diagnostics() -> list[DoctorCheckResult]:
    """Run all doctor diagnostics.

    Returns a list of check results covering:
    - Python version
    - Platform
    - API key
    - Git
    - Shell
    - Config directory
    - Settings files
    - Ripgrep
    - Package managers
    """
    results = []

    results.append(_check_python_version())
    results.append(_check_platform())
    results.append(_check_api_key())
    results.append(_check_git())
    results.append(_check_shell())
    results.append(_check_config_dir())
    results.append(_check_settings())
    results.append(_check_rg_status())
    results.extend(_check_package_managers())

    return results


def get_diagnostic_summary() -> str:
    """Get a summary string of all diagnostics."""
    results = run_diagnostics()

    lines = ["=== py-claw Doctor ===", ""]

    ok_count = sum(1 for r in results if r.is_ok())
    warn_count = sum(1 for r in results if r.is_warning())
    error_count = sum(1 for r in results if r.is_error())

    lines.append(f"Status: {ok_count} OK, {warn_count} warnings, {error_count} errors")
    lines.append("")

    for result in results:
        status_icon = {
            "ok": "[+]",
            "warning": "[!]",
            "error": "[X]",
            "pending": "[-]",
        }.get(result.status, "[-]")

        lines.append(f"{status_icon} {result.name}: {result.message}")

        for detail in result.details:
            lines.append(f"    {detail}")

    return "\n".join(lines)


def get_installation_info() -> DiagnosticInfo:
    """Get detailed installation information."""
    install_type = _get_installation_type()
    version = _get_version()

    # Get installation path
    install_path = Path(sys.executable).parent if sys.executable else ""

    # Get invoked binary
    invoked = sys.argv[0] if sys.argv else ""

    return DiagnosticInfo(
        installation_type=install_type,
        version=version,
        installation_path=str(install_path),
        invoked_binary=invoked,
        config_install_method="not set",
        auto_updates="unknown",
        has_update_permissions=None,
    )


def check_context_warnings(
    tools: list[Any] | None = None,
    agent_info: Any = None,
) -> ContextWarnings:
    """Check context-related warnings.

    This is a simplified version that checks:
    - Large CLAUDE.md files
    - MCP server status

    Args:
        tools: List of MCP tools (simplified - not used in basic check)
        agent_info: Agent definitions info (simplified - not used in basic check)

    Returns:
        ContextWarnings object with any detected warnings
    """
    warnings = ContextWarnings()

    # Check for large CLAUDE.md files
    claude_md_warning = _check_claude_md_files()
    if claude_md_warning:
        warnings.claude_md_warning = claude_md_warning

    return warnings


def _check_claude_md_files() -> ContextWarning | None:
    """Check for large CLAUDE.md files in the current directory tree."""
    MAX_MEMORY_CHARACTER_COUNT = 40_000

    config_home = _get_claude_config_home()
    current_dir = Path(_get_cwd())

    large_files: list[tuple[str, int]] = []

    # Check common locations for CLAUDE.md files
    search_paths = [
        current_dir,
        current_dir.parent,
        config_home,
    ]

    for search_dir in search_paths:
        if not search_dir.exists():
            continue

        for claude_md in search_dir.rglob("CLAUDE.md"):
            try:
                content = claude_md.read_text(encoding="utf-8")
                if len(content) > MAX_MEMORY_CHARACTER_COUNT:
                    large_files.append((str(claude_md), len(content)))
            except (OSError, UnicodeDecodeError):
                continue

    if not large_files:
        return None

    # Sort by size descending
    large_files.sort(key=lambda x: x[1], reverse=True)

    details = [
        f"{path}: {size:,} chars" for path, size in large_files[:5]
    ]

    if len(large_files) > 5:
        details.append(f"({len(large_files) - 5} more files)")

    message = (
        f"Large CLAUDE.md file detected ({large_files[0][1]:,} chars > {MAX_MEMORY_CHARACTER_COUNT:,})"
        if len(large_files) == 1
        else f"{len(large_files)} large CLAUDE.md files detected (each > {MAX_MEMORY_CHARACTER_COUNT:,} chars)"
    )

    return ContextWarning(
        type="claudemd_files",
        severity="warning",
        message=message,
        details=details,
        current_value=len(large_files),
        threshold=MAX_MEMORY_CHARACTER_COUNT,
    )


def check_mcp_servers(mcp_statuses: list[Any]) -> ContextWarning | None:
    """Check MCP server configuration warnings.

    Args:
        mcp_statuses: List of MCP server status objects

    Returns:
        ContextWarning if issues found, None otherwise
    """
    if not mcp_statuses:
        return None

    # Check for servers with errors
    error_servers = [
        s for s in mcp_statuses if getattr(s, "status", "") == "error"
    ]

    if error_servers:
        details = [f"{s.name}: {getattr(s, 'error', 'unknown error')}" for s in error_servers[:5]]
        return ContextWarning(
            type="mcp_tools",
            severity="error",
            message=f"{len(error_servers)} MCP server(s) with errors",
            details=details,
            current_value=len(error_servers),
            threshold=0,
        )

    return None
