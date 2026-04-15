"""API Provider detection - firstParty, Bedrock, Vertex, Foundry."""

from __future__ import annotations

import os
from enum import Enum

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal


class APIProvider(Enum):
    FIRST_PARTY = "firstParty"
    BEDROCK = "bedrock"
    VERTEX = "vertex"
    FOUNDRY = "foundry"


def get_api_provider() -> APIProvider:
    """Detect the API provider based on environment variables."""
    if _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_BEDROCK", "")):
        return APIProvider.BEDROCK
    if _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_VERTEX", "")):
        return APIProvider.VERTEX
    if _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_FOUNDRY", "")):
        return APIProvider.FOUNDRY
    return APIProvider.FIRST_PARTY


def is_first_party_anthropic_base_url() -> bool:
    """
    Check if ANTHROPIC_BASE_URL is a first-party Anthropic API URL.
    Returns True if not set (default API) or points to api.anthropic.com
    (or api-staging.anthropic.com for ant users).
    """
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    if not base_url:
        return True
    try:
        from urllib.parse import urlparse

        host = urlparse(base_url).host or ""
        allowed_hosts = ["api.anthropic.com"]
        if os.environ.get("USER_TYPE") == "ant":
            allowed_hosts.append("api-staging.anthropic.com")
        return host in allowed_hosts
    except Exception:
        return False


def _is_env_truthy(value: str) -> bool:
    """Check if an environment variable value is truthy."""
    return value.lower() in ("true", "1", "yes")
