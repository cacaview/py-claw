"""
Teammate Layout Manager

Manages teammate pane layouts in the swarm view.
Handles color assignments and pane organization.

Based on ClaudeCode-main/src/utils/swarm/teammateLayoutManager.ts
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Agent colors palette (from AgentTool)
AGENT_COLORS = [
    "blue",
    "cyan",
    "green",
    "magenta",
    "orange",
    "pink",
    "purple",
    "red",
    "teal",
    "yellow",
]

# Track color assignments for teammates (persisted per session)
_teammate_color_assignments: dict[str, str] = {}
_color_index = 0


def assign_teammate_color(teammate_id: str) -> str:
    """Assigns a unique color to a teammate from the available palette.

    Colors are assigned in round-robin order.

    Args:
        teammate_id: Unique identifier for the teammate

    Returns:
        The assigned color name
    """
    global _color_index

    if teammate_id in _teammate_color_assignments:
        return _teammate_color_assignments[teammate_id]

    color = AGENT_COLORS[_color_index % len(AGENT_COLORS)]
    _teammate_color_assignments[teammate_id] = color
    _color_index += 1

    return color


def get_teammate_color(teammate_id: str) -> Optional[str]:
    """Get the assigned color for a teammate.

    Args:
        teammate_id: Unique identifier for the teammate

    Returns:
        The assigned color or None if not found
    """
    return _teammate_color_assignments.get(teammate_id)


def clear_teammate_colors() -> None:
    """Clear all teammate color assignments.

    Called during team cleanup to reset state for potential new teams.
    """
    global _color_index
    _teammate_color_assignments.clear()
    _color_index = 0


async def create_teammate_pane_in_swarm_view(
    teammate_name: str,
    teammate_color: str,
) -> dict[str, any]:
    """Create a new teammate pane in the swarm view.

    Automatically selects the appropriate backend (tmux or iTerm2) based on environment.

    Args:
        teammate_name: Name of the teammate
        teammate_color: Color for the teammate

    Returns:
        Dict with pane_id and is_first_teammate
    """
    from py_claw.swarm.backends.registry import detect_backend

    result = await detect_backend()
    if not result:
        raise RuntimeError("No backend available for teammate panes")

    backend = result.backend
    pane_result = await backend.create_teammate_pane_in_swarm_view(
        teammate_name, teammate_color
    )

    return {
        "pane_id": pane_result.pane_id,
        "is_first_teammate": pane_result.is_first_teammate,
    }


async def enable_pane_border_status(
    window_target: Optional[str] = None,
    use_swarm_socket: bool = False,
) -> None:
    """Enable pane border status for a window.

    Args:
        window_target: Target window
        use_swarm_socket: Whether to use swarm socket
    """
    from py_claw.swarm.backends.registry import detect_backend

    result = await detect_backend()
    if not result:
        return

    backend = result.backend
    await backend.enable_pane_border_status(window_target, use_swarm_socket)


async def send_command_to_pane(
    pane_id: str,
    command: str,
    use_swarm_socket: bool = False,
) -> None:
    """Send a command to a specific pane.

    Args:
        pane_id: ID of the target pane
        command: Command to send
        use_swarm_socket: Whether to use swarm socket
    """
    from py_claw.swarm.backends.registry import detect_backend

    result = await detect_backend()
    if not result:
        return

    backend = result.backend
    await backend.send_command_to_pane(pane_id, command, use_swarm_socket)


__all__ = [
    "AGENT_COLORS",
    "assign_teammate_color",
    "get_teammate_color",
    "clear_teammate_colors",
    "create_teammate_pane_in_swarm_view",
    "enable_pane_border_status",
    "send_command_to_pane",
]
