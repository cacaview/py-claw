"""Resolve the parent's model backend config for forked child processes.

The forked child runs in its own process and picks its model protocol from
the ``model_config`` field of the init message (falling back to
ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL environment variables when absent).
This module maps the parent's py-claw config (the single source of truth,
see py_claw.config.loader) onto exactly the fields a child needs to run real
model turns on the same protocol the parent uses.
"""

from __future__ import annotations

from typing import Any


def resolve_fork_model_config() -> dict[str, Any] | None:
    """Build the ``model_config`` dict passed to a forked child via init.

    Returns a dict of the form::

        {"backend": "openai", "api_key": ..., "api_url": ..., "model": ...,
         "temperature": ..., "top_p": ..., "timeout_seconds": ...}

    or ``{"backend": "anthropic", "api_key": ..., "api_url": ..., "model": ...}``
    when the parent's config speaks the Anthropic Messages protocol.

    Returns ``None`` when no usable backend is configured — the child then
    keeps using its environment-based fallback (existing behavior).

    The OpenAI backend is reported as soon as an ``api_url`` exists (even
    with an empty key) so the child can degrade with protocol-specific
    guidance instead of falling back to the Anthropic env path.
    """
    from py_claw.config import load_config

    try:
        cfg = load_config()
    except Exception:
        return None

    api = cfg.api
    if api.protocol == "anthropic":
        backend = "anthropic"
        if not (api.api_key or api.api_url):
            return None
    else:
        backend = "openai"
        if not api.api_url:
            return None

    api_url = (api.api_url or "").rstrip("/")
    if backend == "anthropic" and api_url.endswith("/v1"):
        # The child's Anthropic call appends /v1/messages to the base URL
        # itself, so strip a trailing /v1 to avoid a doubled prefix.
        api_url = api_url[: -len("/v1")]

    config: dict[str, Any] = {
        "backend": backend,
        "api_key": api.api_key or "",
        "api_url": api_url,
        "model": api.model or "",
    }
    if backend == "openai":
        # Forward the sampling/timeout knobs so the child requests match the
        # parent's backend instead of silently using different settings.
        if api.temperature is not None:
            config["temperature"] = api.temperature
        if api.top_p is not None:
            config["top_p"] = api.top_p
        config["timeout_seconds"] = int(api.timeout_seconds or 120)
    return config
