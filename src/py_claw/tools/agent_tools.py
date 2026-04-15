from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import Field, model_validator

from py_claw.query.backend import PlaceholderQueryBackend, QueryBackend
from py_claw.query.engine import PreparedTurn, QueryTurnContext
from py_claw.schemas.common import AgentDefinition, PyClawBaseModel
from py_claw.services.agent_registry import get_builtin_agent
from py_claw.settings.loader import get_settings_with_sources
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState
    from py_claw.tasks import LocalAgentSession


GENERAL_PURPOSE_AGENT_TYPE = "general-purpose"


@dataclass(slots=True)
class AgentExecutionResult:
    assistant_text: str
    usage: dict[str, object] = field(default_factory=dict)
    model_usage: dict[str, object] = field(default_factory=dict)
    backend_type: str = "placeholder"


@dataclass(frozen=True, slots=True)
class ForkSubagentOptions:
    """Options for forked subprocess execution."""
    enabled: bool = False
    inherit_transcript: bool = True
    isolation: str | None = None


@dataclass(frozen=True, slots=True)
class AgentWorktreeInfo:
    worktree_path: str
    worktree_branch: str | None = None
    repo_root: str | None = None
    original_head_commit: str | None = None


class AgentToolInput(PyClawBaseModel):
    description: str
    prompt: str
    subagent_type: str | None = None
    model: str | None = None
    run_in_background: bool = False
    isolation: str | None = None
    name: str | None = None
    team_name: str | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> AgentToolInput:
        if not self.description.strip():
            raise ValueError("description must not be empty")
        if not self.prompt.strip():
            raise ValueError("prompt must not be empty")
        if self.subagent_type is not None and not self.subagent_type.strip():
            raise ValueError("subagent_type must not be empty")
        if self.isolation is not None and self.isolation not in ("worktree", "remote"):
            raise ValueError('isolation must be "worktree" or "remote" when provided')
        if self.name is not None and not self.name.strip():
            raise ValueError("name must not be empty when provided")
        return self


class SendMessageToolInput(PyClawBaseModel):
    to: str
    summary: str | None = None
    message: str | dict[str, Any]

    @model_validator(mode="after")
    def validate_fields(self) -> SendMessageToolInput:
        if not self.to.strip():
            raise ValueError("to must not be empty")
        if isinstance(self.message, str):
            if not self.message.strip():
                raise ValueError("message must not be empty")
            if self.summary is None or not self.summary.strip():
                raise ValueError("summary is required when message is a string")
        elif not self.message:
            raise ValueError("message must not be empty")
        return self


class TeamCreateToolInput(PyClawBaseModel):
    team_name: str
    description: str | None = None
    leader_name: str | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> TeamCreateToolInput:
        if not self.team_name.strip():
            raise ValueError("team_name must not be empty")
        if self.leader_name is not None and not self.leader_name.strip():
            raise ValueError("leader_name must not be empty when provided")
        return self


class TeamDeleteToolInput(PyClawBaseModel):
    team_name: str

    @model_validator(mode="after")
    def validate_fields(self) -> TeamDeleteToolInput:
        if not self.team_name.strip():
            raise ValueError("team_name must not be empty")
        return self


