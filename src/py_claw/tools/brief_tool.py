from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


_IMAGE_SUFFIXES = {
    ".apng",
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}


class SendUserMessageAttachment(PyClawBaseModel):
    path: str
    size: int
    isImage: bool
    file_uuid: str | None = None


class SendUserMessageToolInput(PyClawBaseModel):
    message: str
    attachments: list[str] | None = Field(default=None)
    status: Literal["normal", "proactive"]

    @model_validator(mode="after")
    def validate_fields(self) -> SendUserMessageToolInput:
        if not self.message.strip():
            raise ValueError("message must not be empty")
        if self.attachments is not None:
            normalized = [item.strip() for item in self.attachments if item.strip()]
            self.attachments = normalized or None
        return self


@dataclass(slots=True)
class _ResolvedAttachment:
    path: str
    size: int
    is_image: bool

    def as_output(self) -> dict[str, object]:
        return {
            "path": self.path,
            "size": self.size,
            "isImage": self.is_image,
        }


class _SendUserMessageToolBase:
    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        parts: list[str] = []
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            parts.append(message.strip())
        attachments = payload.get("attachments")
        if isinstance(attachments, list):
            paths = [item.strip() for item in attachments if isinstance(item, str) and item.strip()]
            if paths:
                parts.append(f"attachments:{len(paths)}")
                parts.extend(paths)
        return ToolPermissionTarget(tool_name=self.definition.name, content=" | ".join(parts) if parts else None)

    def execute(self, arguments: SendUserMessageToolInput, *, cwd: str) -> dict[str, object]:
        resolved = self._resolve_attachments(arguments.attachments or [], cwd=cwd)
        output: dict[str, object] = {
            "message": arguments.message,
            "status": arguments.status,
            "sentAt": self._sent_at(),
        }
        if resolved:
            output["attachments"] = [attachment.as_output() for attachment in resolved]
        return output

    def _resolve_attachments(self, raw_paths: list[str], *, cwd: str) -> list[_ResolvedAttachment]:
        resolved: list[_ResolvedAttachment] = []
        for raw_path in raw_paths:
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                base = Path(self._state.cwd) if self._state is not None else Path(cwd)
                path = (base / path).resolve()
            else:
                path = path.resolve()
            if not path.exists():
                raise ToolError(f'Attachment "{raw_path}" does not exist.')
            if not path.is_file():
                raise ToolError(f'Attachment "{raw_path}" is not a regular file.')
            stat = path.stat()
            resolved.append(
                _ResolvedAttachment(
                    path=str(path),
                    size=stat.st_size,
                    is_image=path.suffix.lower() in _IMAGE_SUFFIXES,
                )
            )
        return resolved

    def _sent_at(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class SendUserMessageTool(_SendUserMessageToolBase):
    definition = ToolDefinition(name="SendUserMessage", input_model=SendUserMessageToolInput)


class SendUserFileToolInput(PyClawBaseModel):
    files: list[str] = Field(min_length=1)
    message: str | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> SendUserFileToolInput:
        normalized = [item.strip() for item in self.files if item.strip()]
        if not normalized:
            raise ValueError("files must not be empty")
        self.files = normalized
        if self.message is not None and not self.message.strip():
            self.message = None
        return self


class SendUserFileTool(_SendUserMessageToolBase):
    definition = ToolDefinition(name="SendUserFile", input_model=SendUserFileToolInput)

    def execute(self, arguments: SendUserFileToolInput, *, cwd: str) -> dict[str, object]:
        resolved = self._resolve_attachments(arguments.files, cwd=cwd)
        output: dict[str, object] = {
            "sentAt": self._sent_at(),
            "files": [attachment.as_output() for attachment in resolved],
        }
        if arguments.message is not None:
            output["message"] = arguments.message
        return output


class BriefTool(_SendUserMessageToolBase):
    definition = ToolDefinition(name="Brief", input_model=SendUserMessageToolInput)
