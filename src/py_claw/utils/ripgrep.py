"""
Ripgrep integration utilities.

Provides cross-platform ripgrep execution with support for
system, builtin, and embedded ripgrep modes.

Reference: ClaudeCode-main/src/utils/ripgrep.ts
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

# Maximum buffer size for ripgrep output (20MB)
MAX_BUFFER_SIZE = 20 * 1024 * 1024


@dataclass
class RipgrepConfig:
    """Configuration for ripgrep execution."""
    mode: str  # 'system' | 'builtin' | 'embedded'
    command: str
    args: list[str]
    argv0: str | None = None


@dataclass
class RipgrepResult:
    """Result of ripgrep execution."""
    returncode: int
    stdout: str
    stderr: str
    matches: list[str]


def get_ripgrep_config() -> RipgrepConfig:
    """
    Get the ripgrep configuration based on environment.

    Tries system ripgrep first, then builtin, then embedded.

    Returns:
        RipgrepConfig describing how to invoke ripgrep
    """
    # Check if user wants system ripgrep
    use_builtin = os.environ.get("USE_BUILTIN_RIPGREP", "")

    if not use_builtin:
        # Try to find system ripgrep
        system_path = _find_executable("rg")
        if system_path and system_path != "rg":
            return RipgrepConfig(
                mode="system",
                command="rg",  # Use command name, not path, for security
                args=[],
            )

    # Check if bundled mode (running as compiled binary)
    if getattr(sys, 'frozen', False):
        # Running as compiled executable (PyInstaller, etc.)
        return RipgrepConfig(
            mode="embedded",
            command=sys.executable,
            args=["--no-config"],
            argv0="rg",
        )

    # Try builtin ripgrep
    rg_root = _get_builtin_ripgrep_path()
    if rg_root and os.path.exists(rg_root):
        return RipgrepConfig(
            mode="builtin",
            command=rg_root,
            args=[],
        )

    # Fallback to system rg
    return RipgrepConfig(
        mode="system",
        command="rg",
        args=[],
    )


def _find_executable(name: str) -> str | None:
    """Find an executable in PATH."""
    return shutil.which(name)


def _get_builtin_ripgrep_path() -> str | None:
    """Get path to builtin ripgrep binary."""
    system = platform.system().lower()
    arch = platform.machine().lower()

    # Map platform names
    if system == "windows":
        system = "win32"
        if arch == "amd64":
            arch = "x86_64"

    # Get vendor directory
    import inspect
    try:
        # Try to get the directory of this file
        current_file = inspect.getfile(inspect.currentframe())
        vendor_dir = os.path.join(os.path.dirname(current_file), "vendor", "ripgrep")
    except Exception:
        vendor_dir = None

    if not vendor_dir or not os.path.isdir(vendor_dir):
        return None

    # Build path to ripgrep binary
    if system == "win32":
        rg_name = "rg.exe"
    else:
        rg_name = "rg"

    rg_path = os.path.join(vendor_dir, f"{arch}-{system}", rg_name)

    if os.path.isfile(rg_path) and os.access(rg_path, os.X_OK):
        return rg_path

    return None


def ripgrep_command() -> tuple[str, list[str], str | None]:
    """
    Get the ripgrep command and arguments.

    Returns:
        Tuple of (rg_path, rg_args, argv0)
    """
    config = get_ripgrep_config()
    return config.command, config.args, config.argv0


def ripgrep(
    pattern: str,
    paths: list[str] | None = None,
    *,
    case_sensitive: bool = False,
    word_match: bool = False,
    regex: bool = True,
    line_number: bool = True,
    heading: bool = False,
    color: str = "never",
    max_count: int | None = None,
    before_context: int = 0,
    after_context: int = 0,
    include_pattern: str | None = None,
    exclude_pattern: str | None = None,
    max_buffer: int = MAX_BUFFER_SIZE,
) -> RipgrepResult:
    """
    Execute ripgrep with the given arguments.

    Args:
        pattern: Search pattern
        paths: Files/directories to search
        case_sensitive: Case sensitive search
        word_match: Match whole words only
        regex: Treat pattern as regex
        line_number: Show line numbers
        heading: Group matches by file
        color: Color mode (never/always/auto)
        max_count: Maximum matches per file
        before_context: Lines before match
        after_context: Lines after match
        include_pattern: Include files matching pattern
        exclude_pattern: Exclude files matching pattern
        max_buffer: Maximum output buffer size

    Returns:
        RipgrepResult with matches and output
    """
    config = get_ripgrep_config()
    args = config.args.copy()

    # Add pattern
    args.append(pattern)

    # Add paths
    if paths:
        args.extend(paths)
    else:
        args.append(".")

    # Add options
    if case_sensitive:
        args.append("-s")  # Case sensitive (override -i)
    if word_match:
        args.append("-w")  # Word match
    if not regex:
        args.append("-F")  # Fixed string
    if line_number:
        args.append("-n")  # Line number
    if heading:
        args.append("--heading")  # Group by file
    if color != "never":
        args.append(f"--color={color}")

    if max_count is not None:
        args.extend(["-m", str(max_count)])

    if before_context > 0:
        args.extend(["-B", str(before_context)])

    if after_context > 0:
        args.extend(["-A", str(after_context)])

    if include_pattern:
        args.extend(["-g", include_pattern])

    if exclude_pattern:
        args.extend(["--glob", exclude_pattern])

    # Execute
    try:
        result = subprocess.run(
            [config.command] + args,
            capture_output=True,
            text=True,
            timeout=60,
            max_buffer_size=max_buffer,
        )
        return RipgrepResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=stderr_from_returncode(result.returncode, result.stderr),
            matches=_parse_matches(result.stdout),
        )
    except FileNotFoundError:
        return RipgrepResult(
            returncode=1,
            stdout="",
            stderr=f"Ripgrep not found: {config.command}",
            matches=[],
        )
    except subprocess.TimeoutExpired:
        return RipgrepResult(
            returncode=1,
            stdout="",
            stderr="Ripgrep timed out",
            matches=[],
        )
    except Exception as e:
        return RipgrepResult(
            returncode=1,
            stdout="",
            stderr=str(e),
            matches=[],
        )


def stderr_from_returncode(returncode: int, stderr: str) -> str:
    """Get stderr message based on return code."""
    if returncode == 0:
        return ""  # Success
    if returncode == 1:
        return ""  # No matches
    return stderr


def _parse_matches(output: str) -> list[str]:
    """Parse ripgrep output into list of matches."""
    if not output:
        return []
    return [line for line in output.split("\n") if line.strip()]
