"""
Non-throwing exec wrapper.

Provides exec_file_no_throw() which always resolves
and never throws, returning stdout/stderr/exit code.

Mirrors TS execFileNoThrow.ts behavior.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class ExecResult:
    """Result of exec_file_no_throw."""
    stdout: str
    stderr: str
    code: int
    error: str | None = None


def exec_file_no_throw(
    file: str,
    args: list[str],
    *,
    timeout: int = 10 * 60 * 1000,  # 10 minutes default
    preserve_output_on_error: bool = True,
    use_cwd: bool = True,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
    input: str | None = None,
) -> ExecResult:
    """
    Execute a file and return result without throwing.

    Args:
        file: Executable path
        args: Command line arguments
        timeout: Timeout in milliseconds
        preserve_output_on_error: Include stdout/stderr on failure
        use_cwd: Use current working directory
        env: Environment variables
        stdin: Stdin source ('ignore', 'inherit', 'pipe')
        input: Input string to pass to stdin

    Returns:
        ExecResult with stdout, stderr, code, and optional error
    """
    cwd = os.getcwd() if use_cwd else None

    exec_kwargs: dict[str, Any] = {
        "timeout": timeout / 1000,  # Convert ms to seconds
        "cwd": cwd,
        "shell": sys.platform == "win32",
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }

    if env is not None:
        exec_kwargs["env"] = env

    if stdin is not None:
        if stdin == "ignore":
            exec_kwargs["input"] = None
            exec_kwargs["stdin"] = subprocess.DEVNULL
        elif stdin == "inherit":
            exec_kwargs["input"] = None
            exec_kwargs["stdin"] = None
        # 'pipe' is the default

    if input is not None:
        exec_kwargs["input"] = input

    try:
        result = subprocess.run(
            [file] + args,
            **exec_kwargs,
        )

        if result.returncode != 0:
            if preserve_output_on_error:
                return ExecResult(
                    stdout=result.stdout or "",
                    stderr=result.stderr or "",
                    code=result.returncode or 1,
                    error=_get_error_message(result),
                )
            return ExecResult(
                stdout="",
                stderr="",
                code=result.returncode or 1,
            )

        return ExecResult(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            code=0,
        )

    except subprocess.TimeoutExpired:
        return ExecResult(
            stdout="",
            stderr="",
            code=124,  # Standard timeout exit code
            error="Command timed out",
        )
    except FileNotFoundError:
        return ExecResult(
            stdout="",
            stderr="",
            code=127,
            error=f"Command not found: {file}",
        )
    except Exception as e:
        return ExecResult(
            stdout="",
            stderr="",
            code=1,
            error=str(e),
        )


def _get_error_message(result: subprocess.CompletedProcess) -> str:
    """Extract a human-readable error message from a failed process."""
    # Try stderr first
    if result.stderr:
        return result.stderr.strip()
    # Fall back to return code
    return f"Exit code {result.returncode}"


# Async version for Python asyncio
async def exec_file_no_throw_async(
    file: str,
    args: list[str],
    *,
    timeout: int = 10 * 60 * 1000,
    preserve_output_on_error: bool = True,
    use_cwd: bool = True,
    env: dict[str, str] | None = None,
) -> ExecResult:
    """
    Async version of exec_file_no_throw.

    Args:
        file: Executable path
        args: Command line arguments
        timeout: Timeout in milliseconds
        preserve_output_on_error: Include stdout/stderr on failure
        use_cwd: Use current working directory
        env: Environment variables

    Returns:
        ExecResult with stdout, stderr, code, and optional error
    """
    cwd = os.getcwd() if use_cwd else None

    cmd = [file] + args
    kwargs: dict[str, Any] = {
        "timeout": timeout / 1000,
        "cwd": cwd,
        "shell": sys.platform == "win32",
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }

    if env is not None:
        kwargs["env"] = env

    try:
        result = await asyncio.create_subprocess_exec(
            *cmd,
            **kwargs,
        )
        stdout, stderr = await result.communicate()

        if result.returncode != 0:
            if preserve_output_on_error:
                return ExecResult(
                    stdout=stdout or "",
                    stderr=stderr or "",
                    code=result.returncode or 1,
                    error=stderr.strip() if stderr else f"Exit code {result.returncode}",
                )
            return ExecResult(
                stdout="",
                stderr="",
                code=result.returncode or 1,
            )

        return ExecResult(
            stdout=stdout or "",
            stderr=stderr or "",
            code=0,
        )

    except asyncio.TimeoutError:
        return ExecResult(
            stdout="",
            stderr="",
            code=124,
            error="Command timed out",
        )
    except FileNotFoundError:
        return ExecResult(
            stdout="",
            stderr="",
            code=127,
            error=f"Command not found: {file}",
        )
    except Exception as e:
        return ExecResult(
            stdout="",
            stderr="",
            code=1,
            error=str(e),
        )
