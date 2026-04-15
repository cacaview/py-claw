"""
Types for ultraplan service.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UltraplanPhase(str, Enum):
    """Ultraplan polling phase."""
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    PLAN_READY = "plan_ready"


class PollFailReason(str, Enum):
    """Reason for polling failure."""
    TERMINATED = "terminated"
    TIMEOUT_PENDING = "timeout_pending"
    TIMEOUT_NO_PLAN = "timeout_no_plan"
    EXTRACT_MARKER_MISSING = "extract_marker_missing"
    NETWORK_OR_UNKNOWN = "network_or_unknown"
    STOPPED = "stopped"


@dataclass
class ScanResult:
    """Result of scanning CCR event stream."""
    kind: str  # 'approved', 'teleport', 'rejected', 'pending', 'terminated', 'unchanged'
    plan: str | None = None
    id: str | None = None
    subtype: str | None = None


@dataclass
class UltraplanConfig:
    """Configuration for ultraplan."""
    poll_interval_ms: int = 3000
    max_consecutive_failures: int = 5


@dataclass
class UltraplanResult:
    """Result of ultraplan operation."""
    success: bool
    message: str
    phase: UltraplanPhase | None = None
    plan: str | None = None
