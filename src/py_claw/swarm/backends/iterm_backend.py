"""
ITermBackend implements pane management using iTerm2's native split panes
via the it2 CLI tool.

Based on ClaudeCode-main/src/utils/swarm/backends/ITermBackend.ts
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

from .detection import is_in_iterm2, is_iterm2_cli_available
from .types import (
    BackendType,
    CreatePaneResult,
    PaneBackend,
    PaneId,
)

logger = logging.getLogger(__name__)

# iTerm2 CLI command
IT2_COMMAND = "it2"

# Track session IDs for teammates
_teammate_session_ids: list[str] = []
_first_pane_used = False
_pane_creation_lock: Optional[asyncio.Lock] = None


def _get_leader_session_id() -> Optional[str]:
    """
    Gets the leader's session ID from ITERM_SESSION_ID env var.

    Format: "wXtYpZ:UUID" - we extract the UUID part after the colon.
    Returns None if not in iTerm2 or env var not set.
    """
    iterm_session_id = os.environ.get("ITERM_SESSION_ID", "")
    if not iterm_session_id:
        return None
    colon_index = iterm_session_id.find(":")
    if colon_index == -1:
        return None
    return iterm_session_id[colon_index + 1:]


def _parse_split_output(output: str) -> str:
    """
    Parses the session ID from `it2 session split` output.

    Format: "Created new pane: <session-id>"
    """
    match = re.search(r"Created new pane:\s*(.+)", output)
    if match:
        return match.group(1).strip()
    return ""


async def _run_it2(args: list[str]) -> tuple[int, str, str]:
    """
    Runs an it2 CLI command and returns the result.

    Args:
        args: Command arguments

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            [IT2_COMMAND] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


async def _acquire_pane_creation_lock() -> asyncio.Lock:
    """Acquire a lock for pane creation to prevent race conditions."""
    global _pane_creation_lock
    if _pane_creation_lock is None:
        _pane_creation_lock = asyncio.Lock()
    return _pane_creation_lock


