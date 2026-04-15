from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import shutil
import subprocess
import threading
from typing import Any

from pydantic import ValidationError

from py_claw.hooks.schemas import BashCommandHook, HookMatcher
from py_claw.permissions.rules import PermissionRule, PermissionTarget, matches_permission_rule, parse_permission_rule_value
from py_claw.schemas.common import (
    CwdChangedHookInput,
    CwdChangedHookSpecificOutput,
    ConfigChangeHookInput,
    ElicitationHookInput,
    ElicitationHookSpecificOutput,
    ElicitationResultHookInput,
    ElicitationResultHookSpecificOutput,
    FileChangedHookInput,
    FileChangedHookSpecificOutput,
    InstructionsLoadedHookInput,
    NotificationHookInput,
    NotificationHookSpecificOutput,
    PermissionDeniedHookInput,
    PermissionRequestHookInput,
    PermissionRequestHookSpecificOutput,
    PostCompactHookInput,
    PostToolUseFailureHookInput,
    PostToolUseHookInput,
    PreCompactHookInput,
    PreToolUseHookInput,
    PreToolUseHookSpecificOutput,
    SessionEndHookInput,
    SessionStartHookInput,
    SetupHookInput,
    SetupHookSpecificOutput,
    StopFailureHookInput,
    StopHookInput,
    SubagentStartHookInput,
    SubagentStartHookSpecificOutput,
    SubagentStopHookInput,
    SyncHookJSONOutput,
    TaskCompletedHookInput,
    TaskCreatedHookInput,
    TeammateIdleHookInput,
    UserPromptSubmitHookInput,
    UserPromptSubmitHookSpecificOutput,
    WorktreeCreateHookInput,
    WorktreeCreateHookSpecificOutput,
    WorktreeRemoveHookInput,
)
from py_claw.settings.loader import SettingsLoadResult

_HOOK_EVENTS: set[str] = {
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "UserPromptSubmit",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "PermissionRequest",
    "PermissionDenied",
    "Setup",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "Elicitation",
    "ElicitationResult",
    "ConfigChange",
    "WorktreeCreate",
    "WorktreeRemove",
    "InstructionsLoaded",
    "CwdChanged",
    "FileChanged",
}


@dataclass(slots=True)
class HookExecutionRecord:
    event: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    structured_output: SyncHookJSONOutput | None = None


@dataclass(slots=True)
class HookPermissionDecision:
    behavior: str
    updated_input: dict[str, Any] | None = None
    updated_permissions: list[Any] | None = None
    message: str | None = None
    interrupt: bool | None = None


@dataclass(slots=True)
class HookDispatchResult:
    executions: list[HookExecutionRecord] = field(default_factory=list)
    continue_: bool = True
    stop_reason: str | None = None
    updated_input: dict[str, Any] | None = None
    permission_decision: HookPermissionDecision | None = None
    action: str | None = None
    content: dict[str, Any] | None = None


