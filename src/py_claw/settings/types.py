from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from py_claw.hooks.schemas import HookMatcher
from py_claw.schemas.common import HOOK_EVENTS

CLAUDE_CODE_SETTINGS_SCHEMA_URL = "https://json.schemastore.org/claude-code-settings.json"
CUSTOMIZATION_SURFACES: tuple[str, ...] = ("skills", "agents", "hooks", "mcp")


class SettingsBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class PermissionsSettings(SettingsBaseModel):
    allow: list[str] | None = None
    deny: list[str] | None = None
    ask: list[str] | None = None
    defaultMode: str | None = None
    disableBypassPermissionsMode: str | None = None
    disableAutoMode: str | None = None
    additionalDirectories: list[str] | None = None


class EnvironmentVariablesSettings(RootModel[dict[str, str]]):
    pass


class AllowedMcpServerEntry(SettingsBaseModel):
    serverName: str | None = None
    serverCommand: list[str] | None = None
    serverUrl: str | None = None


class DeniedMcpServerEntry(SettingsBaseModel):
    serverName: str | None = None
    serverCommand: list[str] | None = None
    serverUrl: str | None = None


class SettingsModel(SettingsBaseModel):
    schema_: str | None = Field(default=None, alias="$schema")
    env: dict[str, str] | None = None
    permissions: PermissionsSettings | None = None
    hooks: dict[str, list[HookMatcher]] | None = None
    agents: dict[str, dict] | None = None
    skills: list[str] | None = None
    mcp: dict | None = None
    plugins: dict | None = None  # plugin system config: enabledPlugins, marketplaces, etc.

    @model_validator(mode="after")
    def validate_hook_events(self) -> "SettingsModel":
        if not self.hooks:
            return self
        invalid = [key for key in self.hooks.keys() if key not in HOOK_EVENTS]
        if invalid:
            raise ValueError(f"Unsupported hook events: {', '.join(sorted(invalid))}")
        return self
