"""
Plugin manifest parsing and validation.

Handles loading and validating plugin.json manifests from plugin directories,
including path traversal security checks.
"""
from __future__ import annotations

import re
from pathlib import Path

from .types import PluginAuthor, PluginError, PluginErrorType, PluginManifest


# Path traversal patterns
_PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"(^|/)\.\.(/|$)"),
    re.compile(r"^~"),
    re.compile(r"^[A-Za-z]:"),  # Windows absolute paths
]


def load_plugin_manifest(plugin_dir: Path) -> PluginManifest | PluginError:
    """
    Load and parse a plugin.json manifest from a plugin directory.

    Returns PluginManifest on success, PluginError on failure.
    """
    manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
    if not manifest_path.exists():
        # Also try plugin.json at root of plugin dir (V1 format)
        manifest_path = plugin_dir / "plugin.json"

    if not manifest_path.exists():
        return PluginError(
            plugin=str(plugin_dir),
            error_type=PluginErrorType.PATH_NOT_FOUND,
            message=f"Manifest not found: {manifest_path}",
        )

    try:
        import json
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return PluginError(
            plugin=str(plugin_dir),
            error_type=PluginErrorType.MANIFEST_INVALID,
            message=f"Invalid JSON in manifest: {e}",
        )
    except Exception as e:
        return PluginError(
            plugin=str(plugin_dir),
            error_type=PluginErrorType.MANIFEST_INVALID,
            message=f"Failed to read manifest: {e}",
        )

    # Validate name is kebab-case
    name = data.get("name", "")
    if not isinstance(name, str) or not name:
        return PluginError(
            plugin=str(plugin_dir),
            error_type=PluginErrorType.MANIFEST_INVALID,
            message="Plugin name is required",
        )

    if not _is_valid_plugin_name(name):
        return PluginError(
            plugin=str(plugin_dir),
            error_type=PluginErrorType.MANIFEST_INVALID,
            message=f"Plugin name must be kebab-case: '{name}'",
        )

    # Validate paths in manifest
    path_errors = validate_manifest_paths(data, plugin_dir)
    if path_errors:
        return PluginError(
            plugin=str(plugin_dir),
            error_type=PluginErrorType.MANIFEST_INVALID,
            message=f"Path traversal detected: {', '.join(path_errors)}",
        )

    try:
        # Parse author if present
        if "author" in data:
            author_data = data["author"]
            if isinstance(author_data, str):
                data["author"] = {"name": author_data}
            elif isinstance(author_data, dict):
                data["author"] = author_data

        manifest = PluginManifest(**data)
        return manifest
    except Exception as e:
        return PluginError(
            plugin=str(plugin_dir),
            error_type=PluginErrorType.MANIFEST_INVALID,
            message=f"Invalid manifest: {e}",
        )


def validate_manifest_paths(manifest_data: dict, plugin_dir: Path) -> list[str]:
    """
    Check manifest path fields for path traversal attempts.
    Returns list of invalid paths found.
    """
    invalid_paths: list[str] = []

    # Fields that can contain paths
    path_fields = [
        "commands",
        "agents",
        "skills",
        "hooks",
        "mcpServers",
        "lspServers",
        "settings",
    ]

    def check_value(key: str, value) -> None:
        if isinstance(value, str):
            if _has_path_traversal(value):
                invalid_paths.append(f"{key}={value}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and _has_path_traversal(item):
                    invalid_paths.append(f"{key} contains {item}")
        elif isinstance(value, dict):
            for subkey, subvalue in value.items():
                if subkey in ("command", "args", "script", "path"):
                    if isinstance(subvalue, str) and _has_path_traversal(subvalue):
                        invalid_paths.append(f"{key}.{subkey}={subvalue}")
                elif subkey in ("mcpServers", "lspServers") and isinstance(subvalue, dict):
                    for server_key, server_val in subvalue.items():
                        if isinstance(server_val, dict):
                            for attr in ("command", "args", "path"):
                                if attr in server_val and isinstance(server_val[attr], str):
                                    if _has_path_traversal(server_val[attr]):
                                        invalid_paths.append(f"{key}.{server_key}.{attr}")

    for field_name in path_fields:
        if field_name in manifest_data:
            check_value(field_name, manifest_data[field_name])

    return invalid_paths


def _has_path_traversal(value: str) -> bool:
    """Check if a string contains path traversal patterns."""
    for pattern in _PATH_TRAVERSAL_PATTERNS:
        if pattern.search(value):
            return True
    return False


def _is_valid_plugin_name(name: str) -> bool:
    """Check if a plugin name is valid kebab-case."""
    if not name:
        return False
    # Must be lowercase alphanumeric and hyphens only
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", name):
        return False
    # Cannot start or end with hyphen
    if name.startswith("-") or name.endswith("-"):
        return False
    return True


def validate_manifest_safety(manifest: PluginManifest) -> list[str]:
    """
    Additional safety validations for a parsed manifest.
    Returns list of warning strings (not errors).
    """
    warnings: list[str] = []

    if manifest.license and manifest.license.lower() in ("proprietary", "no-license"):
        warnings.append(f"Non-open license: {manifest.license}")

    if manifest.repository and not manifest.repository.startswith(
        ("https://github.com/", "git@github.com:", "https://gitlab.com/")
    ):
        warnings.append(f"Non-standard repository URL: {manifest.repository}")

    return warnings
