"""
Plugin discovery and loading.

Handles discovering plugins from filesystem, marketplace, and loading their
manifests and component paths.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .config import get_plugin_service_config, is_builtin_plugin, get_builtin_plugin
from .manifest import load_plugin_manifest
from .state import get_plugin_state
from .types import (
    InstallRecord,
    LoadedPlugin,
    PluginError,
    PluginErrorType,
    PluginManifest,
    PluginScope,
    PluginSource,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Main loading
# ---------------------------------------------------------------------------


def load_all_plugins() -> tuple[list[LoadedPlugin], list[LoadedPlugin], list[PluginError]]:
    """
    Discover, load, and validate all plugins.

    Returns (enabled_plugins, disabled_plugins, errors).
    """
    state = get_plugin_state()
    config = get_plugin_service_config()

    enabled: list[LoadedPlugin] = []
    disabled: list[LoadedPlugin] = []
    errors: list[PluginError] = []

    # Load session-only plugins from --plugin-dir
    if config.session_plugin_dir:
        session_dir = Path(config.session_plugin_dir)
        if session_dir.exists():
            plugin, err = load_plugin_from_path(session_dir, is_session=True)
            if err:
                errors.append(err)
            elif plugin:
                if plugin.enabled:
                    enabled.append(plugin)
                else:
                    disabled.append(plugin)

    # Load installed plugins
    for plugin_name, records in state.get_all_install_records().items():
        for record in records:
            plugin, err = _load_installed_plugin(plugin_name, record)
            if err:
                errors.append(err)
            elif plugin:
                if plugin.enabled:
                    enabled.append(plugin)
                else:
                    disabled.append(plugin)

    # Load built-in plugins
    builtin_errors = _load_builtin_plugins(enabled, disabled, errors)

    state.clear_loaded()
    for p in enabled + disabled:
        state.add_loaded(p)

    return enabled, disabled, errors


def _load_installed_plugin(
    plugin_name: str,
    record: InstallRecord,
) -> tuple[LoadedPlugin | None, PluginError | None]:
    """Load a single installed plugin from its install path."""
    install_path = Path(os.path.expanduser(record.install_path))
    if not install_path.exists():
        return None, PluginError(
            plugin=plugin_name,
            error_type=PluginErrorType.PATH_NOT_FOUND,
            message=f"Plugin path does not exist: {record.install_path}",
        )

    result = load_plugin_from_path(install_path)
    if isinstance(result, PluginError):
        return None, result

    plugin: LoadedPlugin = result
    plugin.version = record.version
    return plugin, None


def _load_builtin_plugins(
    enabled: list[LoadedPlugin],
    disabled: list[LoadedPlugin],
    errors: list[PluginError],
) -> None:
    """Load all registered built-in plugins."""
    from .config import BUILTIN_PLUGINS

    for name, definition in BUILTIN_PLUGINS.items():
        if not definition.is_available:
            continue

        # Built-in plugins are always "loaded" from a synthetic path
        # They don't have real filesystem manifests
        manifest = PluginManifest(
            name=definition.name,
            description=definition.description,
            version=definition.version,
            commands=definition.commands_path,
            agents=definition.agents_path,
            skills=definition.skills_path,
            hooks=definition.hooks_config,
            mcpServers=definition.mcp_servers,
            lspServers=definition.lsp_servers,
        )

        plugin = LoadedPlugin(
            name=name,
            manifest=manifest,
            path=f"<builtin:{name}>",
            source_id=f"{name}@builtin",
            enabled=False,  # Built-ins are enabled via settings
            is_builtin=True,
            version=definition.version,
            commands_path=definition.commands_path,
            agents_path=definition.agents_path,
            skills_path=definition.skills_path,
            hooks_config=definition.hooks_config,
            mcp_servers=definition.mcp_servers,
            lsp_servers=definition.lsp_servers,
        )
        disabled.append(plugin)


def load_plugin_from_path(
    plugin_dir: str | Path,
    is_session: bool = False,
) -> LoadedPlugin | PluginError:
    """
    Load a single plugin from a filesystem path.

    Args:
        plugin_dir: Path to the plugin directory
        is_session: If True, this is a session-only plugin (not persisted)

    Returns:
        LoadedPlugin on success, PluginError on failure.
    """
    plugin_dir = Path(plugin_dir).resolve()
    if not plugin_dir.exists():
        return PluginError(
            plugin=str(plugin_dir),
            error_type=PluginErrorType.PATH_NOT_FOUND,
            message=f"Plugin directory not found: {plugin_dir}",
        )

    manifest_or_error = load_plugin_manifest(plugin_dir)
    if isinstance(manifest_or_error, PluginError):
        return manifest_or_error

    manifest: PluginManifest = manifest_or_error

    # Resolve component paths
    commands_path = _resolve_component_path(manifest.commands, plugin_dir)
    agents_path = _resolve_component_path(manifest.agents, plugin_dir)
    skills_path = _resolve_component_path(manifest.skills, plugin_dir)
    hooks_config = _resolve_hooks_config(manifest.hooks, plugin_dir)

    # Determine enabled state from settings
    enabled = _is_plugin_enabled(manifest.name, is_builtin=False)

    plugin = LoadedPlugin(
        name=manifest.name,
        manifest=manifest,
        path=str(plugin_dir),
        source_id=f"{manifest.name}@local",
        enabled=enabled,
        is_builtin=False,
        version=manifest.version,
        repository=manifest.repository,
        commands_path=commands_path,
        agents_path=agents_path,
        skills_path=skills_path,
        hooks_config=hooks_config,
        mcp_servers=_resolve_servers(manifest.mcpServers),
        lsp_servers=_resolve_servers(manifest.lspServers),
        settings=manifest.settings,
    )

    return plugin


# ---------------------------------------------------------------------------
# Marketplace plugin loading
# ---------------------------------------------------------------------------


def load_marketplace_plugin(
    marketplace_name: str,
    plugin_name: str,
) -> tuple[LoadedPlugin | None, PluginError | None]:
    """
    Download and load a plugin from a marketplace.

    Returns (plugin, error).
    """
    from .marketplace import get_marketplace_plugins

    entries = get_marketplace_plugins(marketplace_name)
    if entries is None:
        return None, PluginError(
            plugin=plugin_name,
            error_type=PluginErrorType.PLUGIN_NOT_FOUND,
            message=f"Marketplace '{marketplace_name}' not found or unreachable",
        )

    entry = None
    for e in entries:
        if e.name == plugin_name:
            entry = e
            break

    if entry is None:
        return None, PluginError(
            plugin=plugin_name,
            error_type=PluginErrorType.PLUGIN_NOT_FOUND,
            message=f"Plugin '{plugin_name}' not found in marketplace '{marketplace_name}'",
        )

    # Download the plugin to cache
    cache_path = _download_marketplace_plugin(marketplace_name, plugin_name, entry)
    if cache_path is None:
        return None, PluginError(
            plugin=plugin_name,
            error_type=PluginErrorType.GENERIC_ERROR,
            message=f"Failed to download plugin '{plugin_name}' from marketplace",
        )

    plugin_or_error = load_plugin_from_path(cache_path)
    if isinstance(plugin_or_error, PluginError):
        return None, plugin_or_error

    plugin = plugin_or_error
    plugin.source_id = f"{plugin_name}@{marketplace_name}"
    return plugin, None


def _download_marketplace_plugin(
    marketplace_name: str,
    plugin_name: str,
    entry: "PluginMarketplaceEntry",  # noqa: F401
) -> Path | None:
    """
    Download a marketplace plugin to the local cache.
    Returns the path to the cached plugin directory.
    """
    import shutil

    state = get_plugin_state()
    config = get_plugin_service_config()
    cache_dir = Path(os.path.expanduser(config.cache_dir))
    cache_dir = cache_dir / marketplace_name / plugin_name

    # Check if already cached
    if cache_dir.exists() and (cache_dir / ".claude-plugin" / "plugin.json").exists():
        return cache_dir

    cache_dir.parent.mkdir(parents=True, exist_ok=True)

    source = entry.source
    if isinstance(source, dict):
        source = PluginSource(**source)
    elif source is None:
        source = PluginSource(source="local")

    if source.source == "github":
        return _clone_github_plugin(source, cache_dir)
    elif source.source == "url":
        return _download_url_plugin(source, cache_dir)
    elif source.source == "local":
        # Local path - just return as-is (validate it exists)
        if source.url and Path(source.url).exists():
            return Path(source.url)
        return None
    else:
        # npm/pip - would need npm/pip installed
        # For now, return None
        return None


def _clone_github_plugin(source: PluginSource, cache_dir: Path) -> Path | None:
    """Clone a plugin from GitHub."""
    if not source.repo:
        return None

    try:
        # Remove existing cache
        if cache_dir.exists():
            shutil.rmtree(cache_dir)

        # Build git URL
        if source.url:
            git_url = source.url
        else:
            git_url = f"https://github.com/{source.repo}.git"

        ref_arg = ["--branch", source.ref] if source.ref else []
        subprocess.run(
            ["git", "clone", "--depth", "1"] + ref_arg + [git_url, str(cache_dir)],
            check=True,
            capture_output=True,
        )
        return cache_dir
    except Exception:
        return None


def _download_url_plugin(source: PluginSource, cache_dir: Path) -> Path | None:
    """Download and extract a plugin from a URL."""
    import shutil
    import tarfile
    import zipfile

    if not source.url:
        return None

    try:
        cache_dir.parent.mkdir(parents=True, exist_ok=True)

        # Download to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp:
            tmp_path = Path(tmp.name)

        urllib.request.urlretrieve(source.url, tmp_path)

        # Detect and extract
        if str(source.url).endswith(".zip"):
            with zipfile.ZipFile(tmp_path) as zf:
                zf.extractall(cache_dir.parent)
        else:
            with tarfile.open(tmp_path) as tf:
                tf.extractall(cache_dir.parent)

        tmp_path.unlink()
        return cache_dir
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_component_path(
    component: str | list[str] | dict | None,
    plugin_dir: Path,
) -> str | None:
    """Resolve a component path relative to the plugin directory."""
    if component is None:
        return None
    if isinstance(component, str):
        resolved = (plugin_dir / component).resolve()
        return str(resolved) if resolved.exists() else None
    if isinstance(component, list) and component:
        return str((plugin_dir / component[0]).resolve())
    if isinstance(component, dict):
        # Take the first key's value
        first_key = next(iter(component))
        val = component[first_key]
        if isinstance(val, str):
            return str((plugin_dir / val).resolve())
        return None
    return None


def _resolve_hooks_config(
    hooks: dict | str | list[str] | None,
    plugin_dir: Path,
) -> dict | None:
    """Resolve hooks configuration."""
    if hooks is None:
        return None
    if isinstance(hooks, dict):
        return hooks
    if isinstance(hooks, str):
        hooks_path = (plugin_dir / hooks).resolve()
        if hooks_path.exists():
            import json
            return json.loads(hooks_path.read_text(encoding="utf-8"))
    return None


def _resolve_servers(servers: dict | str | list[str] | None) -> dict | None:
    """Resolve MCP/LSP server configurations."""
    if servers is None:
        return None
    if isinstance(servers, dict):
        return servers
    return None


def _is_plugin_enabled(plugin_name: str, is_builtin: bool) -> bool:
    """
    Check if a plugin is enabled via settings.
    For now, returns False (plugins must be explicitly enabled).
    In full implementation, this would read from settings.
    """
    return False
