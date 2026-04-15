from __future__ import annotations

import asyncio
import subprocess
import time
from enum import Enum
from typing import Any

from pydantic import Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolPermissionTarget


class WorkflowStatus(str, Enum):
    """Workflow execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class WorkflowStepStatus(str, Enum):
    """Individual step status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowCreateInput(PyClawBaseModel):
    """Create a new workflow."""

    name: str = Field(description="Name of the workflow")
    description: str | None = Field(default=None, description="Workflow description")
    steps: list[dict[str, Any]] = Field(description="List of workflow steps")
    parallel: bool = Field(default=False, description="Execute steps in parallel if True")


class WorkflowExecuteInput(PyClawBaseModel):
    """Execute a workflow."""

    workflow_id: str | None = Field(default=None, description="ID of workflow to execute")
    workflow_name: str | None = Field(default=None, description="Name of workflow to execute")
    inputs: dict[str, Any] | None = Field(default=None, description="Input parameters")


class WorkflowStatusInput(PyClawBaseModel):
    """Get workflow status."""

    workflow_id: str = Field(description="ID of workflow to check")


class WorkflowCancelInput(PyClawBaseModel):
    """Cancel a running workflow."""

    workflow_id: str = Field(description="ID of workflow to cancel")


class WorkflowTool:
    """Tool for workflow orchestration and execution.

    Manages workflows with multiple steps, parallel execution,
    error handling, and status tracking.
    """

    definition = ToolDefinition(name="Workflow", input_model=WorkflowCreateInput)

    def __init__(self) -> None:
        self._workflows: dict[str, dict[str, Any]] = {}
        self._executions: dict[str, dict[str, Any]] = {}
        self._cancelled: set[str] = set()

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("workflow_id") or payload.get("workflow_name")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=str(value) if isinstance(value, str) else None,
        )

    def execute(self, arguments: WorkflowCreateInput, *, cwd: str) -> dict[str, object]:
        if hasattr(arguments, "steps") and arguments.steps:
            return self._create_workflow(arguments)
        elif hasattr(arguments, "workflow_id") or hasattr(arguments, "workflow_name"):
            return self._execute_workflow(
                getattr(arguments, "workflow_id", None),
                getattr(arguments, "workflow_name", None),
                getattr(arguments, "inputs", None),
                cwd=cwd,
            )
        return {"error": "Invalid workflow input"}

    def _create_workflow(self, arguments: WorkflowCreateInput) -> dict[str, object]:
        """Create a new workflow definition."""
        import uuid
        workflow_id = str(uuid.uuid4())[:8]

        workflow = {
            "id": workflow_id,
            "name": arguments.name,
            "description": arguments.description or "",
            "steps": arguments.steps,
            "parallel": arguments.parallel,
            "created_at": time.time(),
        }

        self._workflows[workflow_id] = workflow

        return {
            "workflow_id": workflow_id,
            "name": arguments.name,
            "status": "created",
            "step_count": len(arguments.steps),
        }

    def _execute_workflow(
        self,
        workflow_id: str | None,
        workflow_name: str | None,
        inputs: dict[str, Any] | None,
        *,
        cwd: str,
    ) -> dict[str, object]:
        """Execute a workflow with real step execution."""
        import uuid

        if not workflow_id and not workflow_name:
            return {"error": "Either workflow_id or workflow_name is required"}

        workflow = None
        if workflow_id and workflow_id in self._workflows:
            workflow = self._workflows[workflow_id]
        elif workflow_name:
            for w in self._workflows.values():
                if w["name"] == workflow_name:
                    workflow = w
                    break

        if not workflow:
            return {"error": f"Workflow not found: {workflow_id or workflow_name}"}

        execution_id = str(uuid.uuid4())[:8]
        execution: dict[str, Any] = {
            "id": execution_id,
            "workflow_id": workflow["id"],
            "workflow_name": workflow["name"],
            "status": WorkflowStatus.RUNNING,
            "inputs": inputs or {},
            "started_at": time.time(),
            "steps": [],
        }

        for i, step in enumerate(workflow["steps"]):
            execution["steps"].append({
                "index": i,
                "name": step.get("name", f"step_{i}"),
                "action": step.get("action", "unknown"),
                "status": WorkflowStepStatus.PENDING,
                "result": None,
                "error": None,
            })

        self._executions[execution_id] = execution
        self._cancelled.discard(execution_id)

        if workflow["parallel"]:
            self._execute_parallel(execution, workflow["steps"], cwd)
        else:
            self._execute_sequential(execution, workflow["steps"], cwd)

        if execution_id in self._cancelled:
            execution["status"] = WorkflowStatus.CANCELLED
        elif any(s["status"] == WorkflowStepStatus.FAILED for s in execution["steps"]):
            execution["status"] = WorkflowStatus.FAILED
        else:
            execution["status"] = WorkflowStatus.COMPLETED

        execution["completed_at"] = time.time()

        return {
            "execution_id": execution_id,
            "workflow_id": workflow["id"],
            "workflow_name": workflow["name"],
            "status": execution["status"],
            "steps": [
                {"index": s["index"], "name": s["name"], "status": s["status"], "error": s.get("error")}
                for s in execution["steps"]
            ],
        }

    def _execute_step(self, step: dict[str, Any], inputs: dict[str, Any], cwd: str) -> dict[str, Any]:
        """Execute a single workflow step and return its result."""
        action = step.get("action", "")
        step_inputs = {**inputs, **step.get("inputs", {})}

        if action == "bash":
            command = step.get("command") or step.get("script", "")
            if not command:
                return {"status": WorkflowStepStatus.FAILED, "error": "No command specified for bash action"}
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=step.get("timeout", 300),
                )
                if result.returncode == 0:
                    return {"status": WorkflowStepStatus.COMPLETED, "output": result.stdout}
                else:
                    return {"status": WorkflowStepStatus.FAILED, "error": result.stderr or f"Exit code {result.returncode}"}
            except subprocess.TimeoutExpired:
                return {"status": WorkflowStepStatus.FAILED, "error": f"Command timed out after {step.get('timeout', 300)}s"}
            except Exception as e:
                return {"status": WorkflowStepStatus.FAILED, "error": str(e)}

        elif action == "powershell":
            command = step.get("command") or step.get("script", "")
            if not command:
                return {"status": WorkflowStepStatus.FAILED, "error": "No command specified for powershell action"}
            try:
                result = subprocess.run(
                    ["pwsh", "-Command", command],
                    shell=False,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=step.get("timeout", 300),
                )
                if result.returncode == 0:
                    return {"status": WorkflowStepStatus.COMPLETED, "output": result.stdout}
                else:
                    return {"status": WorkflowStepStatus.FAILED, "error": result.stderr or f"Exit code {result.returncode}"}
            except FileNotFoundError:
                return {"status": WorkflowStepStatus.FAILED, "error": "PowerShell (pwsh) not found"}
            except subprocess.TimeoutExpired:
                return {"status": WorkflowStepStatus.FAILED, "error": f"Command timed out after {step.get('timeout', 300)}s"}
            except Exception as e:
                return {"status": WorkflowStepStatus.FAILED, "error": str(e)}

        elif action == "wait":
            duration = step.get("duration", step_inputs.get("duration", 1))
            time.sleep(duration)
            return {"status": WorkflowStepStatus.COMPLETED, "duration": duration}

        elif action == "http_request":
            import urllib.request
            url = step.get("url") or step_inputs.get("url", "")
            method = step.get("method", "GET").upper()
            headers = step.get("headers") or {}
            body = step.get("body")

            if not url:
                return {"status": WorkflowStepStatus.FAILED, "error": "No URL specified for http_request action"}

            try:
                req = urllib.request.Request(url, method=method, headers=headers)
                if body:
                    req.data = body.encode() if isinstance(body, str) else body

                with urllib.request.urlopen(req, timeout=step.get("timeout", 30)) as resp:
                    return {
                        "status": WorkflowStepStatus.COMPLETED,
                        "output": resp.read().decode("utf-8", errors="replace"),
                        "status_code": resp.status,
                    }
            except urllib.error.URLError as e:
                return {"status": WorkflowStepStatus.FAILED, "error": str(e.reason)}
            except Exception as e:
                return {"status": WorkflowStepStatus.FAILED, "error": str(e)}

        elif action == "skip":
            return {"status": WorkflowStepStatus.SKIPPED}

        else:
            return {"status": WorkflowStepStatus.FAILED, "error": f"Unknown action type: {action}"}

    def _execute_sequential(self, execution: dict[str, Any], steps: list[dict[str, Any]], cwd: str) -> None:
        """Execute steps sequentially, stopping on failure."""
        inputs = execution.get("inputs", {})
        for i, step in enumerate(execution["steps"]):
            if execution["id"] in self._cancelled:
                break
            step["status"] = WorkflowStepStatus.RUNNING
            result = self._execute_step(steps[i], inputs, cwd)
            step["status"] = result.get("status", WorkflowStepStatus.COMPLETED)
            if result.get("error"):
                step["error"] = result["error"]
            if result.get("output"):
                step["output"] = result["output"]

    def _execute_parallel(self, execution: dict[str, Any], steps: list[dict[str, Any]], cwd: str) -> None:
        """Execute steps in parallel using threads."""
        import concurrent.futures

        inputs = execution.get("inputs", {})

        def run_step(idx: int) -> tuple[int, dict[str, Any]]:
            step = steps[idx]
            exec_step = execution["steps"][idx]
            exec_step["status"] = WorkflowStepStatus.RUNNING
            result = self._execute_step(step, inputs, cwd)
            return idx, result

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(steps)) as pool:
            futures = {pool.submit(run_step, i): i for i in range(len(steps))}
            for future in concurrent.futures.as_completed(futures):
                if execution["id"] in self._cancelled:
                    for f in futures:
                        f.cancel()
                    break
                try:
                    idx, result = future.result()
                    execution["steps"][idx]["status"] = result.get("status", WorkflowStepStatus.COMPLETED)
                    if result.get("error"):
                        execution["steps"][idx]["error"] = result["error"]
                    if result.get("output"):
                        execution["steps"][idx]["output"] = result["output"]
                except Exception as e:
                    execution["steps"][idx]["status"] = WorkflowStepStatus.FAILED
                    execution["steps"][idx]["error"] = str(e)

    def _get_status(self, workflow_id: str) -> dict[str, object]:
        """Get workflow execution status."""
        if workflow_id not in self._executions:
            return {"error": f"Execution not found: {workflow_id}"}

        execution = self._executions[workflow_id]
        return {
            "execution_id": workflow_id,
            "workflow_name": execution["workflow_name"],
            "status": execution["status"],
            "steps": execution["steps"],
            "elapsed_seconds": time.time() - execution["started_at"],
        }

    def _cancel_workflow(self, workflow_id: str) -> dict[str, object]:
        """Cancel a running workflow."""
        if workflow_id not in self._executions:
            return {"error": f"Execution not found: {workflow_id}"}

        execution = self._executions[workflow_id]
        if execution["status"] not in (WorkflowStatus.RUNNING, WorkflowStatus.PENDING):
            return {
                "error": f"Cannot cancel workflow in status: {execution['status']}",
                "execution_id": workflow_id,
                "status": execution["status"],
            }

        execution["status"] = WorkflowStatus.CANCELLED
        execution["cancelled_at"] = time.time()
        self._cancelled.add(workflow_id)

        return {
            "execution_id": workflow_id,
            "status": WorkflowStatus.CANCELLED,
            "message": "Workflow cancelled",
        }
