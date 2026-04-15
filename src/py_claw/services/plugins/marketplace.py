"""
Plugin marketplace management.

Handles fetching, caching, and managing plugin marketplace manifests.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

from .config import get_plugin_service_config
from .state import get_plugin_state
from .types import MarketplaceConfig, MarketplaceManifest, PluginMarketplaceEntry, PluginSource

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Marketplace fetching
# ---------------------------------------------------------------------------


_MARKETPLACE_CACHE: dict[str, tuple[float, list[PluginMarketplaceEntry]]] = {}


def get_marketplace_plugins(
    marketplace_name: str,
    force_refresh: bool = False,
) -> list[PluginMarketplaceEntry] | None:
    """
    Fetch and cache marketplace manifest for a marketplace.
    Returns None if the marketplace cannot be reached.
    """
    global _MARKETPLACE_CACHE

    state = get_plugin_state()
    marketplace = state.get_marketplace(marketplace_name)
    if marketplace is None:
        return None

    config = get_plugin_service_config()
    cache_ttl = config.marketplace_cache_ttl

    # Check cache
    if not force_refresh and marketplace_name in _MARKETPLACE_CACHE:
        cached_time, cached_plugins = _MARKETPLACE_CACHE[marketplace_name]
        if time.time() - cached_time < cache_ttl:
            return cached_plugins

    # Fetch marketplace manifest
    try:
        url = _build_marketplace_url(marketplace.url)
        plugins = _fetch_marketplace_manifest(url)
        _MARKETPLACE_CACHE[marketplace_name] = (time.time(), plugins)
        return plugins
    except Exception:
        # Return stale cache if available
        if marketplace_name in _MARKETPLACE_CACHE:
            _, cached_plugins = _MARKETPLACE_CACHE[marketplace_name]
            return cached_plugins
        return None


def _build_marketplace_url(base_url: str) -> str:
    """Build the full marketplace manifest URL."""
    base = base_url.rstrip("/")
    if base.endswith("/marketplace.json"):
        return base
    return f"{base}/marketplace.json"


def _fetch_marketplace_manifest(url: str) -> list[PluginMarketplaceEntry]:
    """Fetch a marketplace manifest from a URL."""
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))

    manifest = MarketplaceManifest(**data)
    return list(manifest.plugins)


def clear_marketplace_cache(marketplace_name: str | None = None) -> None:
    """Clear the marketplace cache, optionally for a specific marketplace only."""
    global _MARKETPLACE_CACHE
    if marketplace_name is None:
        _MARKETPLACE_CACHE.clear()
    elif marketplace_name in _MARKETPLACE_CACHE:
        del _MARKETPLACE_CACHE[marketplace_name]


# ---------------------------------------------------------------------------
# Marketplace management
# ---------------------------------------------------------------------------


def add_marketplace(
    url: str,
    name: str | None = None,
    owner: str | None = None,
    description: str | None = None,
) -> tuple[bool, str]:
    """
    Register a new marketplace.

    Args:
        url: Base URL of the marketplace
        name: Optional marketplace name (derived from URL if not provided)
        owner: Optional owner name
        description: Optional description

    Returns:
        (success, message)
    """
    if not url:
        return False, "Marketplace URL is required"

    # Derive name from URL if not provided
    if name is None:
        name = _derive_marketplace_name(url)
        if not name:
            return False, "Could not derive marketplace name from URL"

    # Validate name for impersonation
    if not _is_valid_marketplace_name(name):
        return False, f"Invalid marketplace name: {name}"

    # Check for duplicate
    state = get_plugin_state()
    existing = state.get_marketplace(name)
    if existing is not None:
        return False, f"Marketplace '{name}' is already registered"

    # Validate URL is reachable
    manifest_url = _build_marketplace_url(url)
    try:
        with urllib.request.urlopen(manifest_url, timeout=5) as response:
            json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return False, f"Could not reach marketplace at {manifest_url}: {e}"

    # Save
    config = MarketplaceConfig(
        name=name,
        url=url.rstrip("/"),
        owner=owner,
        description=description,
    )
    state.add_marketplace(config)
    return True, f"Marketplace '{name}' added"


def remove_marketplace(name: str) -> tuple[bool, str]:
    """
    Remove a registered marketplace.

    Args:
        name: Marketplace name

    Returns:
        (success, message)
    """
    state = get_plugin_state()
    if state.get_marketplace(name) is None:
        return False, f"Marketplace '{name}' not found"

    if state.remove_marketplace(name):
        clear_marketplace_cache(name)
        return True, f"Marketplace '{name}' removed"

    return False, f"Failed to remove marketplace '{name}'"


def list_marketplaces() -> list[MarketplaceConfig]:
    """List all registered marketplaces."""
    state = get_plugin_state()
    return state.list_marketplaces()


def _derive_marketplace_name(url: str) -> str | None:
    """Derive a kebab-case marketplace name from a URL."""
    url = url.rstrip("/")
    # Try to get the last path segment
    if "/" in url:
        name = url.rsplit("/", 1)[1]
    else:
        name = url
    # Remove common TLDs
    for tld in (".com", ".io", ".org", ".dev", ".ai"):
        if name.endswith(tld):
            name = name[: -len(tld)]
    # Validate
    if not name or len(name) < 2:
        return None
    # Convert to kebab-case
    name = name.lower().replace("_", "-")
    return name


_ALLOWED_OFFICIAL_MARKETPLACE_NAMES = frozenset([
    "claude-code-marketplace",
    "claude-code-plugins",
    "claude-plugins-official",
    "anthropic-marketplace",
    "anthropic-plugins",
])

_BLOCKED_NAME_PATTERN = __import__("re").compile(
    r"(?:official[^a-z0-9]*(?:anthropic|claude)|"
    r"(?:anthropic|claude)[^a-z0-9]*official)",
    __import__("re").I,
)


def _is_valid_marketplace_name(name: str) -> bool:
    """Validate a marketplace name for safety."""
    if not name:
        return False
    # Must be kebab-case
    if not __import__("re").match(r"^[a-z0-9][a-z0-9-]*$", name):
        return False
    # Cannot start/end with hyphen
    if name.startswith("-") or name.endswith("-"):
        return False
    # Check for impersonation of official names
    if _BLOCKED_NAME_PATTERN.search(name):
        return False
    return True


# ---------------------------------------------------------------------------
# Official marketplace
# ---------------------------------------------------------------------------

# The official Claude Code plugin marketplace
OFFICIAL_MARKETPLACE_NAME = "claude-code-marketplace"
OFFICIAL_MARKETPLACE_URL = "https://github.com/anthropics/claude-code-plugins"


def register_official_marketplace() -> None:
    """Register the official Claude Code plugin marketplace."""
    state = get_plugin_state()
    if state.get_marketplace(OFFICIAL_MARKETPLACE_NAME) is None:
        config = MarketplaceConfig(
            name=OFFICIAL_MARKETPLACE_NAME,
            url=OFFICIAL_MARKETPLACE_URL,
            owner="Anthropic",
            description="Official Claude Code plugin marketplace",
        )
        state.add_marketplace(config)
