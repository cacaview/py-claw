from __future__ import annotations

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tasks import TaskRuntime
from py_claw.tools.base import ToolDefinition, ToolPermissionTarget


class TaskCreateToolInput(PyClawBaseModel):
    subject: str
    description: str
    activeForm: str | None = None


class TaskGetToolInput(PyClawBaseModel):
    taskId: str


class TaskListToolInput(PyClawBaseModel):
    pass


class TaskUpdateToolInput(PyClawBaseModel):
    taskId: str
    subject: str | None = None
    description: str | None = None
    activeForm: str | None = None
    status: str | None = None
    addBlocks: list[str] | None = None
    addBlockedBy: list[str] | None = None
    owner: str | None = None


class TaskOutputToolInput(PyClawBaseModel):
    task_id: str
    block: bool = True
    timeout: int = 30000


class TaskStopToolInput(PyClawBaseModel):
    task_id: str | None = None
    shell_id: str | None = None


class TaskCreateTool:
    definition = ToolDefinition(name="TaskCreate", input_model=TaskCreateToolInput)

    def __init__(self, task_runtime: TaskRuntime) -> None:
        self._task_runtime = task_runtime

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        return ToolPermissionTarget(tool_name=self.definition.name)

    def execute(self, arguments: TaskCreateToolInput, *, cwd: str) -> dict[str, object]:
        task = self._task_runtime.create(
            subject=arguments.subject,
            description=arguments.description,
            active_form=arguments.activeForm,
        )
        return {"task": self._task_runtime.detail(task)}


class TaskGetTool:
    definition = ToolDefinition(name="TaskGet", input_model=TaskGetToolInput)

    def __init__(self, task_runtime: TaskRuntime) -> None:
        self._task_runtime = task_runtime

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("taskId")
        return ToolPermissionTarget(tool_name=self.definition.name, content=str(value) if isinstance(value, str) else None)

    def execute(self, arguments: TaskGetToolInput, *, cwd: str) -> dict[str, object]:
        task = self._task_runtime.get(arguments.taskId)
        return {"task": self._task_runtime.detail(task)}


class TaskListTool:
    definition = ToolDefinition(name="TaskList", input_model=TaskListToolInput)

    def __init__(self, task_runtime: TaskRuntime) -> None:
        self._task_runtime = task_runtime

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        return ToolPermissionTarget(tool_name=self.definition.name)

    def execute(self, arguments: TaskListToolInput, *, cwd: str) -> dict[str, object]:
        return {"tasks": [self._task_runtime.summary(task) for task in self._task_runtime.list()]}


class TaskUpdateTool:
    definition = ToolDefinition(name="TaskUpdate", input_model=TaskUpdateToolInput)

    def __init__(self, task_runtime: TaskRuntime) -> None:
        self._task_runtime = task_runtime

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("taskId")
        return ToolPermissionTarget(tool_name=self.definition.name, content=str(value) if isinstance(value, str) else None)

    def execute(self, arguments: TaskUpdateToolInput, *, cwd: str) -> dict[str, object]:
        task = self._task_runtime.update(
            arguments.taskId,
            subject=arguments.subject,
            description=arguments.description,
            active_form=arguments.activeForm,
            status=arguments.status,
            owner=arguments.owner,
            add_blocks=arguments.addBlocks,
            add_blocked_by=arguments.addBlockedBy,
        )
        if task is None:
            return {"deleted": True, "taskId": arguments.taskId}
        return {"task": self._task_runtime.detail(task)}


class TaskOutputTool:
    definition = ToolDefinition(name="TaskOutput", input_model=TaskOutputToolInput)

    def __init__(self, task_runtime: TaskRuntime) -> None:
        self._task_runtime = task_runtime

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("task_id")
        return ToolPermissionTarget(tool_name=self.definition.name, content=str(value) if isinstance(value, str) else None)

    def execute(self, arguments: TaskOutputToolInput, *, cwd: str) -> dict[str, object]:
        task = self._task_runtime.get(arguments.task_id)
        if arguments.block:
            task = self._task_runtime.wait_for_task(arguments.task_id, arguments.timeout)
        retrieval_status = "success"
        if task.status in {"pending", "in_progress"}:
            retrieval_status = "timeout" if arguments.block else "not_ready"
        return {
            "retrieval_status": retrieval_status,
            "task": self._task_runtime.output(task),
        }


class TaskStopTool:
    definition = ToolDefinition(name="TaskStop", input_model=TaskStopToolInput)

    def __init__(self, task_runtime: TaskRuntime) -> None:
        self._task_runtime = task_runtime

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("task_id") or payload.get("shell_id")
        return ToolPermissionTarget(tool_name=self.definition.name, content=str(value) if isinstance(value, str) else None)

    def execute(self, arguments: TaskStopToolInput, *, cwd: str) -> dict[str, object]:
        task_id = arguments.task_id or arguments.shell_id
        if task_id is None:
            raise ValueError("Missing required parameter: task_id")
        task = self._task_runtime.stop(task_id)
        return {
            "message": f"Successfully stopped task: {task.id} ({task.command or task.description})",
            "task_id": task.id,
            "task_type": task.task_type,
            "command": task.command or task.description,
        }
