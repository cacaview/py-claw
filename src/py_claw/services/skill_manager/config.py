"""
SkillManager configuration.

Manages built-in and custom skills.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Built-in skill definitions
BUILTIN_SKILL_DEFINITIONS = {
    "batch": {
        "description": "Execute multiple operations in batch",
        "argument_hint": "<operations>",
        "when_to_use": "When you need to run multiple commands or operations together",
        "source": "builtin",
    },
    "debug": {
        "description": "Debug code and identify issues",
        "argument_hint": "<code-or-issue>",
        "when_to_use": "When debugging code or identifying issues",
        "source": "builtin",
    },
    "simplify": {
        "description": "Simplify and refactor code",
        "argument_hint": "<code>",
        "when_to_use": "When code needs to be simplified or refactored",
        "source": "builtin",
    },
    "verify": {
        "description": "Verify code changes or functionality",
        "argument_hint": "<changes>",
        "when_to_use": "When verifying that changes work correctly",
        "source": "builtin",
    },
    "hunter": {
        "description": "Find and analyze bugs or issues in code",
        "argument_hint": "<pattern>",
        "when_to_use": "When hunting for bugs or specific patterns in code",
        "source": "builtin",
    },
    "remember": {
        "description": "Remember information for future sessions",
        "argument_hint": "<information>",
        "when_to_use": "When you want to save information for later",
        "source": "builtin",
    },
    "stuck": {
        "description": "Get help when stuck on a problem",
        "argument_hint": "<problem>",
        "when_to_use": "When you need help continuing with a difficult problem",
        "source": "builtin",
    },
    "skillify": {
        "description": "Convert a workflow into a reusable skill",
        "argument_hint": "<workflow>",
        "when_to_use": "When you want to save a workflow as a skill",
        "source": "builtin",
    },
    "update-config": {
        "description": "Update Claude Code configuration",
        "argument_hint": "<key=value>",
        "when_to_use": "When configuring Claude Code settings",
        "source": "builtin",
    },
    "keybindings": {
        "description": "Manage keyboard shortcuts",
        "argument_hint": "[action]",
        "when_to_use": "When managing keybindings",
        "source": "builtin",
    },
    "lorem-ipsum": {
        "description": "Generate placeholder text",
        "argument_hint": "[word-count]",
        "when_to_use": "When generating placeholder text for testing",
        "source": "builtin",
    },
    "schedule-remote-agents": {
        "description": "Schedule remote agents for background tasks",
        "argument_hint": "<task>",
        "when_to_use": "When scheduling background agent tasks",
        "source": "builtin",
    },
    "claude-in-chrome": {
        "description": "Interact with Claude in Chrome browser",
        "argument_hint": "<command>",
        "when_to_use": "When using Claude Chrome extension",
        "source": "builtin",
    },
    "dream": {
        "description": "Generate a dream consolidation for memory",
        "argument_hint": "[topic]",
        "when_to_use": "When consolidating memories and learnings",
        "source": "builtin",
    },
}


@dataclass(frozen=True)
class SkillDefinition:
    """A skill definition."""

    name: str
    description: str
    argument_hint: str = ""
    when_to_use: str | None = None
    source: str = "builtin"  # "builtin", "custom", "installed"
    version: str | None = None
    enabled: bool = True


@dataclass(frozen=True)
class SkillManagerConfig:
    """Configuration for SkillManager service."""

    enabled: bool = True
    # Enable built-in skills
    enable_builtin: bool = True
    # Enable custom skills from skills directory
    enable_custom: bool = True
    # Skills directory path
    skills_dir: str = ".claude/skills"
    # Default skill if none specified
    default_skill: str | None = None

    @classmethod
    def from_settings(cls, settings: dict) -> SkillManagerConfig:
        """Create config from settings dictionary."""
        sm_settings = settings.get("skillManager", {})
        return cls(
            enabled=sm_settings.get("enabled", True),
            enable_builtin=sm_settings.get("enableBuiltin", True),
            enable_custom=sm_settings.get("enableCustom", True),
            skills_dir=sm_settings.get("skillsDir", ".claude/skills"),
            default_skill=sm_settings.get("defaultSkill"),
        )


# Global config instance
_config: SkillManagerConfig | None = None


def get_skill_manager_config() -> SkillManagerConfig:
    """Get the current SkillManager configuration."""
    global _config
    if _config is None:
        _config = SkillManagerConfig()
    return _config


def set_skill_manager_config(config: SkillManagerConfig) -> None:
    """Set the SkillManager configuration."""
    global _config
    _config = config
