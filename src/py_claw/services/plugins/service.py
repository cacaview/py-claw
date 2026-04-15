"""
Plugin service - main facade.

Provides the high-level plugin service interface.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from .config import (
    get_plugin_service_config,
    is_builtin_plugin,
)
from .loader import load_all_plugins, load_plugin_from_path
from .marketplace import (
    add_marketplace as _add_marketplace,
    list_marketplaces,
    register_official_marketplace,
    remove_marketplace as _remove_marketplace,
)
from .operations import (
    disable_plugin as _disable_plugin,
    enable_plugin as _enable_plugin,
    install_plugin as _install_plugin,
    uninstall_plugin as _uninstall_plugin,
    update_plugin as _update_plugin,
)
from .state import get_plugin_state
from .types import (
    LoadedPlugin,
    MarketplaceConfig,
    PluginError,
    PluginOperationResult,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# PluginService
# ---------------------------------------------------------------------------


class PluginService:
    """
    Main plugin service facade.

    Coordinates plugin discovery, loading, installation, and lifecycle management.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._enabled_plugins: list[LoadedPlugin] = []
        self._disabled_plugins: list[LoadedPlugin] = []
        self._errors: list[PluginError] = []

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Initialize the plugin service.

        Loads all installed plugins and built-in plugins.
        Must be called before using other service methods.
        """
        if self._initialized:
            return

        config = get_plugin_service_config()
        if not config.enabled:
            self._initialized = True
            return

        # Register official marketplace
        register_official_marketplace()

        # Load all plugins
        self._enabled_plugins, self._disabled_plugins, self._errors = load_all_plugins()

        self._initialized = True

    @property
    def initialized(self) -> bool:
        return self._initialized

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_plugins(
        self,
        include_disabled: bool = True,
        include_errors: bool = False,
    ) -> list[dict]:
        """
        List all loaded plugins.

        Args:
            include_disabled: Include disabled plugins
            include_errors: Include load errors

        Returns:
            List of plugin info dicts
        """
        results: list[dict] = []

        for plugin in self._enabled_plugins:
            results.append(self._plugin_to_dict(plugin))

        if include_disabled:
            for plugin in self._disabled_plugins:
                results.append(self._plugin_to_dict(plugin))

        if include_errors:
            for error in self._errors:
                results.append(error.to_dict())

        return results

    def get_plugin(self, name: str) -> dict | None:
        """Get a plugin by name."""
        for plugin in self._enabled_plugins + self._disabled_plugins:
            if plugin.name == name:
                return self._plugin_to_dict(plugin)
        return None

    def is_enabled(self, plugin_name: str) -> bool:
        """Check if a plugin is enabled."""
        for plugin in self._enabled_plugins:
            if plugin.name == plugin_name:
                return True
        return False

    def is_installed(self, plugin_name: str) -> bool:
        """Check if a plugin is installed."""
        for plugin in self._enabled_plugins + self._disabled_plugins:
            if plugin.name == plugin_name:
                return True
        return False

    def is_builtin(self, plugin_name: str) -> bool:
        """Check if a plugin is a built-in plugin."""
        return is_builtin_plugin(plugin_name)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def install(
        self,
        plugin_id: str,
        scope: str = "user",
    ) -> PluginOperationResult:
        """
        Install a plugin.

        Args:
            plugin_id: Plugin ID (e.g. "my-plugin" or "my-plugin@marketplace")
            scope: Installation scope

        Returns:
            Operation result
        """
        result = _install_plugin(plugin_id, scope)
        if result.success:
            self._reload()
        return result

    def uninstall(
        self,
        plugin_id: str,
        scope: str = "user",
    ) -> PluginOperationResult:
        """
        Uninstall a plugin.

        Args:
            plugin_id: Plugin ID
            scope: Installation scope

        Returns:
            Operation result
        """
        result = _uninstall_plugin(plugin_id, scope)
        if result.success:
            self._reload()
        return result

    def enable(self, plugin_id: str) -> PluginOperationResult:
        """
        Enable a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            Operation result
        """
        result = _enable_plugin(plugin_id)
        if result.success:
            self._reload()
        return result

    def disable(self, plugin_id: str) -> PluginOperationResult:
        """
        Disable a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            Operation result
        """
        result = _disable_plugin(plugin_id)
        if result.success:
            self._reload()
        return result

    def update(self, plugin_id: str) -> PluginOperationResult:
        """
        Update a plugin to the latest version.

        Args:
            plugin_id: Plugin ID

        Returns:
            Operation result
        """
        result = _update_plugin(plugin_id)
        if result.success:
            self._reload()
        return result

    # ------------------------------------------------------------------
    # Marketplaces
    # ------------------------------------------------------------------

    def add_marketplace(
        self,
        url: str,
        name: str | None = None,
    ) -> tuple[bool, str]:
        """
        Add a marketplace.

        Args:
            url: Marketplace base URL
            name: Optional marketplace name

        Returns:
            (success, message)
        """
        return _add_marketplace(url, name)

    def remove_marketplace(self, name: str) -> tuple[bool, str]:
        """
        Remove a marketplace.

        Args:
            name: Marketplace name

        Returns:
            (success, message)
        """
        return _remove_marketplace(name)

    def list_marketplaces(self) -> list[MarketplaceConfig]:
        """List all registered marketplaces."""
        return list_marketplaces()

    def get_marketplace_plugins(
        self,
        marketplace_name: str,
        force_refresh: bool = False,
    ) -> list[dict]:
        """
        Get plugins available in a marketplace.

        Args:
            marketplace_name: Marketplace name
            force_refresh: Skip cache and refetch

        Returns:
            List of marketplace plugin entries
        """
        from .marketplace import get_marketplace_plugins

        entries = get_marketplace_plugins(marketplace_name, force_refresh)
        if entries is None:
            return []
        return [e.model_dump() for e in entries]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _reload(self) -> None:
        """Reload all plugins."""
        self._enabled_plugins, self._disabled_plugins, self._errors = load_all_plugins()

    def _plugin_to_dict(self, plugin: LoadedPlugin) -> dict:
        """Convert a LoadedPlugin to a dict."""
        return {
            "name": plugin.name,
            "version": plugin.version,
            "description": plugin.manifest.description,
            "enabled": plugin.enabled,
            "builtin": plugin.is_builtin,
            "path": plugin.path,
            "source": plugin.source_id,
            "repository": plugin.repository,
            "commandsPath": plugin.commands_path,
            "agentsPath": plugin.agents_path,
            "skillsPath": plugin.skills_path,
        }


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_service: PluginService | None = None


def get_plugin_service() -> PluginService:
    """Get the global plugin service instance."""
    global _service
    if _service is None:
        _service = PluginService()
    return _service


def initialize_plugins() -> None:
    """Initialize the plugin service at startup."""
    get_plugin_service().initialize()
