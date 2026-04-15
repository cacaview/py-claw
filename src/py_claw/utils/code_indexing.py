"""
Code indexing tool detection utility.

Detects usage of common code indexing solutions like Sourcegraph, Cody, etc.
both via CLI commands and MCP server integrations.
"""
from __future__ import annotations

from typing import Literal

# Known code indexing tool identifiers
CodeIndexingTool = Literal[
    # Code search engines
    "sourcegraph",
    "hound",
    "seagoat",
    "bloop",
    "gitloop",
    # AI coding assistants with indexing
    "cody",
    "aider",
    "continue",
    "github-copilot",
    "cursor",
    "tabby",
    "codeium",
    "tabnine",
    "augment",
    "windsurf",
    "aide",
    "pieces",
    "qodo",
    "amazon-q",
    "gemini",
    # MCP code indexing servers
    "claude-context",
    "code-index-mcp",
    "local-code-search",
    "autodev-codebase",
    # Context providers
    "openctx",
]

# Mapping of CLI command prefixes to code indexing tools
CLI_COMMAND_MAPPING: dict[str, CodeIndexingTool] = {
    # Sourcegraph ecosystem
    "src": "sourcegraph",
    "cody": "cody",
    # AI coding assistants
    "aider": "aider",
    "tabby": "tabby",
    "tabnine": "tabnine",
    "augment": "augment",
    "pieces": "pieces",
    "qodo": "qodo",
    "aide": "aide",
    # Code search tools
    "hound": "hound",
    "seagoat": "seagoat",
    "bloop": "bloop",
    "gitloop": "gitloop",
    # Cloud provider AI assistants
    "q": "amazon-q",
    "gemini": "gemini",
}

# MCP server name patterns for code indexing tools
MCP_SERVER_PATTERNS: list[tuple[str, CodeIndexingTool]] = [
    # Sourcegraph ecosystem
    ("sourcegraph", "sourcegraph"),
    ("cody", "cody"),
    ("openctx", "openctx"),
    # AI coding assistants
    ("aider", "aider"),
    ("continue", "continue"),
    ("github[-_]?copilot", "github-copilot"),
    ("copilot", "github-copilot"),
    ("cursor", "cursor"),
    ("tabby", "tabby"),
    ("codeium", "codeium"),
    ("tabnine", "tabnine"),
    ("augment[-_]?code", "augment"),
    ("augment", "augment"),
    ("windsurf", "windsurf"),
    ("aide", "aide"),
    ("codestory", "aide"),
    ("pieces", "pieces"),
    ("qodo", "qodo"),
    ("amazon[-_]?q", "amazon-q"),
    ("gemini[-_]?code[-_]?assist", "gemini"),
    ("gemini", "gemini"),
    # Code search tools
    ("hound", "hound"),
    ("seagoat", "seagoat"),
    ("bloop", "bloop"),
    ("gitloop", "gitloop"),
    # MCP code indexing servers
    ("claude[-_]?context", "claude-context"),
    ("code[-_]?index[-_]?mcp", "code-index-mcp"),
    ("code[-_]?index", "code-index-mcp"),
    ("local[-_]?code[-_]?search", "local-code-search"),
    ("codebase", "autodev-codebase"),
    ("autodev[-_]?codebase", "autodev-codebase"),
    ("code[-_]?context", "claude-context"),
]


def detect_code_indexing_from_command(command: str) -> CodeIndexingTool | None:
    """
    Detects if a bash command is using a code indexing CLI tool.

    Args:
        command: The full bash command string

    Returns:
        The code indexing tool identifier, or None if not a code indexing command

    Examples:
        >>> detect_code_indexing_from_command('src search "pattern"')
        'sourcegraph'
        >>> detect_code_indexing_from_command('cody chat --message "help"')
        'cody'
        >>> detect_code_indexing_from_command('ls -la')
        None
    """
    import re

    trimmed = command.strip()
    if not trimmed:
        return None

    first_word = trimmed.split()[0].lower() if trimmed.split() else None

    if not first_word:
        return None

    # Check for npx/bunx prefixed commands
    if first_word in ("npx", "bunx"):
        parts = trimmed.split()
        if len(parts) > 1:
            second_word = parts[1].lower()
            return CLI_COMMAND_MAPPING.get(second_word)
        return None

    return CLI_COMMAND_MAPPING.get(first_word)


def detect_code_indexing_from_mcp_tool(tool_name: str) -> CodeIndexingTool | None:
    """
    Detects if an MCP tool is from a code indexing server.

    Args:
        tool_name: The MCP tool name (format: mcp__serverName__toolName)

    Returns:
        The code indexing tool identifier, or None if not a code indexing tool

    Examples:
        >>> detect_code_indexing_from_mcp_tool('mcp__sourcegraph__search')
        'sourcegraph'
        >>> detect_code_indexing_from_mcp_tool('mcp__cody__chat')
        'cody'
        >>> detect_code_indexing_from_mcp_tool('mcp__filesystem__read')
        None
    """
    import re

    if not tool_name.startswith("mcp__"):
        return None

    parts = tool_name.split("__")
    if len(parts) < 3:
        return None

    server_name = parts[1]
    if not server_name:
        return None

    for pattern_str, tool in MCP_SERVER_PATTERNS:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        if pattern.match(server_name):
            return tool

    return None


def detect_code_indexing_from_mcp_server_name(server_name: str) -> CodeIndexingTool | None:
    """
    Detects if an MCP server name corresponds to a code indexing tool.

    Args:
        server_name: The MCP server name

    Returns:
        The code indexing tool identifier, or None if not a code indexing server

    Examples:
        >>> detect_code_indexing_from_mcp_server_name('sourcegraph')
        'sourcegraph'
        >>> detect_code_indexing_from_mcp_server_name('filesystem')
        None
    """
    import re

    for pattern_str, tool in MCP_SERVER_PATTERNS:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        if pattern.match(server_name):
            return tool

    return None
