"""
Fast mode command - Toggle fast mode for premium speed.

This module provides the /fast command that enables or disables
fast mode, a high-speed mode that uses a faster model at premium rates.

TS Reference: ClaudeCode-main/src/commands/fast/
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.commands import CommandDefinition
    from py_claw.cli.runtime import RuntimeState
    from py_claw.settings.loader import SettingsLoadResult


# Fast mode model - Sonnet 4 for speed
FAST_MODE_MODEL = "sonnet-4-20250514"

# Fast mode is not yet implemented
_FAST_MODE_AVAILABLE = False


def fast_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle /fast command - toggle fast mode on or off."""
    args = arguments.strip().lower() if arguments else ""

    if not _FAST_MODE_AVAILABLE:
        return "Fast mode is not yet available in this version."

    if args == "on":
        return _enable_fast_mode(state)
    elif args == "off":
        return _disable_fast_mode(state)
    elif args == "":
        # Show current status
        return _show_fast_mode_status(state)
    else:
        return (
            "Usage: /fast [on|off]\n"
            "  on  - Enable fast mode\n"
            "  off - Disable fast mode\n"
            "  (no argument) - Show current status"
        )


def _show_fast_mode_status(state: RuntimeState) -> str:
    """Show current fast mode status."""
    current = getattr(state, "fast_mode", False)
    if current:
        model = getattr(state, "model", None) or FAST_MODE_MODEL
        return (
            f"Fast mode is ON\n"
            f"Model: {model}\n"
            f"Fast mode uses Sonnet 4 for faster responses at a premium rate."
        )
    else:
        return (
            "Fast mode is OFF\n"
            "Enable with /fast on"
        )


def _enable_fast_mode(state: RuntimeState) -> str:
    """Enable fast mode."""
    try:
        from py_claw.services.config.service import save_global_config

        def update(config):
            config.fast_mode_enabled = True
            return config

        save_global_config(update)
        state.fast_mode = True
        state.model = FAST_MODE_MODEL
        return (
            f"Fast mode enabled. Model set to {FAST_MODE_MODEL}.\n"
            "Fast mode uses Sonnet 4 for faster responses at a premium rate."
        )
    except Exception as e:
        return f"Failed to enable fast mode: {e}"


def _disable_fast_mode(state: RuntimeState) -> str:
    """Disable fast mode."""
    try:
        from py_claw.services.config.service import save_global_config

        def update(config):
            config.fast_mode_enabled = False
            return config

        save_global_config(update)
        state.fast_mode = False
        return "Fast mode disabled."
    except Exception as e:
        return f"Failed to disable fast mode: {e}"