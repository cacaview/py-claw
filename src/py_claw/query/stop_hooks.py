"""Stop hooks for the query engine.

Runs after every model response, before the next user turn.
Based on ClaudeCode-main/src/query/stopHooks.ts pattern.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


@dataclass(slots=True)
class StopHookResult:
    """Result from running stop hooks."""
    blocking_errors: list[str] = field(default_factory=list)
    prevent_continuation: bool = False
    additional_context: str | None = None
    updated_input: str | None = None


def handle_stop_hooks(
    state: RuntimeState,
    *,
    session_id: str,
    last_assistant_message: str = "",
    subagent_id: str | None = None,
) -> StopHookResult:
    """Run stop hooks after model response.

    This is the synchronous entry point. It dispatches to the HookRuntime's
    Stop or SubagentStop event and processes the results.

    Args:
        state: Runtime state with hook_runtime
        session_id: Current session ID
        last_assistant_message: Text of the last assistant message
        subagent_id: If set, fires SubagentStop instead of Stop

    Returns:
        StopHookResult with blocking errors and continuation control
    """
    result = StopHookResult()

    hook_runtime = state.hook_runtime
    if hook_runtime is None:
        return result

    # Load settings for hook dispatch
    from py_claw.settings.loader import get_settings_with_sources
    settings_result = get_settings_with_sources(cwd=state.cwd, home_dir=state.home_dir)
    settings = settings_result.settings

    # Fire the appropriate stop hook
    if subagent_id:
        hook_result = hook_runtime.run_subagent_stop(
            settings=settings,
            cwd=state.cwd,
            agent_id=subagent_id,
            agent_type="subagent",
            agent_transcript_path="",
            stop_hook_active=False,
            last_assistant_message=last_assistant_message or None,
        )
    else:
        hook_result = hook_runtime.run_stop(
            settings=settings,
            cwd=state.cwd,
            stop_hook_active=False,
            last_assistant_message=last_assistant_message or None,
        )

    # Process hook results
    if hook_result is not None:
        # Check for blocking errors (exit code != 0 with no structured output)
        for execution in hook_result.executions:
            if execution.exit_code != 0 and execution.structured_output is None:
                stderr = execution.stderr.strip()
                if stderr:
                    result.blocking_errors.append(stderr)
                elif execution.stdout.strip():
                    result.blocking_errors.append(execution.stdout.strip())
                else:
                    result.blocking_errors.append(f"Stop hook failed (exit code {execution.exit_code})")

        # Check for continuation control
        if not hook_result.continue_:
            result.prevent_continuation = True

        # Check for additional context from structured output
        if hook_result.content is not None:
            additional = hook_result.content.get("additionalContext")
            if additional and isinstance(additional, str):
                result.additional_context = additional

    return result
