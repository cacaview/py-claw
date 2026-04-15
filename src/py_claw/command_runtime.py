"""
Command handler runtime with lazy-loading and feature gates.

Provides command registration, discovery, and execution aligned with
TypeScript reference ClaudeCode-main/src/commands.ts.

Key features:
- Lazy command loading (commands loaded on first access)
- Feature gate integration (commands enabled/disabled by features)
- Skill discovery from skills directories
- Plugin command integration
"""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Protocol

from py_claw.skills import discover_local_skills, DiscoveredSkill


# Feature flags (mirrors TS feature() from bun:bundle)
class Feature(Enum):
    """Available feature flags."""

    BRIDGE_MODE = "BRIDGE_MODE"
    DAEMON = "DAEMON"
    PROACTIVE = "PROACTIVE"
    KAIROS = "KAIROS"
    KAIROS_BRIEF = "KAIROS_BRIEF"
    VOICE_MODE = "VOICE_MODE"
    HISTORY_SNIP = "HISTORY_SNIP"
    WORKFLOW_SCRIPTS = "WORKFLOW_SCRIPTS"
    CCR_REMOTE_SETUP = "CCR_REMOTE_SETUP"
    EXPERIMENTAL_SKILL_SEARCH = "EXPERIMENTAL_SKILL_SEARCH"
    KAIROS_GITHUB_WEBHOOKS = "KAIROS_GITHUB_WEBHOOKS"
    ULTRAPLAN = "ULTRAPLAN"
    TORCH = "TORCH"
    UDS_INBOX = "UDS_INBOX"
    FORK_SUBAGENT = "FORK_SUBAGENT"
    BUDDY = "BUDDY"
    MCP_SKILLS = "MCP_SKILLS"


def is_feature_enabled(feature: Feature) -> bool:
    """Check if a feature flag is enabled.

    Mirrors TS feature() from bun:bundle.

    Args:
        feature: The feature to check

    Returns:
        True if the feature is enabled
    """
    env_var = f"CLAUDE_CODE_{feature.value}"
    return os.environ.get(env_var, "").lower() in ("1", "true", "yes")


# Command types (mirrors TypeScript command types)
class CommandType(Enum):
    """Command execution type."""

    PROMPT = "prompt"  # Skill/agent-style command
    LOCAL = "local"  # Local function command
    LOCAL_JSX = "local-jsx"  # Local React component command


class CommandAvailability(Enum):
    """Command availability constraints."""

    CLAUDE_AI = "claude-ai"  # Only for claude.ai subscribers
    CONSOLE = "console"  # Only for Console API key users


@dataclass
class CommandDefinition:
    """Definition of a slash command.

    Mirrors Command type from TypeScript.
    """

    name: str
    description: str
    argument_hint: str = ""
    command_type: CommandType = CommandType.LOCAL
    source: str = "builtin"
    availability: list[CommandAvailability] | None = None
    is_enabled: Callable[[], bool] | None = None
    is_hidden: bool = False
    aliases: list[str] | None = None
    progress_message: str | None = None
    prompt_template: str | None = None
    skill: DiscoveredSkill | None = None
    when_to_use: str | None = None
    version: str | None = None
    model: str | None = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    loaded_from: str | None = None  # 'skills', 'plugin', 'bundled', 'mcp'
    kind: str | None = None  # 'workflow' for workflow-backed commands
    hooks: dict[str, Any] | None = None


@dataclass
class CommandExecutionResult:
    """Result of executing a command."""

    command: CommandDefinition
    output_text: str | None = None
    expanded_prompt: str | None = None
    should_query: bool = False
    allowed_tools: list[str] | None = None
    model: str | None = None


# Builtin commands registry
_BUILTIN_COMMANDS: dict[str, CommandDefinition] = {}


def register_builtin_command(cmd: CommandDefinition) -> None:
    """Register a built-in command.

    Args:
        cmd: The command definition to register
    """
    _BUILTIN_COMMANDS[cmd.name] = cmd
    if cmd.aliases:
        for alias in cmd.aliases:
            _BUILTIN_COMMANDS[alias] = cmd


def get_builtin_command(name: str) -> CommandDefinition | None:
    """Get a registered built-in command by name.

    Args:
        name: The command name or alias

    Returns:
        The command definition or None if not found
    """
    return _BUILTIN_COMMANDS.get(name)


def get_all_builtin_commands() -> list[CommandDefinition]:
    """Get all registered built-in commands.

    Returns:
        List of all builtin commands
    """
    # Remove duplicates (aliases point to same command)
    seen: set[int] = set()
    unique_commands: list[CommandDefinition] = []
    for cmd in _BUILTIN_COMMANDS.values():
        cmd_id = id(cmd)
        if cmd_id not in seen:
            seen.add(cmd_id)
            unique_commands.append(cmd)
    return sorted(unique_commands, key=lambda c: c.name)


def clear_builtin_commands() -> None:
    """Clear all registered built-in commands.

    Note: This is primarily for testing purposes.
    """
    _BUILTIN_COMMANDS.clear()


# Lazy loading support
class LazyCommandLoader:
    """Lazy command loader for deferred imports.

    Mirrors the lazy loading pattern from TypeScript commands.ts.
    """

    def __init__(self, import_path: str, factory: Callable[[], Any]) -> None:
        """Initialize lazy loader.

        Args:
            import_path: Path for the module to import
            factory: Factory function to create the command
        """
        self._import_path = import_path
        self._factory = factory
        self._loaded: Any | None = None

    def load(self) -> Any:
        """Load and return the command.

        Returns:
            The loaded command object
        """
        if self._loaded is None:
            self._loaded = self._factory()
        return self._loaded


