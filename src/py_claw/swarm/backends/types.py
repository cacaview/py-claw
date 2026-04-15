"""
Swarm backend types for team orchestration.

Based on ClaudeCode-main/src/utils/swarm/backends/types.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol


class BackendType(Enum):
    """Backend type for teammate panes."""
    TMUX = "tmux"
    ITERM2 = "iterm2"
    IN_PROCESS = "in_process"
    WEB = "web"


class PaneBackendType(Enum):
    """Pane-based backend types only."""
    TMUX = "tmux"
    ITERM2 = "iterm2"


# Type aliases
PaneId = str


@dataclass
class CreatePaneResult:
    """Result of creating a new teammate pane."""
    pane_id: PaneId
    is_first_teammate: bool


@dataclass
class TeammateIdentity:
    """Identity fields for a teammate."""
    name: str  # Agent name (e.g., "researcher", "tester")
    team_name: str  # Team name this teammate belongs to
    color: str | None = None  # Assigned color for UI
    plan_mode_required: bool = False


@dataclass
class TeammateSpawnConfig:
    """Configuration for spawning a teammate."""
    name: str  # Agent name
    team_name: str  # Team name
    prompt: str  # Initial prompt
    cwd: str  # Working directory
    parent_session_id: str
    model: str | None = None
    color: str | None = None
    plan_mode_required: bool = False
    system_prompt: str | None = None
    system_prompt_mode: str = "default"  # 'default' | 'replace' | 'append'
    worktree_path: str | None = None
    permissions: list[str] = field(default_factory=list)
    allow_permission_prompts: bool = False


@dataclass
class TeammateSpawnResult:
    """Result from spawning a teammate."""
    success: bool
    agent_id: str  # Format: agentName@teamName
    error: str | None = None
    abort_controller: Any = None  # For in-process only
    task_id: str | None = None  # For in-process only
    pane_id: PaneId | None = None  # For pane-based only


@dataclass
class TeammateMessage:
    """Message to send to a teammate."""
    text: str
    from_agent: str  # Sender agent ID
    color: str | None = None
    timestamp: datetime | None = None
    summary: str | None = None  # 5-10 word preview


@dataclass
class BackendDetectionResult:
    """Result from backend detection."""
    backend: "PaneBackend"
    is_native: bool
    needs_it2_setup: bool = False


@dataclass
class BackendInfo:
    """Backend information for registry."""
    backend_type: BackendType
    display_name: str
    supports_hide_show: bool


# Protocol for pane backends
class PaneBackend(Protocol):
    """Interface for pane management backends."""

    @property
    def type(self) -> BackendType:
        """Backend type identifier."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        ...

    @property
    def supports_hide_show(self) -> bool:
        """Whether this backend supports hiding and showing panes."""
        ...

    async def is_available(self) -> bool:
        """Check if this backend is available on the system."""
        ...

    async def is_running_inside(self) -> bool:
        """Check if we're running inside this backend's environment."""
        ...

    async def create_teammate_pane_in_swarm_view(
        self,
        name: str,
        color: str,
    ) -> CreatePaneResult:
        """Create a new pane for a teammate."""
        ...

    async def send_command_to_pane(
        self,
        pane_id: PaneId,
        command: str,
        use_external_session: bool = False,
    ) -> None:
        """Send a command to a specific pane."""
        ...

    async def set_pane_border_color(
        self,
        pane_id: PaneId,
        color: str,
        use_external_session: bool = False,
    ) -> None:
        """Set the border color for a pane."""
        ...

    async def set_pane_title(
        self,
        pane_id: PaneId,
        name: str,
        color: str,
        use_external_session: bool = False,
    ) -> None:
        """Set the title for a pane."""
        ...

    async def enable_pane_border_status(
        self,
        window_target: str | None = None,
        use_external_session: bool = False,
    ) -> None:
        """Enable pane border status display."""
        ...

    async def rebalance_panes(
        self,
        window_target: str,
        has_leader: bool,
    ) -> None:
        """Rebalance panes."""
        ...

    async def kill_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Kill/close a specific pane."""
        ...

    async def hide_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Hide a pane."""
        ...

    async def show_pane(
        self,
        pane_id: PaneId,
        target_window_or_pane: str,
        use_external_session: bool = False,
    ) -> bool:
        """Show a previously hidden pane."""
        ...


# Protocol for teammate executors
class TeammateExecutor(Protocol):
    """Common interface for teammate execution backends."""

    @property
    def executor_type(self) -> BackendType:
        """Backend type identifier."""
        ...

    async def is_available(self) -> bool:
        """Check if this executor is available."""
        ...

    async def spawn(self, config: TeammateSpawnConfig) -> TeammateSpawnResult:
        """Spawn a new teammate."""
        ...

    async def send_message(self, agent_id: str, message: TeammateMessage) -> None:
        """Send a message to a teammate."""
        ...

    async def terminate(self, agent_id: str, reason: str | None = None) -> bool:
        """Terminate a teammate gracefully."""
        ...

    async def kill(self, agent_id: str) -> bool:
        """Force kill a teammate."""
        ...

    async def is_active(self, agent_id: str) -> bool:
        """Check if a teammate is still active."""
        ...


def is_pane_backend(backend_type: BackendType) -> bool:
    """Type guard to check if a backend type uses terminal panes."""
    return backend_type in (BackendType.TMUX, BackendType.ITERM2)


__all__ = [
    "BackendDetectionResult",
    "BackendInfo",
    "BackendType",
    "CreatePaneResult",
    "PaneBackend",
    "PaneBackendType",
    "PaneId",
    "TeammateExecutor",
    "TeammateIdentity",
    "TeammateMessage",
    "TeammateSpawnConfig",
    "TeammateSpawnResult",
    "is_pane_backend",
]
