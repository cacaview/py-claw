"""Bridge system types for Remote Control."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class BridgeState(Enum):
    """Bridge connection state."""

    READY = "ready"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    DISCONNECTED = "disconnected"


class BridgeVersion(Enum):
    """Bridge protocol version."""

    V1 = "v1"
    V2 = "v2"


@dataclass
class BridgeConfig:
    """Configuration for bridge mode."""

    enabled: bool = False
    base_url: str | None = None
    session_ingress_url: str | None = None
    environment_id: str | None = None
    poll_interval_seconds: float = 1.0
    max_poll_interval_seconds: float = 30.0
    max_concurrent_sessions: int = 32
    request_timeout_seconds: float = 30.0
    ping_interval_seconds: float = 30.0


@dataclass
class BridgeSession:
    """A bridge session representing a Remote Control connection."""

    session_id: str
    environment_id: str
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    state: BridgeState = BridgeState.DISCONNECTED
    git_repo_url: str | None = None
    branch: str | None = None
    machine_name: str | None = None
    permission_mode: str | None = None
    worker_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    session_url: str | None = None  # Remote session URL for QR code display


@dataclass
class GitSource:
    """Git source context for a bridge session."""

    type: str = "git_repository"
    url: str | None = None
    revision: str | None = None


@dataclass
class GitOutcome:
    """Git outcome context for a bridge session."""

    type: str = "git_repository"
    git_info: dict[str, Any] | None = None


@dataclass
class SessionEvent:
    """An event to send to the bridge session API."""

    type: str = "event"
    data: dict[str, Any] | None = None


@dataclass
class CreateSessionParams:
    """Parameters for creating a bridge session."""

    environment_id: str
    title: str | None = None
    events: list[SessionEvent] | None = None
    git_repo_url: str | None = None
    branch: str | None = None
    permission_mode: str | None = None
    base_url: str | None = None


@dataclass
class CreateSessionResult:
    """Result from creating a bridge session."""

    success: bool
    session_id: str | None = None
    error: str | None = None


@dataclass
class TrustedDeviceToken:
    """Trusted device enrollment token."""

    token: str | None = None
    expires_at: datetime | None = None
    device_name: str | None = None


@dataclass
class BridgeCapability:
    """A capability or feature of the bridge system."""

    name: str
    enabled: bool = False
    reason: str | None = None


@dataclass
class BridgeEntitlement:
    """Result of a bridge entitlement check."""

    allowed: bool
    reason: str | None = None
    capabilities: list[BridgeCapability] = field(default_factory=list)


@dataclass
class SessionBridgeId:
    """Session to bridge ID mapping."""

    session_id: str
    bridge_id: str
    environment_id: str


@dataclass
class ReplBridgeHandle:
    """Handle for an active REPL bridge connection."""

    bridge_session_id: str
    environment_id: str
    session_ingress_url: str
    state: BridgeState = BridgeState.DISCONNECTED
    created_at: datetime | None = None
