"""
Plugin operations: install, uninstall, enable, disable, update.

Implements the core CRUD operations on plugins.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .config import get_plugin_service_config, is_builtin_plugin
from .loader import load_marketplace_plugin, load_plugin_from_path
from .manifest import load_plugin_manifest
from .state import get_plugin_state
from .types import (
    InstallRecord,
    LoadedPlugin,
    MarketplaceConfig,
    PluginError,
    PluginErrorType,
    PluginOperationResult,
    PluginScope,
    PluginSource,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def install_plugin(
    plugin_id: str,
    scope: str = "user",
) -> PluginOperationResult:
    """
    Install a plugin.

    Args:
        plugin_id: Plugin ID in format "name" or "name@marketplace"
        scope: Installation scope ("user", "project", "local")

    Returns:
        PluginOperationResult
    """
    # Parse plugin ID
    if "@" in plugin_id:
        name, marketplace = plugin_id.rsplit("@", 1)
    else:
        name = plugin_id
        marketplace = None

    # Check for builtin
    if is_builtin_plugin(plugin_id):
        # Builtins don't need installation, just enable
        return enable_plugin(plugin_id)

    state = get_plugin_state()
    config = get_plugin_service_config()

    # Determine installation path
    plugins_dir = Path(os.path.expanduser(config.cache_dir))
    install_path = plugins_dir / (marketplace or "local") / name

    try:
        if marketplace:
            # Install from marketplace
            plugin, err = load_marketplace_plugin(marketplace, name)
            if err:
                return PluginOperationResult(
                    success=False,
                    plugin=name,
                    error=err.message,
                )
            # Copy to install path
            if plugin and install_path.exists() is False:
                import shutil
                install_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(Path(plugin.path), install_path)
        else:
            # Install from local path
            source_path = Path(name).expanduser()
            if not source_path.exists():
                return PluginOperationResult(
                    success=False,
                    plugin=name,
                    error=f"Local plugin path does not exist: {name}",
                )

            manifest_or_error = load_plugin_manifest(source_path)
            if isinstance(manifest_or_error, PluginError):
                return PluginOperationResult(
                    success=False,
                    plugin=name,
                    error=manifest_or_error.message,
                )

            import shutil
            install_path.parent.mkdir(parents=True, exist_ok=True)
            if install_path.exists():
                shutil.rmtree(install_path)
            shutil.copytree(source_path, install_path)

        # Record installation
        record = InstallRecord(
            scope=PluginScope(scope),
            install_path=str(install_path),
            version=manifest_or_error.version if isinstance(manifest_or_error, LoadedPlugin) else None,
        )
        state.add_install_record(name, record)

        return PluginOperationResult(
            success=True,
            plugin=name,
            message=f"Plugin '{name}' installed successfully",
        )

    except Exception as e:
        return PluginOperationResult(
            success=False,
            plugin=name,
            error=f"Installation failed: {e}",
        )


# ---------------------------------------------------------------------------
# Uninstallation
# ---------------------------------------------------------------------------


def uninstall_plugin(
    plugin_id: str,
    scope: str = "user",
) -> PluginOperationResult:
    """
    Uninstall a plugin.

    Args:
        plugin_id: Plugin ID
        scope: Installation scope ("user", "project", "local")

    Returns:
        PluginOperationResult
    """
    if is_builtin_plugin(plugin_id):
        # Builtins - just disable
        return disable_plugin(plugin_id)

    name = plugin_id.rsplit("@", 1)[0] if "@" in plugin_id else plugin_id

    state = get_plugin_state()

    # Check if installed
    records = state.get_install_records(name)
    scope_enum = PluginScope(scope)
    matching = [r for r in records if r.scope == scope_enum]

    if not matching:
        return PluginOperationResult(
            success=False,
            plugin=name,
            error=f"Plugin '{name}' is not installed at scope '{scope}'",
        )

    # Remove from state
    state.remove_install_record(name, scope_enum)

    # Remove from filesystem
    for record in matching:
        path = Path(os.path.expanduser(record.install_path))
        if path.exists():
            import shutil
            try:
                shutil.rmtree(path)
            except Exception:
                pass

    return PluginOperationResult(
        success=True,
        plugin=name,
        message=f"Plugin '{name}' uninstalled successfully",
    )


# ---------------------------------------------------------------------------
# Enable / Disable
# ---------------------------------------------------------------------------


def enable_plugin(plugin_id: str) -> PluginOperationResult:
    """
    Enable a plugin.

    Args:
        plugin_id: Plugin ID

    Returns:
        PluginOperationResult
    """
    name = plugin_id.rsplit("@", 1)[0] if "@" in plugin_id else plugin_id

    state = get_plugin_state()

    # Update loaded plugin state
    plugin = state.get_loaded(name)
    if plugin is not None:
        plugin.enabled = True
    else:
        # Load it now
        records = state.get_install_records(name)
        if not records and not is_builtin_plugin(plugin_id):
            return PluginOperationResult(
                success=False,
                plugin=name,
                error=f"Plugin '{name}' is not installed",
            )
        # The enable state is tracked via settings in full impl
        # For now, just update the loaded state
        if plugin is None:
            # Trigger a reload
            pass

    return PluginOperationResult(
        success=True,
        plugin=name,
        message=f"Plugin '{name}' enabled",
    )


def disable_plugin(plugin_id: str) -> PluginOperationResult:
    """
    Disable a plugin.

    Args:
        plugin_id: Plugin ID

    Returns:
        PluginOperationResult
    """
    name = plugin_id.rsplit("@", 1)[0] if "@" in plugin_id else plugin_id

    state = get_plugin_state()

    plugin = state.get_loaded(name)
    if plugin is not None:
        plugin.enabled = False

    return PluginOperationResult(
        success=True,
        plugin=name,
        message=f"Plugin '{name}' disabled",
    )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def update_plugin(plugin_id: str) -> PluginOperationResult:
    """
    Update a plugin to the latest version.

    Args:
        plugin_id: Plugin ID

    Returns:
        PluginOperationResult
    """
    name = plugin_id.rsplit("@", 1)[0] if "@" in plugin_id else plugin_id

    if is_builtin_plugin(plugin_id):
        return PluginOperationResult(
            success=False,
            plugin=name,
            error="Built-in plugins cannot be updated",
        )

    state = get_plugin_state()
    records = state.get_install_records(name)
    if not records:
        return PluginOperationResult(
            success=False,
            plugin=name,
            error=f"Plugin '{name}' is not installed",
        )

    # Re-install from marketplace
    marketplace = None
    if "@" in plugin_id:
        marketplace = plugin_id.rsplit("@", 1)[1]

    if marketplace:
        # Uninstall then reinstall
        uninstall_plugin(plugin_id)
        return install_plugin(plugin_id, scope=records[0].scope.value)

    return PluginOperationResult(
        success=False,
        plugin=name,
        error=f"Update not supported for local plugin '{name}'",
    )


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------


def install_marketplace_plugins(
    marketplace_name: str,
) -> list[PluginOperationResult]:
    """
    Install all plugins from a marketplace.

    Args:
        marketplace_name: Name of the marketplace

    Returns:
        List of results
    """
    from .marketplace import get_marketplace_plugins

    entries = get_marketplace_plugins(marketplace_name)
    if entries is None:
        return [
            PluginOperationResult(
                success=False,
                error=f"Marketplace '{marketplace_name}' not found",
            )
        ]

    results: list[PluginOperationResult] = []
    for entry in entries:
        result = install_plugin(f"{entry.name}@{marketplace_name}")
        results.append(result)

    return results
