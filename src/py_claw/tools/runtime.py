from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from py_claw.hooks.runtime import HookRuntime
from py_claw.permissions.engine import PermissionEngine
from py_claw.settings.loader import SettingsLoadResult
from py_claw.tasks import TaskRuntime
from py_claw.tools.agent_tools import AgentTool, SendMessageTool
from py_claw.tools.ask_user_question_tool import AskUserQuestionTool
from py_claw.tools.base import Tool, ToolError, ToolPermissionError, ToolPermissionTarget
from py_claw.tools.mcp_resource_tools import ListMcpResourcesTool, ReadMcpResourceTool
from py_claw.tools.plan_mode_tools import EnterPlanModeTool, ExitPlanModeTool
from py_claw.tools.schedule_cron_tool import CronCreateTool, CronDeleteTool, CronListTool
from py_claw.tools.registry import ToolRegistry, build_default_tool_registry
from py_claw.tools.skill_tool import SkillTool
from py_claw.tools.snip_tool import SnipTool
from py_claw.tools.todo_write_tool import TodoWriteTool
from py_claw.tools.worktree_tools import EnterWorktreeTool, ExitWorktreeTool


@dataclass(frozen=True, slots=True)
class ToolRuntimePermissionTarget:
    tool_name: str
    content: str | None = None


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    tool_name: str
    arguments: dict[str, Any]
    permission_target: ToolRuntimePermissionTarget
    output: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FileMutationRecord:
    tool_name: str
    file_path: str
    original_content: str | None
    updated_content: str


