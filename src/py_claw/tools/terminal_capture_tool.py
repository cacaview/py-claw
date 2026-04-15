from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tasks import TaskRuntime
from py_claw.tools.base import ToolDefinition, ToolPermissionTarget


class TerminalCaptureStartInput(PyClawBaseModel):
    """Start capturing terminal output."""

    session_name: str | None = Field(default=None, description="Optional name for this capture session")
    output_file: str | None = Field(default=None, description="Optional output file path")


class TerminalCaptureStopInput(PyClawBaseModel):
    """Stop capturing terminal output."""

    session_name: str | None = Field(default=None, description="Name of the capture session to stop")


class TerminalCaptureReadInput(PyClawBaseModel):
    """Read captured terminal output."""

    session_name: str | None = Field(default=None, description="Name of the capture session to read")
    task_id: str | None = Field(default=None, description="Task ID to read output from")
    offset: int = Field(default=0, ge=0, description="Offset in lines to start reading")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum lines to read")


class TerminalCaptureListInput(PyClawBaseModel):
    """List active capture sessions."""

    pass


class TerminalCaptureTool:
    """Tool for capturing and reading terminal output from background tasks."""

    definition = ToolDefinition(name="TerminalCapture", input_model=TerminalCaptureStartInput)

    def __init__(self, task_runtime: TaskRuntime) -> None:
        self._task_runtime = task_runtime
        self._capture_sessions: dict[str, str] = {}  # session_name -> output_file

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("session_name") or payload.get("task_id")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=str(value) if isinstance(value, str) else None,
        )

    def execute(self, arguments: TerminalCaptureStartInput, *, cwd: str) -> dict[str, object]:
        # This tool has multiple input types - delegate based on which fields are set
        # For simplicity, we dispatch based on the first non-None field
        if arguments.session_name is not None or arguments.output_file is not None:
            return self._start_capture(arguments.session_name, arguments.output_file, cwd)
        return {"error": "No valid input provided for TerminalCapture tool"}

    def _start_capture(
        self,
        session_name: str | None,
        output_file: str | None,
        cwd: str,
    ) -> dict[str, object]:
        """Start a new capture session."""
        if not session_name:
            session_name = f"capture_{len(self._capture_sessions) + 1}"

        if not output_file:
            # Create capture directory if needed
            capture_dir = Path(cwd) / ".py_claw" / "captures"
            capture_dir.mkdir(parents=True, exist_ok=True)
            output_file = str(capture_dir / f"{session_name}.log")

        self._capture_sessions[session_name] = output_file

        return {
            "session_name": session_name,
            "output_file": output_file,
            "status": "started",
        }

    def _stop_capture(self, session_name: str | None) -> dict[str, object]:
        """Stop a capture session."""
        if not session_name:
            return {"error": "session_name is required"}

        if session_name not in self._capture_sessions:
            return {"error": f"Unknown capture session: {session_name}"}

        output_file = self._capture_sessions.pop(session_name)

        return {
            "session_name": session_name,
            "output_file": output_file,
            "status": "stopped",
        }

    def _read_capture(
        self,
        session_name: str | None,
        task_id: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, object]:
        """Read captured output."""
        if task_id:
            # Read from task output file
            task = self._task_runtime.get(task_id)
            if not task:
                return {"error": f"Task not found: {task_id}"}

            output_file = task.output_file
            if not output_file or not Path(output_file).exists():
                return {"error": f"No output file for task: {task_id}", "task_id": task_id}

            with open(output_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start = min(offset, total_lines)
            end = min(offset + limit, total_lines)
            content_lines = lines[start:end]

            return {
                "task_id": task_id,
                "total_lines": total_lines,
                "offset": offset,
                "limit": limit,
                "content": "".join(content_lines),
                "truncated": end < total_lines,
            }

        elif session_name:
            # Read from capture session
            if session_name not in self._capture_sessions:
                return {"error": f"Unknown capture session: {session_name}"}

            output_file = self._capture_sessions[session_name]
            if not Path(output_file).exists():
                return {"error": f"Output file not found: {output_file}", "session_name": session_name}

            with open(output_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start = min(offset, total_lines)
            end = min(offset + limit, total_lines)
            content_lines = lines[start:end]

            return {
                "session_name": session_name,
                "total_lines": total_lines,
                "offset": offset,
                "limit": limit,
                "content": "".join(content_lines),
                "truncated": end < total_lines,
            }

        return {"error": "Either session_name or task_id is required"}

    def _list_captures(self) -> dict[str, object]:
        """List active capture sessions."""
        sessions = []
        for name, output_file in self._capture_sessions.items():
            file_exists = Path(output_file).exists()
            file_size = Path(output_file).stat().st_size if file_exists else 0
            sessions.append({
                "session_name": name,
                "output_file": output_file,
                "active": file_exists,
                "size_bytes": file_size,
            })

        return {
            "sessions": sessions,
            "total": len(sessions),
        }


def create_terminal_capture_tools(task_runtime: TaskRuntime) -> list:
    """Create all TerminalCapture tool variants."""
    base = TerminalCaptureTool(task_runtime)

    class TerminalCaptureStartTool:
        definition = ToolDefinition(name="TerminalCapture", input_model=TerminalCaptureStartInput)

        def __init__(self) -> None:
            pass

        def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
            value = payload.get("session_name")
            return ToolPermissionTarget(
                tool_name="TerminalCapture",
                content=str(value) if isinstance(value, str) else None,
            )

        def execute(self, arguments: TerminalCaptureStartInput, *, cwd: str) -> dict[str, object]:
            return base._start_capture(arguments.session_name, arguments.output_file, cwd)

    class TerminalCaptureStopTool:
        definition = ToolDefinition(name="TerminalCaptureStop", input_model=TerminalCaptureStopInput)

        def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
            value = payload.get("session_name")
            return ToolPermissionTarget(
                tool_name="TerminalCaptureStop",
                content=str(value) if isinstance(value, str) else None,
            )

        def execute(self, arguments: TerminalCaptureStopInput, *, cwd: str) -> dict[str, object]:
            return base._stop_capture(arguments.session_name)

    class TerminalCaptureReadTool:
        definition = ToolDefinition(name="TerminalCaptureRead", input_model=TerminalCaptureReadInput)

        def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
            value = payload.get("session_name") or payload.get("task_id")
            return ToolPermissionTarget(
                tool_name="TerminalCaptureRead",
                content=str(value) if isinstance(value, str) else None,
            )

        def execute(self, arguments: TerminalCaptureReadInput, *, cwd: str) -> dict[str, object]:
            return base._read_capture(arguments.session_name, arguments.task_id, arguments.offset, arguments.limit)

    class TerminalCaptureListTool:
        definition = ToolDefinition(name="TerminalCaptureList", input_model=TerminalCaptureListInput)

        def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
            return ToolPermissionTarget(tool_name="TerminalCaptureList")

        def execute(self, arguments: TerminalCaptureListInput, *, cwd: str) -> dict[str, object]:
            return base._list_captures()

    return [
        TerminalCaptureStartTool(),
        TerminalCaptureStopTool(),
        TerminalCaptureReadTool(),
        TerminalCaptureListTool(),
    ]
