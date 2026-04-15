"""
Permission prompts over channels (Telegram, iMessage, Discord).

Mirrors: ClaudeCode-main/src/services/mcp/channelPermissions.ts

When CC hits a permission dialog, it ALSO sends the prompt via active channels
and races the reply against local UI / bridge / hooks / classifier. First
resolver wins via claim().

Inbound is a structured event: the server parses the user's "yes tbxkq"
reply and emits notifications/claude/channel/permission with
{request_id, behavior}. CC never sees the reply as text — approval
requires the server to deliberately emit that specific event, not just
relay content.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

# Reply format spec for channel servers to implement:
#   /^\s*(y|yes|n|no)\s+([a-km-z]{5})\s*$/i
# 5 lowercase letters, no 'l' (looks like 1/I). Case-insensitive.
PERMISSION_REPLY_RE = re.compile(r"^\s*(y|yes|n|no)\s+([a-km-z]{5})\s*$", re.IGNORECASE)

# 25-letter alphabet: a-z minus 'l' (looks like 1/I). 25^5 ≈ 9.8M space.
ID_ALPHABET = "abcdefghijkmnopqrstuvwxyz"

# Substring blocklist — 5 random letters can spell things
ID_AVOID_SUBSTRINGS = [
    "fuck", "shit", "cunt", "cock", "dick", "twat", "piss", "crap", "bitch",
    "whore", "ass", "tit", "cum", "fag", "dyke", "nig", "kike", "rape", "nazi",
    "damn", "poo", "pee", "wank", "anus",
]


def hash_to_id(input_str: str) -> str:
    """
    Generate a short ID from a string using FNV-1a hash.

    Args:
        input_str: Input string to hash

    Returns:
        5-character short ID
    """
    h = 0x811C9DC5
    for char in input_str:
        h ^= ord(char)
        h = (h * 0x01000193) & 0xFFFFFFFF
    h = h & 0xFFFFFFFF

    result = ""
    for _ in range(5):
        result = ID_ALPHABET[h % 25] + result
        h //= 25
    return result


def short_request_id(tool_use_id: str) -> str:
    """
    Generate a short ID from a toolUseID.

    5 letters from a 25-char alphabet (a-z minus 'l' — looks like 1/I).
    Re-hashes with a salt suffix if the result contains a blocklisted substring.

    Args:
        tool_use_id: The tool use ID to hash

    Returns:
        5-letter short ID
    """
    candidate = hash_to_id(tool_use_id)
    for salt in range(10):
        if not any(bad in candidate for bad in ID_AVOID_SUBSTRINGS):
            return candidate
        candidate = hash_to_id(f"{tool_use_id}:{salt}")
    return candidate


def truncate_for_preview(input_data: Any, max_chars: int = 200) -> str:
    """
    Truncate tool input to a phone-sized JSON preview.

    200 chars is roughly 3 lines on a narrow phone screen.

    Args:
        input_data: Input to truncate
        max_chars: Maximum characters

    Returns:
        Truncated string
    """
    try:
        s = json.dumps(input_data)
        return s[:max_chars] + "…" if len(s) > max_chars else s
    except Exception:
        return "(unserializable)"


def filter_permission_relay_clients(
    clients: list[dict[str, Any]],
    is_in_allowlist: Callable[[str], bool],
) -> list[dict[str, Any]]:
    """
    Filter MCP clients down to those that can relay permission prompts.

    Three conditions, ALL required:
    1. type === 'connected'
    2. In the session's --channels allowlist
    3. Declares BOTH capabilities (claude/channel and claude/channel/permission)

    Args:
        clients: List of MCP clients
        is_in_allowlist: Function to check if server is in allowlist

    Returns:
        Filtered list of clients that can relay permission prompts
    """
    result = []
    for client in clients:
        if client.get("type") != "connected":
            continue
        if not is_in_allowlist(client.get("name", "")):
            continue

        capabilities = client.get("capabilities") or {}
        experimental = capabilities.get("experimental") or {}

        if experimental.get("claude/channel") is None:
            continue
        if experimental.get("claude/channel/permission") is None:
            continue

        result.append(client)
    return result


class ChannelPermissionCallbacks:
    """
    Factory for channel permission callbacks.

    The pending Map is closed over — NOT module-level, NOT in AppState.
    Same lifetime pattern as replBridgePermissionCallbacks.
    """

    def __init__(self) -> None:
        self._pending: dict[str, list[Callable[[dict[str, str]], None]]] = {}

    def on_response(
        self,
        request_id: str,
        handler: Callable[[dict[str, str]], None],
    ) -> Callable[[], None]:
        """
        Register a resolver for a request ID.

        Args:
            request_id: The request ID
            handler: Callback when response received

        Returns:
            Unsubscribe function
        """
        # Lowercase for case-insensitive matching
        key = request_id.lower()
        if key not in self._pending:
            self._pending[key] = []
        self._pending[key].append(handler)

        def unsubscribe() -> None:
            if key in self._pending:
                self._pending[key] = [h for h in self._pending[key] if h != handler]
                if not self._pending[key]:
                    del self._pending[key]

        return unsubscribe

    def resolve(
        self,
        request_id: str,
        behavior: str,
        from_server: str,
    ) -> bool:
        """
        Resolve a pending request from a structured channel event.

        Returns True if the ID was pending.

        Args:
            request_id: The request ID
            behavior: 'allow' or 'deny'
            from_server: Server that sent the response

        Returns:
            True if request was pending and resolved
        """
        key = request_id.lower()
        handlers = self._pending.get(key)
        if not handlers:
            return False

        # Delete BEFORE calling — if handler throws or re-enters,
        # the entry is already gone
        del self._pending[key]

        response = {"behavior": behavior, "fromServer": from_server}
        for handler in handlers:
            handler(response)
        return True


def create_channel_permission_callbacks() -> ChannelPermissionCallbacks:
    """
    Create a new ChannelPermissionCallbacks instance.

    Returns:
        New callbacks instance
    """
    return ChannelPermissionCallbacks()
