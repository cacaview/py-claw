"""
McpServerApproval types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ApprovalStatus(str, Enum):
    """Status of an MCP server approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ServerRiskLevel(str, Enum):
    """Risk level assessment for an MCP server."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ServerApprovalRequest:
    """A request to approve an MCP server."""

    server_name: str
    server_type: str  # "stdio", "http", "sse", "websocket", "sdk", "claudeai-proxy"
    server_config: dict  # The actual server configuration
    requested_at: datetime
    risk_level: ServerRiskLevel = ServerRiskLevel.UNKNOWN
    requested_permissions: tuple[str, ...] = ()
    status: ApprovalStatus = ApprovalStatus.PENDING
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ServerApprovalResult:
    """Result of an approval decision."""

    server_name: str
    status: ApprovalStatus
    decision: str  # "approved", "rejected", "auto_approved", "auto_rejected"
    reason: str | None = None
    expires_at: datetime | None = None
    risk_level: ServerRiskLevel = ServerRiskLevel.UNKNOWN


@dataclass
class McpServerApprovalState:
    """State for MCP server approval service."""

    pending_requests: dict[str, ServerApprovalRequest] = field(default_factory=dict)
    approved_servers: dict[str, datetime] = field(default_factory=dict)  # server_name -> approved_at
    rejected_servers: dict[str, datetime] = field(default_factory=dict)  # server_name -> rejected_at
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def add_pending_request(self, request: ServerApprovalRequest) -> None:
        """Add a pending approval request."""
        with self._lock:
            self.pending_requests[request.server_name] = request

    def approve_server(self, server_name: str) -> bool:
        """Approve a server."""
        with self._lock:
            if server_name in self.pending_requests:
                del self.pending_requests[server_name]
            self.approved_servers[server_name] = datetime.now(timezone.utc)
            if server_name in self.rejected_servers:
                del self.rejected_servers[server_name]
            return True

    def reject_server(self, server_name: str) -> bool:
        """Reject a server."""
        with self._lock:
            if server_name in self.pending_requests:
                del self.pending_requests[server_name]
            self.rejected_servers[server_name] = datetime.now(timezone.utc)
            if server_name in self.approved_servers:
                del self.approved_servers[server_name]
            return True

    def is_approved(self, server_name: str) -> bool:
        """Check if a server is approved."""
        with self._lock:
            return server_name in self.approved_servers

    def is_rejected(self, server_name: str) -> bool:
        """Check if a server is rejected."""
        with self._lock:
            return server_name in self.rejected_servers

    def clear_pending(self, server_name: str) -> bool:
        """Clear a pending request."""
        with self._lock:
            if server_name in self.pending_requests:
                del self.pending_requests[server_name]
                return True
            return False


# Global state
_state: McpServerApprovalState | None = None


def get_mcp_server_approval_state() -> McpServerApprovalState:
    """Get the global MCP server approval state."""
    global _state
    if _state is None:
        _state = McpServerApprovalState()
    return _state
