from __future__ import annotations

import time

from pydantic import Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolPermissionTarget


class SleepToolInput(PyClawBaseModel):
    duration_ms: int = Field(gt=0, le=600_000)


class SleepTool:
    definition = ToolDefinition(name="Sleep", input_model=SleepToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("duration_ms")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=str(value) if isinstance(value, int) else None,
        )

    def execute(self, arguments: SleepToolInput, *, cwd: str) -> dict[str, object]:
        duration_seconds = arguments.duration_ms / 1000
        time.sleep(duration_seconds)
        return {
            "durationMs": arguments.duration_ms,
            "durationSeconds": duration_seconds,
            "slept": True,
        }
