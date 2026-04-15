"""
Vim service for managing Vim mode.

Note: This is a simplified implementation. The actual Claude Code
Vim mode is more sophisticated with keybinding integration.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .types import VimConfig, VimMode, VimResult

logger = logging.getLogger(__name__)

_vim_config = VimConfig()


def get_vim_storage_path() -> Path:
    """Get the path to vim configuration.

    Returns:
        Path to vim.json
    """
    config_dir = Path.home() / ".claude"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "vim.json"


def load_vim_config() -> VimConfig:
    """Load vim configuration from storage.

    Returns:
        VimConfig object
    """
    path = get_vim_storage_path()
    if not path.exists():
        return VimConfig()

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return VimConfig(
            enabled=data.get("enabled", False),
            current_mode=VimMode(data.get("current_mode", "normal")),
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Error loading vim config: %s", e)
        return VimConfig()


def save_vim_config(config: VimConfig) -> None:
    """Save vim configuration to storage.

    Args:
        config: VimConfig to save
    """
    path = get_vim_storage_path()
    try:
        data = {
            "enabled": config.enabled,
            "current_mode": config.current_mode.value,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        logger.error("Error saving vim config: %s", e)


def get_current_mode() -> VimMode:
    """Get the current vim mode.

    Returns:
        Current VimMode
    """
    global _vim_config
    _vim_config = load_vim_config()
    return _vim_config.current_mode


def is_vim_enabled() -> bool:
    """Check if vim mode is enabled.

    Returns:
        True if vim mode is enabled
    """
    global _vim_config
    _vim_config = load_vim_config()
    return _vim_config.enabled


def toggle_vim_mode() -> VimResult:
    """Toggle vim mode on/off.

    Returns:
        VimResult with operation status
    """
    global _vim_config
    _vim_config = load_vim_config()

    _vim_config.enabled = not _vim_config.enabled
    save_vim_config(_vim_config)

    if _vim_config.enabled:
        return VimResult(
            success=True,
            message="Vim mode enabled. Use 'i' for insert mode, Escape to return to normal mode.",
            mode=_vim_config.current_mode,
        )
    else:
        return VimResult(
            success=True,
            message="Vim mode disabled.",
            mode=None,
        )


def set_vim_mode(mode: VimMode) -> VimResult:
    """Set the vim mode.

    Args:
        mode: VimMode to set

    Returns:
        VimResult with operation status
    """
    global _vim_config
    _vim_config = load_vim_config()

    if not _vim_config.enabled:
        return VimResult(
            success=False,
            message="Vim mode is not enabled. Use /vim to enable it first.",
            mode=None,
        )

    _vim_config.current_mode = mode
    save_vim_config(_vim_config)

    return VimResult(
        success=True,
        message=f"Vim mode set to {mode.value}",
        mode=mode,
    )


def get_vim_info() -> VimResult:
    """Get vim mode information.

    Returns:
        VimResult with vim status
    """
    global _vim_config
    _vim_config = load_vim_config()

    if _vim_config.enabled:
        return VimResult(
            success=True,
            message=f"Vim mode: {_vim_config.current_mode.value}",
            mode=_vim_config.current_mode,
        )
    else:
        return VimResult(
            success=True,
            message="Vim mode is disabled",
            mode=None,
        )


def format_vim_text(result: VimResult) -> str:
    """Format vim result as plain text.

    Args:
        result: VimResult to format

    Returns:
        Formatted text
    """
    lines = [
        "Claude Code Vim Mode",
        "=" * 40,
        "",
    ]

    if result.mode:
        lines.append(f"Mode: {result.mode.value}")
        lines.append("")
        lines.append("Keybindings:")
        lines.append("  i - Enter insert mode")
        lines.append("  Escape - Return to normal mode")
        lines.append("  v - Enter visual mode")
        lines.append("  : - Enter command mode")
        lines.append("")
        lines.append("Use /vim to disable vim mode")
    else:
        lines.append("Vim mode is disabled")
        lines.append("")
        lines.append("Use /vim to enable vim mode")

    return "\n".join(lines)
