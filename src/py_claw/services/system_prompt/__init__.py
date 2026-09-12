"""Default system prompt builder.

Upstream Claude Code never sends a bare user message: every request carries an
identity block, environment context, and tool-usage guidance. py-claw mirrors
that so OpenAI-compatible backends behave like an agentic coding harness
instead of a stateless chat model.
"""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from py_claw.utils.claude_md.service import load_claude_md_files

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState

_IDENTITY = """\
You are py-claw, a CLI-based agentic coding assistant modeled on Claude Code's
behavior. You help the user with software engineering tasks: reading and
editing code, running shell commands, and answering questions about their
project. You operate inside the user's terminal session; be concise, factual,
and action-oriented. When the user asks you to change something, prefer
performing the change with your tools over describing it."""

_TOOL_GUIDANCE = """\
# Tool use

- You have access to the tools listed in this request. Use them whenever they
  are the right way to gather information or make a change; do not ask the
  user to run commands for you.
- Call a tool only when its result is needed to make progress. When a tool
  result already contains the information you asked for, act on it and produce
  a final answer — never repeat a call with identical arguments.
- After using tools, summarize the outcome briefly. If a task cannot be
  completed, explain what failed and why instead of retrying blindly."""


def _environment_block(state: RuntimeState) -> str:
    cwd = state.cwd or "<unknown>"
    dirs_note = "Working directory is part of the user's project tree."
    return "\n".join(
        [
            "# Environment",
            f"- Working directory: {cwd}",
            f"- Is a git repository: {'yes' if _is_git_repo(cwd) else 'no'}",
            f"- Platform: {platform.system()} ({platform.release()})",
            f"- Today's date: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d')}",
            f"- {dirs_note}",
        ]
    )


def _is_git_repo(cwd: str) -> bool:
    import os

    probe = cwd
    for _ in range(32):
        if os.path.isdir(os.path.join(probe, ".git")):
            return True
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent
    return False


def _claude_md_block(state: RuntimeState) -> str:
    """Project/user CLAUDE.md instructions, if any."""
    try:
        result = load_claude_md_files(cwd=state.cwd)
    except Exception:
        return ""
    content = result.combined_content.strip()
    if not content:
        return ""
    limit = 40_000
    if len(content) > limit:
        content = content[:limit] + "\n... (truncated)"
    return f"# CLAUDE.md project instructions\n\nThe user has added instructions for working in this project. Follow them.\n\n{content}"


def build_default_system_prompt(state: RuntimeState) -> str:
    """Compose the default system prompt for turns without an explicit one."""
    sections = [_IDENTITY, _TOOL_GUIDANCE, _environment_block(state)]
    claude_md = _claude_md_block(state)
    if claude_md:
        sections.append(claude_md)
    return "\n\n".join(section for section in sections if section)


def is_default_system_prompt_enabled(state: RuntimeState) -> bool:
    """Allow opting out via settings flag or env for SDK parity experiments."""
    import os

    if os.environ.get("PY_CLAW_DISABLE_DEFAULT_SYSTEM_PROMPT"):
        return False
    extra = getattr(state, "flag_settings", None) or {}
    return not extra.get("DISABLE_DEFAULT_SYSTEM_PROMPT", False)
