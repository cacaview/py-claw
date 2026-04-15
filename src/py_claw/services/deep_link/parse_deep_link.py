"""Deep link URI parser for claude-cli://open URIs."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

DEEP_LINK_PROTOCOL = "claude-cli"

# Cap on pre-filled prompt length
MAX_QUERY_LENGTH = 5000

# Cap on cwd path length (PATH_MAX on Linux is 4096)
MAX_CWD_LENGTH = 4096

# GitHub owner/repo slug pattern
REPO_SLUG_PATTERN = re.compile(r"^[\w.-]+/[\w.-]+$")


@dataclass
class DeepLinkAction:
    """Represents a parsed deep link action."""

    query: str | None = None
    cwd: str | None = None
    repo: str | None = None


def _contains_control_chars(s: str) -> bool:
    """Check if string contains ASCII control characters (0x00-0x1F, 0x7F)."""
    for char in s:
        code = ord(char)
        if code <= 0x1F or code == 0x7F:
            return True
    return False


def _partially_sanitize_unicode(text: str) -> str:
    """
    Strip hidden Unicode characters (ASCII smuggling / hidden prompt injection).

    Removes zero-width characters, BOM, and other potentially dangerous Unicode.
    """
    # Remove zero-width characters
    text = text.replace("\u200B", "")  # zero width space
    text = text.replace("\u200C", "")  # zero width non-joiner
    text = text.replace("\u200D", "")  # zero width joiner
    text = text.replace("\uFEFF", "")  # BOM
    text = text.replace("\uFFFE", "")  # invalid Unicode
    text = text.replace("\uFFFF", "")  # invalid Unicode

    # Normalize Unicode to NFC form
    text = unicodedata.normalize("NFC", text)

    return text


def parse_deep_link(uri: str) -> DeepLinkAction:
    """
    Parse a claude-cli:// URI into a structured action.

    Args:
        uri: The deep link URI to parse

    Returns:
        DeepLinkAction with query, cwd, and repo fields

    Raises:
        Error: If the URI is malformed or contains dangerous characters

    Examples:
        >>> parse_deep_link("claude-cli://open")
        DeepLinkAction(query=None, cwd=None, repo=None)
        >>> parse_deep_link("claude-cli://open?q=hello+world")
        DeepLinkAction(query='hello world', cwd=None, repo=None)
    """
    # Normalize: accept with or without the trailing colon in protocol
    if uri.startswith(f"{DEEP_LINK_PROTOCOL}://"):
        normalized = uri
    elif uri.startswith(f"{DEEP_LINK_PROTOCOL}:"):
        normalized = uri.replace(f"{DEEP_LINK_PROTOCOL}:", f"{DEEP_LINK_PROTOCOL}://")
    else:
        raise ValueError(f'Invalid deep link: expected {DEEP_LINK_PROTOCOL}:// scheme, got "{uri}"')

    # Parse URL
    try:
        from urllib.parse import urlparse, unquote
    except ImportError:
        from urllib.parse import urlparse, unquote

    parsed = urlparse(normalized)

    if parsed.scheme != DEEP_LINK_PROTOCOL:
        raise ValueError(f'Invalid deep link scheme: expected {DEEP_LINK_PROTOCOL}, got "{parsed.scheme}"')

    if parsed.hostname != "open":
        raise ValueError(f'Unknown deep link action: "{parsed.hostname}"')

    # Extract parameters
    cwd = unquote(parsed.path) if parsed.path else None
    repo = unquote(parsed.query) if parsed.query else None

    # Re-parse query string properly
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(normalized)
    query_params = parse_qs(parsed.query)

    cwd = query_params.get("cwd", [None])[0]
    repo = query_params.get("repo", [None])[0]
    raw_query = query_params.get("q", [None])[0]

    # Validate cwd if present - must be an absolute path
    if cwd:
        if not cwd.startswith("/") and not re.match(r"^[a-zA-Z]:[/\\]", cwd):
            raise ValueError(f'Invalid cwd in deep link: must be an absolute path, got "{cwd}"')

        # Reject control characters
        if _contains_control_chars(cwd):
            raise ValueError("Deep link cwd contains disallowed control characters")

        # Check length
        if len(cwd) > MAX_CWD_LENGTH:
            raise ValueError(
                f"Deep link cwd exceeds {MAX_CWD_LENGTH} characters (got {len(cwd)})"
            )

    # Validate repo slug format
    if repo and not REPO_SLUG_PATTERN.match(repo):
        raise ValueError(f'Invalid repo in deep link: expected "owner/repo", got "{repo}"')

    # Parse and validate query
    query: str | None = None
    if raw_query and raw_query.strip():
        # Strip hidden Unicode characters
        query = _partially_sanitize_unicode(raw_query.strip())

        if _contains_control_chars(query):
            raise ValueError("Deep link query contains disallowed control characters")

        if len(query) > MAX_QUERY_LENGTH:
            raise ValueError(
                f"Deep link query exceeds {MAX_QUERY_LENGTH} characters (got {len(query)})"
            )

    return DeepLinkAction(query=query, cwd=cwd, repo=repo)


def build_deep_link(action: DeepLinkAction) -> str:
    """
    Build a claude-cli:// deep link URL from an action.

    Args:
        action: The deep link action to encode

    Returns:
        Complete deep link URL string
    """
    from urllib.parse import urlencode

    base = f"{DEEP_LINK_PROTOCOL}://open"
    params = {}

    if action.query:
        params["q"] = action.query
    if action.cwd:
        params["cwd"] = action.cwd
    if action.repo:
        params["repo"] = action.repo

    if params:
        return f"{base}?{urlencode(params)}"
    return base
