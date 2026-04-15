"""
Install Slack App service.

Opens the Slack app installation page in the browser.

Based on ClaudeCode-main/src/services/install-slack-app/
"""
from py_claw.services.install_slack_app.service import (
    get_slack_install_config,
    open_slack_install_page,
)
from py_claw.services.install_slack_app.types import (
    SlackInstallConfig,
    SlackInstallResult,
)


__all__ = [
    "get_slack_install_config",
    "open_slack_install_page",
    "SlackInstallConfig",
    "SlackInstallResult",
]
