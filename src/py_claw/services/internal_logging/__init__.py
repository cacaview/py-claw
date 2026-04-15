"""
Internal logging service for Claude Code.

Logs internal events, errors, and diagnostics for internal analytics.
Used primarily in ant (enterprise) deployments.
"""
from __future__ import annotations

from .service import (
    get_container_id,
    log_permission_context_for_ants,
)

__all__ = [
    "get_container_id",
    "log_permission_context_for_ants",
]
