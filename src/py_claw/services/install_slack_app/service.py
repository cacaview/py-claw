"""
Install Slack App service.

Opens the Slack app installation page in the browser.
"""
from __future__ import annotations

import logging
import webbrowser

from .types import SlackInstallConfig, SlackInstallResult

logger = logging.getLogger(__name__)

_slack_config = SlackInstallConfig()


def get_slack_install_config() -> SlackInstallConfig:
    """Get the Slack install configuration."""
    return _slack_config


def open_slack_install_page() -> SlackInstallResult:
    """Open the Slack app installation page.

    Returns:
        SlackInstallResult with success status and message
    """
    url = _slack_config.app_url
    try:
        # Log the event (in Python we don't have analytics, so just log)
        logger.info("Opening Slack install page: %s", url)

        # Open the browser
        success = webbrowser.open(url)

        if success:
            return SlackInstallResult(
                success=True,
                message=f"Opened Slack app page in browser: {url}",
                url=url,
            )
        else:
            return SlackInstallResult(
                success=False,
                message=f"Failed to open browser. Please visit: {url}",
                url=url,
            )
    except Exception as e:
        logger.exception("Error opening Slack install page")
        return SlackInstallResult(
            success=False,
            message=f"Error opening Slack install page: {e}",
            url=url,
        )
