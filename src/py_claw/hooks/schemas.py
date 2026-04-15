from __future__ import annotations

from typing import Literal

from pydantic import AnyHttpUrl, Field, RootModel

from py_claw.schemas.common import HOOK_EVENTS, PyClawBaseModel

ShellType = Literal["bash", "powershell"]


class BashCommandHook(PyClawBaseModel):
    type: Literal["command"]
    command: str
    if_: str | None = Field(default=None, alias="if")
    shell: ShellType | None = None
    timeout: float | None = None
    statusMessage: str | None = None
    once: bool | None = None
    async_: bool | None = Field(default=None, alias="async")
    asyncRewake: bool | None = None


class PromptHook(PyClawBaseModel):
    type: Literal["prompt"]
    prompt: str
    if_: str | None = Field(default=None, alias="if")
    timeout: float | None = None
    model: str | None = None
    statusMessage: str | None = None
    once: bool | None = None


class HttpHook(PyClawBaseModel):
    type: Literal["http"]
    url: AnyHttpUrl
    if_: str | None = Field(default=None, alias="if")
    timeout: float | None = None
    headers: dict[str, str] | None = None
    allowedEnvVars: list[str] | None = None
    statusMessage: str | None = None
    once: bool | None = None


class AgentHook(PyClawBaseModel):
    type: Literal["agent"]
    prompt: str
    if_: str | None = Field(default=None, alias="if")
    timeout: float | None = None
    model: str | None = None
    statusMessage: str | None = None
    once: bool | None = None


HookCommand = BashCommandHook | PromptHook | HttpHook | AgentHook


class HookMatcher(PyClawBaseModel):
    matcher: str | None = None
    hooks: list[HookCommand]


class HooksSettings(RootModel[dict[str, list[HookMatcher]]]):
    @classmethod
    def from_event_map(cls, value: dict[str, list[HookMatcher]]) -> "HooksSettings":
        invalid = sorted(set(value) - set(HOOK_EVENTS))
        if invalid:
            raise ValueError(f"Unsupported hook events: {', '.join(invalid)}")
        return cls.model_validate(value)
