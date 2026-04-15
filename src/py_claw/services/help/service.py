"""
Help service for displaying help and documentation.
"""
from __future__ import annotations

import logging
from typing import Any

from .types import HelpCategory, HelpConfig, HelpTopic

logger = logging.getLogger(__name__)

_help_config = HelpConfig()


def get_help_config() -> HelpConfig:
    """Get the help configuration."""
    return _help_config


def get_help_categories() -> list[HelpCategory]:
    """Get all help categories.

    Returns:
        List of HelpCategory objects
    """
    return [
        HelpCategory(
            name="Getting Started",
            description="Learn the basics of Claude Code",
            topics=[
                HelpTopic(
                    id="introduction",
                    title="Introduction to Claude Code",
                    content="""Claude Code is an AI coding assistant that helps you write, review, and debug code.

Key features:
- Natural language programming
- Multi-file editing
- Git integration
- Terminal access
- MCP (Model Context Protocol) tools

To get started, just describe what you want to build in plain English.""",
                ),
                HelpTopic(
                    id="first-steps",
                    title="Your First Session",
                    content="""1. Start a conversation by describing a task
2. Claude will propose code changes
3. Review and approve changes
4. Use /help to see available commands

Commands start with / (e.g., /help, /compact, /doctor)""",
                ),
            ],
        ),
        HelpCategory(
            name="Commands",
            description="Slash commands available in Claude Code",
            topics=[
                HelpTopic(
                    id="slash-commands",
                    title="Using Slash Commands",
                    content="""Slash commands provide quick access to features.

Common commands:
- /help - Show this help
- /compact - Reduce context size
- /doctor - Run diagnostics
- /model - Change AI model
- /permissions - Manage permissions

Type /help <command> for details on a specific command.""",
                    related_topics=["slash-commands"],
                ),
                HelpTopic(
                    id="keybindings",
                    title="Keyboard Shortcuts",
                    content="""Keyboard shortcuts for Claude Code:

Navigation:
- Ctrl+O - Open file
- Ctrl+P - Quick open
- Ctrl+Shift+P - Command palette

Editing:
- Ctrl+S - Save
- Ctrl+Z - Undo
- Ctrl+Y - Redo

Use /keybindings to customize shortcuts.""",
                    related_topics=["customization"],
                ),
            ],
        ),
        HelpCategory(
            name="Tools",
            description="Tools available during conversations",
            topics=[
                HelpTopic(
                    id="built-in-tools",
                    title="Built-in Tools",
                    content="""Claude Code provides several built-in tools:

File Operations:
- Read - Read file contents
- Edit - Make targeted changes
- Write - Create new files
- Glob - Find files by pattern
- Grep - Search file contents

System:
- Bash - Run shell commands
- WebSearch - Search the web
- WebFetch - Fetch web pages

Task Management:
- TodoWrite - Track tasks
- subtask - Create subtasks""",
                ),
            ],
        ),
        HelpCategory(
            name="Customization",
            description="Personalize Claude Code",
            topics=[
                HelpTopic(
                    id="settings",
                    title="Settings",
                    content="""Configure Claude Code via ~/.claude/settings.json

Key settings:
- model - Default AI model
- permissions - Tool permission rules
- autoCompact - Auto compact context
- color - UI color theme

Use /config to view and edit settings.""",
                    related_topics=["permissions", "themes"],
                ),
                HelpTopic(
                    id="permissions",
                    title="Permissions",
                    content="""Claude Code has a permission system for tools.

Permission modes:
- default - Ask for dangerous operations
- low - Allow most operations
- medium - Balanced security
- high - Require approval for all

Use /permissions to manage rules.""",
                    related_topics=["settings"],
                ),
            ],
        ),
        HelpCategory(
            name="Troubleshooting",
            description="Solve common issues",
            topics=[
                HelpTopic(
                    id="diagnostics",
                    title="Running Diagnostics",
                    content="""If you're having issues, run /doctor to check:

- Python version
- API key configuration
- Git installation
- Shell availability
- Configuration issues

This helps identify common problems.""",
                ),
                HelpTopic(
                    id="context-issues",
                    title="Context Issues",
                    content="""If Claude Code is running slow or hitting limits:

1. Use /compact to reduce context
2. Use /clear to start fresh
3. Break large tasks into smaller ones
4. Use /context to see context usage

Context is limited by model token limits.""",
                    related_topics=["compact"],
                ),
            ],
        ),
    ]


def get_topic(topic_id: str) -> HelpTopic | None:
    """Get a specific help topic by ID.

    Args:
        topic_id: The topic ID to look up

    Returns:
        HelpTopic if found, None otherwise
    """
    for category in get_help_categories():
        for topic in category.topics:
            if topic.id == topic_id:
                return topic
    return None


def search_help(query: str) -> list[HelpTopic]:
    """Search help topics.

    Args:
        query: Search query

    Returns:
        List of matching HelpTopic objects
    """
    query_lower = query.lower()
    results = []

    for category in get_help_categories():
        for topic in category.topics:
            if (query_lower in topic.title.lower() or
                query_lower in topic.content.lower()):
                results.append(topic)

    return results


def format_help_text(
    category: HelpCategory | None = None,
    topic: HelpTopic | None = None,
) -> str:
    """Format help content as plain text.

    Args:
        category: Optional specific category to show
        topic: Optional specific topic to show

    Returns:
        Formatted help text
    """
    if topic:
        lines = [
            f"## {topic.title}",
            "",
            topic.content,
        ]
        if topic.related_topics:
            lines.append("")
            lines.append("See also:")
            for related in topic.related_topics:
                lines.append(f"- /help {related}")
        return "\n".join(lines)

    if category:
        lines = [
            f"# {category.name}",
            "",
            category.description,
            "",
        ]
        for t in category.topics:
            lines.append(f"### {t.title}")
            lines.append("")
            # First 100 chars of content
            preview = t.content[:100].replace("\n", " ")
            lines.append(f"{preview}...")
            lines.append("")
        return "\n".join(lines)

    # Show all categories
    lines = [
        "Claude Code Help",
        "=" * 40,
        "",
        "Categories:",
    ]
    for cat in get_help_categories():
        lines.append(f"- {cat.name}: {cat.description}")
    lines.append("")
    lines.append("Use /help <category> or /help <topic> for more details.")
    return "\n".join(lines)
