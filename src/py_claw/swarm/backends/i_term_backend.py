"""
iTerm2 Backend for swarm team orchestration.

Provides pane management via iTerm2's Python API.

Based on ClaudeCode-main/src/utils/swarm/backends/ITermBackend.ts
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from py_claw.swarm.backends.types import (
    BackendType,
    CreatePaneResult,
    PaneBackend,
    PaneId,
)

logger = logging.getLogger(__name__)


class ITermBackend:
    """iTerm2 backend for pane management.

    Uses the it2 CLI tool to communicate with iTerm2's Python API
    for creating and managing split panes.
    """

    def __init__(self):
        """Initialize the iTerm backend."""
        self._type = BackendType.ITERM2

    @property
    def type(self) -> BackendType:
        """Backend type identifier."""
        return BackendType.ITERM2

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return "iTerm2"

    @property
    def supports_hide_show(self) -> bool:
        """Whether this backend supports hiding and showing panes."""
        return True

    async def is_available(self) -> bool:
        """Check if this backend is available on the system."""
        # Check if we're on macOS
        import platform

        if platform.system() != "Darwin":
            return False

        # Check if it2 CLI is available
        try:
            result = subprocess.run(
                ["it2", "session", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    async def is_running_inside(self) -> bool:
        """Check if we're running inside iTerm2."""
        import os

        term_program = os.environ.get("TERM_PROGRAM", "")
        return term_program == "iTerm.app"

    async def create_teammate_pane_in_swarm_view(
        self,
        name: str,
        color: str,
    ) -> CreatePaneResult:
        """Create a new pane for a teammate.

        Args:
            name: Teammate name
            color: Color for the pane

        Returns:
            CreatePaneResult with pane_id
        """
        try:
            # Use it2 to create a vertical split pane
            result = subprocess.run(
                [
                    "it2",
                    "session",
                    "split",
                    "-v",
                    "-p",
                    f"CLAUDE_CODE_AGENT_NAME={name}",
                    f"CLAUDE_CODE_AGENT_COLOR={color}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.error(f"[ITermBackend] Failed to create pane: {result.stderr}")
                raise RuntimeError(f"Failed to create pane: {result.stderr}")

            # Parse output for pane ID
            pane_id = result.stdout.strip()
            if not pane_id:
                # Generate a pane ID based on name
                pane_id = f"iterm-{name}"

            return CreatePaneResult(
                pane_id=pane_id,
                is_first_teammate=True,  # Simplified
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError("Timeout creating iTerm pane")
        except Exception as e:
            raise RuntimeError(f"Failed to create iTerm pane: {e}")

    async def send_command_to_pane(
        self,
        pane_id: PaneId,
        command: str,
        use_external_session: bool = False,
    ) -> None:
        """Send a command to a specific pane.

        Args:
            pane_id: Target pane ID
            command: Command to send
            use_external_session: Not used for iTerm2
        """
        try:
            subprocess.run(
                ["it2", "session", "send", pane_id, command],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception as e:
            logger.error(f"[ITermBackend] Failed to send command: {e}")

    async def set_pane_border_color(
        self,
        pane_id: PaneId,
        color: str,
        use_external_session: bool = False,
    ) -> None:
        """Set the border color for a pane.

        Args:
            pane_id: Target pane ID
            color: Border color
            use_external_session: Not used
        """
        # iTerm2 doesn't have a direct border color command
        pass

    async def set_pane_title(
        self,
        pane_id: PaneId,
        name: str,
        color: str,
        use_external_session: bool = False,
    ) -> None:
        """Set the title for a pane.

        Args:
            pane_id: Target pane ID
            name: Title name
            color: Title color
            use_external_session: Not used
        """
        try:
            subprocess.run(
                ["it2", "session", "rename", pane_id, f"{name} ({color})"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception as e:
            logger.error(f"[ITermBackend] Failed to set title: {e}")

    async def enable_pane_border_status(
        self,
        window_target: Optional[str] = None,
        use_external_session: bool = False,
    ) -> None:
        """Enable pane border status display.

        Args:
            window_target: Target window
            use_external_session: Not used
        """
        # iTerm2 shows pane titles automatically
        pass

    async def rebalance_panes(
        self,
        window_target: str,
        has_leader: bool,
    ) -> None:
        """Rebalance panes.

        Args:
            window_target: Target window
            has_leader: Whether leader pane exists
        """
        # iTerm2 doesn't support automatic rebalancing
        pass

    async def kill_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Kill/close a specific pane.

        Args:
            pane_id: Target pane ID
            use_external_session: Not used

        Returns:
            True if killed successfully
        """
        try:
            result = subprocess.run(
                ["it2", "session", "close", pane_id],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"[ITermBackend] Failed to kill pane: {e}")
            return False

    async def hide_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Hide a pane.

        Args:
            pane_id: Target pane ID
            use_external_session: Not used

        Returns:
            True if hidden successfully
        """
        # iTerm2 doesn't support hiding individual panes
        return False

    async def show_pane(
        self,
        pane_id: PaneId,
        target_window_or_pane: str,
        use_external_session: bool = False,
    ) -> bool:
        """Show a previously hidden pane.

        Args:
            pane_id: Target pane ID
            target_window_or_pane: Target window
            use_external_session: Not used

        Returns:
            True if shown successfully
        """
        # iTerm2 doesn't support showing individual panes
        return False


def create_iterm_backend() -> ITermBackend:
    """Factory function to create an ITermBackend instance.

    Returns:
        New ITermBackend instance
    """
    return ITermBackend()


__all__ = [
    "ITermBackend",
    "create_iterm_backend",
]
