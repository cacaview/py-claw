from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tasks import TaskRuntime
from py_claw.tools.base import ToolDefinition, ToolPermissionTarget


class MonitorInterval(str, Enum):
    """Monitoring interval in seconds."""

    IMMEDIATE = "0"
    ONE_SECOND = "1"
    FIVE_SECONDS = "5"
    TEN_SECONDS = "10"
    THIRTY_SECONDS = "30"


class MonitorToolInput(PyClawBaseModel):
    """Input for MonitorTool."""

    operation: str = Field(description="The monitoring operation to perform")
    task_id: str | None = Field(default=None, description="Task ID to monitor")
    interval: MonitorInterval = Field(default=MonitorInterval.IMMEDIATE, description="Monitoring interval")
    duration_seconds: int = Field(default=60, gt=0, le=3600, description="Maximum duration to monitor")


class MonitorTool:
    """Tool for monitoring ongoing operations, tasks, and system status."""

    definition = ToolDefinition(name="Monitor", input_model=MonitorToolInput)

    def __init__(self, task_runtime: TaskRuntime) -> None:
        self._task_runtime = task_runtime

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("task_id")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=str(value) if isinstance(value, str) else None,
        )

    def execute(self, arguments: MonitorToolInput, *, cwd: str) -> dict[str, object]:
        operation = arguments.operation.lower()

        if operation == "task":
            return self._monitor_task(
                arguments.task_id,
                arguments.interval,
                arguments.duration_seconds,
            )
        elif operation == "tasks":
            return self._monitor_all_tasks(arguments.interval, arguments.duration_seconds)
        elif operation == "status":
            return self._monitor_status()
        elif operation == "processes":
            return self._monitor_processes()
        else:
            return {
                "error": f"Unknown operation: {operation}",
                "supported_operations": ["task", "tasks", "status", "processes"],
            }

    def _monitor_task(
        self,
        task_id: str | None,
        interval: MonitorInterval,
        duration_seconds: int,
    ) -> dict[str, object]:
        """Monitor a specific task by ID."""
        if not task_id:
            return {"error": "task_id is required for 'task' operation"}

        start_time = time.time()
        samples: list[dict[str, Any]] = []

        while time.time() - start_time < duration_seconds:
            task = self._task_runtime.get(task_id)
            if task is None:
                return {"error": f"Task not found: {task_id}", "task_id": task_id}

            sample = {
                "task_id": task.id,
                "status": task.status,
                "description": task.description,
                "exit_code": task.exit_code,
                "error": task.error,
                "elapsed_seconds": round(time.time() - start_time, 1),
            }
            samples.append(sample)

            # If task is terminal, return immediately
            if task.status == "completed":
                return {
                    "task_id": task_id,
                    "final_status": task.status,
                    "exit_code": task.exit_code,
                    "completed": True,
                    "samples": samples,
                }

            # Sleep according to interval (skip for immediate)
            if interval != MonitorInterval.IMMEDIATE:
                time.sleep(float(interval.value))

        # Timeout - return latest state
        task = self._task_runtime.get(task_id)
        return {
            "task_id": task_id,
            "final_status": task.status if task else "unknown",
            "timeout": True,
            "duration_seconds": duration_seconds,
            "samples": samples,
        }

    def _monitor_all_tasks(
        self,
        interval: MonitorInterval,
        duration_seconds: int,
    ) -> dict[str, object]:
        """Monitor all tasks."""
        start_time = time.time()
        samples: list[dict[str, Any]] = []

        while time.time() - start_time < duration_seconds:
            tasks = self._task_runtime.list()
            pending = sum(1 for t in tasks if t.status == "pending")
            in_progress = sum(1 for t in tasks if t.status == "in_progress")
            completed = sum(1 for t in tasks if t.status == "completed")

            sample = {
                "total": len(tasks),
                "pending": pending,
                "in_progress": in_progress,
                "completed": completed,
                "elapsed_seconds": round(time.time() - start_time, 1),
            }
            samples.append(sample)

            # If all tasks are terminal, return
            if pending == 0 and in_progress == 0:
                return {
                    "final": True,
                    "total": len(tasks),
                    "completed": completed,
                    "samples": samples,
                }

            # Sleep according to interval
            if interval != MonitorInterval.IMMEDIATE:
                time.sleep(float(interval.value))

        return {
            "timeout": True,
            "total": len(tasks) if (tasks := self._task_runtime.list()) else 0,
            "duration_seconds": duration_seconds,
            "samples": samples,
        }

    def _monitor_status(self) -> dict[str, object]:
        """Get current system/task status snapshot."""
        tasks = self._task_runtime.list()
        processes = self._task_runtime._processes

        return {
            "timestamp": time.time(),
            "tasks": {
                "total": len(tasks),
                "pending": sum(1 for t in tasks if t.status == "pending"),
                "in_progress": sum(1 for t in tasks if t.status == "in_progress"),
                "completed": sum(1 for t in tasks if t.status == "completed"),
            },
            "background_processes": {
                "total": len(processes),
                "running": sum(1 for p in processes.values() if p.poll() is None),
            },
        }

    def _monitor_processes(self) -> dict[str, object]:
        """Monitor background processes."""
        processes = self._task_runtime._processes
        result: dict[str, Any] = {"processes": []}

        for shell_id, proc in processes.items():
            poll_result = proc.poll()
            result["processes"].append({
                "shell_id": shell_id,
                "running": poll_result is None,
                "exit_code": poll_result,
            })

        return result
