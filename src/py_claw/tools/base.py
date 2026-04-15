from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel


class ToolError(Exception):
    pass


class ToolPermissionError(ToolError):
    def __init__(self, message: str, *, behavior: str = "deny") -> None:
        super().__init__(message)
        self.behavior = behavior


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    input_model: type[BaseModel]


@dataclass(frozen=True, slots=True)
class ToolPermissionTarget:
    tool_name: str
    content: str | None = None


class Tool(Protocol):
    @property
    def definition(self) -> ToolDefinition: ...

    def permission_target(self, payload: dict[str, Any]) -> ToolPermissionTarget: ...

    def execute(self, arguments: BaseModel, *, cwd: str) -> dict[str, Any]: ...
