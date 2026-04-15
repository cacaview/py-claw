"""
McpServerApproval service.

Handles approval/rejection logic for MCP server connections.
"""
from py_claw.services.mcp_server_approval.config import (
    McpServerApprovalConfig,
    get_mcp_server_approval_config,
    set_mcp_server_approval_config,
)
from py_claw.services.mcp_server_approval.service import (
    approve_server,
    check_approval,
    get_approval_stats,
    list_approved_servers,
    list_pending_requests,
    reject_server,
    request_approval,
    revoke_approval,
)
from py_claw.services.mcp_server_approval.types import (
    ApprovalStatus,
    McpServerApprovalState,
    ServerApprovalRequest,
    ServerApprovalResult,
    ServerRiskLevel,
    get_mcp_server_approval_state,
)


__all__ = [
    "McpServerApprovalConfig",
    "ApprovalStatus",
    "ServerRiskLevel",
    "ServerApprovalRequest",
    "ServerApprovalResult",
    "McpServerApprovalState",
    "get_mcp_server_approval_config",
    "set_mcp_server_approval_config",
    "request_approval",
    "check_approval",
    "approve_server",
    "reject_server",
    "list_pending_requests",
    "list_approved_servers",
    "revoke_approval",
    "get_approval_stats",
    "get_mcp_server_approval_state",
]
