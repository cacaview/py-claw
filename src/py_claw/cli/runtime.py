from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol
import os
import threading

from py_claw.commands import CommandRegistry
from py_claw.hooks.runtime import HookRuntime
from py_claw.mcp.runtime import McpRuntime
from py_claw.schemas.common import AgentDefinition, PermissionMode
from py_claw.skills import DiscoveredSkill, discover_local_skills
from py_claw.tasks import TaskRuntime
from py_claw.tools.runtime import ToolRuntime
from py_claw.tools.todo_write_tool import TodoWriteTool
from py_claw.services.plugins import initialize_plugins

if TYPE_CHECKING:
    from py_claw.query.backend import QueryBackend


class QueryControl(Protocol):
    def interrupt(self) -> None: ...

    def cancel_async_message(self, message_uuid: str) -> bool: ...

    def save_session_state(self, session_id: str) -> None: ...

    def restore_session_state(self, session_id: str) -> bool: ...


@dataclass(slots=True)
class ActiveWorktreeSession:
    original_cwd: str
    worktree_path: str
    worktree_branch: str | None = None
    repo_root: str | None = None
    original_head_commit: str | None = None
    backend: Literal["git", "hook"] = "git"


@dataclass(slots=True)
class RuntimeState:
    cwd: str = field(default_factory=os.getcwd)
    home_dir: str | None = None
    permission_mode: PermissionMode = "default"
    model: str | None = None
    max_thinking_tokens: int | None = None
    include_partial_messages: bool = False
    interrupt_event: threading.Event = field(default_factory=threading.Event)
    query_runtime: QueryControl | None = None
    query_backend: QueryBackend | None = None
    initialized_agents: dict[str, AgentDefinition] = field(default_factory=dict)
    initialized_hooks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    sdk_mcp_servers: list[str] = field(default_factory=list)
    json_schema: dict[str, Any] | None = None
    system_prompt: str | None = None
    append_system_prompt: str | None = None
    prompt_suggestions: bool = False
    agent_progress_summaries: bool = False
    flag_settings: dict[str, Any] = field(default_factory=dict)
    policy_settings: dict[str, Any] = field(default_factory=dict)
    todos: list[dict[str, Any]] = field(default_factory=list)
    scheduled_cron_jobs: list[object] = field(default_factory=list)
    task_runtime: TaskRuntime = field(default_factory=TaskRuntime)
    tool_runtime: ToolRuntime | None = None
    hook_runtime: HookRuntime = field(default_factory=HookRuntime)
    mcp_runtime: McpRuntime = field(default_factory=McpRuntime)
    active_worktree_session: ActiveWorktreeSession | None = None
    advisor_model: str | None = None

    def __post_init__(self) -> None:
        if self.tool_runtime is None:
            self.tool_runtime = ToolRuntime(task_runtime=self.task_runtime)
        else:
            self.task_runtime = self.tool_runtime.task_runtime
        self.tool_runtime.set_state(self)
        self.set_initialized_agents(self.initialized_agents)
        initialize_plugins()

    def set_initialized_agents(self, agents: dict[str, AgentDefinition] | dict[str, dict] | None) -> None:
        normalized: dict[str, AgentDefinition] = {}
        for name, payload in (agents or {}).items():
            if isinstance(payload, AgentDefinition):
                normalized[name] = payload
                continue
            if isinstance(payload, dict):
                try:
                    normalized[name] = AgentDefinition.model_validate(payload)
                except Exception:
                    continue
        self.initialized_agents = normalized

    def clear_initialized_agents(self) -> None:
        self.initialized_agents = {}

    def apply_initialize_request(self, request: Any) -> None:
        self.set_initialized_agents(getattr(request, "agents", None))
        hooks = getattr(request, "hooks", None)
        self.initialized_hooks = hooks if isinstance(hooks, dict) else {}
        sdk_mcp_servers = getattr(request, "sdkMcpServers", None)
        self.sdk_mcp_servers = [str(name) for name in sdk_mcp_servers or [] if str(name).strip()]
        json_schema = getattr(request, "jsonSchema", None)
        self.json_schema = json_schema if isinstance(json_schema, dict) else None
        system_prompt = getattr(request, "systemPrompt", None)
        self.system_prompt = str(system_prompt) if isinstance(system_prompt, str) and system_prompt else None
        append_system_prompt = getattr(request, "appendSystemPrompt", None)
        self.append_system_prompt = (
            str(append_system_prompt) if isinstance(append_system_prompt, str) and append_system_prompt else None
        )
        self.prompt_suggestions = bool(getattr(request, "promptSuggestions", False))
        self.agent_progress_summaries = bool(getattr(request, "agentProgressSummaries", False))

    def effective_agent_definitions(self, settings_agents: dict[str, dict] | None) -> dict[str, AgentDefinition]:
        merged: dict[str, AgentDefinition] = {}
        for name, payload in (settings_agents or {}).items():
            if not isinstance(payload, dict):
                continue
            try:
                merged[name] = AgentDefinition.model_validate(payload)
            except Exception:
                continue
        merged.update(self.initialized_agents)
        return merged

    def build_agent_infos(self, settings_agents: dict[str, dict] | None) -> list[dict[str, str]]:
        agent_infos: list[dict[str, str]] = []
        for name, definition in sorted(self.effective_agent_definitions(settings_agents).items()):
            entry: dict[str, str] = {"name": name, "description": definition.description}
            if definition.model is not None:
                entry["model"] = str(definition.model)
            agent_infos.append(entry)
        return agent_infos

    def build_agent_usage(self, settings_agents: dict[str, dict] | None) -> list[dict[str, Any]]:
        configured_agents: dict[str, AgentDefinition] = {}
        for name, payload in (settings_agents or {}).items():
            if not isinstance(payload, dict):
                continue
            try:
                configured_agents[name] = AgentDefinition.model_validate(payload)
            except Exception:
                continue
        agent_names = sorted(set(configured_agents) | set(self.initialized_agents))
        return [
            {"agentType": name, "source": "session" if name in self.initialized_agents else "settings", "tokens": 0}
            for name in agent_names
        ]

    def discovered_skills(self, settings_skills: list[str] | None) -> list[DiscoveredSkill]:
        return discover_local_skills(cwd=self.cwd, home_dir=self.home_dir, settings_skills=settings_skills)

    def build_command_registry(self, settings_skills: list[str] | None) -> CommandRegistry:
        return CommandRegistry.build(skills=self.discovered_skills(settings_skills))

    def build_slash_commands(self, settings_skills: list[str] | None) -> list[dict[str, str]]:
        return self.build_command_registry(settings_skills).slash_commands()

    def build_slash_command_usage(self, settings_skills: list[str] | None) -> dict[str, int] | None:
        command_count = len(self.build_slash_commands(settings_skills))
        if command_count == 0:
            return None
        return {"totalCommands": command_count, "includedCommands": command_count, "tokens": 0}

    def build_skill_usage(self, settings_skills: list[str] | None) -> dict[str, Any] | None:
        resolved_skills = self.discovered_skills(settings_skills)
        if not resolved_skills:
            return None
        return {
            "totalSkills": len(resolved_skills),
            "includedSkills": len(resolved_skills),
            "tokens": 0,
            "skillFrontmatter": [
                {
                    "name": skill.name,
                    "source": skill.source,
                    "tokens": 0,
                    "argumentHint": skill.argument_hint or None,
                    "whenToUse": skill.when_to_use,
                    "version": skill.version,
                    "model": skill.model,
                    "allowedTools": list(skill.allowed_tools) if skill.allowed_tools else None,
                    "effort": str(skill.effort) if skill.effort is not None else None,
                    "userInvocable": skill.user_invocable,
                    "disableModelInvocation": skill.disable_model_invocation,
                }
                for skill in resolved_skills
            ],
        }

    def build_command_and_agent_catalog(
        self,
        *,
        settings_agents: dict[str, dict] | None,
        settings_skills: list[str] | None,
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        return self.build_slash_commands(settings_skills), self.build_agent_infos(settings_agents)
