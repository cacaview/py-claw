"""
Types for install_slack_app service.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SlackInstallResult:
    """Result of opening Slack install page."""
    success: bool
    message: str
    url: str = "https://slack.com/apps"


@dataclass
class SlackInstallConfig:
    """Configuration for Slack install."""
    app_url: str = "https://slack.com/apps"
