"""
Embedded tools detection.

Detects whether the current binary has embedded search tools
(bfs/ugrep) similar to embedded ripgrep.

Mirrors TS embeddedTools.ts behavior.
"""
from __future__ import annotations

import os
import sys

from .env import is_env_truthy


def has_embedded_search_tools() -> bool:
    """
    Check if this build has bfs/ugrep embedded in the binary.

    Returns True for ant-native builds where:
    - find and grep are shadowed by shell functions invoking the bun binary
    - Dedicated Glob/Grep tools are removed from the registry
    - Prompt guidance about find/grep is omitted

    Returns:
        True if embedded search tools are available
    """
    if not is_env_truthy(os.environ.get("EMBEDDED_SEARCH_TOOLS", "")):
        return False

    entrypoint = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")
    # Not available in SDK entrypoints
    excluded = {"sdk-ts", "sdk-py", "sdk-cli", "local-agent"}
    return entrypoint not in excluded


def embedded_search_tools_binary_path() -> str:
    """
    Get the path to the binary containing embedded search tools.

    Returns:
        Path to the executable with embedded tools
    """
    return sys.executable
