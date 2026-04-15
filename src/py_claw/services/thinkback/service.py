"""
Thinkback service for Claude Code Year in Review animation.

Manages the thinkback skill - a personalized ASCII animation
showcasing user's coding year.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from .types import AnimationResult, MenuAction, ThinkbackPhase, ThinkbackResult

logger = logging.getLogger(__name__)

INTERNAL_MARKETPLACE = "claude-code-marketplace"
OFFICIAL_MARKETPLACE = "claude-plugins-official"
SKILL_NAME = "thinkback"


def get_skill_directories() -> list[Path]:
    """Find all directories that might contain the thinkback skill.

    Returns:
        List of potential skill directories
    """
    directories = []

    # User plugins directory
    user_root = Path.home() / ".claude"
    directories.append(user_root / "plugins")
    directories.append(user_root / "skills")

    # Project-level skills
    cwd = Path.cwd()
    directories.append(cwd / ".claude" / "skills")

    return [d for d in directories if d.exists()]


def find_thinkback_skill_dir() -> Path | None:
    """Find the installed thinkback skill directory.

    Returns:
        Path to thinkback skill directory or None
    """
    for base_dir in get_skill_directories():
        skill_dir = base_dir / SKILL_NAME
        if skill_dir.exists() and skill_dir.is_dir():
            return skill_dir

        # Check nested in plugin directories
        if base_dir.is_dir():
            for item in base_dir.iterdir():
                if item.is_dir():
                    nested = item / "skills" / SKILL_NAME
                    if nested.exists():
                        return nested

    return None


async def play_animation(skill_dir: Path | None = None) -> AnimationResult:
    """Play the thinkback animation.

    Args:
        skill_dir: Path to thinkback skill directory

    Returns:
        AnimationResult with playback status
    """
    if skill_dir is None:
        skill_dir = find_thinkback_skill_dir()

    if skill_dir is None:
        return AnimationResult(
            success=False,
            message="Thinkback skill not installed. Use /think-back to install it first.",
        )

    try:
        # Look for player script or HTML file
        player_path = skill_dir / "player.js"
        html_path = skill_dir / "index.html"

        if player_path.exists():
            # Run player with node
            result = subprocess.run(
                ["node", str(player_path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(skill_dir),
            )

            if result.returncode == 0:
                return AnimationResult(
                    success=True,
                    message=result.stdout or "Animation played successfully.",
                    path=str(skill_dir),
                )
            else:
                return AnimationResult(
                    success=False,
                    message=f"Animation error: {result.stderr}",
                    path=str(skill_dir),
                )

        elif html_path.exists():
            # Open HTML in browser
            import webbrowser
            webbrowser.open(f"file://{html_path}")
            return AnimationResult(
                success=True,
                message=f"Opened thinkback in browser: {html_path}",
                path=str(html_path),
            )

        else:
            return AnimationResult(
                success=False,
                message="Thinkback skill is missing required files.",
                path=str(skill_dir),
            )

    except subprocess.TimeoutExpired:
        return AnimationResult(
            success=False,
            message="Animation playback timed out.",
        )
    except Exception as e:
        logger.exception("Error playing thinkback")
        return AnimationResult(
            success=False,
            message=f"Error: {e}",
        )


async def check_installation() -> ThinkbackResult:
    """Check if thinkback is installed.

    Returns:
        ThinkbackResult with installation status
    """
    skill_dir = find_thinkback_skill_dir()

    if skill_dir:
        return ThinkbackResult(
            success=True,
            message=f"Thinkback is installed: {skill_dir}",
            phase=ThinkbackPhase.READY,
        )
    else:
        return ThinkbackResult(
            success=True,
            message="Thinkback is not installed. Use /think-back to install.",
            phase=ThinkbackPhase.CHECKING,
        )


def show_menu(has_generated: bool = True) -> MenuAction:
    """Show the thinkback menu and get user choice.

    Args:
        has_generated: Whether thinkback data exists

    Returns:
        Selected MenuAction
    """
    # This would show a UI menu in real implementation
    # For now, return PLAY as default
    return MenuAction.PLAY


async def get_thinkback_info() -> ThinkbackResult:
    """Get thinkback information.

    Returns:
        ThinkbackResult with status
    """
    skill_dir = find_thinkback_skill_dir()

    if skill_dir is None:
        return ThinkbackResult(
            success=False,
            message="Thinkback not installed. Use /think-back to install.",
            phase=ThinkbackPhase.CHECKING,
        )

    # Check for generated data
    data_dir = skill_dir / "data"
    has_data = data_dir.exists() and any(data_dir.iterdir()) if data_dir.exists() else False

    return ThinkbackResult(
        success=True,
        message=f"Thinkback installed at {skill_dir}. "
        + ("Has generated data." if has_data else "No generated data yet."),
        phase=ThinkbackPhase.READY,
    )
