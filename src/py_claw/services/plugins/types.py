"""
Plugin system type definitions.

Implements the Python equivalent of the TypeScript plugin type system
(src/types/plugin.ts, src/utils/plugins/schemas.ts).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PluginSourceType(str, Enum):
    """Plugin source type - how a plugin is fetched/installed."""
    LOCAL = "local"  # relative path or local directory
    NPM = "npm"  # from npm registry
    PIP = "pip"  # from PyPI
    URL = "url"  # from a direct URL
    GITHUB = "github"  # from a GitHub repo


class PluginScope(str, Enum):
    """Installation scope - determines persistence."""
    MANAGED = "managed"  # enterprise/system-wide (read-only)
    USER = "user"  # ~/.claude/settings.json
    PROJECT = "project"  # $project/.claude/settings.json (shared)
    LOCAL = "local"  # $project/.claude/settings.local.json (personal override)


class PluginErrorType(str, Enum):
    """Plugin error types (discriminated union equivalents)."""
    PATH_NOT_FOUND = "path-not-found"
    GIT_AUTH_FAILED = "git-auth-failed"
    PLUGIN_NOT_FOUND = "plugin-not-found"
    MARKETPLACE_BLOCKED_BY_POLICY = "marketplace-blocked-by-policy"
    DEPENDENCY_UNSATISFIED = "dependency-unsatisfied"
    MANIFEST_INVALID = "manifest-invalid"
    GENERIC_ERROR = "generic-error"


class PluginStatus(str, Enum):
    """Plugin enabled status."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Source / Manifest models
# ---------------------------------------------------------------------------


class PluginSource(BaseModel):
    """How to fetch a plugin."""
    model_config = ConfigDict(extra="allow")

    source: Literal["local", "npm", "pip", "url", "github"]
    package: str | None = None  # npm/pip package name
    version: str | None = None
    registry: str | None = None
    url: str | None = None
    repo: str | None = None  # github: "owner/repo"
    ref: str | None = None  # git branch/tag/ref
    path: str | None = None  # for git-subdir


class PluginAuthor(BaseModel):
    """Plugin author information."""
    name: str
    email: str | None = None
    url: str | None = None


class PluginManifest(BaseModel):
    """plugin.json manifest format - the core plugin descriptor."""
    model_config = ConfigDict(extra="allow")

    name: str  # kebab-case required
    version: str | None = None
    description: str | None = None
    author: PluginAuthor | dict | None = None
    homepage: str | None = None
    repository: str | None = None
    license: str | None = None
    keywords: list[str] | None = None
    # Component path overrides
    commands: str | list[str] | dict | None = None
    agents: str | list[str] | dict | None = None
    skills: str | list[str] | None = None
    hooks: dict | str | list[str] | None = None
    mcpServers: dict | str | list[str] | None = None
    lspServers: dict | str | list[str] | None = None
    # User configuration schema
    userConfig: dict | None = None
    channels: list[dict] | None = None
    settings: dict | None = None


class MarketplaceManifest(BaseModel):
    """marketplace.json format - a plugin marketplace index."""
    model_config = ConfigDict(extra="allow")

    name: str
    owner: PluginAuthor | dict
    plugins: list["PluginMarketplaceEntry"] = Field(default_factory=list)
    forceRemoveDeletedPlugins: bool = False
    metadata: dict | None = None


class PluginMarketplaceEntry(BaseModel):
    """A single plugin entry in a marketplace."""
    model_config = ConfigDict(extra="allow")

    name: str
    source: dict | PluginSource | None = None
    description: str | None = None
    version: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    strict: bool = True  # require plugin.json


# ---------------------------------------------------------------------------
# Loaded plugin representation
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LoadedPlugin:
    """A loaded plugin instance."""
    name: str
    manifest: PluginManifest
    path: str  # absolute path to plugin directory
    source_id: str  # e.g. "my-plugin@marketplace" or "my-plugin@builtin"
    enabled: bool = False
    is_builtin: bool = False
    version: str | None = None
    repository: str | None = None
    # Component paths (resolved)
    commands_path: str | None = None
    agents_path: str | None = None
    skills_path: str | None = None
    hooks_config: dict | None = None
    mcp_servers: dict | None = None
    lsp_servers: dict | None = None
    settings: dict | None = None
    error: str | None = None  # load error if any

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.manifest.description,
            "enabled": self.enabled,
            "builtin": self.is_builtin,
            "path": self.path,
            "source": self.source_id,
            "repository": self.repository,
        }


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PluginError:
    """Plugin error with type discrimination."""
    plugin: str
    error_type: PluginErrorType
    message: str

    def to_dict(self) -> dict:
        return {
            "plugin": self.plugin,
            "type": self.error_type.value,
            "message": self.message,
        }


@dataclass(slots=True)
class InstallRecord:
    """A single installation record for a plugin."""
    scope: PluginScope
    install_path: str
    version: str | None = None
    project_path: str | None = None  # for project-scope installs

    def to_dict(self) -> dict:
        return {
            "scope": self.scope.value,
            "installPath": self.install_path,
            "version": self.version,
            "projectPath": self.project_path,
        }


@dataclass(slots=True)
class FlaggedPlugin:
    """A delisted/flagged plugin entry."""
    flagged_at: str  # ISO timestamp
    seen_at: str | None = None  # 48hr expiry timestamp


# ---------------------------------------------------------------------------
# Operation result types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PluginOperationResult:
    """Result of a plugin operation."""
    success: bool
    plugin: str | None = None
    message: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "plugin": self.plugin,
            "message": self.message,
            "error": self.error,
        }


@dataclass(slots=True)
class MarketplaceConfig:
    """Configuration for a known marketplace."""
    name: str
    url: str
    owner: str | None = None
    description: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "owner": self.owner,
            "description": self.description,
        }


# MarketplaceManifest forward ref resolution
PluginMarketplaceEntry.model_rebuild()
