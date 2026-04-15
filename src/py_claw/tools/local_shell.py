from __future__ import annotations

import shutil
import subprocess
import threading
from typing import TextIO

from pydantic import BaseModel, Field

from py_claw.tasks import TaskRuntime
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget
from py_claw.tools.bash_security import BashSecurityCheckResult, check_bash_security, check_path_security

# AST-based security analysis (complementary layer)
try:
    from py_claw.tools.bash.security import BashSecurityResult, analyze_command_security
    _HAS_AST_ANALYSIS = True
except ImportError:
    _HAS_AST_ANALYSIS = False


def _ast_to_security_result(ast_result: BashSecurityResult) -> BashSecurityCheckResult:
    """Map AST security result to the BashSecurityCheckResult interface."""
    # Map AST severity strings to shell severity literals
    _AST_SEVERITY_MAP: dict[str, str] = {
        "safe": "safe",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "critical": "critical",
    }
    severity_str = _AST_SEVERITY_MAP.get(ast_result.severity, "safe")

    # Build pattern labels from AST findings
    patterns: list[str] = []
    if ast_result.has_injection and ast_result.injection_type:
        patterns.append(f"injection:{ast_result.injection_type}")
    if ast_result.has_zsh_bypass and ast_result.zsh_bypass_details:
        patterns.append(f"zsh_bypass:{ast_result.zsh_bypass_details}")
    if ast_result.has_dangerous_patterns:
        patterns.extend(ast_result.dangerous_patterns)
    if ast_result.is_file_destructive:
        patterns.append("file_destructive")
    if ast_result.is_network_command:
        patterns.append("network_command")

    # Warnings from AST
    warnings: list[str] = list(ast_result.warnings)
    if ast_result.unsafe_env_vars:
        warnings.append(f"unsafe_env_vars:{','.join(ast_result.unsafe_env_vars)}")
    if ast_result.safe_wrappers_stripped:
        warnings.append(f"safe_wrappers:{','.join(ast_result.safe_wrappers_stripped)}")

    return BashSecurityCheckResult(
        is_safe=ast_result.is_safe,
        shell_type="bash",
        dangerous_patterns=patterns,
        warnings=warnings,
        severity=severity_str,  # type: ignore[arg-type]
    )


class BashToolInput(BaseModel):
    command: str
    timeout: int | None = Field(default=None, ge=1, le=600000)
    description: str | None = None
    run_in_background: bool = False
    dangerouslyDisableSandbox: bool = False


def _describe_security_result(result: BashSecurityCheckResult) -> dict:
    info: dict[str, object] = {
        "severity": result.severity,
        "shellType": result.shell_type,
        "dangerousPatterns": result.dangerous_patterns,
        "warnings": result.warnings,
    }
    # Surface command class if non-standard
    if not result.is_safe and result.dangerous_patterns:
        for p in result.dangerous_patterns:
            if p in ("network_command", "file_destructive"):
                info["commandClass"] = p
                break
    return info


class BashTool:
    definition = ToolDefinition(name="Bash", input_model=BashToolInput)

    def __init__(self, task_runtime: TaskRuntime | None = None) -> None:
        self._task_runtime = task_runtime

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        raw_value = payload.get("command")
        content = str(raw_value) if isinstance(raw_value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: BashToolInput, *, cwd: str) -> dict[str, object]:
        output: dict[str, object] = {
            "command": arguments.command,
        }

        if not arguments.dangerouslyDisableSandbox:
            # Primary: AST-based security analysis (deeper structural checks)
            if _HAS_AST_ANALYSIS:
                ast_result = analyze_command_security(arguments.command)
                security = _ast_to_security_result(ast_result)
                output["security"] = _describe_security_result(security)
                if security.severity == "critical":
                    raise ToolError(
                        f"Command blocked due to critical security risk: {security.dangerous_patterns[0] if security.dangerous_patterns else security.severity}. "
                        "To bypass, set dangerouslyDisableSandbox: true."
                    )
                if not security.is_safe:
                    # Non-critical risk — still allow but log
                    pass
            else:
                # Fallback: regex-based security check
                security = check_bash_security(arguments.command)
                output["security"] = _describe_security_result(security)
                if security.severity == "critical":
                    raise ToolError(
                        f"Command blocked due to critical security risk: {security.dangerous_patterns[0] if security.dangerous_patterns else security.severity}. "
                        "To bypass, set dangerouslyDisableSandbox: true."
                    )
            path_ok, path_reason = check_path_security(arguments.command, cwd)
            if not path_ok:
                raise ToolError(
                    f"Command accesses path outside allowed scope ({path_reason}). "
                    "To bypass, set dangerouslyDisableSandbox: true."
                )

        if arguments.run_in_background:
            if self._task_runtime is None:
                raise ToolError("Background bash execution requires task runtime")
            return self._execute_in_background(
                arguments,
                cwd=cwd,
                security_result=output.get("security"),
            )
        bash_path = shutil.which("bash")
        if bash_path is None:
            raise ToolError("bash executable not found")
        timeout_ms = arguments.timeout or 120000
        try:
            completed = subprocess.run(
                [bash_path, "-lc", arguments.command],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(f"Command timed out after {timeout_ms}ms") from exc
        output.update({
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "exitCode": completed.returncode,
        })
        return output

    def _execute_in_background(
        self,
        arguments: BashToolInput,
        *,
        cwd: str,
        security_result: dict | None = None,
    ) -> dict[str, object]:
        bash_path = shutil.which("bash")
        if bash_path is None:
            raise ToolError("bash executable not found")
        task = self._task_runtime.create_background_shell_task(
            command=arguments.command,
            cwd=cwd,
            description=arguments.description,
        )
        try:
            process = subprocess.Popen(
                [bash_path, "-lc", arguments.command],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:
            self._task_runtime.mark_process_failed(task.id, str(exc))
            raise
        self._task_runtime.attach_process(task.id, process)
        threading.Thread(
            target=self._stream_output,
            args=(task.id, process.stdout, "stdout"),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._stream_output,
            args=(task.id, process.stderr, "stderr"),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._wait_for_process,
            args=(task.id, process),
            daemon=True,
        ).start()
        result: dict[str, object] = {
            "task_id": task.id,
            "command": arguments.command,
            "status": task.status,
            "description": task.description,
            "outputFile": task.output_file,
        }
        if security_result is not None:
            result["security"] = security_result
        return result

    def _stream_output(self, task_id: str, stream: TextIO | None, stream_name: str) -> None:
        if stream is None:
            return
        try:
            for chunk in iter(stream.readline, ""):
                if not chunk:
                    break
                self._task_runtime.append_output(task_id, chunk, stream=stream_name)
        finally:
            stream.close()

    def _wait_for_process(self, task_id: str, process: subprocess.Popen[str]) -> None:
        exit_code = process.wait()
        self._task_runtime.mark_process_finished(task_id, exit_code)
