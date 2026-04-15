from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.settings.loader import get_settings_with_sources
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


class ConfigGetInput(PyClawBaseModel):
    key: str = Field(description="Dot-separated config key path, e.g. 'model' or 'permissions.allow'")


class ConfigSetInput(PyClawBaseModel):
    key: str = Field(description="Dot-separated config key path, e.g. 'model'")
    value: Any = Field(description="New value for the config key")


class ConfigListInput(PyClawBaseModel):
    source: str | None = Field(default=None, description="Filter by source: 'user', 'project', 'local', 'flag', 'policy'")


class ConfigTool:
    definition = ToolDefinition(name="Config", input_model=ConfigGetInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        key = payload.get("key")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=str(key) if isinstance(key, str) else None,
        )

    def execute(self, arguments: ConfigGetInput, *, cwd: str) -> dict[str, object]:
        if self._state is None:
            raise ToolError("Config tool requires runtime state")

        settings = get_settings_with_sources(
            flag_settings=self._state.flag_settings,
            policy_settings=self._state.policy_settings,
            cwd=self._state.cwd,
            home_dir=self._state.home_dir,
        )

        # Navigate to the nested key
        value = settings.effective
        for part in arguments.key.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return {
                    "key": arguments.key,
                    "value": None,
                    "found": False,
                    "message": f"Cannot navigate to '{part}' in non-object value",
                }

        if value is None:
            return {
                "key": arguments.key,
                "value": None,
                "found": False,
                "message": f"Config key not found: {arguments.key}",
            }

        return {
            "key": arguments.key,
            "value": value,
            "found": True,
            "message": None,
        }


class ConfigSetTool:
    definition = ToolDefinition(name="ConfigSet", input_model=ConfigSetInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        key = payload.get("key")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=f"set:{str(key) if isinstance(key, str) else None}",
        )

    def execute(self, arguments: ConfigSetInput, *, cwd: str) -> dict[str, object]:
        if self._state is None:
            raise ToolError("ConfigSet tool requires runtime state")

        # Config changes via tool are not persisted - they're runtime only
        # For actual config changes, users should edit settings files directly
        return {
            "key": arguments.key,
            "value": arguments.value,
            "set": True,
            "message": (
                f"Runtime config '{arguments.key}' would be set to {arguments.value}. "
                "Note: ConfigSet tool does not persist changes. "
                "To persist config, edit .claude/settings.json directly."
            ),
        }


class ConfigListTool:
    definition = ToolDefinition(name="ConfigList", input_model=ConfigListInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        return ToolPermissionTarget(tool_name=self.definition.name, content=None)

    def execute(self, arguments: ConfigListInput, *, cwd: str) -> dict[str, object]:
        if self._state is None:
            raise ToolError("ConfigList tool requires runtime state")

        settings = get_settings_with_sources(
            flag_settings=self._state.flag_settings,
            policy_settings=self._state.policy_settings,
            cwd=self._state.cwd,
            home_dir=self._state.home_dir,
        )

        sources = []
        for src in settings.sources:
            src_name = src.get("source", "unknown")
            if arguments.source and src_name != arguments.source:
                continue
            sources.append({
                "source": src_name,
                "settings": src.get("settings", {}),
            })

        return {
            "sources": sources,
            "effective": settings.effective,
            "count": len(sources),
        }
