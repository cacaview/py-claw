"""Plugin type definitions for py-claw.

Based on ClaudeCode-main/src/types/plugin.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class PluginScope(Enum):
    """Installation scope for plugins."""

    MANAGED = "managed"  # Enterprise/system-wide (read-only)
    USER = "user"  # User's global settings
    PROJECT = "project"  # Shared project settings
    LOCAL = "local"  # Personal project overrides


@dataclass(frozen=True)
class PluginAuthor:
    """Plugin author information."""

    name: str | None = None
    email: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class DependencyRef:
    """A plugin dependency reference."""

    name: str
    version: str | None = None  # semver range or exact version


@dataclass(frozen=True)
class CommandPath:
    """Path to a command file or directory."""

    source: str  # path string or metadata source


@dataclass(frozen=True)
class CommandMetadata:
    """Metadata for a command defined in plugin manifest."""

    name: str
    description: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class McpServerConfig:
    """MCP server configuration from plugin."""

    command: str
    args: list[str] | None = None
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class LspServerConfig:
    """LSP server configuration from plugin."""

    command: str
    args: list[str] | None = None
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class ChannelDeclaration:
    """MCP server channel declaration."""

    server: str
    channel: str


@dataclass(frozen=True)
class HookConfig:
    """Hook configuration from plugin."""

    path: str | None = None
    settings: dict[str, Any] | None = None


@dataclass(frozen=True)
class SkillPath:
    """Path to a skill directory."""

    source: str  # path string


@dataclass(frozen=True)
class AgentPath:
    """Path to an agent definition."""

    source: str  # path string


@dataclass(frozen=True)
class StylePath:
    """Path to an output style file."""

    source: str  # path string


@dataclass
class PluginManifest:
    """Plugin manifest (plugin.json) definition.

    Corresponds to PluginManifest in TypeScript.
    """

    name: str
    version: str | None = None
    description: str | None = None
    author: PluginAuthor | None = None
    homepage: str | None = None
    repository: str | None = None
    license: str | None = None
    keywords: list[str] | None = None
    # Dependencies: plugins this plugin requires
    dependencies: list[DependencyRef] | None = None

    # Plugin components (all optional)
    commands: CommandPath | list[CommandPath] | dict[str, CommandMetadata] | None = None
    agents: AgentPath | list[AgentPath] | None = None
    skills: SkillPath | list[SkillPath] | None = None
    hooks: HookConfig | None = None
    output_styles: StylePath | list[StylePath] | None = None
    mcp_servers: dict[str, McpServerConfig] | None = None
    lsp_servers: dict[str, LspServerConfig] | None = None
    channels: list[ChannelDeclaration] | None = None
    settings: dict[str, Any] | None = None
    user_config: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        """Create PluginManifest from a dictionary."""
        author_data = data.get("author")
        author = PluginAuthor.from_dict(author_data) if author_data else None

        deps_data = data.get("dependencies", [])
        dependencies = [DependencyRef(**d) if isinstance(d, dict) else DependencyRef(name=str(d))
                       for d in deps_data] if deps_data else None

        mcp_servers = None
        if mcp_data := data.get("mcpServers"):
            mcp_servers = {k: McpServerConfig(**v) if isinstance(v, dict) else McpServerConfig(command=str(v))
                          for k, v in mcp_data.items()}

        lsp_servers = None
        if lsp_data := data.get("lspServers"):
            lsp_servers = {k: LspServerConfig(**v) if isinstance(v, dict) else LspServerConfig(command=str(v))
                          for k, v in lsp_data.items()}

        return cls(
            name=data["name"],
            version=data.get("version"),
            description=data.get("description"),
            author=author,
            homepage=data.get("homepage"),
            repository=data.get("repository"),
            license=data.get("license"),
            keywords=data.get("keywords"),
            dependencies=dependencies,
            commands=data.get("commands"),
            agents=data.get("agents"),
            skills=data.get("skills"),
            hooks=data.get("hooks"),
            output_styles=data.get("outputStyles"),
            mcp_servers=mcp_servers,
            lsp_servers=lsp_servers,
            channels=data.get("channels"),
            settings=data.get("settings"),
            user_config=data.get("userConfig"),
        )


@dataclass
class PluginSource:
    """Source specification for a plugin.

    Corresponds to PluginSource in TypeScript.
    """

    type: Literal["path", "npm", "pip", "url", "github", "git-subdir"]
    path: str | None = None  # for type="path"
    package: str | None = None  # for type="npm", "pip"
    version: str | None = None
    registry: str | None = None  # for type="npm"
    url: str | None = None  # for type="url", "git-subdir"
    repo: str | None = None  # for type="github"
    ref: str | None = None
    sha: str | None = None
    git_url: str | None = None  # for type="git-subdir"
    subdir: str | None = None  # for type="git-subdir"


@dataclass
class PluginMarketplaceEntry:
    """Marketplace plugin entry with source information."""

    name: str
    source: PluginSource
    version: str | None = None
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    # Strict mode: plugin.json required (default True)
    strict: bool = True


@dataclass
class LoadedPlugin:
    """Runtime state of a loaded plugin.

    Corresponds to LoadedPlugin in TypeScript.
    """

    name: str
    manifest: PluginManifest
    path: str
    source: str  # Plugin ID (e.g., "name@marketplace")
    repository: str | None = None
    enabled: bool = True
    is_builtin: bool = False
    sha: str | None = None

    # Component paths
    commands_path: str | None = None
    commands_paths: list[str] | None = None
    commands_metadata: dict[str, CommandMetadata] | None = None
    agents_path: str | None = None
    agents_paths: list[str] | None = None
    skills_path: str | None = None
    skills_paths: list[str] | None = None
    output_styles_path: str | None = None
    output_styles_paths: list[str] | None = None

    # Runtime config
    hooks_config: dict[str, Any] | None = None
    mcp_servers: dict[str, McpServerConfig] | None = None
    lsp_servers: dict[str, LspServerConfig] | None = None
    settings: dict[str, Any] | None = None


@dataclass
class PluginInstallationEntry:
    """Installation metadata for a plugin."""

    scope: PluginScope
    install_path: str = ""
    project_path: str | None = None  # For project/local scopes
    version: str | None = None
    installed_at: str | None = None
    last_updated: str | None = None
    git_commit_sha: str | None = None


@dataclass
class InstalledPluginsFileV2:
    """V2 format for installed_plugins.json."""

    version: int = 2
    plugins: dict[str, list[PluginInstallationEntry]] = field(default_factory=dict)


# Plugin error types
class PluginError(Exception):
    """Base class for plugin errors."""

    pass


class PluginNotFoundError(PluginError):
    """Plugin not found error."""

    def __init__(self, plugin_id: str, marketplace: str | None = None) -> None:
        self.plugin_id = plugin_id
        self.marketplace = marketplace
        super().__init__(f"Plugin not found: {plugin_id}")


class PluginLoadError(PluginError):
    """Plugin load error."""

    pass


class PluginDependencyError(PluginError):
    """Plugin dependency error."""

    def __init__(self, plugin: str, dependency: str, reason: str) -> None:
        self.plugin = plugin
        self.dependency = dependency
        self.reason = reason
        super().__init__(f"Plugin {plugin} has unsatisfied dependency: {dependency} ({reason})")


class PluginValidationError(PluginError):
    """Plugin manifest validation error."""

    pass
