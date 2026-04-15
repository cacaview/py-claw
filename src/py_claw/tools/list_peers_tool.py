"""
ListPeersTool - List connected peers in UDS inbox network.

Provides peer discovery and listing capabilities for
inter-process communication via Unix Domain Sockets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import Field

from py_claw.tools.base import BaseTool, ToolResult


@dataclass
class ListPeersInput:
    """Input schema for ListPeersTool."""
    filter_type: str | None = Field(default=None, description="Filter peers by type: agent, client, server")
    include_metadata: bool = Field(default=False, description="Include peer metadata in response")


class ListPeersTool(BaseTool):
    """
    ListPeersTool - List connected peers.

    Provides peer discovery and listing capabilities for
    inter-process communication via Unix Domain Sockets.
    """

    name = "ListPeers"
    description = "List connected peers in the UDS inbox network"
    input_schema = ListPeersInput

    def __init__(self) -> None:
        super().__init__()
        self._peers: list[dict[str, Any]] = []

    async def execute(self, input_data: ListPeersInput, **kwargs: Any) -> ToolResult:
        """
        List connected peers.

        Args:
            input_data: ListPeersInput with filter options
            **kwargs: Additional context

        Returns:
            ToolResult with peer list
        """
        filter_type = input_data.filter_type
        include_metadata = input_data.include_metadata

        peers = self._peers.copy()

        # Apply filter
        if filter_type:
            peers = [p for p in peers if p.get("type") == filter_type]

        lines = [f"[ListPeers] Found {len(peers)} peer(s)"]

        if not peers:
            lines.append("No peers connected")
            lines.append("(UDS inbox feature not yet active)")
        else:
            for i, peer in enumerate(peers, 1):
                lines.append(f"")
                lines.append(f"Peer {i}:")
                lines.append(f"  ID: {peer.get('id', 'unknown')}")
                lines.append(f"  Type: {peer.get('type', 'unknown')}")
                lines.append(f"  Status: {peer.get('status', 'unknown')}")
                if include_metadata and peer.get("metadata"):
                    lines.append(f"  Metadata: {peer['metadata']}")

        return ToolResult(
            success=True,
            content="\n".join(lines),
        )

    def add_peer(self, peer_id: str, peer_type: str, metadata: dict[str, Any] | None = None) -> None:
        """Add a peer to the list (for testing/internal use)."""
        self._peers.append({
            "id": peer_id,
            "type": peer_type,
            "status": "connected",
            "metadata": metadata,
        })

    def remove_peer(self, peer_id: str) -> None:
        """Remove a peer from the list."""
        self._peers = [p for p in self._peers if p.get("id") != peer_id]

    def get_peer_count(self) -> int:
        """Get the number of peers."""
        return len(self._peers)
