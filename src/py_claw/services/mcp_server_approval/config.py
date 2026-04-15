"""
McpServerApproval configuration.

Service for approving/rejecting MCP server connections.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class McpServerApprovalConfig:
    """Configuration for MCP Server Approval service."""

    enabled: bool = True
    # Auto-approve servers in this list
    auto_approve_servers: tuple[str, ...] = ()
    # Require approval for all servers by default
    require_approval: bool = True
    # Approval timeout in seconds
    approval_timeout: int = 300
    # Store approved servers persistently
    persist_approvals: bool = True
    # Approval storage path
    approvals_path: str = ".claude/mcp_approvals.json"

    @classmethod
    def from_settings(cls, settings: dict) -> McpServerApprovalConfig:
        """Create config from settings dictionary."""
        mcp_settings = settings.get("mcpServerApproval", {})
        auto_approve = mcp_settings.get("autoApproveServers")
        return cls(
            enabled=mcp_settings.get("enabled", True),
            auto_approve_servers=tuple(auto_approve) if auto_approve else (),
            require_approval=mcp_settings.get("requireApproval", True),
            approval_timeout=mcp_settings.get("approvalTimeout", 300),
            persist_approvals=mcp_settings.get("persistApprovals", True),
            approvals_path=mcp_settings.get("approvalsPath", ".claude/mcp_approvals.json"),
        )


# Global config instance
_config: McpServerApprovalConfig | None = None


def get_mcp_server_approval_config() -> McpServerApprovalConfig:
    """Get the current MCP Server Approval configuration."""
    global _config
    if _config is None:
        _config = McpServerApprovalConfig()
    return _config


def set_mcp_server_approval_config(config: McpServerApprovalConfig) -> None:
    """Set the MCP Server Approval configuration."""
    global _config
    _config = config
