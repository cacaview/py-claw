from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from py_claw.schemas.common import AgentDefinition, EffortLevel, PyClawBaseModel
from py_claw.skills import get_local_skill, render_skill_prompt
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


class SkillToolInput(PyClawBaseModel):
    skill: str = Field(description="The skill name. E.g., 'commit', 'review-pr', or 'pdf'")
    args: str | None = Field(default=None, description="Optional arguments for the skill")
    execution: str | None = Field(
        default=None,
        description="Execution mode: 'inline' (default), 'fork' (subagent), or 'remote' (experimental)",
    )


class SkillToolResultInline(PyClawBaseModel):
    success: bool = True
    commandName: str
    source: str | None = None
    argumentHint: str | None = None
    allowedTools: list[str] | None = None
    model: str | None = None
    effort: EffortLevel | None = None
    status: str = "inline"
    prompt: str


class SkillToolResultForked(PyClawBaseModel):
    success: bool = True
    commandName: str
    source: str | None = None
    status: str = "forked"
    agent_id: str | None = None
    result: str | None = None


class SkillTool:
    definition = ToolDefinition(name="Skill", input_model=SkillToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("skill")
        normalized = str(value).strip().lstrip("/") if isinstance(value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=normalized or None)

    def execute(self, arguments: SkillToolInput, *, cwd: str) -> dict[str, object]:
        skill_name = arguments.skill.strip().lstrip("/")
        if not skill_name:
            raise ToolError("Skill name cannot be empty")

        skill = get_local_skill(skill_name, cwd=cwd)
        if skill is None:
            raise ToolError(f"Unknown skill: {skill_name}")
        if skill.disable_model_invocation:
            raise ToolError(f"Skill is disabled for model invocation: {skill_name}")

        prompt = render_skill_prompt(skill, arguments.args)

        # Forked execution: spawn a sub-agent (if runtime state available and fork requested)
        execution = (arguments.execution or "inline").strip().lower()
        if execution == "fork" and self._state is not None:
            return self._execute_forked(skill_name, prompt, arguments, cwd)

        # Inline execution: return skill prompt for current turn
        return {
            "success": True,
            "commandName": skill.name,
            "source": skill.source,
            "argumentHint": skill.argument_hint,
            "allowedTools": skill.allowed_tools,
            "model": skill.model,
            "effort": skill.effort,
            "status": "inline",
            "prompt": prompt,
        }

    def _execute_forked(
        self,
        skill_name: str,
        prompt: str,
        arguments: SkillToolInput,
        cwd: str,
    ) -> dict[str, object]:
        """Execute a skill in a forked subagent context.

        Runs the skill prompt in an isolated agent session with its own backend.
        """
        from uuid import uuid4

        from py_claw.query.backend import PlaceholderQueryBackend
        from py_claw.query.engine import PreparedTurn, QueryTurnContext

        if self._state is None:
            raise ToolError("Forked skill execution requires runtime state")

        state = self._state
        backend = state.query_backend if state.query_backend is not None else PlaceholderQueryBackend()
        agent_id = f"skill-{uuid4().hex[:8]}"

        # Prepare turn
        prepared = PreparedTurn(
            query_text=prompt,
            should_query=True,
            model=None,
            system_prompt=f"You are executing the skill: {skill_name}",
        )
        context = QueryTurnContext(
            state=state,
            session_id=f"agent-session-{uuid4()}",
            transcript=[],
            turn_count=0,
        )

        # Execute
        try:
            result = backend.run_turn(prepared, context)
            return {
                "success": True,
                "commandName": skill_name,
                "source": None,
                "status": "forked",
                "agent_id": agent_id,
                "result": result.assistant_text,
            }
        except Exception as exc:
            return {
                "success": False,
                "commandName": skill_name,
                "source": None,
                "status": "forked",
                "agent_id": agent_id,
                "result": f"Skill execution failed: {exc}",
            }
