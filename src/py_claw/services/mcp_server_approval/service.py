"""
McpServerApproval service.

Handles approval/rejection logic for MCP server connections.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from py_claw.services.mcp_server_approval.config import (
    get_mcp_server_approval_config,
)

from .types import (
    ApprovalStatus,
    ServerApprovalRequest,
    ServerApprovalResult,
    ServerRiskLevel,
    get_mcp_server_approval_state,
)


def _assess_risk_level(server_type: str, server_config: dict) -> ServerRiskLevel:
    """Assess the risk level of an MCP server.

    Args:
        server_type: Type of MCP server
        server_config: Server configuration

    Returns:
        Risk level assessment
    """
    # Local stdio is lower risk (runs local command)
    if server_type in ("stdio",):
        return ServerRiskLevel.LOW

    # HTTP/SSE/WebSocket to localhost is medium risk
    if server_type in ("http", "sse", "websocket"):
        url = server_config.get("url", "")
        if "localhost" in url or "127.0.0.1" in url:
            return ServerRiskLevel.MEDIUM
        # External URL is higher risk
        return ServerRiskLevel.HIGH

    # SDK and claudeai-proxy are medium risk (authenticated)
    if server_type in ("sdk", "claudeai-proxy"):
        return ServerRiskLevel.MEDIUM

    return ServerRiskLevel.UNKNOWN


def request_approval(
    server_name: str,
    server_type: str,
    server_config: dict,
    requested_permissions: list[str] | None = None,
) -> ServerApprovalRequest:
    """Request approval for an MCP server.

    Args:
        server_name: Name of the MCP server
        server_type: Type of server ("stdio", "http", etc.)
        server_config: Server configuration dict
        requested_permissions: List of permissions being requested

    Returns:
        ServerApprovalRequest with the request details
    """
    config = get_mcp_server_approval_config()
    state = get_mcp_server_approval_state()

    risk_level = _assess_risk_level(server_type, server_config)

    request = ServerApprovalRequest(
        server_name=server_name,
        server_type=server_type,
        server_config=server_config,
        requested_at=datetime.now(timezone.utc),
        risk_level=risk_level,
        requested_permissions=tuple(requested_permissions) if requested_permissions else (),
        status=ApprovalStatus.PENDING,
        request_id=str(uuid.uuid4())[:8],
    )

    state.add_pending_request(request)

    return request


def check_approval(server_name: str) -> ServerApprovalResult:
    """Check if a server is approved, rejected, or pending.

    Args:
        server_name: Name of the MCP server

    Returns:
        ServerApprovalResult with the decision
    """
    config = get_mcp_server_approval_config()
    state = get_mcp_server_approval_state()

    # Check if auto-approved
    if server_name in config.auto_approve_servers:
        return ServerApprovalResult(
            server_name=server_name,
            status=ApprovalStatus.APPROVED,
            decision="auto_approved",
            reason="Server is on auto-approve list",
            risk_level=_assess_risk_level(
                state.pending_requests.get(server_name, ServerApprovalRequest(
                    server_name=server_name,
                    server_type="unknown",
                    server_config={},
                    requested_at=datetime.now(timezone.utc),
                )).server_type,
                state.pending_requests.get(server_name, ServerApprovalRequest(
                    server_name=server_name,
                    server_type="unknown",
                    server_config={},
                    requested_at=datetime.now(timezone.utc),
                )).server_config,
            ),
        )

    # Check if already approved
    if state.is_approved(server_name):
        return ServerApprovalResult(
            server_name=server_name,
            status=ApprovalStatus.APPROVED,
            decision="approved",
            reason="Server was previously approved",
        )

    # Check if rejected
    if state.is_rejected(server_name):
        return ServerApprovalResult(
            server_name=server_name,
            status=ApprovalStatus.REJECTED,
            decision="rejected",
            reason="Server was previously rejected",
        )

    # Check if pending
    if server_name in state.pending_requests:
        request = state.pending_requests[server_name]
        return ServerApprovalResult(
            server_name=server_name,
            status=ApprovalStatus.PENDING,
            decision="pending",
            reason="Approval request is pending",
            risk_level=request.risk_level,
        )

    # Not in system - if require_approval is False, auto-approve
    if not config.require_approval:
        return ServerApprovalResult(
            server_name=server_name,
            status=ApprovalStatus.APPROVED,
            decision="auto_approved",
            reason="Approval not required",
        )

    # Unknown server and approval required
    return ServerApprovalResult(
        server_name=server_name,
        status=ApprovalStatus.PENDING,
        decision="pending",
        reason="Server requires approval",
    )


def approve_server(server_name: str, reason: str | None = None) -> ServerApprovalResult:
    """Approve an MCP server.

    Args:
        server_name: Name of the server to approve
        reason: Optional reason for approval

    Returns:
        ServerApprovalResult with the decision
    """
    state = get_mcp_server_approval_state()
    config = get_mcp_server_approval_config()

    if not state.approve_server(server_name):
        # Wasn't pending, add to approved anyway
        pass

    # Calculate expiry
    from datetime import timedelta
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=config.approval_timeout)

    return ServerApprovalResult(
        server_name=server_name,
        status=ApprovalStatus.APPROVED,
        decision="approved",
        reason=reason or "Approved by user",
        expires_at=expires_at,
    )


def reject_server(server_name: str, reason: str | None = None) -> ServerApprovalResult:
    """Reject an MCP server.

    Args:
        server_name: Name of the server to reject
        reason: Optional reason for rejection

    Returns:
        ServerApprovalResult with the decision
    """
    state = get_mcp_server_approval_state()

    state.reject_server(server_name)

    return ServerApprovalResult(
        server_name=server_name,
        status=ApprovalStatus.REJECTED,
        decision="rejected",
        reason=reason or "Rejected by user",
    )


def list_pending_requests() -> list[ServerApprovalRequest]:
    """List all pending approval requests.

    Returns:
        List of pending ServerApprovalRequest objects
    """
    state = get_mcp_server_approval_state()
    return list(state.pending_requests.values())


def list_approved_servers() -> list[str]:
    """List all approved servers.

    Returns:
        List of approved server names
    """
    state = get_mcp_server_approval_state()
    return list(state.approved_servers.keys())


def revoke_approval(server_name: str) -> bool:
    """Revoke approval for a server.

    Args:
        server_name: Name of the server

    Returns:
        True if revoked, False if not found
    """
    state = get_mcp_server_approval_state()
    with state._lock:
        if server_name in state.approved_servers:
            del state.approved_servers[server_name]
            return True
    return False


def get_approval_stats() -> dict:
    """Get approval statistics.

    Returns:
        Dictionary with approval statistics
    """
    config = get_mcp_server_approval_config()
    state = get_mcp_server_approval_state()

    return {
        "enabled": config.enabled,
        "require_approval": config.require_approval,
        "auto_approve_count": len(config.auto_approve_servers),
        "pending_count": len(state.pending_requests),
        "approved_count": len(state.approved_servers),
        "rejected_count": len(state.rejected_servers),
    }
