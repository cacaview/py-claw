from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import RootModel

from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


class SyntheticOutputToolInput(RootModel[dict[str, Any]]):
    pass


class SyntheticOutputTool:
    """Return structured output for non-interactive runs."""

    definition = ToolDefinition(name="StructuredOutput", input_model=SyntheticOutputToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def bind_state(self, state: RuntimeState) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        keys = ",".join(sorted(str(key) for key in payload.keys())) if isinstance(payload, dict) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=keys or None)

    def execute(self, arguments: SyntheticOutputToolInput, *, cwd: str) -> dict[str, object]:
        del cwd
        payload = arguments.root
        schema = self._schema()
        if schema is not None:
            self._validate_against_schema(payload, schema)
        return {
            "data": "Structured output provided successfully",
            "structured_output": payload,
        }

    def _schema(self) -> dict[str, Any] | None:
        if self._state is None:
            return None
        schema = self._state.json_schema
        return schema if isinstance(schema, dict) else None

    def _validate_against_schema(self, payload: dict[str, Any], schema: dict[str, Any]) -> None:
        if schema.get("type") not in {None, "object"}:
            return
        required = schema.get("required")
        if isinstance(required, list):
            missing = [str(name) for name in required if str(name) not in payload]
            if missing:
                raise ToolError(f"Structured output is missing required fields: {', '.join(missing)}")
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return
        for name, property_schema in properties.items():
            if name not in payload or not isinstance(property_schema, dict):
                continue
            expected_type = property_schema.get("type")
            if expected_type is None:
                continue
            if not self._value_matches_type(payload[name], expected_type):
                raise ToolError(f"Field '{name}' must be of type {expected_type}")

    def _value_matches_type(self, value: Any, expected_type: Any) -> bool:
        if expected_type == "string":
            return isinstance(value, str)
        if expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "boolean":
            return isinstance(value, bool)
        if expected_type == "object":
            return isinstance(value, dict)
        if expected_type == "array":
            return isinstance(value, list)
        if expected_type == "null":
            return value is None
        return True


StructuredOutputTool = SyntheticOutputTool
