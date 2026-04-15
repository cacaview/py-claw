"""Chrome Extension integration service.

Re-implements ClaudeCode-main/src/utils/claudeInChrome/
"""
from __future__ import annotations

from py_claw.services.chrome.common import (
    CLAUDE_IN_CHROME_MCP_SERVER_NAME,
    CHROME_EXTENSION_URL,
    CHROME_PERMISSIONS_URL,
    CHROME_RECONNECT_URL,
    detect_available_browser,
    get_all_browser_data_paths,
    open_in_chrome,
)
from py_claw.services.chrome.setup import (
    is_chrome_extension_installed,
    should_enable_claude_in_chrome,
)

__all__ = [
    "CLAUDE_IN_CHROME_MCP_SERVER_NAME",
    "CHROME_EXTENSION_URL",
    "CHROME_PERMISSIONS_URL",
    "CHROME_RECONNECT_URL",
    "detect_available_browser",
    "get_all_browser_data_paths",
    "is_chrome_extension_installed",
    "open_in_chrome",
    "should_enable_claude_in_chrome",
]