@dataclass(slots=True)
class HookRuntime:
    default_shell: str = "bash"
    default_timeout_seconds: float = 600.0
    default_session_id: str = "session"
    default_transcript_path: str = ".claude/transcript.jsonl"

    def run_pre_tool_use(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        content: str | None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = PreToolUseHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_use_id": tool_use_id,
            }
        )
        return self._dispatch(
            event="PreToolUse",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name=tool_name,
            content=content,
        )

    def run_post_tool_use(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_response: dict[str, Any],
        tool_use_id: str,
        content: str | None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = PostToolUseHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "PostToolUse",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_response": tool_response,
                "tool_use_id": tool_use_id,
            }
        )
        return self._dispatch(
            event="PostToolUse",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name=tool_name,
            content=content,
        )

    def run_post_tool_use_failure(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        content: str | None,
        error: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = PostToolUseFailureHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_use_id": tool_use_id,
                "error": error,
            }
        )
        return self._dispatch(
            event="PostToolUseFailure",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name=tool_name,
            content=content,
        )

    def run_permission_request(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        tool_name: str,
        tool_input: dict[str, Any],
        content: str | None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = PermissionRequestHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "PermissionRequest",
                "tool_name": tool_name,
                "tool_input": tool_input,
            }
        )
        return self._dispatch(
            event="PermissionRequest",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name=tool_name,
            content=content,
        )

    def run_permission_denied(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        content: str | None,
        reason: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = PermissionDeniedHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "PermissionDenied",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_use_id": tool_use_id,
                "reason": reason,
            }
        )
        return self._dispatch(
            event="PermissionDenied",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name=tool_name,
            content=content,
        )

    def run_elicitation(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        mcp_server_name: str,
        message: str,
        mode: str | None = None,
        url: str | None = None,
        elicitation_id: str | None = None,
        requested_schema: dict[str, Any] | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = ElicitationHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "Elicitation",
                "mcp_server_name": mcp_server_name,
                "message": message,
                "mode": mode,
                "url": url,
                "elicitation_id": elicitation_id,
                "requested_schema": requested_schema,
            }
        )
        return self._dispatch(
            event="Elicitation",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name=f"mcp__{mcp_server_name}",
            content=message,
        )

    def run_elicitation_result(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        mcp_server_name: str,
        elicitation_id: str | None,
        mode: str | None,
        action: str,
        content: dict[str, Any] | None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = ElicitationResultHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "ElicitationResult",
                "mcp_server_name": mcp_server_name,
                "elicitation_id": elicitation_id,
                "mode": mode,
                "action": action,
                "content": content,
            }
        )
        return self._dispatch(
            event="ElicitationResult",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name=f"mcp__{mcp_server_name}",
            content=None,
        )

    def run_worktree_create(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        name: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = WorktreeCreateHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "WorktreeCreate",
                "name": name,
            }
        )
        return self._dispatch(
            event="WorktreeCreate",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="EnterWorktree",
            content=name,
        )

    def run_worktree_remove(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        worktree_path: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = WorktreeRemoveHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "WorktreeRemove",
                "worktree_path": worktree_path,
            }
        )
        return self._dispatch(
            event="WorktreeRemove",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="ExitWorktree",
            content=worktree_path,
        )

    def run_cwd_changed(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        old_cwd: str,
        new_cwd: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = CwdChangedHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "CwdChanged",
                "old_cwd": old_cwd,
                "new_cwd": new_cwd,
            }
        )
        return self._dispatch(
            event="CwdChanged",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="CwdChanged",
            content=new_cwd,
        )

    def run_notification(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        message: str,
        notification_type: str,
        title: str | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = NotificationHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "Notification",
                "message": message,
                "notification_type": notification_type,
                "title": title,
            }
        )
        return self._dispatch(
            event="Notification",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="Notification",
            content=message,
        )

    def run_user_prompt_submit(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        prompt: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = UserPromptSubmitHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "UserPromptSubmit",
                "prompt": prompt,
            }
        )
        return self._dispatch(
            event="UserPromptSubmit",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="UserPromptSubmit",
            content=prompt,
        )

    def run_session_start(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        source: str,
        model: str | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = SessionStartHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "SessionStart",
                "source": source,
                "model": model,
            }
        )
        return self._dispatch(
            event="SessionStart",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="SessionStart",
            content=source,
        )

    def run_session_end(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        reason: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = SessionEndHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "SessionEnd",
                "reason": reason,
            }
        )
        return self._dispatch(
            event="SessionEnd",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="SessionEnd",
            content=reason,
        )

    def run_stop(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        stop_hook_active: bool,
        last_assistant_message: str | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = StopHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "Stop",
                "stop_hook_active": stop_hook_active,
                "last_assistant_message": last_assistant_message,
            }
        )
        return self._dispatch(
            event="Stop",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="Stop",
            content=last_assistant_message,
        )

    def run_stop_failure(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        error: str,
        error_details: str | None = None,
        last_assistant_message: str | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = StopFailureHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "StopFailure",
                "error": error,
                "error_details": error_details,
                "last_assistant_message": last_assistant_message,
            }
        )
        return self._dispatch(
            event="StopFailure",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="StopFailure",
            content=last_assistant_message,
        )

    def run_subagent_start(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        agent_id: str,
        agent_type: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = SubagentStartHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "SubagentStart",
                "agent_id": agent_id,
                "agent_type": agent_type,
            }
        )
        return self._dispatch(
            event="SubagentStart",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="SubagentStart",
            content=agent_id,
        )

    def run_subagent_stop(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        agent_id: str,
        agent_type: str,
        agent_transcript_path: str,
        stop_hook_active: bool = False,
        last_assistant_message: str | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = SubagentStopHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "SubagentStop",
                "agent_id": agent_id,
                "agent_type": agent_type,
                "agent_transcript_path": agent_transcript_path,
                "stop_hook_active": stop_hook_active,
                "last_assistant_message": last_assistant_message,
            }
        )
        return self._dispatch(
            event="SubagentStop",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="SubagentStop",
            content=agent_id,
        )

    def run_pre_compact(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        trigger: str,
        custom_instructions: str | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = PreCompactHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "PreCompact",
                "trigger": trigger,
                "custom_instructions": custom_instructions,
            }
        )
        return self._dispatch(
            event="PreCompact",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="PreCompact",
            content=custom_instructions,
        )

    def run_post_compact(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        trigger: str,
        compact_summary: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = PostCompactHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "PostCompact",
                "trigger": trigger,
                "compact_summary": compact_summary,
            }
        )
        return self._dispatch(
            event="PostCompact",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="PostCompact",
            content=compact_summary,
        )

    def run_setup(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        trigger: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = SetupHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "Setup",
                "trigger": trigger,
            }
        )
        return self._dispatch(
            event="Setup",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="Setup",
            content=trigger,
        )

    def run_teammate_idle(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        teammate_name: str,
        team_name: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = TeammateIdleHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "TeammateIdle",
                "teammate_name": teammate_name,
                "team_name": team_name,
            }
        )
        return self._dispatch(
            event="TeammateIdle",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="TeammateIdle",
            content=teammate_name,
        )

    def run_task_created(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        task_id: str,
        task_subject: str,
        task_description: str | None = None,
        teammate_name: str | None = None,
        team_name: str | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = TaskCreatedHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "TaskCreated",
                "task_id": task_id,
                "task_subject": task_subject,
                "task_description": task_description,
                "teammate_name": teammate_name,
                "team_name": team_name,
            }
        )
        return self._dispatch(
            event="TaskCreated",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="TaskCreated",
            content=task_subject,
        )

    def run_task_completed(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        task_id: str,
        task_subject: str,
        task_description: str | None = None,
        teammate_name: str | None = None,
        team_name: str | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = TaskCompletedHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "TaskCompleted",
                "task_id": task_id,
                "task_subject": task_subject,
                "task_description": task_description,
                "teammate_name": teammate_name,
                "team_name": team_name,
            }
        )
        return self._dispatch(
            event="TaskCompleted",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="TaskCompleted",
            content=task_subject,
        )

    def run_config_change(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        source: str,
        file_path: str | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = ConfigChangeHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "ConfigChange",
                "source": source,
                "file_path": file_path,
            }
        )
        return self._dispatch(
            event="ConfigChange",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="ConfigChange",
            content=file_path or source,
        )

    def run_instructions_loaded(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        file_path: str,
        memory_type: str,
        load_reason: str,
        globs: list[str] | None = None,
        trigger_file_path: str | None = None,
        parent_file_path: str | None = None,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = InstructionsLoadedHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "InstructionsLoaded",
                "file_path": file_path,
                "memory_type": memory_type,
                "load_reason": load_reason,
                "globs": globs,
                "trigger_file_path": trigger_file_path,
                "parent_file_path": parent_file_path,
            }
        )
        return self._dispatch(
            event="InstructionsLoaded",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="InstructionsLoaded",
            content=file_path,
        )

    def run_file_changed(
        self,
        *,
        settings: SettingsLoadResult,
        cwd: str,
        file_path: str,
        event: str,
        permission_mode: str | None = None,
    ) -> HookDispatchResult:
        hook_input = FileChangedHookInput.model_validate(
            self._base_input(cwd, permission_mode)
            | {
                "hook_event_name": "FileChanged",
                "file_path": file_path,
                "event": event,
            }
        )
        return self._dispatch(
            event="FileChanged",
            settings=settings,
            cwd=cwd,
            hook_input=hook_input.model_dump(by_alias=True, exclude_none=True),
            tool_name="FileChanged",
            content=file_path,
        )

    def _dispatch(
        self,
        *,
        event: str,
        settings: SettingsLoadResult,
        cwd: str,
        hook_input: dict[str, Any],
        tool_name: str,
        content: str | None,
    ) -> HookDispatchResult:
        result = HookDispatchResult()
        for hook in self._matching_command_hooks(settings, event=event, tool_name=tool_name, content=content):
            execution = self._execute_command_hook(hook, hook_input, cwd)
            result.executions.append(execution)
            self._apply_execution_result(result, event=event, execution=execution)
            if not result.continue_ or result.permission_decision is not None:
                break
        return result

    def _matching_command_hooks(
        self,
        settings: SettingsLoadResult,
        *,
        event: str,
        tool_name: str,
        content: str | None,
    ) -> list[BashCommandHook]:
        if event not in _HOOK_EVENTS:
            return []

        hooks: list[BashCommandHook] = []
        for source_entry in settings.sources:
            source_settings = source_entry.get("settings")
            if not isinstance(source_settings, dict):
                continue
            event_map = source_settings.get("hooks")
            if not isinstance(event_map, dict):
                continue
            matchers = event_map.get(event)
            if not isinstance(matchers, list):
                continue
            for raw_matcher in matchers:
                matcher = HookMatcher.model_validate(raw_matcher)
                if not self._matches(matcher.matcher, tool_name=tool_name, content=content):
                    continue
                for hook in matcher.hooks:
                    if hook.type != "command":
                        continue
                    if not self._matches(hook.if_, tool_name=tool_name, content=content):
                        continue
                    hooks.append(hook)
        return hooks

    def _matches(self, matcher: str | None, *, tool_name: str, content: str | None) -> bool:
        if matcher is None:
            return True
        rule = PermissionRule(
            source="session",
            rule_behavior="allow",
            rule_value=parse_permission_rule_value(matcher),
        )
        return matches_permission_rule(rule, PermissionTarget(tool_name=tool_name, content=content))

    def _execute_command_hook(self, hook: BashCommandHook, hook_input: dict[str, Any], cwd: str) -> HookExecutionRecord:
        command = self._shell_command(hook)
        timeout = hook.timeout if hook.timeout is not None else self.default_timeout_seconds
        event_name = hook_input.get("hook_event_name", "unknown")

        # Handle async hooks: run in background thread, return immediately
        if hook.async_:
            result_holder: dict[str, Any] = {}

            def run_async_hook() -> None:
                try:
                    completed = subprocess.run(
                        command,
                        input=json.dumps(hook_input),
                        capture_output=True,
                        text=True,
                        cwd=cwd,
                        timeout=timeout,
                        check=False,
                    )
                    result_holder["completed"] = completed
                except Exception as exc:
                    result_holder["error"] = str(exc)

            thread = threading.Thread(target=run_async_hook, daemon=True)
            thread.start()
            # Fire-and-forget: return immediately with exit_code -1 to indicate async
            return HookExecutionRecord(
                event=event_name,
                command=hook.command,
                exit_code=-1,
                stdout="",
                stderr="",
                structured_output=None,
            )

        # Synchronous execution (blocking)
        completed = subprocess.run(
            command,
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            check=False,
        )
        return HookExecutionRecord(
            event=event_name,
            command=hook.command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            structured_output=self._parse_structured_output(completed.stdout),
        )

    def _shell_command(self, hook: BashCommandHook) -> list[str]:
        shell = hook.shell or self.default_shell
        if shell == "powershell":
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            if powershell is None:
                raise RuntimeError("powershell executable not found")
            return [powershell, "-NoProfile", "-Command", hook.command]
        bash = shutil.which("bash")
        if bash is None:
            raise RuntimeError("bash executable not found")
        return [bash, "-lc", hook.command]

    def _parse_structured_output(self, stdout: str) -> SyncHookJSONOutput | None:
        payloads = [stdout.strip()]
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if lines:
            payloads.append(lines[-1])
        for payload in payloads:
            if not payload:
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            try:
                parsed = SyncHookJSONOutput.model_validate(data)
            except ValidationError:
                continue
            return parsed
        return None

    def _apply_execution_result(self, result: HookDispatchResult, *, event: str, execution: HookExecutionRecord) -> None:
        output = execution.structured_output
        if execution.exit_code != 0 and output is None:
            if event == "PermissionRequest":
                result.permission_decision = HookPermissionDecision(
                    behavior="deny",
                    message=self._execution_message(event, execution),
                )
            elif event == "PreToolUse":
                result.continue_ = False
                result.stop_reason = self._execution_message(event, execution)
            return

        if output is None:
            return

        if event == "PreToolUse":
            self._apply_pre_tool_output(result, output)
            return
        if event == "PermissionRequest":
            self._apply_permission_request_output(result, output)
            return
        if event == "Elicitation":
            self._apply_elicitation_output(result, output)
            return
        if event == "ElicitationResult":
            self._apply_elicitation_result_output(result, output)
            return
        if event == "WorktreeCreate":
            self._apply_worktree_create_output(result, output)
            return
        if event == "CwdChanged":
            self._apply_cwd_changed_output(result, output)
            return
        if event == "PreCompact":
            self._apply_pre_compact_output(result, output)
            return
        if event == "PostCompact":
            self._apply_post_compact_output(result, output)
            return
        if event == "SubagentStart":
            self._apply_subagent_start_output(result, output)
            return
        if event == "SubagentStop":
            self._apply_subagent_stop_output(result, output)
            return
        if event == "UserPromptSubmit":
            self._apply_user_prompt_submit_output(result, output)
            return
        if event == "SessionStart":
            self._apply_session_start_output(result, output)
            return
        if event == "Setup":
            self._apply_setup_output(result, output)
            return
        if event == "Notification":
            self._apply_notification_output(result, output)
            return
        if event == "FileChanged":
            self._apply_file_changed_output(result, output)

    def _apply_pre_tool_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        if output.hookSpecificOutput is not None and isinstance(output.hookSpecificOutput, PreToolUseHookSpecificOutput):
            if output.hookSpecificOutput.updatedInput is not None:
                result.updated_input = output.hookSpecificOutput.updatedInput
            if output.hookSpecificOutput.permissionDecision == "deny":
                result.continue_ = False
                result.stop_reason = output.hookSpecificOutput.permissionDecisionReason or self._output_message(output)
                return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_permission_request_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, PermissionRequestHookSpecificOutput):
            decision = hook_specific.decision
            result.permission_decision = HookPermissionDecision(
                behavior=decision.behavior,
                updated_input=getattr(decision, "updatedInput", None),
                updated_permissions=getattr(decision, "updatedPermissions", None),
                message=getattr(decision, "message", None),
                interrupt=getattr(decision, "interrupt", None),
            )
            return
        if output.continue_ is False or output.decision == "block":
            result.permission_decision = HookPermissionDecision(
                behavior="deny",
                message=self._output_message(output),
            )

    def _apply_elicitation_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, ElicitationHookSpecificOutput):
            result.action = hook_specific.action
            result.content = hook_specific.content
            return
        if output.continue_ is False or output.decision == "block":
            result.action = "cancel"
            result.content = None

    def _apply_elicitation_result_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, ElicitationResultHookSpecificOutput):
            if hook_specific.action is not None:
                result.action = hook_specific.action
            result.content = hook_specific.content
            return
        if output.continue_ is False or output.decision == "block":
            result.action = "cancel"
            result.content = None

    def _apply_worktree_create_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, WorktreeCreateHookSpecificOutput):
            result.content = {"worktreePath": hook_specific.worktreePath}
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_cwd_changed_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, CwdChangedHookSpecificOutput):
            result.content = {"watchPaths": hook_specific.watchPaths} if hook_specific.watchPaths is not None else None
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_pre_compact_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, NotificationHookSpecificOutput):
            if hook_specific.additionalContext is not None:
                result.content = {"additionalContext": hook_specific.additionalContext}
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_post_compact_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, NotificationHookSpecificOutput):
            if hook_specific.additionalContext is not None:
                result.content = {"additionalContext": hook_specific.additionalContext}
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_subagent_start_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, SubagentStartHookSpecificOutput):
            if hook_specific.additionalContext is not None:
                result.content = {"additionalContext": hook_specific.additionalContext}
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_subagent_stop_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, NotificationHookSpecificOutput):
            if hook_specific.additionalContext is not None:
                result.content = {"additionalContext": hook_specific.additionalContext}
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_user_prompt_submit_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, UserPromptSubmitHookSpecificOutput):
            if hook_specific.additionalContext is not None:
                result.content = {"additionalContext": hook_specific.additionalContext}
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_session_start_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        from py_claw.schemas.common import SessionStartHookSpecificOutput as SessionStartOutput
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, SessionStartOutput):
            content: dict[str, Any] = {}
            if hook_specific.additionalContext is not None:
                content["additionalContext"] = hook_specific.additionalContext
            if hook_specific.initialUserMessage is not None:
                content["initialUserMessage"] = hook_specific.initialUserMessage
            if hook_specific.watchPaths is not None:
                content["watchPaths"] = hook_specific.watchPaths
            if content:
                result.content = content
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_setup_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, SetupHookSpecificOutput):
            if hook_specific.additionalContext is not None:
                result.content = {"additionalContext": hook_specific.additionalContext}
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_notification_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, NotificationHookSpecificOutput):
            if hook_specific.additionalContext is not None:
                result.content = {"additionalContext": hook_specific.additionalContext}
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _apply_file_changed_output(self, result: HookDispatchResult, output: SyncHookJSONOutput) -> None:
        hook_specific = output.hookSpecificOutput
        if hook_specific is not None and isinstance(hook_specific, FileChangedHookSpecificOutput):
            result.content = {"watchPaths": hook_specific.watchPaths} if hook_specific.watchPaths is not None else None
            return
        if output.continue_ is False or output.decision == "block":
            result.continue_ = False
            result.stop_reason = self._output_message(output)

    def _execution_message(self, event: str, execution: HookExecutionRecord) -> str:
        detail = execution.stderr.strip() or execution.stdout.strip()
        if detail:
            return detail
        return f"{event} hook failed"

    def _output_message(self, output: SyncHookJSONOutput) -> str:
        return output.stopReason or output.systemMessage or output.reason or "Hook blocked execution"

    def _base_input(self, cwd: str, permission_mode: str | None) -> dict[str, Any]:
        return {
            "session_id": self.default_session_id,
            "transcript_path": self.default_transcript_path,
            "cwd": cwd,
            "permission_mode": permission_mode,
        }
