"""Plugin system for py-claw.

Provides builtin plugin registry, plugin loading, enable/disable functionality.
"""
from __future__ import annotations

from py_claw.plugins.builtin import (
    BUILTIN_PLUGINS,
    BUILTIN_MARKETPLACE_NAME,
    register_builtin_plugin,
    is_builtin_plugin_id,
    get_builtin_plugin_definition,
    get_builtin_plugins,
    get_builtin_plugin_skill_commands,
    clear_builtin_plugins,
)
from py_claw.plugins.types import (
    PluginSource,
    PluginAuthor,
    PluginScope,
    PluginInstallationEntry,
)
from py_claw.plugins.manifest import (
    PluginManifest,
    PluginValidationError,
)
from py_claw.plugins.registry import (
    PluginRegistry,
    get_plugin_registry,
)

__all__ = [
    # builtin
    "BUILTIN_PLUGINS",
    "BUILTIN_MARKETPLACE_NAME",
    "register_builtin_plugin",
    "is_builtin_plugin_id",
    "get_builtin_plugin_definition",
    "get_builtin_plugins",
    "get_builtin_plugin_skill_commands",
    "clear_builtin_plugins",
    # manifest
    "PluginManifest",
    "PluginSource",
    "PluginAuthor",
    "PluginScope",
    "PluginInstallationEntry",
    # registry
    "PluginRegistry",
    "get_plugin_registry",
]
