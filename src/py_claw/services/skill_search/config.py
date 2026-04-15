"""
SkillSearch configuration.

Service for searching and discovering skills.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillSearchConfig:
    """Configuration for SkillSearch service."""

    enabled: bool = True
    # Search result limit
    max_results: int = 10
    # Include built-in skills in search
    include_builtin: bool = True
    # Include custom skills in search
    include_custom: bool = True
    # Cache search results
    cache_enabled: bool = True
    # Cache TTL in seconds
    cache_ttl: int = 300

    @classmethod
    def from_settings(cls, settings: dict) -> SkillSearchConfig:
        """Create config from settings dictionary."""
        ss_settings = settings.get("skillSearch", {})
        return cls(
            enabled=ss_settings.get("enabled", True),
            max_results=ss_settings.get("maxResults", 10),
            include_builtin=ss_settings.get("includeBuiltin", True),
            include_custom=ss_settings.get("includeCustom", True),
            cache_enabled=ss_settings.get("cacheEnabled", True),
            cache_ttl=ss_settings.get("cacheTtl", 300),
        )


# Global config instance
_config: SkillSearchConfig | None = None


def get_skill_search_config() -> SkillSearchConfig:
    """Get the current SkillSearch configuration."""
    global _config
    if _config is None:
        _config = SkillSearchConfig()
    return _config


def set_skill_search_config(config: SkillSearchConfig) -> None:
    """Set the SkillSearch configuration."""
    global _config
    _config = config


# Built-in skill definitions
BUILTIN_SKILLS = {
    "batch": {
        "description": "Execute multiple operations in batch",
        "argument_hint": "<operations>",
        "when_to_use": "When you need to run multiple commands or operations together",
    },
    "debug": {
        "description": "Debug code and identify issues",
        "argument_hint": "<code-or-issue>",
        "when_to_use": "When debugging code or identifying issues",
    },
    "simplify": {
        "description": "Simplify and refactor code",
        "argument_hint": "<code>",
        "when_to_use": "When code needs to be simplified or refactored",
    },
    "verify": {
        "description": "Verify code changes or functionality",
        "argument_hint": "<changes>",
        "when_to_use": "When verifying that changes work correctly",
    },
    "hunter": {
        "description": "Find and analyze bugs or issues",
        "argument_hint": "<pattern>",
        "when_to_use": "When hunting for bugs or specific patterns in code",
    },
    "remember": {
        "description": "Remember information for future sessions",
        "argument_hint": "<information>",
        "when_to_use": "When you want to save information for later",
    },
    "stuck": {
        "description": "Get help when stuck on a problem",
        "argument_hint": "<problem>",
        "when_to_use": "When you need help continuing with a difficult problem",
    },
    "skillify": {
        "description": "Convert a workflow into a reusable skill",
        "argument_hint": "<workflow>",
        "when_to_use": "When you want to save a workflow as a skill",
    },
    "update-config": {
        "description": "Update Claude Code configuration",
        "argument_hint": "<key=value>",
        "when_to_use": "When configuring Claude Code settings",
    },
    "keybindings": {
        "description": "Manage keyboard shortcuts",
        "argument_hint": "[action]",
        "when_to_use": "When managing keybindings",
    },
    "lorem-ipsum": {
        "description": "Generate placeholder text",
        "argument_hint": "[word-count]",
        "when_to_use": "When generating placeholder text for testing",
    },
    "schedule-remote-agents": {
        "description": "Schedule remote agents for background tasks",
        "argument_hint": "<task>",
        "when_to_use": "When scheduling background agent tasks",
    },
    "claude-in-chrome": {
        "description": "Interact with Claude in Chrome",
        "argument_hint": "<command>",
        "when_to_use": "When using Claude Chrome extension",
    },
    "dream": {
        "description": "Generate a dream consolidation",
        "argument_hint": "[topic]",
        "when_to_use": "When consolidating memories and learnings",
    },
}
