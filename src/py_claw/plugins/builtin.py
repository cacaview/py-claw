"""Builtin plugin registry for py-claw.

Based on ClaudeCode-main/src/plugins/builtinPlugins.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from py_claw.commands import CommandDefinition

# Builtin marketplace name constant
BUILTIN_MARKETPLACE_NAME = "builtin"

# Builtin plugins registry
BUILTIN_PLUGINS: dict[str, dict[str, Any]] = {}


@dataclass
class BuiltinPluginDefinition:
    """Definition for a built-in plugin.

    Corresponds to BuiltinPluginDefinition in TypeScript.
    """

    name: str  # Used in {name}@builtin
    description: str
    version: str | None = None
    # Skills/commands provided by this plugin
    skills: list[dict[str, Any]] | None = None
    # Hook configurations
    hooks: dict[str, Any] | None = None
    # MCP servers to register
    mcp_servers: dict[str, Any] | None = None
    # Availability check function
    is_available: Any = None  # callable -> bool
    # Default enabled state (defaults to True if omitted)
    default_enabled: bool = True


def _get_builtin_plugins_map() -> dict[str, BuiltinPluginDefinition]:
    """Get the mutable builtin plugins map."""
    return BUILTIN_PLUGINS  # type: ignore[return-value]


def register_builtin_plugin(definition: BuiltinPluginDefinition) -> None:
    """Register a built-in plugin.

    Args:
        definition: The plugin definition to register
    """
    plugin_id = f"{definition.name}@{BUILTIN_MARKETPLACE_NAME}"
    _get_builtin_plugins_map()[plugin_id] = definition


def is_builtin_plugin_id(plugin_id: str) -> bool:
    """Check if a plugin ID is a built-in plugin.

    Args:
        plugin_id: The plugin ID to check

    Returns:
        True if the plugin ID ends with @builtin
    """
    return plugin_id.endswith(f"@{BUILTIN_MARKETPLACE_NAME}")


def get_builtin_plugin_definition(name: str) -> BuiltinPluginDefinition | None:
    """Get a built-in plugin definition by name.

    Args:
        name: The plugin name (without @builtin suffix)

    Returns:
        The plugin definition or None if not found
    """
    plugin_id = f"{name}@{BUILTIN_MARKETPLACE_NAME}"
    return _get_builtin_plugins_map().get(plugin_id)


def get_builtin_plugins() -> tuple[list[Any], list[Any]]:
    """Get all registered built-in plugins.

    Returns:
        Tuple of (enabled_plugins, disabled_plugins)
    """
    # For now, return empty - actual implementation would check settings
    return [], []


def get_builtin_plugin_skill_commands() -> list["CommandDefinition"]:
    """Get skill commands from all enabled built-in plugins.

    Returns:
        List of CommandDefinition objects from enabled built-in plugins
    """
    # Import here to avoid circular imports
    from py_claw.commands import CommandDefinition
    from py_claw.skills import DiscoveredSkill

    commands: list[CommandDefinition] = []
    enabled_plugins, _ = get_builtin_plugins()

    for plugin in enabled_plugins:
        if not plugin.skills:
            continue

        for skill_def in plugin.skills:
            # Convert skill definition to DiscoveredSkill
            skill = DiscoveredSkill(
                name=skill_def.get("name", ""),
                description=skill_def.get("description", ""),
                content=skill_def.get("content", ""),
                skill_path=skill_def.get("path", ""),
                skill_root=skill_def.get("root", ""),
                source=f"plugin:{plugin.name}@builtin",
            )
            commands.append(
                CommandDefinition(
                    name=skill.name,
                    description=skill.description,
                    source="bundled",
                    skill=skill,
                )
            )

    return commands


def clear_builtin_plugins() -> None:
    """Clear all registered built-in plugins.

    Note: This is primarily for testing purposes.
    """
    _get_builtin_plugins_map().clear()


def init_builtin_plugins() -> None:
    """Initialize built-in plugins.

    This is called at startup to register any built-in plugins.
    Currently empty - no built-in plugins are registered yet.
    """
    # No built-in plugins are registered in the initial implementation.
    # Plugins can register themselves by calling register_builtin_plugin().
    pass
