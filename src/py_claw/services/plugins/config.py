"""
Plugin service configuration.

Manages built-in plugin definitions and plugin system configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Builtin Plugin Definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BuiltinPluginDefinition:
    """Definition of a built-in plugin that ships with py-claw."""
    name: str
    description: str
    version: str | None = None
    # Paths within the plugin package
    commands_path: str | None = None
    agents_path: str | None = None
    skills_path: str | None = None
    hooks_config: dict | None = None
    mcp_servers: dict | None = None
    lsp_servers: dict | None = None
    is_available: bool = True  # can be overridden by env/feature flag


# Registry of built-in plugins.
# These appear in /plugin list under "Built-in" and can be toggled via settings.
BUILTIN_PLUGINS: dict[str, BuiltinPluginDefinition] = {}


def is_builtin_plugin(plugin_id: str) -> bool:
    """Check if a plugin ID refers to a built-in plugin."""
    if "@builtin" in plugin_id:
        name = plugin_id.replace("@builtin", "")
        return name in BUILTIN_PLUGINS
    name = plugin_id
    return name in BUILTIN_PLUGINS


def get_builtin_plugin(name: str) -> BuiltinPluginDefinition | None:
    """Get a built-in plugin definition by name."""
    return BUILTIN_PLUGINS.get(name)


def register_builtin_plugin(definition: BuiltinPluginDefinition) -> None:
    """Register a new built-in plugin definition."""
    BUILTIN_PLUGINS[definition.name] = definition


# ---------------------------------------------------------------------------
# Plugin Service Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PluginServiceConfig:
    """Configuration for the plugin service."""
    enabled: bool = True
    # Cache directory for installed plugins
    cache_dir: str = "~/.claude/plugins/cache"
    # Marketplace manifest cache TTL in seconds (default 1 hour)
    marketplace_cache_ttl: float = 3600.0
    # Allow installing from untrusted sources
    allow_unsafe_sources: bool = False
    # Plugin directory for session-only plugins (--plugin-dir flag)
    session_plugin_dir: str | None = None

    @classmethod
    def from_env(cls) -> PluginServiceConfig:
        """Create config from environment variables."""
        cache_dir = os.environ.get("CLAUDE_PLUGIN_CACHE_DIR", "~/.claude/plugins/cache")
        return cls(
            enabled=os.environ.get("CLAUDE_PLUGINS_ENABLED", "true").lower() != "false",
            cache_dir=cache_dir,
            allow_unsafe_sources=os.environ.get("CLAUDE_PLUGIN_ALLOW_UNSAFE", "false").lower() == "true",
            session_plugin_dir=os.environ.get("CLAUDE_SESSION_PLUGIN_DIR"),
        )


# Global config instance
_config: PluginServiceConfig | None = None


def get_plugin_service_config() -> PluginServiceConfig:
    """Get the current plugin service configuration."""
    global _config
    if _config is None:
        _config = PluginServiceConfig.from_env()
    return _config


def set_plugin_service_config(config: PluginServiceConfig) -> None:
    """Set the plugin service configuration."""
    global _config
    _config = config