class TeamCreateTool:
    definition = ToolDefinition(name="TeamCreate", input_model=TeamCreateToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("team_name")
        return ToolPermissionTarget(tool_name=self.definition.name, content=str(value) if isinstance(value, str) else None)

    def execute(self, arguments: TeamCreateToolInput, *, cwd: str) -> dict[str, object]:
        state = _require_state(self._state, self.definition.name)
        team_name = arguments.team_name.strip()
        leader_name = arguments.leader_name.strip() if isinstance(arguments.leader_name, str) and arguments.leader_name.strip() else None
        team = state.task_runtime.create_team(
            team_name,
            description=arguments.description.strip() if isinstance(arguments.description, str) and arguments.description.strip() else None,
            leader_name=leader_name,
        )
        return {
            "success": True,
            "team_name": team.team_name,
            "description": team.description,
            "leader_name": leader_name,
            "member_count": len(team.member_agent_ids),
        }


class TeamDeleteTool:
    definition = ToolDefinition(name="TeamDelete", input_model=TeamDeleteToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("team_name")
        return ToolPermissionTarget(tool_name=self.definition.name, content=str(value) if isinstance(value, str) else None)

    def execute(self, arguments: TeamDeleteToolInput, *, cwd: str) -> dict[str, object]:
        state = _require_state(self._state, self.definition.name)
        team_name = arguments.team_name.strip()
        team = state.task_runtime.delete_team(team_name)
        return {"success": True, "team_name": team.team_name}


class AgentTool:
    definition = ToolDefinition(name="Agent", input_model=AgentToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        parts: list[str] = []
        subagent_type = payload.get("subagent_type")
        if isinstance(subagent_type, str) and subagent_type.strip():
            parts.append(f"type:{subagent_type.strip()}")
        description = payload.get("description")
        if isinstance(description, str) and description.strip():
            parts.append(description.strip())
        return ToolPermissionTarget(tool_name=self.definition.name, content=" | ".join(parts) if parts else None)

    def execute(self, arguments: AgentToolInput, *, cwd: str) -> dict[str, object]:
        state = _require_state(self._state, self.definition.name)
        definition, resolved_type = _resolve_agent_definition(state, arguments, cwd)

        fork_enabled = bool(state.flag_settings.get("FORK_SUBAGENT", False))
        fork_options = ForkSubagentOptions(
            enabled=fork_enabled,
            isolation=arguments.isolation,
        )

        # Handle worktree isolation
        worktree_info: AgentWorktreeInfo | None = None
        effective_cwd = cwd
        isolation_context: dict[str, Any] | None = None
        if arguments.isolation == "worktree":
            worktree_info = _create_agent_worktree(state, arguments.description)
            effective_cwd = worktree_info.worktree_path
            isolation_context = {
                "parent_cwd": cwd,
                "worktree_cwd": worktree_info.worktree_path,
                "persistent": spawn_subagent,
            }

        try:
            is_teammate = arguments.name is not None
            spawn_subagent = fork_enabled and (arguments.run_in_background or is_teammate)

            if spawn_subagent:
                # Spawn persistent forked subprocess (subprocess handles initial turn)
                message = (
                    "py-claw launched a persistent forked subagent in an isolated subprocess. "
                    "The agent executed via the placeholder backend. "
                    "Teammate routing is now functional. "
                    "MCP-isolated agent runtimes, transcript recording, and skill preloading are not yet implemented."
                )
                session = state.task_runtime.create_agent_session(
                    agent_name=resolved_type,
                    description=arguments.description.strip(),
                    cwd=effective_cwd,
                    system_prompt=definition.prompt,
                    initial_prompt=arguments.prompt,
                    assistant_text="[Agent is initializing...]",
                    model=arguments.model or definition.model,
                    allowed_tools=list(definition.tools or []),
                    backend_type="forked",
                    name=arguments.name,
                    team_name=arguments.team_name.strip() if isinstance(arguments.team_name, str) and arguments.team_name.strip() else None,
                    spawn_subagent=True,
                    mcp_servers=definition.mcpServers,
                    isolation=isolation_context,
                )
                if session.team_name is not None:
                    state.task_runtime.register_team_member(session.team_name, session.agent_id, member_name=session.name)
                    state.query_runtime.save_session_state(session.agent_id)
                # Get result from the initial turn that already ran inside subprocess
                result_assistant_text = (
                    session.exchanges[-1].assistant_text if session.exchanges else "[No response]"
                )
                result: dict[str, object] = {
                    "agent_id": session.agent_id,
                    "agentType": resolved_type,
                    "status": "teammate_spawned" if is_teammate else "background_ready",
                    "task_id": session.task_id,
                    "output_file": session.output_file,
                    "message": message,
                    "result": result_assistant_text,
                    "usage": {},
                    "modelUsage": {},
                }
                if is_teammate and session.name:
                    result["teammate_id"] = session.agent_id
                    result["name"] = session.name
                if worktree_info is not None:
                    result["worktreePath"] = worktree_info.worktree_path
                    result["worktreeBranch"] = worktree_info.worktree_branch
                return result

            # Non-forked / foreground path
            execution = _run_agent_execution(
                state,
                definition=definition,
                prompt=arguments.prompt,
                model_override=arguments.model,
                fork_options=fork_options,
            )
            message = (
                "py-claw launched a local degraded agent session using the current query backend. "
                "This agent runs via the local placeholder/runtime backend. "
                "Full Claude Code subagent orchestration, teammate routing, and MCP-isolated agent runtimes are not implemented yet. "
                "The agent result is returned directly in this response."
            )
            if arguments.run_in_background or is_teammate:
                session = state.task_runtime.create_agent_session(
                    agent_name=resolved_type,
                    description=arguments.description.strip(),
                    cwd=effective_cwd,
                    system_prompt=definition.prompt,
                    initial_prompt=arguments.prompt,
                    assistant_text=execution.assistant_text,
                    model=arguments.model or definition.model,
                    allowed_tools=list(definition.tools or []),
                    backend_type=execution.backend_type,
                    name=arguments.name,
                    team_name=arguments.team_name.strip() if isinstance(arguments.team_name, str) and arguments.team_name.strip() else None,
                    isolation=isolation_context,
                )
                if session.team_name is not None:
                    state.task_runtime.register_team_member(session.team_name, session.agent_id, member_name=session.name)
                    state.query_runtime.save_session_state(session.agent_id)
                result = {
                    "agent_id": session.agent_id,
                    "agentType": resolved_type,
                    "status": "teammate_spawned" if is_teammate else "background_ready",
                    "task_id": session.task_id,
                    "output_file": session.output_file,
                    "message": message,
                    "result": execution.assistant_text,
                    "usage": execution.usage,
                    "modelUsage": execution.model_usage,
                }
                if is_teammate and session.name:
                    result["teammate_id"] = session.agent_id
                    result["name"] = session.name
                if worktree_info is not None:
                    result["worktreePath"] = worktree_info.worktree_path
                    result["worktreeBranch"] = worktree_info.worktree_branch
                return result
            return {
                "agentType": resolved_type,
                "status": "completed",
                "message": message,
                "result": execution.assistant_text,
                "usage": execution.usage,
                "modelUsage": execution.model_usage,
                **({"worktreePath": worktree_info.worktree_path, "worktreeBranch": worktree_info.worktree_branch} if worktree_info else {}),
            }
        finally:
            # Clean up worktree after agent completes (unless background - cleanup happens on exit)
            if worktree_info is not None and not arguments.run_in_background:
                _cleanup_agent_worktree(worktree_info)


class SendMessageTool:
    definition = ToolDefinition(name="SendMessage", input_model=SendMessageToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        recipient = payload.get("to")
        summary = payload.get("summary")
        parts: list[str] = []
        if isinstance(recipient, str) and recipient.strip():
            parts.append(f"to:{recipient.strip()}")
        if isinstance(summary, str) and summary.strip():
            parts.append(f"summary:{summary.strip()}")
        return ToolPermissionTarget(tool_name=self.definition.name, content=" | ".join(parts) if parts else None)

    def execute(self, arguments: SendMessageToolInput, *, cwd: str) -> dict[str, object]:
        state = _require_state(self._state, self.definition.name)
        session = state.task_runtime.resolve_agent_session(arguments.to.strip())
        rendered_message = _render_send_message(arguments.message)

        # Check if this session has a persistent forked subprocess
        forked_process = state.task_runtime.get_forked_process(session.agent_id)
        assistant_text: str
        usage: dict[str, object] = {}
        model_usage: dict[str, object] = {}

        if forked_process is not None and forked_process.is_running:
            # Use persistent forked subprocess for this turn
            turn_count = len(session.exchanges)
            try:
                result = forked_process.send_turn_sync(rendered_message, turn_count, timeout=120.0)
                assistant_text = result.get("assistant_text", "")
                usage = result.get("usage", {})
                model_usage = result.get("model_usage", {})
            except RuntimeError as exc:
                assistant_text = f"[Subprocess error: {exc}]"
        else:
            # Fall back to non-forked execution
            execution = _run_agent_execution(
                state,
                definition=_session_definition(session),
                prompt=rendered_message,
                model_override=session.model,
            )
            assistant_text = execution.assistant_text
            usage = execution.usage
            model_usage = execution.model_usage

        state.task_runtime.append_agent_exchange(
            session.agent_id,
            summary=arguments.summary,
            user_message=rendered_message,
            assistant_text=assistant_text,
        )
        return {
            "sent": True,
            "recipient": session.agent_id,
            "agentType": session.agent_name,
            "task_id": session.task_id,
            "output_file": session.output_file,
            "message": rendered_message,
            "summary": arguments.summary,
            "result": assistant_text,
            "usage": usage,
            "modelUsage": model_usage,
        }


def _create_agent_worktree(state: "RuntimeState", description: str) -> AgentWorktreeInfo:
    """Create a temporary git worktree for agent isolation.

    Returns an AgentWorktreeInfo with the worktree path and metadata.
    Raises ToolError if worktree creation fails.
    """
    slug = f"agent-{uuid4().hex[:8]}"
    original_cwd = state.cwd
    repo_root = _git_repo_root(original_cwd)

    if repo_root is not None:
        root_path = Path(repo_root)
        worktree_dir = (root_path / ".claude" / "worktrees" / slug).resolve()
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)
        worktree_branch = f"worktree/{slug.replace('/', '-')}"
        original_head_commit = _git_head_commit(repo_root)

        completed = subprocess.run(
            ["git", "-C", repo_root, "worktree", "add", "-b", worktree_branch, str(worktree_dir), "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "git worktree add failed"
            raise ToolError(f"Failed to create worktree: {detail}")

        return AgentWorktreeInfo(
            worktree_path=str(worktree_dir),
            worktree_branch=worktree_branch,
            repo_root=repo_root,
            original_head_commit=original_head_commit,
        )
    else:
        # Non-git directory: create a simple isolated directory
        worktree_dir = (Path(original_cwd) / ".claude" / "worktrees" / slug).resolve()
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)
        return AgentWorktreeInfo(
            worktree_path=str(worktree_dir),
            worktree_branch=None,
            repo_root=None,
            original_head_commit=None,
        )


def _cleanup_agent_worktree(worktree_info: AgentWorktreeInfo) -> None:
    """Clean up a temporary agent worktree."""
    if worktree_info.repo_root is not None and worktree_info.worktree_branch is not None:
        # Remove git worktree
        subprocess.run(
            ["git", "-C", worktree_info.repo_root, "worktree", "remove", worktree_info.worktree_path],
            capture_output=True,
            text=True,
            check=False,
        )
        # Delete the branch
        subprocess.run(
            ["git", "-C", worktree_info.repo_root, "branch", "-D", worktree_info.worktree_branch],
            capture_output=True,
            text=True,
            check=False,
        )
    # Clean up directory
    worktree_path = Path(worktree_info.worktree_path)
    if worktree_path.exists():
        shutil.rmtree(worktree_path, ignore_errors=True)


def _git_repo_root(cwd: str) -> str | None:
    """Find the git repository root for a given directory."""
    completed = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    root = completed.stdout.strip()
    return str(Path(root).resolve()) if root else None


def _git_head_commit(cwd: str) -> str | None:
    """Get the current HEAD commit hash."""
    completed = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit or None


def _require_state(state: RuntimeState | None, tool_name: str) -> RuntimeState:
    if state is None:
        raise ToolError(f"{tool_name} requires runtime state")
    return state


def _resolve_agent_definition(state: RuntimeState, arguments: AgentToolInput, cwd: str) -> tuple[AgentDefinition, str]:
    settings = get_settings_with_sources(
        flag_settings=state.flag_settings,
        policy_settings=state.policy_settings,
        cwd=state.cwd,
        home_dir=state.home_dir,
    )
    configured = state.effective_agent_definitions(settings.effective.get("agents"))
    requested_type = arguments.subagent_type.strip() if arguments.subagent_type is not None else None
    if requested_type is not None:
        # First check configured agents
        definition = configured.get(requested_type)
        if definition is not None:
            return definition, requested_type
        # Then check built-in agents
        builtin = get_builtin_agent(requested_type)
        if builtin is not None and builtin.enabled:
            return (
                AgentDefinition(
                    description=builtin.description,
                    prompt=builtin.prompt,
                    tools=builtin.tools,
                    disallowedTools=builtin.disallowed_tools,
                    model=arguments.model or builtin.model,
                ),
                requested_type,
            )
        available = ", ".join(sorted(set(list(configured.keys()) + ["general-purpose", "Explore", "Plan"]))) or "none"
        raise ToolError(f'Unknown agent type: {requested_type}. Available agent types: {available}')
    ephemeral_type = _ephemeral_agent_name(arguments.description)
    return (
        AgentDefinition(
            description=arguments.description.strip(),
            prompt="You are a local py-claw subagent. This session uses the current runtime backend. "
            "Full Claude Code subagent features (teammate routing, MCP isolation) are not available.",
            model=arguments.model,
        ),
        ephemeral_type,
    )


def _ephemeral_agent_name(description: str) -> str:
    normalized = "-".join(part for part in description.lower().split() if part)
    return normalized or "agent"


def _session_definition(session: LocalAgentSession) -> AgentDefinition:
    return AgentDefinition(
        description=session.description,
        prompt=session.system_prompt,
        model=session.model,
        tools=list(session.allowed_tools or []),
    )


def _run_agent_execution(
    state: RuntimeState,
    *,
    definition: AgentDefinition,
    prompt: str,
    model_override: str | None,
    fork_options: ForkSubagentOptions | None = None,
) -> AgentExecutionResult:
    fork_enabled = (
        fork_options is not None
        and fork_options.enabled
        and bool(state.flag_settings.get("FORK_SUBAGENT", False))
    )
    if fork_enabled:
        return _run_forked_agent_execution(state, definition, prompt, model_override, fork_options)

    backend = _select_backend(state)
    prepared = PreparedTurn(
        query_text=prompt,
        should_query=True,
        model=model_override or definition.model,
        allowed_tools=list(definition.tools or []) or None,
        system_prompt=definition.prompt,
    )
    context = QueryTurnContext(
        state=state,
        session_id=f"agent-session-{uuid4()}",
        transcript=[],
        turn_count=0,
    )
    result = backend.run_turn(prepared, context)
    return AgentExecutionResult(
        assistant_text=result.assistant_text,
        usage=dict(result.usage),
        model_usage=dict(result.model_usage),
        backend_type=str(result.usage.get("backendType", "placeholder")),
    )


def _run_forked_agent_execution(
    state: RuntimeState,
    *,
    definition: AgentDefinition,
    prompt: str,
    model_override: str | None,
    fork_options: ForkSubagentOptions,
) -> AgentExecutionResult:
    """Execute agent in a forked subprocess via ForkedAgentBackend."""
    from py_claw.fork.backend import ForkedAgentBackend

    backend = ForkedAgentBackend()
    try:
        prepared = PreparedTurn(
            query_text=prompt,
            should_query=True,
            model=model_override or definition.model,
            allowed_tools=list(definition.tools or []) or None,
            system_prompt=definition.prompt,
        )
        context = QueryTurnContext(
            state=state,
            session_id=f"agent-session-{uuid4()}",
            transcript=[],
            turn_count=0,
        )
        result = backend.run_turn(prepared, context)
        return AgentExecutionResult(
            assistant_text=result.assistant_text,
            usage=dict(result.usage),
            model_usage=dict(result.model_usage),
            backend_type="forked",
        )
    finally:
        backend.close()


def _select_backend(state: RuntimeState) -> QueryBackend:
    query_runtime = state.query_runtime
    if query_runtime is not None:
        backend = query_runtime.runtime_turn_executor.backend
        if backend is not None:
            return backend
    if state.query_backend is not None:
        return state.query_backend
    return PlaceholderQueryBackend()


def _render_send_message(message: str | dict[str, Any]) -> str:
    if isinstance(message, str):
        return message.strip()
    return json.dumps(message, ensure_ascii=False, sort_keys=True)
