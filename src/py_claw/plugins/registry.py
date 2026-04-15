"""Plugin registry for py-claw.

Based on ClaudeCode-main/src/services/plugins/pluginOperations.ts
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from py_claw.plugins.builtin import (
    BUILTIN_MARKETPLACE_NAME,
    get_builtin_plugin_definition,
    is_builtin_plugin_id,
)
from py_claw.plugins.manifest import (
    load_installed_plugins,
    save_installed_plugins,
)
from py_claw.plugins.types import (
    InstalledPluginsFileV2,
    LoadedPlugin,
    PluginInstallationEntry,
    PluginManifest,
    PluginNotFoundError,
    PluginScope,
)


class PluginRegistry:
    """Registry for managing plugin state and operations.

    Corresponds to the plugin management logic in TypeScript.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        """Initialize the plugin registry.

        Args:
            config_dir: Directory for plugin configuration. Defaults to ~/.claude
        """
        if config_dir is None:
            config_dir = Path.home() / ".claude"
        self._config_dir = config_dir
        self._installed_plugins_file = config_dir / "installed_plugins.json"
        self._settings_file = config_dir / "settings.json"
        self._cache: dict[str, LoadedPlugin] = {}
        self._installed_data: InstalledPluginsFileV2 | None = None

    def _load_settings(self) -> dict[str, Any]:
        """Load settings from settings.json."""
        if not self._settings_file.exists():
            return {}
        try:
            return json.loads(self._settings_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _save_settings(self, settings: dict[str, Any]) -> None:
        """Save settings to settings.json."""
        self._settings_file.parent.mkdir(parents=True, exist_ok=True)
        self._settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    def _get_enabled_plugins_setting(self) -> dict[str, bool]:
        """Get the enabled plugins setting from settings."""
        settings = self._load_settings()
        return settings.get("enabledPlugins", {})

    def _set_plugin_enabled(
        self,
        plugin_id: str,
        enabled: bool,
        scope: PluginScope = PluginScope.USER,
    ) -> None:
        """Set plugin enabled state in settings.

        Args:
            plugin_id: The plugin ID
            enabled: Whether to enable or disable
            scope: The settings scope
        """
        settings = self._load_settings()

        if "enabledPlugins" not in settings:
            settings["enabledPlugins"] = {}

        settings["enabledPlugins"][plugin_id] = enabled
        self._save_settings(settings)

    def is_plugin_enabled(self, plugin_id: str) -> bool:
        """Check if a plugin is enabled.

        Args:
            plugin_id: The plugin ID

        Returns:
            True if the plugin is enabled
        """
        # Check if it's a built-in plugin
        if is_builtin_plugin_id(plugin_id):
            name = plugin_id.removesuffix(f"@{BUILTIN_MARKETPLACE_NAME}")
            builtin_def = get_builtin_plugin_definition(name)
            if builtin_def is None:
                return False

            # Check settings for explicit enable/disable
            enabled_plugins = self._get_enabled_plugins_setting()
            if plugin_id in enabled_plugins:
                return enabled_plugins[plugin_id]

            # Fall back to default
            return builtin_def.default_enabled

        # For installed plugins, check the enabledPlugins setting
        enabled_plugins = self._get_enabled_plugins_setting()
        if plugin_id in enabled_plugins:
            return enabled_plugins[plugin_id]

        # Default to enabled
        return True

    def enable_plugin(self, plugin_id: str) -> None:
        """Enable a plugin.

        Args:
            plugin_id: The plugin ID to enable
        """
        if is_builtin_plugin_id(plugin_id):
            # Built-in plugins always use user scope
            self._set_plugin_enabled(plugin_id, True, PluginScope.USER)
        else:
            self._set_plugin_enabled(plugin_id, True)

        # Clear cache
        self._cache.clear()

    def disable_plugin(self, plugin_id: str) -> None:
        """Disable a plugin.

        Args:
            plugin_id: The plugin ID to disable
        """
        if is_builtin_plugin_id(plugin_id):
            self._set_plugin_enabled(plugin_id, False, PluginScope.USER)
        else:
            self._set_plugin_enabled(plugin_id, False)

        # Clear cache
        self._cache.clear()

    def get_plugin_scope(self, plugin_id: str) -> PluginScope:
        """Determine the installation scope for a plugin.

        Args:
            plugin_id: The plugin ID

        Returns:
            The plugin's installation scope
        """
        if is_builtin_plugin_id(plugin_id):
            return PluginScope.USER

        # Check installed plugins file for scope
        installed = self._get_installed_data()
        if plugin_id in installed.plugins:
            entries = installed.plugins[plugin_id]
            if entries:
                return entries[0].scope

        # Default to user scope
        return PluginScope.USER

    def _get_installed_data(self) -> InstalledPluginsFileV2:
        """Get the installed plugins data."""
        if self._installed_data is None:
            self._installed_data = load_installed_plugins(self._installed_plugins_file)
        return self._installed_data

    def get_installed_plugins(self) -> dict[str, list[PluginInstallationEntry]]:
        """Get all installed plugins.

        Returns:
            Dictionary of plugin IDs to their installation entries
        """
        return self._get_installed_data().plugins

    def add_installed_plugin(
        self,
        plugin_id: str,
        install_path: str,
        scope: PluginScope = PluginScope.USER,
        version: str | None = None,
    ) -> None:
        """Add an installed plugin entry.

        Args:
            plugin_id: The plugin ID
            install_path: Path where the plugin is installed
            scope: The installation scope
            version: Optional version string
        """
        installed = self._get_installed_data()

        entry = PluginInstallationEntry(
            scope=scope,
            install_path=install_path,
            version=version,
        )

        if plugin_id not in installed.plugins:
            installed.plugins[plugin_id] = []

        installed.plugins[plugin_id].append(entry)
        save_installed_plugins(self._installed_plugins_file, installed)
        self._installed_data = installed

    def remove_installed_plugin(
        self,
        plugin_id: str,
        scope: PluginScope | None = None,
    ) -> bool:
        """Remove an installed plugin entry.

        Args:
            plugin_id: The plugin ID
            scope: Optional specific scope to remove. If None, removes all.

        Returns:
            True if any entries were removed
        """
        installed = self._get_installed_data()

        if plugin_id not in installed.plugins:
            return False

        if scope is None:
            del installed.plugins[plugin_id]
        else:
            original_len = len(installed.plugins[plugin_id])
            installed.plugins[plugin_id] = [
                e for e in installed.plugins[plugin_id]
                if e.scope != scope
            ]
            if not installed.plugins[plugin_id]:
                del installed.plugins[plugin_id]
            elif len(installed.plugins[plugin_id]) == original_len:
                return False

        save_installed_plugins(self._installed_plugins_file, installed)
        self._installed_data = installed
        return True

    def get_plugin_config(
        self,
        plugin_id: str,
    ) -> dict[str, Any] | None:
        """Get plugin-specific configuration.

        Args:
            plugin_id: The plugin ID

        Returns:
            The plugin config or None if not set
        """
        settings = self._load_settings()
        plugin_configs = settings.get("pluginConfigs", {})
        return plugin_configs.get(plugin_id)

    def set_plugin_config(
        self,
        plugin_id: str,
        config: dict[str, Any],
    ) -> None:
        """Set plugin-specific configuration.

        Args:
            plugin_id: The plugin ID
            config: The configuration to save
        """
        settings = self._load_settings()
        if "pluginConfigs" not in settings:
            settings["pluginConfigs"] = {}
        settings["pluginConfigs"][plugin_id] = config
        self._save_settings(settings)


# Global registry instance
_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry instance.

    Returns:
        The global PluginRegistry
    """
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