@dataclass(slots=True)
class ToolRuntime:
    task_runtime: TaskRuntime = field(default_factory=TaskRuntime)
    registry: ToolRegistry | None = None
    seeded_read_state: dict[str, dict[str, object]] = field(default_factory=dict)
    file_mutation_history: list[FileMutationRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = build_default_tool_registry(self.task_runtime)

    def set_state(self, state: Any) -> None:
        if self.registry is None:
            self.registry = build_default_tool_registry(self.task_runtime, state=state)
            return
        self.registry.register(AskUserQuestionTool(state))
        self.registry.register(EnterPlanModeTool(state))
        self.registry.register(ExitPlanModeTool(state))
        self.registry.register(CronCreateTool(state))
        self.registry.register(CronDeleteTool(state))
        self.registry.register(CronListTool(state))
        self.registry.register(EnterWorktreeTool(state))
        self.registry.register(ExitWorktreeTool(state))
        self.registry.register(ListMcpResourcesTool(state))
        self.registry.register(ReadMcpResourceTool(state))
        self.registry.register(AgentTool(state))
        self.registry.register(SendMessageTool(state))
        self.registry.register(SnipTool(state))
        self.registry.register(TodoWriteTool(state))

    def register(self, tool: Tool) -> None:
        self.registry.register(tool)

    def available_tool_names(self) -> list[str]:
        return sorted(tool.definition.name for tool in self.registry.values())

    def permission_target_for(self, tool_name: str, payload: dict[str, object]) -> ToolRuntimePermissionTarget:
        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolRuntimePermissionTarget(tool_name=tool_name, content=None)
        target = tool.permission_target(payload)
        return ToolRuntimePermissionTarget(tool_name=target.tool_name, content=target.content)

    def execute(
        self,
        tool_name: str,
        payload: dict[str, object],
        *,
        cwd: str,
        permission_engine: PermissionEngine | None = None,
        hook_runtime: HookRuntime | None = None,
        hook_settings: SettingsLoadResult | None = None,
        tool_use_id: str = "tool",
        permission_mode: str | None = None,
    ) -> ToolExecutionResult:
        tool = self.registry.require(tool_name)
        arguments = self._validate_input(tool_name, tool.definition.input_model, payload)
        normalized_payload = arguments.model_dump(by_alias=True, exclude_none=True)
        permission_target = self._runtime_permission_target(tool.permission_target(normalized_payload))

        if hook_runtime is not None and hook_settings is not None:
            pre_result = hook_runtime.run_pre_tool_use(
                settings=hook_settings,
                cwd=cwd,
                tool_name=tool.definition.name,
                tool_input=normalized_payload,
                tool_use_id=tool_use_id,
                content=permission_target.content,
                permission_mode=permission_mode,
            )
            if pre_result.updated_input is not None:
                arguments = self._validate_input(tool_name, tool.definition.input_model, pre_result.updated_input)
                normalized_payload = arguments.model_dump(by_alias=True, exclude_none=True)
                permission_target = self._runtime_permission_target(tool.permission_target(normalized_payload))
            if not pre_result.continue_:
                raise ToolError(pre_result.stop_reason or f"{tool_name} blocked by hook")

        if permission_engine is not None:
            evaluation = permission_engine.evaluate(permission_target.tool_name, permission_target.content)
            if evaluation.behavior != "allow":
                raise ToolPermissionError(
                    self._build_permission_message(tool_name, evaluation.reason, evaluation.mode),
                    behavior=evaluation.behavior,
                )

        try:
            output = tool.execute(arguments, cwd=cwd)
        except Exception as exc:
            if hook_runtime is not None and hook_settings is not None:
                hook_runtime.run_post_tool_use_failure(
                    settings=hook_settings,
                    cwd=cwd,
                    tool_name=tool.definition.name,
                    tool_input=normalized_payload,
                    tool_use_id=tool_use_id,
                    content=permission_target.content,
                    error=str(exc),
                    permission_mode=permission_mode,
                )
            raise

        if hook_runtime is not None and hook_settings is not None:
            hook_runtime.run_post_tool_use(
                settings=hook_settings,
                cwd=cwd,
                tool_name=tool.definition.name,
                tool_input=normalized_payload,
                tool_response=output,
                tool_use_id=tool_use_id,
                content=permission_target.content,
                permission_mode=permission_mode,
            )

        self._record_execution_side_effects(tool.definition.name, normalized_payload, output)
        return ToolExecutionResult(
            tool_name=tool.definition.name,
            arguments=normalized_payload,
            permission_target=permission_target,
            output=output,
        )











    def _validate_input(
        self,
        tool_name: str,
        input_model: type[BaseModel],
        payload: dict[str, object],
    ) -> BaseModel:
        try:
            return input_model.model_validate(payload)
        except ValidationError as exc:
            raise ToolError(f"Invalid input for {tool_name}: {exc}") from exc

    def seed_read_state(self, *, path: str, mtime: float, cwd: str) -> None:
        candidate = Path(path)
        normalized = candidate if candidate.is_absolute() else Path(cwd) / candidate
        normalized = normalized.expanduser().resolve(strict=False)
        if not normalized.exists() or normalized.is_dir():
            return
        disk_mtime = normalized.stat().st_mtime
        if disk_mtime > mtime:
            return
        try:
            with normalized.open("r", encoding="utf-8", newline="") as handle:
                raw = handle.read()
        except UnicodeDecodeError:
            return
        content = raw[1:] if raw.startswith("\ufeff") else raw
        normalized_content = content.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
        self.seeded_read_state[str(normalized)] = {
            "content": normalized_content,
            "timestamp": disk_mtime,
            "offset": None,
            "limit": None,
        }

    def rewind_mutations(self, *, dry_run: bool = False) -> dict[str, object]:
        if not self.file_mutation_history:
            return {"canRewind": False, "error": "No recorded file changes", "filesChanged": []}
        files_changed = sorted({record.file_path for record in self.file_mutation_history})
        insertions = 0
        deletions = 0
        for record in self.file_mutation_history:
            original_lines = [] if record.original_content is None else record.original_content.splitlines()
            updated_lines = record.updated_content.splitlines()
            if len(updated_lines) > len(original_lines):
                insertions += len(updated_lines) - len(original_lines)
            elif len(original_lines) > len(updated_lines):
                deletions += len(original_lines) - len(updated_lines)
        if not dry_run:
            for record in reversed(self.file_mutation_history):
                path = Path(record.file_path)
                if record.original_content is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.write_text(record.original_content, encoding="utf-8")
            self.file_mutation_history.clear()
        return {
            "canRewind": True,
            "filesChanged": files_changed,
            "insertions": insertions,
            "deletions": deletions,
        }

    def _runtime_permission_target(self, target: ToolPermissionTarget) -> ToolRuntimePermissionTarget:
        return ToolRuntimePermissionTarget(tool_name=target.tool_name, content=target.content)

    def _record_execution_side_effects(self, tool_name: str, payload: dict[str, Any], output: dict[str, Any]) -> None:
        if tool_name == "Write":
            file_path = output.get("filePath")
            content = output.get("content")
            original = output.get("originalFile")
            if isinstance(file_path, str) and isinstance(content, str):
                self.file_mutation_history.append(
                    FileMutationRecord(
                        tool_name=tool_name,
                        file_path=file_path,
                        original_content=original if isinstance(original, str) or original is None else None,
                        updated_content=content,
                    )
                )
            return
        if tool_name == "Edit":
            file_path = output.get("filePath")
            content = output.get("content")
            old_string = payload.get("old_string")
            new_string = payload.get("new_string")
            replace_all = bool(payload.get("replace_all", False))
            if not isinstance(file_path, str) or not isinstance(content, str):
                return
            path = Path(file_path)
            try:
                current_text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return
            if current_text != content:
                return
            if not isinstance(old_string, str) or not isinstance(new_string, str):
                return
            replacements = -1 if replace_all else 1
            original = content.replace(new_string, old_string, replacements)
            self.file_mutation_history.append(
                FileMutationRecord(
                    tool_name=tool_name,
                    file_path=file_path,
                    original_content=original,
                    updated_content=content,
                )
            )
            return
        if tool_name == "NotebookEdit":
            file_path = output.get("notebook_path")
            original = output.get("original_file")
            updated = output.get("updated_file")
            if isinstance(file_path, str) and isinstance(original, str) and isinstance(updated, str):
                self.file_mutation_history.append(
                    FileMutationRecord(
                        tool_name=tool_name,
                        file_path=file_path,
                        original_content=original,
                        updated_content=updated,
                    )
                )

    def _build_permission_message(self, tool_name: str, reason: str | None, mode: str) -> str:
        if reason == "mode" and mode == "dontAsk":
            return f"Current permission mode ({mode}) denies {tool_name}"
        return f"{tool_name} requires permission"
