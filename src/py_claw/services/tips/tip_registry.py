"""
Tip registry - contains all built-in tips and custom tip loading.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

from .types import Tip, TipContext

if TYPE_CHECKING:
    pass


# External tips that can be shown to all users
EXTERNAL_TIPS: list[Tip] = [
    Tip(
        id="new-user-warmup",
        content="Start with small features or bug fixes, tell Claude to propose a plan, and verify its suggested edits",
        cooldown_sessions=3,
        is_relevant=lambda _: True,  # Simplified: would check numStartups < 10
    ),
    Tip(
        id="plan-mode-for-complex-tasks",
        content="Use Plan Mode to prepare for a complex request before making changes. Press Shift+Tab twice to enable.",
        cooldown_sessions=5,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="default-permission-mode-config",
        content="Use /config to change your default permission mode (including Plan Mode)",
        cooldown_sessions=10,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="git-worktrees",
        content="Use git worktrees to run multiple Claude sessions in parallel.",
        cooldown_sessions=10,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="color-when-multi-clauding",
        content="Running multiple Claude sessions? Use /color and /rename to tell them apart at a glance.",
        cooldown_sessions=10,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="terminal-setup",
        content="Run /terminal-setup to enable convenient terminal integration like Shift+Enter for new line and more",
        cooldown_sessions=10,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="shift-enter",
        content="Press Shift+Enter to send a multi-line message",
        cooldown_sessions=10,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="memory-command",
        content="Use /memory to view and manage Claude memory",
        cooldown_sessions=15,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="theme-command",
        content="Use /theme to change the color theme",
        cooldown_sessions=20,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="status-line",
        content="Use /statusline to set up a custom status line that will display beneath the input box",
        cooldown_sessions=25,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="prompt-queue",
        content="Hit Enter to queue up additional messages while Claude is working.",
        cooldown_sessions=5,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="continue",
        content="Run claude --continue or claude --resume to resume a conversation",
        cooldown_sessions=10,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="rename-conversation",
        content="Name your conversations with /rename to find them easily in /resume later",
        cooldown_sessions=15,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="custom-commands",
        content="Create skills by adding .md files to .claude/skills/ in your project or ~/.claude/skills/ for skills that work in any project",
        cooldown_sessions=15,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="shift-tab",
        content='Hit Shift+Tab to cycle between default mode, auto-accept edit mode, and plan mode',
        cooldown_sessions=10,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="custom-agents",
        content="Use /agents to optimize specific tasks. Eg. Software Architect, Code Writer, Code Reviewer",
        cooldown_sessions=15,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="agent-flag",
        content="Use --agent <agent_name> to directly start a conversation with a subagent",
        cooldown_sessions=15,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="desktop-app",
        content="Run Claude Code locally or remotely using the Claude desktop app: clau.de/desktop",
        cooldown_sessions=15,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="web-app",
        content="Run tasks in the cloud while you keep coding locally · clau.de/web",
        cooldown_sessions=15,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="mobile-app",
        content="/mobile to use Claude Code from the Claude app on your phone",
        cooldown_sessions=15,
        is_relevant=lambda _: True,
    ),
    Tip(
        id="feedback-command",
        content="Use /feedback to help us improve!",
        cooldown_sessions=15,
        is_relevant=lambda _: True,
    ),
]


def get_external_tips() -> list[Tip]:
    """Get all external tips available to users."""
    return EXTERNAL_TIPS.copy()


async def get_relevant_tips(context: TipContext | None = None) -> list[Tip]:
    """
    Get tips that are relevant given the current context.

    Args:
        context: Optional context information for determining relevance

    Returns:
        List of tips that are relevant and ready to be shown
    """
    tips = get_external_tips()

    # Filter by relevance
    relevant_tips = []
    for tip in tips:
        is_relevant = tip.is_relevant(context)
        if is_relevant:
            relevant_tips.append(tip)

    return relevant_tips
