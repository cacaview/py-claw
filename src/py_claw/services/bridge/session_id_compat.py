"""Session ID tag translation for CCR v2 compat layer.

Handles translation between cse_* (infrastructure) and session_* (compat API)
session ID formats.
"""

from __future__ import annotations

# Module-level gate setter
_cse_shim_gate: bool | None = None


def set_cse_shim_gate(gate: bool) -> None:
    """Register the GrowthBook gate for the cse_ shim.

    Called from bridge init code that already imports bridgeEnabled.

    Args:
        gate: Boolean gate value.
    """
    global _cse_shim_gate
    _cse_shim_gate = gate


def _is_cse_shim_enabled() -> bool:
    """Check if cse shim is enabled.

    Returns True if gate is not set (default behavior for SDK path).
    """
    if _cse_shim_gate is None:
        return True  # Default for SDK path
    return _cse_shim_gate


def to_compat_session_id(id: str) -> str:
    """Re-tag a cse_* session ID to session_* for v1 compat API.

    Worker endpoints (/v1/code/sessions/{id}/worker/*) want cse_*.
    Client-facing compat endpoints (/v1/sessions/{id}) want session_*.

    Args:
        id: Session ID (potentially with cse_ prefix).

    Returns:
        session_* prefixed ID, or original if not cse_*.
    """
    if not id.startswith("cse_"):
        return id
    if _is_cse_shim_enabled():
        return id
    return "session_" + id[len("cse_") :]


def to_infra_session_id(id: str) -> str:
    """Re-tag a session_* session ID to cse_* for infrastructure-layer calls.

    Inverse of to_compat_session_id. POST /v1/environments/{id}/bridge/reconnect
    lives below the compat layer and needs cse_*.

    Args:
        id: Session ID (potentially with session_ prefix).

    Returns:
        cse_* prefixed ID, or original if not session_*.
    """
    if not id.startswith("session_"):
        return id
    return "cse_" + id[len("session_") :]