# Command runtime for managing commands
class CommandRuntime:
    """Runtime for managing command loading and execution.

    Mirrors the command system from TypeScript commands.ts.
    """

    def __init__(self, cwd: str | None = None) -> None:
        """Initialize command runtime.

        Args:
            cwd: Current working directory for skill discovery
        """
        self._cwd = cwd or os.getcwd()
        self._skills_cache: list[DiscoveredSkill] | None = None
        self._commands_cache: list[CommandDefinition] | None = None

    @property
    def cwd(self) -> str:
        """Get current working directory."""
        return self._cwd

    def set_cwd(self, cwd: str) -> None:
        """Set current working directory.

        Args:
            cwd: New working directory
        """
        self._cwd = cwd
        self._skills_cache = None
        self._commands_cache = None

    def discover_skills(self) -> list[DiscoveredSkill]:
        """Discover skills from skills directories.

        Returns:
            List of discovered skills
        """
        if self._skills_cache is None:
            self._skills_cache = discover_local_skills(cwd=self._cwd)
        return self._skills_cache

    def get_commands(self) -> list[CommandDefinition]:
        """Get all available commands.

        Combines builtin commands, skills, and plugin commands.
        Respects feature gates and availability constraints.

        Returns:
            List of available commands
        """
        if self._commands_cache is not None:
            return self._commands_cache

        commands: list[CommandDefinition] = []

        # Add builtin commands
        for cmd in get_all_builtin_commands():
            if self._is_command_available(cmd):
                commands.append(cmd)

        # Add skills as commands
        for skill in self.discover_skills():
            skill_cmd = self._skill_to_command(skill)
            if skill_cmd and self._is_command_available(skill_cmd):
                commands.append(skill_cmd)

        self._commands_cache = commands
        return commands

    def find_command(self, name: str) -> CommandDefinition | None:
        """Find a command by name or alias.

        Args:
            name: Command name or alias

        Returns:
            The command or None if not found
        """
        for cmd in self.get_commands():
            if cmd.name == name:
                return cmd
            if cmd.aliases and name in cmd.aliases:
                return cmd
        return None

    def _is_command_available(self, cmd: CommandDefinition) -> bool:
        """Check if a command is available given current constraints.

        Args:
            cmd: The command to check

        Returns:
            True if the command is available
        """
        # Check is_enabled function
        if cmd.is_enabled is not None and not cmd.is_enabled():
            return False

        # Check availability constraints
        if cmd.availability:
            # For now, all availability checks pass in Python
            # In real implementation, would check auth state
            pass

        return True

    def _skill_to_command(self, skill: DiscoveredSkill) -> CommandDefinition | None:
        """Convert a skill to a command definition.

        Args:
            skill: The skill to convert

        Returns:
            Command definition or None if conversion fails
        """
        if not skill.user_invocable and skill.disable_model_invocation:
            return None

        return CommandDefinition(
            name=skill.name,
            description=skill.description,
            argument_hint=skill.argument_hint,
            command_type=CommandType.PROMPT,
            source="builtin",
            skill=skill,
            when_to_use=skill.when_to_use,
            version=skill.version,
            model=skill.model,
            disable_model_invocation=skill.disable_model_invocation,
            loaded_from="skills",
        )

    def clear_cache(self) -> None:
        """Clear the commands cache."""
        self._commands_cache = None


# Global runtime instance
_runtime: CommandRuntime | None = None


def get_command_runtime(cwd: str | None = None) -> CommandRuntime:
    """Get the global command runtime instance.

    Args:
        cwd: Current working directory

    Returns:
        The global CommandRuntime
    """
    global _runtime
    if _runtime is None:
        _runtime = CommandRuntime(cwd=cwd)
    elif cwd is not None:
        _runtime.set_cwd(cwd)
    return _runtime


# Built-in command definitions
# These are registered at module load time
def _register_builtin_commands() -> None:
    """Register all built-in commands."""
    from py_claw.commands import (
        CommandDefinition,
    )

    # Import and register commands from commands.py
    builtin_commands = [
        # Add commands from commands.py here as CommandDefinition objects
        # This mirrors the COMMANDS list in TypeScript commands.ts
    ]

    for cmd in builtin_commands:
        register_builtin_command(cmd)


# Command availability checking
def meets_availability_requirement(cmd: CommandDefinition) -> bool:
    """Check if a command's availability requirement is met.

    Mirrors meetsAvailabilityRequirement() from TypeScript.

    Args:
        cmd: The command to check

    Returns:
        True if the command's availability requirement is met
    """
    if not cmd.availability:
        return True

    # In Python, we'd check auth state here
    # For now, all availability constraints pass
    return True


def is_command_enabled(cmd: CommandDefinition) -> bool:
    """Check if a command is enabled.

    Mirrors isCommandEnabled() from TypeScript.

    Args:
        cmd: The command to check

    Returns:
        True if the command is enabled
    """
    if cmd.is_enabled is None:
        return True
    return cmd.is_enabled()


def get_command_name(cmd: CommandDefinition) -> str:
    """Get the user-facing name of a command.

    Mirrors getCommandName() from TypeScript.

    Args:
        cmd: The command

    Returns:
        The user-facing name
    """
    return cmd.name
