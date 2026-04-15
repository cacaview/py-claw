"""
Official MCP registry integration.

Provides verification that an MCP server URL is in the official Anthropic MCP registry.
This is used to determine if an MCP server is a trusted/official server.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Registry API endpoint
REGISTRY_API_URL = "https://api.anthropic.com/mcp-registry/v0/servers?version=latest&visibility=commercial"

# Environment variable to disable non-essential traffic
DISABLE_NONESSENTIAL_TRAFFIC_ENV = "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"

# In-memory cache of official URLs
_official_urls: set[str] | None = None
_official_urls_lock = threading.Lock()


def _normalize_url(url: str) -> str | None:
    """Normalize a URL for comparison.

    Strips query string and trailing slash.
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        # Remove trailing slash
        normalized = normalized.rstrip("/")
        return normalized
    except Exception:
        return None


def _fetch_registry_urls(timeout_ms: int = 5000) -> set[str] | None:
    """Fetch the official MCP registry URLs.

    Returns None on failure.
    """
    import os
    if os.environ.get(DISABLE_NONESSENTIAL_TRAFFIC_ENV):
        logger.debug("[mcp-registry] Non-essential traffic disabled, skipping fetch")
        return None

    try:
        import urllib.request as urllib_request

        req = urllib_request.Request(
            REGISTRY_API_URL,
            headers={"Accept": "application/json"},
        )

        with urllib_request.urlopen(req, timeout=timeout_ms / 1000) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        urls: set[str] = set()
        servers = data.get("servers", [])
        for entry in servers:
            for remote in entry.get("server", {}).get("remotes", []):
                url = remote.get("url")
                if url:
                    normalized = _normalize_url(url)
                    if normalized:
                        urls.add(normalized)

        logger.debug("[mcp-registry] Loaded %d official MCP URLs", len(urls))
        return urls

    except Exception as e:
        logger.warning("Failed to fetch MCP registry: %s", e)
        return None


async def prefetch_official_mcp_urls() -> None:
    """Fire-and-forget fetch of the official MCP registry.

    Populates officialUrls for is_official_mcp_url lookups.
    """
    global _official_urls

    urls = _fetch_registry_urls()
    if urls is not None:
        with _official_urls_lock:
            _official_urls = urls


def is_official_mcp_url(normalized_url: str) -> bool:
    """Check if a URL is in the official MCP registry.

    Args:
        normalized_url: A URL that has already been normalized via _normalize_url

    Returns:
        True if the URL is in the official registry, False otherwise.
        If the registry hasn't been fetched yet, returns False (fail-closed).
    """
    with _official_urls_lock:
        if _official_urls is None:
            return False
        return normalized_url in _official_urls


def reset_official_mcp_urls_for_testing() -> None:
    """Reset the official MCP URLs cache (for testing)."""
    global _official_urls
    with _official_urls_lock:
        _official_urls = None


def get_official_mcp_urls() -> set[str] | None:
    """Get the current cache of official MCP URLs (for testing).

    Returns None if not yet fetched.
    """
    with _official_urls_lock:
        return _official_urls.copy() if _official_urls is not None else None


# ─── Registry Server Entry ─────────────────────────────────────────────────────


@dataclass
class RegistryServerEntry:
    """An entry in the MCP registry."""
    name: str | None = None
    description: str | None = None
    url: str | None = None


@dataclass
class RegistryServer:
    """A server entry from the registry."""
    server: RegistryServerEntry | None = None


@dataclass
class RegistryResponse:
    """Response from the registry API."""
    servers: list[RegistryServer] = field(default_factory=list)


def check_url_in_registry(url: str) -> bool:
    """Check if a URL is in the official MCP registry.

    This is a synchronous convenience function that fetches the registry
    if not already cached.

    Args:
        url: The URL to check

    Returns:
        True if the URL is in the registry, False otherwise.
    """
    normalized = _normalize_url(url)
    if normalized is None:
        return False

    # If not cached, try to fetch
    global _official_urls
    if _official_urls is None:
        urls = _fetch_registry_urls()
        if urls is not None:
            _official_urls = urls

    return is_official_mcp_url(normalized)
