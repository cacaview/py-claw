"""
Channel permissions and notifications for MCP servers.

This module handles permission prompts over channels (Telegram, iMessage, Discord).
When Claude Code hits a permission dialog, it can also send the prompt via active
channels and race the reply against local UI/bridge/hooks/classifier.

Inbound is a structured event: the server parses the user's "yes tbxkq"
reply and emits notifications/claude/channel/permission with {request_id, behavior}.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 25-letter alphabet: a-z minus 'l' (looks like 1/I). 25^5 ≈ 9.8M space.
ID_ALPHABET = "abcdefghijkmnopqrstuvwxyz"

# Substring blocklist — 5 random letters can spell things
# prettier-ignore
ID_AVOID_SUBSTRINGS = [
    "fuck", "shit", "cunt", "cock", "dick", "twat", "piss", "crap",
    "bitch", "whore", "ass", "tit", "cum", "fag", "dyke", "nig",
    "kike", "rape", "nazi", "damn", "poo", "pee", "wank", "anus",
]


def _fnv1a_hash(input_str: str) -> int:
    """FNV-1a hash → uint32."""
    h = 0x811c9dc5
    for c in input_str:
        h ^= ord(c)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def short_request_id(tool_use_id: str) -> str:
    """Generate a short ID from a toolUseID.

    5 letters from a 25-char alphabet (a-z minus 'l').
    Letters-only so phone users don't switch keyboard modes.
    Re-hashes with a salt suffix if the result contains a blocklisted substring.
    """
    for salt in range(10):
        candidate_raw = _fnv1a_hash(f"{tool_use_id}:{salt}" if salt else tool_use_id)
        h = candidate_raw
        s = ""
        for _ in range(5):
            s += ID_ALPHABET[h % 25]
            h //= 25
        if not any(bad in s for bad in ID_AVOID_SUBSTRINGS):
            return s
    # Fallback: just return last 5 chars of hex (shouldn't happen)
    return tool_use_id[-5:] if len(tool_use_id) >= 5 else tool_use_id.ljust(5, "x")


# Permission reply regex: /^\s*(y|yes|n|no)\s+([a-km-z]{5})\s*$/i
PERMISSION_REPLY_RE = re.compile(r"^\s*(y|yes|n|no)\s+([a-km-z]{5})\s*$", re.IGNORECASE)


def truncate_for_preview(input_data: Any, max_chars: int = 200) -> str:
    """Truncate tool input to a phone-sized JSON preview."""
    try:
        s = json.dumps(input_data)
        return s[:max_chars] + "…" if len(s) > max_chars else s
    except (TypeError, ValueError):
        return "(unserializable)"


# ─── Channel Permission Callbacks ───────────────────────────────────────────────


@dataclass
class ChannelPermissionResponse:
    """Response from a channel permission reply."""
    behavior: str  # 'allow' | 'deny'
    from_server: str  # Which channel server (e.g., "plugin:telegram:tg")


class ChannelPermissionCallbacks:
    """Callbacks for channel permission relay.

    First resolver wins via claim(). The pending Map is closed over —
    not module-level, not in AppState (functions-in-state causes issues
    with equality/serialization).
    """

    def __init__(self) -> None:
        self._pending: dict[str, Callable[[ChannelPermissionResponse], None]] = {}
        self._lock = threading.Lock()

    def on_response(
        self,
        request_id: str,
        handler: Callable[[ChannelPermissionResponse], None],
    ) -> Callable[[], None]:
        """Register a resolver for a request ID.

        Returns an unsubscribe function.
        """
        key = request_id.lower()
        with self._lock:
            self._pending[key] = handler
        return lambda: self._unsubscribe(key)

    def _unsubscribe(self, key: str) -> None:
        with self._lock:
            self._pending.pop(key, None)

    def resolve(
        self,
        request_id: str,
        behavior: str,
        from_server: str,
    ) -> bool:
        """Resolve a pending request from a structured channel event.

        Returns True if the ID was pending.
        """
        key = request_id.lower()
        with self._lock:
            resolver = self._pending.pop(key, None)
        if not resolver:
            return False
        resolver(ChannelPermissionResponse(behavior=behavior, from_server=from_server))
        return True


def create_channel_permission_callbacks() -> ChannelPermissionCallbacks:
    """Factory for channel permission callbacks object."""
    return ChannelPermissionCallbacks()


# ─── Permission Relay Client Filter ────────────────────────────────────────────


def filter_permission_relay_clients(
    clients: list[dict[str, Any]],
    is_in_allowlist: Callable[[str], bool],
) -> list[dict[str, Any]]:
    """Filter MCP clients down to those that can relay permission prompts.

    Three conditions, ALL required: connected + in the session's --channels
    allowlist + declares BOTH capabilities.

    Returns clients with type 'connected'.
    """
    result = []
    for c in clients:
        if c.get("type") != "connected":
            continue
        if not is_in_allowlist(c.get("name", "")):
            continue
        caps = c.get("capabilities", {})
        exp = caps.get("experimental", {})
        if exp.get("claude/channel") is None:
            continue
        if exp.get("claude/channel/permission") is None:
            continue
        result.append(c)
    return result


# ─── Channel Gate ───────────────────────────────────────────────────────────────


@dataclass
class ChannelGateResult:
    """Result of gating a channel server."""
    action: str  # 'register' | 'skip'
    kind: str | None = None  # 'capability' | 'disabled' | 'auth' | 'policy' | 'session' | 'marketplace' | 'allowlist'
    reason: str | None = None


def is_channel_permission_relay_enabled() -> bool:
    """Check if channel permission relay is enabled via GrowthBook gate."""
    # In Python impl, we check an environment variable as a simplified version
    import os
    return os.environ.get("CLAUDE_CODE_CHANNEL_PERMISSIONS", "").lower() in ("1", "true", "yes")


def gate_channel_server(
    server_name: str,
    capabilities: dict[str, Any] | None,
    plugin_source: str | None = None,
    is_channels_enabled: bool = True,
    has_oauth_token: bool = False,
    subscription_type: str | None = None,
    org_channels_enabled: bool | None = None,
    is_in_session_channels: bool = False,
    channel_entry_dev: bool = False,
    channel_entry_marketplace: str | None = None,
    plugin_allowed: bool = False,
) -> ChannelGateResult:
    """Gate an MCP server's channel-notification path.

    Gate order: capability → runtime gate → auth → org policy →
    session --channels → allowlist.
    """
    # Capability check
    exp = capabilities.get("experimental", {}) if capabilities else {}
    if not exp.get("claude/channel"):
        return ChannelGateResult(
            action="skip",
            kind="capability",
            reason="server did not declare claude/channel capability",
        )

    # Runtime gate
    if not is_channels_enabled:
        return ChannelGateResult(
            action="skip",
            kind="disabled",
            reason="channels feature is not currently available",
        )

    # Auth check (OAuth only)
    if not has_oauth_token:
        return ChannelGateResult(
            action="skip",
            kind="auth",
            reason="channels requires claude.ai authentication (run /login)",
        )

    # Org policy check (teams/enterprise)
    if subscription_type in ("team", "enterprise") and org_channels_enabled is not True:
        return ChannelGateResult(
            action="skip",
            kind="policy",
            reason="channels not enabled by org policy",
        )

    # Session --channels check
    if not is_in_session_channels:
        return ChannelGateResult(
            action="skip",
            kind="session",
            reason=f"server {server_name} not in --channels list for this session",
        )

    # Allowlist check for non-dev entries
    if not channel_entry_dev:
        if channel_entry_marketplace is not None:
            # Plugin-kind entry
            if not plugin_allowed:
                return ChannelGateResult(
                    action="skip",
                    kind="allowlist",
                    reason=f"plugin {server_name} is not on the approved channels allowlist",
                )
        else:
            # Server-kind entry
            return ChannelGateResult(
                action="skip",
                kind="allowlist",
                reason=f"server {server_name} is not on the approved channels allowlist",
            )

    return ChannelGateResult(action="register")


# ─── Channel Message Wrapping ───────────────────────────────────────────────────


def wrap_channel_message(
    server_name: str,
    content: str,
    meta: dict[str, str] | None = None,
) -> str:
    """Wrap an inbound channel message in a <channel> tag.

    Meta keys become XML attribute names. Only safe identifiers are accepted.
    """
    import re as _re
    SAFE_META_KEY = _re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

    def esc_attr(s: str) -> str:
        return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

    attrs = ""
    if meta:
        for k, v in meta.items():
            if SAFE_META_KEY.match(k):
                attrs += f' {k}="{esc_attr(v)}"'
    return f'<channel source="{esc_attr(server_name)}"{attrs}>\n{content}\n</channel>'
