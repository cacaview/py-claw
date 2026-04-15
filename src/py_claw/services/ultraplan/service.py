"""
Ultraplan service for CCR ExitPlanMode polling.

Handles CCR ultraplan feature - polls remote session for
ExitPlanMode approval, extracts approved plan text.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

from .types import (
    PollFailReason,
    ScanResult,
    UltraplanConfig,
    UltraplanPhase,
    UltraplanResult,
)

logger = logging.getLogger(__name__)

# Sentinel for ultraplan keyword
ULTRAPLAN_TELEPORT_SENTINEL = "__ULTRAPLAN_TELEPORT_LOCAL__"


def find_ultraplan_trigger_positions(text: str) -> list[tuple[int, int]]:
    """Find 'ultraplan' keyword positions in text.

    Args:
        text: Text to search

    Returns:
        List of (start, end) positions
    """
    positions = []
    pattern = re.compile(r"\bultraplan\b", re.IGNORECASE)
    for match in pattern.finditer(text):
        positions.append((match.start(), match.end()))
    return positions


def has_ultraplan_keyword(text: str) -> bool:
    """Check if text contains 'ultraplan' keyword.

    Args:
        text: Text to check

    Returns:
        True if ultraplan keyword found
    """
    return bool(find_ultraplan_trigger_positions(text))


def replace_ultraplan_keyword(text: str) -> str:
    """Replace 'ultraplan' with 'plan' for grammatical forwarding.

    Args:
        text: Text to process

    Returns:
        Text with ultraplan replaced by plan
    """
    return re.sub(r"\bultraplan\b", "plan", text, flags=re.IGNORECASE)


class ExitPlanModeScanner:
    """Stateful classifier for CCR event stream.

    Processes SDK messages to detect ExitPlanMode approval/rejection.
    """

    def __init__(self) -> None:
        self._pending_plan: str | None = None
        self._reject_count: int = 0
        self._has_pending: bool = False

    def ingest(self, events: list[dict]) -> ScanResult:
        """Process batch of SDK messages.

        Args:
            events: List of SDK message events

        Returns:
            ScanResult with ExitPlanMode verdict
        """
        self._reject_count = 0

        for event in events:
            # Check for tool_use with ExitPlanMode
            if event.get("type") == "tool_use":
                tool_name = event.get("name", "")
                if "exit_plan_mode" in tool_name.lower():
                    self._has_pending = True

            # Check for content block with approval
            elif event.get("type") == "content_block":
                content = event.get("content", [])
                if isinstance(content, str):
                    if ULTRAPLAN_TELEPORT_SENTINEL in content:
                        return ScanResult(
                            kind="teleport",
                            plan=content.replace(ULTRAPLAN_TELEPORT_SENTINEL, ""),
                        )
                    if "approved" in content.lower() or "exit_plan_mode" in content.lower():
                        self._pending_plan = content
                        self._has_pending = False
                        return ScanResult(kind="approved", plan=content)

            # Check for error/rejection
            elif event.get("type") == "error":
                self._reject_count += 1
                return ScanResult(
                    kind="rejected",
                    id=str(event.get("id", "")),
                )

            # Check for termination
            elif event.get("type") == "termination":
                return ScanResult(
                    kind="terminated",
                    subtype=event.get("reason", "unknown"),
                )

        if self._pending_plan:
            return ScanResult(kind="approved", plan=self._pending_plan)

        if self._has_pending:
            return ScanResult(kind="pending")

        return ScanResult(kind="unchanged")

    @property
    def has_pending_plan(self) -> bool:
        """Check if there's a pending plan awaiting approval.

        Returns:
            True if pending
        """
        return self._has_pending

    @property
    def reject_count(self) -> int:
        """Get number of consecutive rejections.

        Returns:
            Rejection count
        """
        return self._reject_count


def create_exit_plan_mode_scanner() -> ExitPlanModeScanner:
    """Create a new ExitPlanModeScanner.

    Returns:
        New scanner instance
    """
    return ExitPlanModeScanner()


async def poll_for_approval(
    session_id: str,
    config: UltraplanConfig | None = None,
) -> UltraplanResult:
    """Poll CCR session until ExitPlanMode is approved.

    Args:
        session_id: Session ID to poll
        config: Optional configuration

    Returns:
        UltraplanResult with approved plan text
    """
    if config is None:
        config = UltraplanConfig()

    scanner = create_exit_plan_mode_scanner()
    consecutive_failures = 0

    while consecutive_failures < config.max_consecutive_failures:
        try:
            # In real implementation, would call CCR API to get events
            # For now, return error as placeholder
            await asyncio.sleep(config.poll_interval_ms / 1000)

            # Simulate polling - in real implementation would check CCR session
            return UltraplanResult(
                success=False,
                message="Ultraplan polling requires CCR session. This feature is not yet implemented.",
                phase=UltraplanPhase.RUNNING,
            )

        except Exception as e:
            logger.exception("Error polling for approval")
            consecutive_failures += 1

            if consecutive_failures >= config.max_consecutive_failures:
                return UltraplanResult(
                    success=False,
                    message=f"Polling failed after {consecutive_failures} attempts: {e}",
                    phase=UltraplanPhase.RUNNING,
                )

    return UltraplanResult(
        success=False,
        message="Max consecutive failures reached",
        phase=UltraplanPhase.RUNNING,
    )


def get_ultraplan_info() -> UltraplanResult:
    """Get ultraplan status information.

    Returns:
        UltraplanResult with status
    """
    return UltraplanResult(
        success=True,
        message="Ultraplan service is available. Use /plan in a CCR session to use ultraplan.",
        phase=UltraplanPhase.RUNNING,
    )
