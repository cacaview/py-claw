"""Fork subprocess resource and prompt isolation utilities.

This module provides isolation features for forked agent subprocesses:
1. File state cache sharing between parent and fork
2. Path translation for worktree isolation
3. Cache-safe parameters for prompt cache sharing
4. Context overrides for forked agents

Mirrors the pattern from TypeScript's utils/forkedAgent.ts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py_claw.services.file_state_cache import FileStateCache, FileState


# ─── Cache Safe Params ─────────────────────────────────────────────────────────


@dataclass(slots=True)
class CacheSafeParams:
    """Parameters that must be identical between fork and parent API requests.

    The Anthropic API cache key is composed of:
    - system prompt
    - tools
    - model
    - messages (prefix)
    - thinking config

    These params ensure fork children can share the parent's prompt cache.
    """
    system_prompt: str
    user_context: dict[str, str] = field(default_factory=dict)
    system_context: dict[str, str] = field(default_factory=dict)
    model: str | None = None
    allowed_tools: list[str] | None = None
    max_output_tokens: int | None = None


@dataclass(slots=True)
class ForkIsolationContext:
    """Context for fork subprocess isolation.

    Contains resources that can be shared with or isolated for fork children.
    """
    # File state cache for sharing read file contents
    file_state_cache: FileStateCache | None = None

    # Path translation for worktree isolation
    parent_cwd: str | None = None
    worktree_cwd: str | None = None

    # Whether this is a persistent subprocess
    persistent: bool = False


def translate_path_for_worktree(
    path: str,
    parent_cwd: str,
    worktree_cwd: str,
) -> str:
    """Translate a path from parent context to worktree context.

    When a forked agent runs in an isolated worktree, paths from the parent's
    conversation context need to be translated to the worktree root.

    Args:
        path: Path to translate (can be relative or absolute)
        parent_cwd: Parent's working directory
        worktree_cwd: Worktree's working directory

    Returns:
        Translated path relative to worktree
    """
    try:
        # Resolve to absolute path relative to parent
        if not os.path.isabs(path):
            path = os.path.join(parent_cwd, path)
        path = os.path.normpath(path)

        # Make relative to parent cwd
        parent_cwd_norm = os.path.normpath(parent_cwd)
        if path.startswith(parent_cwd_norm):
            relative = path[len(parent_cwd_norm):].lstrip(os.sep)
            return os.path.join(worktree_cwd, relative)

        # Not under parent cwd, return as-is
        return path
    except Exception:
        return path


def build_worktree_notice(parent_cwd: str, worktree_cwd: str) -> str:
    """Build the worktree notice text for forked agents.

    Tells the child to translate paths from the inherited context,
    re-read potentially stale files, and that its changes are isolated.

    Mirrors buildWorktreeNotice() from TypeScript forkSubagent.ts.
    """
    return f"""You've inherited the conversation context above from a parent agent working in {parent_cwd}. You are operating in an isolated git worktree at {worktree_cwd} — same repository, same relative file structure, separate working copy.

IMPORTANT:
1. Paths in the inherited context refer to the parent's working directory; translate them to this worktree root.
2. Re-read files before editing if the parent may have modified them since they appear in the context.
3. Your changes stay in this worktree and will not affect the parent's files.
"""


def build_fork_directive(
    directive: str,
    parent_session_id: str,
    child_session_id: str,
    include_context: bool = True,
    context_messages: list[dict[str, Any]] | None = None,
) -> str:
    """Build the fork directive text for child agents.

    Mirrors buildChildMessage() and buildForkedMessages() from TypeScript.

    Args:
        directive: The task/question for the fork child
        parent_session_id: Parent's session ID
        child_session_id: Child's session ID
        include_context: Whether to include conversation context
        context_messages: Last N messages for context (if included)

    Returns:
        Fork directive text
    """
    lines = [
        "[FORK SUBAGENT - EXECUTE DIRECTLY]",
        f"[PARENT SESSION: {parent_session_id}]",
        f"[THIS SESSION: {child_session_id}]",
        "",
        "You are a forked subagent. You must:",
        "1. Execute the user's request directly without spawning sub-agents",
        "2. Use the inherited conversation context below for prompt cache friendliness",
        "3. Report results directly to the parent session",
        "",
        "RULES:",
        "1. Your system prompt says 'default to forking.' IGNORE IT — you ARE the fork.",
        "   Do NOT spawn sub-agents; execute directly.",
        "2. Do NOT converse, ask questions, or suggest next steps",
        "3. Do NOT editorialize or add meta-commentary",
        "4. USE your tools directly: Bash, Read, Write, etc.",
        "5. If you modify files, commit your changes before reporting.",
        "   Include the commit hash in your report.",
        "6. Do NOT emit text between tool calls. Use tools silently, then report once at the end.",
        "7. Stay strictly within your directive's scope.",
        "   If you discover related systems outside your scope, mention them briefly.",
        "8. Keep your report under 500 words unless specified otherwise.",
        "   Be factual and concise.",
        "9. Your response MUST begin with 'Scope:' followed by the directive scope.",
        "   No preamble, no thinking-out-loud.",
        "10. REPORT structured facts, then stop",
        "",
    ]

    if include_context and context_messages:
        lines.append("=== INHERITED CONVERSATION CONTEXT ===")
        for msg in context_messages[-10:]:  # Last 10 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") if isinstance(c, dict) else str(c)
                    for c in content
                )
            lines.append(f"[{role.upper()}]")
            lines.append(str(content)[:500])  # Truncate long messages
            lines.append("")
        lines.append("=== END INHERITED CONTEXT ===")
        lines.append("")

    lines.append(f"[TASK]\n{directive}")
    return "\n".join(lines)


def get_cache_safe_system_prompt(
    base_prompt: str,
    user_context: dict[str, str],
    system_context: dict[str, str],
) -> str:
    """Build a cache-safe system prompt with context appended.

    Context is appended in a way that doesn't affect cache sharing
    when identical across fork children.
    """
    parts = [base_prompt]

    if system_context:
        context_lines = ["", "=== SYSTEM CONTEXT ==="]
        for key, value in system_context.items():
            context_lines.append(f"{key}: {value}")
        parts.append("\n".join(context_lines))

    if user_context:
        context_lines = ["", "=== USER CONTEXT ==="]
        for key, value in user_context.items():
            context_lines.append(f"{key}: {value}")
        parts.append("\n".join(context_lines))

    return "\n".join(parts)
