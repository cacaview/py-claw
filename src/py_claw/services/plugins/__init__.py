"""
Plugin system service.

Provides a Python plugin system with marketplace support, manifest parsing,
installation management, and built-in plugin registry.
"""
from __future__ import annotations

from .config import (
    BUILTIN_PLUGINS,
    BuiltinPluginDefinition,
    PluginServiceConfig,
    get_plugin_service_config,
    is_builtin_plugin,
    register_builtin_plugin,
    set_plugin_service_config,
)
from .loader import load_all_plugins, load_plugin_from_path
from .manifest import load_plugin_manifest, validate_manifest_paths
from .marketplace import (
    add_marketplace,
    clear_marketplace_cache,
    get_marketplace_plugins,
    list_marketplaces,
    register_official_marketplace,
    remove_marketplace,
)
from .operations import (
    disable_plugin,
    enable_plugin,
    install_marketplace_plugins,
    install_plugin,
    uninstall_plugin,
    update_plugin,
)
from .service import (
    PluginService,
    get_plugin_service,
    initialize_plugins,
)
from .state import (
    PluginState,
    get_plugin_state,
    reset_plugin_state,
)
from .types import (
    FlaggedPlugin,
    InstallRecord,
    LoadedPlugin,
    MarketplaceConfig,
    MarketplaceManifest,
    PluginAuthor,
    PluginError,
    PluginErrorType,
    PluginManifest,
    PluginMarketplaceEntry,
    PluginOperationResult,
    PluginScope,
    PluginSource,
    PluginSourceType,
    PluginStatus,
)

__all__ = [
    # Config
    "BUILTIN_PLUGINS",
    "BuiltinPluginDefinition",
    "PluginServiceConfig",
    "get_plugin_service_config",
    "is_builtin_plugin",
    "register_builtin_plugin",
    "set_plugin_service_config",
    # Loader
    "load_all_plugins",
    "load_plugin_from_path",
    # Manifest
    "load_plugin_manifest",
    "validate_manifest_paths",
    # Marketplace
    "add_marketplace",
    "clear_marketplace_cache",
    "get_marketplace_plugins",
    "list_marketplaces",
    "register_official_marketplace",
    "remove_marketplace",
    # Operations
    "disable_plugin",
    "enable_plugin",
    "install_marketplace_plugins",
    "install_plugin",
    "uninstall_plugin",
    "update_plugin",
    # Service
    "PluginService",
    "get_plugin_service",
    "initialize_plugins",
    # State
    "PluginState",
    "get_plugin_state",
    "reset_plugin_state",
    # Types
    "FlaggedPlugin",
    "InstallRecord",
    "LoadedPlugin",
    "MarketplaceConfig",
    "MarketplaceManifest",
    "PluginAuthor",
    "PluginError",
    "PluginErrorType",
    "PluginManifest",
    "PluginMarketplaceEntry",
    "PluginOperationResult",
    "PluginScope",
    "PluginSource",
    "PluginSourceType",
    "PluginStatus",
]
