"""Plugin manifest handling for py-claw.

Based on ClaudeCode-main/src/utils/plugins/validatePlugin.ts and schemas.ts
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from py_claw.plugins.types import (
    PluginAuthor,
    PluginError,
    PluginManifest,
    PluginScope,
    PluginInstallationEntry,
    InstalledPluginsFileV2,
    PluginValidationError,
)


def validate_plugin_manifest(manifest: PluginManifest) -> list[str]:
    """Validate a plugin manifest.

    Args:
        manifest: The manifest to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    if not manifest.name:
        errors.append("Plugin name is required")
    elif not re.match(r"^[a-zA-Z0-9_-]+$", manifest.name):
        errors.append(f"Invalid plugin name: {manifest.name}")

    if manifest.version:
        if not re.match(r"^\d+\.\d+\.\d+", manifest.version):
            errors.append(f"Invalid version format: {manifest.version}")

    if manifest.keywords:
        for keyword in manifest.keywords:
            if len(keyword) > 50:
                errors.append(f"Keyword too long: {keyword}")

    return errors


def load_plugin_manifest(plugin_dir: Path) -> PluginManifest:
    """Load and parse a plugin manifest from a directory.

    Args:
        plugin_dir: Directory containing the plugin

    Returns:
        The parsed PluginManifest

    Raises:
        PluginValidationError: If manifest is missing or invalid
    """
    manifest_path = plugin_dir / "plugin.json"

    if not manifest_path.exists():
        raise PluginValidationError(f"Plugin manifest not found: {manifest_path}")

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise PluginValidationError(f"Failed to parse plugin.json: {e}") from e

    if not isinstance(data, dict):
        raise PluginValidationError("Plugin manifest must be a JSON object")

    # Validate required fields
    if "name" not in data:
        raise PluginValidationError("Plugin manifest missing required field: name")

    # Validate and create manifest
    errors = validate_plugin_manifest(PluginManifest(name=data["name"]))
    if errors:
        raise PluginValidationError(f"Invalid plugin manifest: {', '.join(errors)}")

    return PluginManifest.from_dict(data)


def save_plugin_manifest(plugin_dir: Path, manifest: PluginManifest) -> None:
    """Save a plugin manifest to a directory.

    Args:
        plugin_dir: Directory to save the manifest in
        manifest: The manifest to save
    """
    manifest_path = plugin_dir / "plugin.json"
    data = _manifest_to_dict(manifest)
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _manifest_to_dict(manifest: PluginManifest) -> dict[str, Any]:
    """Convert a PluginManifest to a dictionary for JSON serialization."""
    data: dict[str, Any] = {"name": manifest.name}

    if manifest.version:
        data["version"] = manifest.version
    if manifest.description:
        data["description"] = manifest.description
    if manifest.author:
        data["author"] = {
            k: v for k, v in {
                "name": manifest.author.name,
                "email": manifest.author.email,
                "url": manifest.author.url,
            }.items() if v is not None
        }
    if manifest.homepage:
        data["homepage"] = manifest.homepage
    if manifest.repository:
        data["repository"] = manifest.repository
    if manifest.license:
        data["license"] = manifest.license
    if manifest.keywords:
        data["keywords"] = manifest.keywords
    if manifest.dependencies:
        data["dependencies"] = [
            {"name": d.name, "version": d.version}
            for d in manifest.dependencies
            if d.version
        ]

    return data


def load_installed_plugins(path: Path) -> InstalledPluginsFileV2:
    """Load the installed plugins registry file.

    Args:
        path: Path to installed_plugins.json

    Returns:
        The parsed InstalledPluginsFileV2
    """
    if not path.exists():
        return InstalledPluginsFileV2()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return InstalledPluginsFileV2()

    if not isinstance(data, dict):
        return InstalledPluginsFileV2()

    version = data.get("version", 1)

    if version == 2:
        plugins: dict[str, list[PluginInstallationEntry]] = {}
        for plugin_id, entries in data.get("plugins", {}).items():
            if not isinstance(entries, list):
                continue
            parsed_entries: list[PluginInstallationEntry] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                scope_str = entry.get("scope", "user")
                try:
                    scope = PluginScope(scope_str)
                except ValueError:
                    scope = PluginScope.USER
                parsed_entries.append(PluginInstallationEntry(
                    scope=scope,
                    project_path=entry.get("projectPath"),
                    install_path=entry.get("installPath", ""),
                    version=entry.get("version"),
                    installed_at=entry.get("installedAt"),
                    last_updated=entry.get("lastUpdated"),
                    git_commit_sha=entry.get("gitCommitSha"),
                ))
            plugins[plugin_id] = parsed_entries
        return InstalledPluginsFileV2(version=2, plugins=plugins)

    # V1 format - migrate to V2
    return InstalledPluginsFileV2()


def save_installed_plugins(path: Path, data: InstalledPluginsFileV2) -> None:
    """Save the installed plugins registry file.

    Args:
        path: Path to save to
        data: The installed plugins data
    """
    plugins_dict: dict[str, list[dict[str, Any]]] = {}
    for plugin_id, entries in data.plugins.items():
        plugins_dict[plugin_id] = [
            {
                "scope": entry.scope.value,
                "projectPath": entry.project_path,
                "installPath": entry.install_path,
                "version": entry.version,
                "installedAt": entry.installed_at,
                "lastUpdated": entry.last_updated,
                "gitCommitSha": entry.git_commit_sha,
            }
            for entry in entries
        ]

    output = {
        "version": data.version,
        "plugins": plugins_dict,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
