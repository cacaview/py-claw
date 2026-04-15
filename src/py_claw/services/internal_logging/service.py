"""
Internal logging service implementation.

Logs internal events, errors, and diagnostics for internal analytics.
Used primarily in ant (enterprise) deployments.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache


def _is_ant_user() -> bool:
    """Check if running as ant user type."""
    return os.environ.get("USER_TYPE") == "ant"


@lru_cache(maxsize=1)
def get_container_id() -> str | None:
    """
    Get the OCI container ID from within a running container.

    Returns:
        Container ID if running in a container, None otherwise.

    Notes:
        - Docker: /docker/containers/[64-char-hex]
        - Containerd/CRI-O: /sandboxes/[64-char-hex]
    """
    if not _is_ant_user():
        return None

    container_id_not_found = "container ID not found"
    container_id_not_found_in_mountinfo = "container ID not found in mountinfo"

    try:
        with open("/proc/self/mountinfo", "r", encoding="utf-8") as f:
            mountinfo = f.read().strip()
    except (FileNotFoundError, OSError):
        return container_id_not_found

    # Pattern to match both Docker and containerd/CRI-O container IDs
    # Docker: /docker/containers/[64-char-hex]
    # Containerd: /sandboxes/[64-char-hex]
    container_id_pattern = r"(?:\/docker\/containers\/|\/sandboxes\/)([0-9a-f]{64})"

    for line in mountinfo.split("\n"):
        match = re.search(container_id_pattern, line)
        if match and match.group(1):
            return match.group(1)

    return container_id_not_found_in_mountinfo


@lru_cache(maxsize=1)
def get_kubernetes_namespace() -> str | None:
    """
    Get the current Kubernetes namespace.

    Returns:
        - None on laptops/local development
        - "default" for devboxes in default namespace
        - "ts" for devboxes in ts namespace
        - etc.
    """
    if not _is_ant_user():
        return None

    namespace_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    namespace_not_found = "namespace not found"

    try:
        with open(namespace_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return namespace_not_found


async def log_permission_context_for_ants(
    tool_permission_context: dict | None,
    moment: str,
) -> None:
    """
    Logs an event with the current namespace and tool permission context.

    Used for internal analytics in ant deployments to track permission
    grants and denials.

    Args:
        tool_permission_context: The permission context to log
        moment: When the permission was logged ('summary' or 'initialization')
    """
    if not _is_ant_user():
        return

    try:
        from py_claw.services.telemetry import log_event

        namespace = get_kubernetes_namespace()
        container_id = get_container_id()

        # Serialize context to JSON
        import json

        context_json = json.dumps(tool_permission_context, sort_keys=True, default=str)

        log_event(
            "tengu_internal_record_permission_context",
            {
                "moment": moment,
                "namespace": namespace,
                "toolPermissionContext": context_json,
                "containerId": container_id,
            },
        )
    except ImportError:
        # Telemetry service not available
        pass
    except Exception:
        # Best effort logging
        pass