class ITermBackend:
    """
    ITermBackend implements pane management using iTerm2's native split panes
    via the it2 CLI tool.
    """

    type: BackendType = BackendType.ITERM2
    display_name: str = "iTerm2"
    supports_hide_show: bool = False

    async def is_available(self) -> bool:
        """
        Checks if iTerm2 backend is available (in iTerm2 with it2 CLI installed).

        Returns:
            True if available
        """
        if platform.system() != "Darwin":
            logger.debug("[ITermBackend] isAvailable: false (not on macOS)")
            return False

        in_iterm = is_in_iterm2()
        logger.debug(f"[ITermBackend] isAvailable check: inITerm2={in_iterm}")
        if not in_iterm:
            logger.debug("[ITermBackend] isAvailable: false (not in iTerm2)")
            return False

        it2_available = await is_iterm2_cli_available()
        logger.debug(
            f"[ITermBackend] isAvailable: {it2_available} (it2 CLI {it2_available and 'found' or 'not found'})"
        )
        return it2_available

    async def is_running_inside(self) -> bool:
        """
        Checks if we're currently running inside iTerm2.

        Returns:
            True if running inside iTerm2
        """
        result = is_in_iterm2()
        logger.debug(f"[ITermBackend] isRunningInside: {result}")
        return result

    async def create_teammate_pane_in_swarm_view(
        self,
        name: str,
        color: str,
    ) -> CreatePaneResult:
        """
        Creates a new teammate pane in the swarm view.

        Uses a lock to prevent race conditions when multiple teammates are
        spawned in parallel.

        Args:
            name: Teammate name
            color: Agent color

        Returns:
            CreatePaneResult with pane ID
        """
        logger.debug(f"[ITermBackend] createTeammatePaneInSwarmView called for {name} with color {color}")

        lock = await _acquire_pane_creation_lock()
        async with lock:
            global _first_pane_used

            # Layout: Leader on left, teammates stacked vertically on the right
            is_first_teammate = not _first_pane_used

            logger.debug(
                f"[ITermBackend] Creating pane: isFirstTeammate={is_first_teammate}, existingPanes={len(_teammate_session_ids)}"
            )

            split_args: list[str] = []
            targeted_teammate_id: Optional[str] = None

            if is_first_teammate:
                # Split from leader's session (extracted from ITERM_SESSION_ID env var)
                leader_session_id = _get_leader_session_id()
                if leader_session_id:
                    split_args = ["session", "split", "-v", "-s", leader_session_id]
                    logger.debug(f"[ITermBackend] First split from leader session: {leader_session_id}")
                else:
                    # Fallback to active session
                    split_args = ["session", "split", "-v"]
                    logger.debug("[ITermBackend] First split from active session (no leader ID)")
            else:
                # Split from the last teammate's session to stack vertically
                if _teammate_session_ids:
                    targeted_teammate_id = _teammate_session_ids[-1]
                    split_args = ["session", "split", "-s", targeted_teammate_id]
                    logger.debug(f"[ITermBackend] Subsequent split from teammate session: {targeted_teammate_id}")
                else:
                    # Fallback to active session
                    split_args = ["session", "split"]
                    logger.debug("[ITermBackend] Subsequent split from active session (no teammate ID)")

            code, stdout, stderr = await _run_it2(split_args)

            if code != 0:
                raise RuntimeError(f"Failed to create iTerm2 split pane: {stderr}")

            if is_first_teammate:
                _first_pane_used = True

            # Parse the session ID from split output
            pane_id = _parse_split_output(stdout)

            if not pane_id:
                raise RuntimeError(f"Failed to parse session ID from split output: {stdout}")

            logger.debug(f"[ITermBackend] Created teammate pane for {name}: {pane_id}")

            _teammate_session_ids.append(pane_id)

            return CreatePaneResult(pane_id=pane_id, is_first_teammate=is_first_teammate)

    async def send_command_to_pane(
        self,
        pane_id: PaneId,
        command: str,
        use_external_session: bool = False,
    ) -> None:
        """
        Sends a command to a specific pane.

        Args:
            pane_id: Pane ID
            command: Command to send
            use_external_session: Unused for iTerm2
        """
        # Use it2 session run to execute command
        args = ["session", "run"]
        if pane_id:
            args.extend(["-s", pane_id])
        args.append(command)

        code, _, stderr = await _run_it2(args)

        if code != 0:
            raise RuntimeError(f"Failed to send command to iTerm2 pane {pane_id}: {stderr}")

    async def set_pane_border_color(
        self,
        pane_id: PaneId,
        color: str,
        use_external_session: bool = False,
    ) -> None:
        """
        No-op for iTerm2 - pane colors would require escape sequences.

        Args:
            pane_id: Pane ID (unused)
            color: Color (unused)
            use_external_session: Unused
        """
        # Skip for performance - each it2 call spawns a Python process
        pass

    async def set_pane_title(
        self,
        pane_id: PaneId,
        name: str,
        color: str,
        use_external_session: bool = False,
    ) -> None:
        """
        No-op for iTerm2 - titles would require escape sequences.

        Args:
            pane_id: Pane ID (unused)
            name: Name (unused)
            color: Color (unused)
            use_external_session: Unused
        """
        # Skip for performance
        pass

    async def enable_pane_border_status(
        self,
        window_target: Optional[str] = None,
        use_external_session: bool = False,
    ) -> None:
        """
        No-op for iTerm2 - tab titles are shown in tabs automatically.

        Args:
            window_target: Unused
            use_external_session: Unused
        """
        # iTerm2 doesn't have the concept of pane border status like tmux
        pass

    async def rebalance_panes(
        self,
        window_target: str,
        has_leader: bool,
    ) -> None:
        """
        No-op for iTerm2 - pane balancing is handled automatically.

        Args:
            window_target: Unused
            has_leader: Unused
        """
        logger.debug("[ITermBackend] Pane rebalancing not implemented for iTerm2")

    async def kill_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """
        Kills/closes a specific pane using the it2 CLI.

        Also removes the pane from tracked session IDs.

        Args:
            pane_id: Pane ID to kill
            use_external_session: Unused

        Returns:
            True if killed successfully
        """
        # -f (force) is required to avoid confirm dialogs
        code, _, stderr = await _run_it2(["session", "close", "-f", "-s", pane_id])

        # Clean up module state regardless of close result
        if pane_id in _teammate_session_ids:
            _teammate_session_ids.remove(pane_id)

        global _first_pane_used
        if not _teammate_session_ids:
            _first_pane_used = False

        return code == 0

    async def hide_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """
        Stub for hiding a pane - not supported in iTerm2 backend.

        Args:
            pane_id: Unused
            use_external_session: Unused

        Returns:
            Always False
        """
        logger.debug("[ITermBackend] hidePane not supported in iTerm2")
        return False

    async def show_pane(
        self,
        pane_id: PaneId,
        target_window_or_pane: str,
        use_external_session: bool = False,
    ) -> bool:
        """
        Stub for showing a hidden pane - not supported in iTerm2 backend.

        Args:
            pane_id: Unused
            target_window_or_pane: Unused
            use_external_session: Unused

        Returns:
            Always False
        """
        logger.debug("[ITermBackend] showPane not supported in iTerm2")
        return False


def register_iterm_backend() -> None:
    """Register the ITermBackend with the registry."""
    from .registry import register_backend
    register_backend(BackendType.ITERM2, ITermBackend)


__all__ = [
    "ITermBackend",
    "register_iterm_backend",
]
