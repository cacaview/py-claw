"""
Extra usage command - Manage extra usage/subscription.

This module provides the /extra-usage command that helps users
manage their subscription and extra usage settings.

TS Reference: ClaudeCode-main/src/commands/extra-usage/
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.commands import CommandDefinition
    from py_claw.cli.runtime import RuntimeState
    from py_claw.settings.loader import SettingsLoadResult


def extra_usage_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle /extra-usage command - manage subscription and extra usage."""
    # Try to get subscription info from config
    from py_claw.services.config.service import get_global_config

    subscription_type = _get_subscription_type()
    is_team_or_enterprise = subscription_type in ("team", "enterprise")

    # Check if user is logged in
    oauth_account = _get_oauth_account()
    if not oauth_account:
        return "Please log in to Claude Code first using /login"

    # For team/enterprise users, show admin request info
    if is_team_or_enterprise:
        return (
            "Your organization uses team/enterprise subscription.\n"
            "To manage extra usage, please contact your admin.\n"
            "Or visit: https://claude.ai/admin-settings/usage"
        )

    # For personal users, open browser to usage settings
    url = "https://claude.ai/settings/usage"
    return (
        f"Opening {url} in your browser...\n"
        "You can also manually visit this URL to manage your extra usage settings."
    )


def _get_subscription_type() -> str | None:
    """Get subscription type from config."""
    try:
        from py_claw.services.config.service import get_global_config
        config = get_global_config()
        oauth = config.oauth_account or {}
        return oauth.get("subscription_type")
    except Exception:
        return None


def _get_oauth_account() -> dict | None:
    """Get OAuth account info."""
    try:
        from py_claw.services.config.service import get_global_config
        config = get_global_config()
        return config.oauth_account
    except Exception:
        return None