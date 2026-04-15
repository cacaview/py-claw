from __future__ import annotations

from typing import TYPE_CHECKING, Any

from py_claw.schemas.common import PermissionMode, PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


class EnterPlanModeToolInput(PyClawBaseModel):
    pass


class ExitPlanModeToolInput(PyClawBaseModel):
    allowedPrompts: list[dict[str, Any]] | None = None


class EnterPlanModeTool:
    definition = ToolDefinition(name="EnterPlanMode", input_model=EnterPlanModeToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        return ToolPermissionTarget(tool_name=self.definition.name)

    def execute(self, arguments: EnterPlanModeToolInput, *, cwd: str) -> dict[str, object]:
        state = self._require_state()
        state.permission_mode = "plan"
        return {
            "message": (
                "Entered plan mode. Focus on exploring the codebase and designing an implementation approach before coding."
            )
        }

    def _require_state(self) -> RuntimeState:
        if self._state is None:
            raise ToolError("EnterPlanMode requires runtime state")
        return self._state


class ExitPlanModeTool:
    definition = ToolDefinition(name="ExitPlanMode", input_model=ExitPlanModeToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        prompts = payload.get("allowedPrompts")
        if isinstance(prompts, list) and prompts:
            return ToolPermissionTarget(tool_name=self.definition.name, content=str(len(prompts)))
        return ToolPermissionTarget(tool_name=self.definition.name)

    def execute(self, arguments: ExitPlanModeToolInput, *, cwd: str) -> dict[str, object]:
        state = self._require_state()
        if state.permission_mode != "plan":
            raise ToolError(
                "You are not in plan mode. This tool is only for exiting plan mode after writing a plan."
            )
        state.permission_mode = self._restore_mode(state.permission_mode)
        return {
            "message": "Exited plan mode. The implementation plan is ready for approval and coding can begin after approval.",
            "allowedPrompts": arguments.allowedPrompts,
        }

    def _restore_mode(self, current_mode: PermissionMode) -> PermissionMode:
        if current_mode == "plan":
            return "default"
        return current_mode

    def _require_state(self) -> RuntimeState:
        if self._state is None:
            raise ToolError("ExitPlanMode requires runtime state")
        return self._state
