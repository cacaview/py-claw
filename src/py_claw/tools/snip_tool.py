from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.services.compact import get_compact_config, snip_compact_if_needed
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


class SnipToolInput(PyClawBaseModel):
    target_tokens: int | None = Field(default=None, ge=1, description="Target token budget for the snip pass")


class SnipTool:
    definition = ToolDefinition(name="Snip", input_model=SnipToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("target_tokens")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=str(value) if isinstance(value, int) else None,
        )

    def execute(self, arguments: SnipToolInput, *, cwd: str) -> dict[str, object]:
        del cwd
        state = self._require_state()
        runtime = state.query_runtime
        if runtime is None:
            raise ToolError("Snip requires a query runtime")

        target_tokens = arguments.target_tokens
        if target_tokens is None:
            target_tokens = get_compact_config().compact_token_reserve

        transcript = runtime.transcript
        snipped_transcript, changed = snip_compact_if_needed(transcript, {"target_tokens": target_tokens})
        runtime.replace_transcript(snipped_transcript)

        return {
            "changed": changed,
            "previousMessageCount": len(transcript),
            "messageCount": len(snipped_transcript),
            "targetTokens": target_tokens,
        }

    def _require_state(self) -> RuntimeState:
        if self._state is None:
            raise ToolError("Snip requires runtime state")
        return self._state
