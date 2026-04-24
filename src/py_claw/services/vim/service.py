"""
Vim service for managing Vim mode.

Provides Vim editing mode state management with TUI integration.
When vim mode changes, publishes updates to the global TUI store
so the UI can react to mode changes.

Based on ClaudeCode-main/src/services/vim/
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .types import VimConfig, VimMode, VimResult

if TYPE_CHECKING:
    from py_claw.state.tui_state import TUIStateSnapshot

logger = logging.getLogger(__name__)

_vim_config = VimConfig()

# ── TUI state integration ──────────────────────────────────────────────────


def _get_tui_state_snapshot() -> "TUIStateSnapshot | None":
    """Get TUI state snapshot if available."""
    try:
        from py_claw.state.tui_state import get_tui_state_snapshot
        return get_tui_state_snapshot()
    except ImportError:
        return None


def _publish_vim_mode_to_tui(mode: VimMode | None) -> None:
    """Publish vim mode change to global TUI store.

    Args:
        mode: The new vim mode, or None if vim is disabled
    """
    try:
        from py_claw.state.tui_state import update_tui_vim_mode
        # Convert lowercase vim service mode to uppercase TUI mode
        if mode is None:
            update_tui_vim_mode("INSERT")  # Default when disabled
        else:
            tui_mode = mode.value.upper()
            update_tui_vim_mode(tui_mode)
    except ImportError:
        logger.debug("TUI state not available for vim mode publish")


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

    was_enabled = _vim_config.enabled
    _vim_config.enabled = not _vim_config.enabled
    save_vim_config(_vim_config)

    if _vim_config.enabled:
        # Publish to TUI state when enabling
        _publish_vim_mode_to_tui(_vim_config.current_mode)
        return VimResult(
            success=True,
            message="Vim mode enabled. Use 'i' for insert mode, Escape to return to normal mode.",
            mode=_vim_config.current_mode,
        )
    else:
        # Clear TUI vim mode when disabling
        _publish_vim_mode_to_tui(None)
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

    # Publish to TUI state for UI integration
    _publish_vim_mode_to_tui(mode)

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


# ── TUI state helpers ────────────────────────────────────────────────────────


def get_tui_vim_mode() -> str:
    """Get current vim mode from TUI state.

    Returns:
        Uppercase vim mode string ('INSERT', 'NORMAL', 'VISUAL') or 'INSERT' if not in vim mode
    """
    snapshot = _get_tui_state_snapshot()
    if snapshot is None:
        return "INSERT"
    # Return the TUI vim mode, defaulting to INSERT
    return snapshot.vim_mode or "INSERT"


def is_vim_active_in_tui() -> bool:
    """Check if vim mode is currently active in the TUI.

    Vim is considered active in TUI if the TUI vim mode is not INSERT
    (meaning user is in NORMAL or VISUAL mode).

    Returns:
        True if vim mode is active in TUI
    """
    mode = get_tui_vim_mode()
    return mode != "INSERT"


def get_vim_status_for_tui() -> dict:
    """Get vim status information for TUI display.

    Returns:
        Dictionary with vim status suitable for TUI rendering
    """
    global _vim_config
    _vim_config = load_vim_config()

    tui_mode = get_tui_vim_mode()

    return {
        "vim_enabled": _vim_config.enabled,
        "vim_mode": tui_mode,
        "short_label": tui_mode[:3] if _vim_config.enabled else "",
        "status_text": f"VIM {_vim_config.current_mode.value.upper()}" if _vim_config.enabled else "",
    }
