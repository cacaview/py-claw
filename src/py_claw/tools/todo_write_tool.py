from __future__ import annotations

from typing import TYPE_CHECKING

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


class TodoItem(PyClawBaseModel):
    content: str
    status: str
    activeForm: str


class TodoWriteToolInput(PyClawBaseModel):
    todos: list[TodoItem]


class TodoWriteTool:
    definition = ToolDefinition(name="TodoWrite", input_model=TodoWriteToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        todos = payload.get("todos")
        content = str(len(todos)) if isinstance(todos, list) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: TodoWriteToolInput, *, cwd: str) -> dict[str, object]:
        state = self._require_state()
        old_todos = list(state.todos)
        all_done = all(todo.status == "completed" for todo in arguments.todos)
        new_todos = [] if all_done else [todo.model_dump(by_alias=True) for todo in arguments.todos]
        state.todos = list(new_todos)
        return {
            "oldTodos": old_todos,
            "newTodos": new_todos,
            "verificationNudgeNeeded": False,
        }

    def _require_state(self) -> RuntimeState:
        if self._state is None:
            raise ToolError("TodoWrite requires runtime state")
        return self._state
