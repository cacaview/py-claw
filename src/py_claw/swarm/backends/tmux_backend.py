"""
Tmux backend for swarm team orchestration.

Based on ClaudeCode-main/src/utils/swarm/backends/TmuxBackend.ts

Provides pane management using tmux for teammate visualization.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from typing import Any

from .types import (
    BackendInfo,
    BackendType,
    CreatePaneResult,
    PaneBackend,
    PaneId,
)


# Constants
TMUX_COMMAND = os.environ.get("TMUX_COMMAND", "tmux")
SWARM_WINDOW_NAME = "swarm"


class TmuxBackend:
    """Tmux backend for pane management."""

    def __init__(self) -> None:
        self._info = BackendInfo(
            backend_type=BackendType.TMUX,
            display_name="tmux",
            supports_hide_show=True,
        )

    @property
    def type(self) -> BackendType:
        return self._info.backend_type

    @property
    def display_name(self) -> str:
        return self._info.display_name

    @property
    def supports_hide_show(self) -> bool:
        return self._info.supports_hide_show

    async def is_available(self) -> bool:
        """Check if tmux is available on the system."""
        return shutil.which("tmux") is not None

    async def is_running_inside(self) -> bool:
        """Check if we're currently running inside a tmux session."""
        return os.environ.get("TMUX") is not None

    async def _run_tmux_command(
        self,
        args: list[str],
        timeout_ms: int = 5000,
    ) -> tuple[str, int]:
        """Run a tmux command and return stdout and return code."""
        try:
            proc = await asyncio.create_subprocess_exec(
                TMUX_COMMAND,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout_ms / 1000,
                )
                return stdout.decode("utf-8", errors="replace"), proc.returncode
            except asyncio.TimeoutError:
                proc.kill()
                return "", 1
        except Exception:
            return "", 1

    async def create_teammate_pane_in_swarm_view(
        self,
        name: str,
        color: str,
    ) -> CreatePaneResult:
        """
        Create a new pane for a teammate in the swarm view.

        Args:
            name: The teammate's name for display
            color: The color to use for the pane border/title

        Returns:
            CreatePaneResult with pane ID and first teammate flag
        """
        # Check if this is the first teammate
        stdout, code = await self._run_tmux_command(
            ["list-panes", "-t", SWARM_WINDOW_NAME],
            timeout_ms=3000,
        )
        is_first = code != 0 or stdout.strip() == ""

        # Split the window to create a new pane
        split_cmd = ["split-window", "-t", SWARM_WINDOW_NAME, "-h", "-b"]
        stdout, code = await self._run_tmux_command(split_cmd)

        if code != 0:
            raise RuntimeError(f"Failed to create tmux pane: {stdout}")

        # Get the pane ID of the new pane
        pane_id = stdout.strip() if stdout.strip() else "%1"

        return CreatePaneResult(
            pane_id=pane_id,
            is_first_teammate=is_first,
        )

    async def send_command_to_pane(
        self,
        pane_id: PaneId,
        command: str,
        use_external_session: bool = False,
    ) -> None:
        """Send a command to execute in a specific pane."""
        target = f"{SWARM_WINDOW_NAME}.{pane_id}" if "." not in pane_id else pane_id
        await self._run_tmux_command(
            ["send-keys", "-t", target, command, "Enter"]
        )

    async def set_pane_border_color(
        self,
        pane_id: PaneId,
        color: str,
        use_external_session: bool = False,
    ) -> None:
        """Set the border color for a pane."""
        target = f"{SWARM_WINDOW_NAME}.{pane_id}" if "." not in pane_id else pane_id
        # tmux doesn't support direct border color change via CLI
        # This would require using terminal escape sequences or a plugin
        pass

    async def set_pane_title(
        self,
        pane_id: PaneId,
        name: str,
        color: str,
        use_external_session: bool = False,
    ) -> None:
        """Set the title for a pane."""
        target = f"{SWARM_WINDOW_NAME}.{pane_id}" if "." not in pane_id else pane_id
        await self._run_tmux_command(
            ["select-pane", "-t", target, "-T", name]
        )

    async def enable_pane_border_status(
        self,
        window_target: str | None = None,
        use_external_session: bool = False,
    ) -> None:
        """Enable pane border status display."""
        target = window_target or SWARM_WINDOW_NAME
        await self._run_tmux_command(
            ["setw", "-t", target, "window-style", "fg=colour250"]
        )
        await self._run_tmux_command(
            ["setw", "-t", target, "window-active-style", "fg=colour250"]
        )

    async def rebalance_panes(
        self,
        window_target: str,
        has_leader: bool,
    ) -> None:
        """Rebalance panes to achieve the desired layout."""
        await self._run_tmux_command(
            ["select-layout", "-t", window_target, "even-horizontal"]
        )

    async def kill_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Kill/close a specific pane."""
        target = f"{SWARM_WINDOW_NAME}.{pane_id}" if "." not in pane_id else pane_id
        stdout, code = await self._run_tmux_command(
            ["kill-pane", "-t", target]
        )
        return code == 0

    async def hide_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Hide a pane by breaking it out into a hidden window."""
        # This would require creating a hidden window and moving the pane there
        # For now, just return False as this is complex to implement
        return False

    async def show_pane(
        self,
        pane_id: PaneId,
        target_window_or_pane: str,
        use_external_session: bool = False,
    ) -> bool:
        """Show a previously hidden pane by joining it back into the main window."""
        # This would require moving the pane from a hidden window back to main
        # For now, just return False as this is complex to implement
        return False


__all__ = [
    "TmuxBackend",
]
