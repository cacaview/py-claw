"""
LSP server configuration.

Loads LSP server configurations, typically from plugin declarations.
Based on ClaudeCode-main/src/services/lsp/config.ts.
"""
from __future__ import annotations

from typing import Any

from py_claw.services.lsp.types import ScopedLspServerConfig


def load_lsp_configs_from_settings(settings: dict[str, Any]) -> list[ScopedLspServerConfig]:
    """Load LSP server configurations from settings.

    Settings format:
        "lsp": {
            "servers": [
                {
                    "name": "pylsp",
                    "command": "pylsp",
                    "scope": ".py"
                }
            ]
        }

    Also supports loading from MCP server configs that declare LSP capabilities.
    """
    configs: list[ScopedLspServerConfig] = []
    lsp_settings = settings.get("lsp", {})
    servers = lsp_settings.get("servers", [])

    for server in servers:
        if not isinstance(server, dict):
            continue

        name = server.get("name")
        if not name:
            continue

        command = server.get("command")
        if not command:
            continue

        config = ScopedLspServerConfig(
            name=str(name),
            command=str(command),
            args=[str(a) for a in server.get("args", [])],
            scope=server.get("scope"),
            restartOnCrash=server.get("restartOnCrash", True),
            shutdownTimeout=int(server.get("shutdownTimeout", 5000)),
            env=server.get("env"),
            cwd=server.get("cwd"),
        )
        configs.append(config)

    return configs


# Built-in server configurations for common languages
BUILTIN_LSP_CONFIGS: list[ScopedLspServerConfig] = [
    # Python
    ScopedLspServerConfig(
        name="pylsp",
        command="pylsp",
        scope=".py",
        restartOnCrash=True,
    ),
    # TypeScript/JavaScript
    ScopedLspServerConfig(
        name="typescript-language-server",
        command="typescript-language-server",
        args=["--stdio"],
        scope=".ts",
        restartOnCrash=True,
    ),
    ScopedLspServerConfig(
        name="typescript-language-server",
        command="typescript-language-server",
        args=["--stdio"],
        scope=".js",
        restartOnCrash=True,
    ),
    # Rust
    ScopedLspServerConfig(
        name="rust-analyzer",
        command="rust-analyzer",
        scope=".rs",
        restartOnCrash=True,
    ),
    # Go
    ScopedLspServerConfig(
        name="gopls",
        command="gopls",
        scope=".go",
        restartOnCrash=True,
    ),
    # Ruby
    ScopedLspServerConfig(
        name="solargraph",
        command="solargraph",
        scope=".rb",
        restartOnCrash=True,
    ),
]
