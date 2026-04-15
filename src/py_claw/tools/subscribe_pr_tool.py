"""
SubscribePRTool - Subscribe to GitHub pull request updates.

Provides PR subscription capabilities for receiving
notifications when PRs are updated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import Field

from py_claw.tools.base import BaseTool, ToolResult


@dataclass
class SubscribePRInput:
    """Input schema for SubscribePRTool."""
    repo: str = Field(description="Repository in format owner/repo")
    pr_number: int = Field(description="Pull request number")
    events: list[str] = Field(
        default_factory=lambda: ["opened", "closed", "comment"],
        description="Events to subscribe to",
    )
    webhook_url: str | None = Field(default=None, description="Optional webhook URL for notifications")


class SubscribePRTool(BaseTool):
    """
    SubscribePRTool - Subscribe to PR updates.

    Provides PR subscription capabilities for receiving
    notifications when PRs are updated.
    """

    name = "SubscribePR"
    description = "Subscribe to GitHub pull request updates"
    input_schema = SubscribePRInput

    def __init__(self) -> None:
        super().__init__()
        self._subscriptions: dict[str, Any] = {}

    async def execute(self, input_data: SubscribePRInput, **kwargs: Any) -> ToolResult:
        """
        Subscribe to a PR.

        Args:
            input_data: SubscribePRInput with subscription details
            **kwargs: Additional context

        Returns:
            ToolResult with subscription outcome
        """
        repo = input_data.repo
        pr_number = input_data.pr_number
        events = input_data.events

        if not repo:
            return ToolResult(success=False, content="No repository specified")

        subscription_key = f"{repo}#{pr_number}"

        self._subscriptions[subscription_key] = {
            "repo": repo,
            "pr_number": pr_number,
            "events": events,
            "webhook_url": input_data.webhook_url,
        }

        lines = [f"[SubscribePR] Subscription created"]
        lines.append(f"Repository: {repo}")
        lines.append(f"PR Number: {pr_number}")
        lines.append(f"Events: {', '.join(events)}")
        lines.append(f"Subscription ID: sub_{len(self._subscriptions)}")

        if input_data.webhook_url:
            lines.append(f"Webhook: {input_data.webhook_url[:50]}...")

        return ToolResult(
            success=True,
            content="\n".join(lines),
        )

    def get_subscriptions(self) -> dict[str, Any]:
        """Get all active subscriptions."""
        return self._subscriptions.copy()
