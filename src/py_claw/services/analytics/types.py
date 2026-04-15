"""
Analytics and feature gate types.

Provides:
- Event logging with typed metadata
- Feature gates with environment/config overrides
- Dynamic configuration with caching
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    pass


class EventSinkType(str, Enum):
    """Type of analytics sink."""
    CONSOLE = "console"
    FILE = "file"
    CALLBACK = "callback"


@dataclass
class AnalyticsEvent:
    """A single analytics event."""
    event_name: str
    metadata: dict[str, Any]
    timestamp: float | None = None

    def __post_init__(self) -> None:
        import time
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", time.time())


@dataclass
class FeatureGate:
    """
    A feature gate with value and override support.

    Gates can be:
    - Boolean (true/false)
    - String values
    - Number values
    - JSON object values
    """
    name: str
    default_value: Any
    description: str | None = None

    # Override values (highest priority first)
    env_override: Any = field(default=None, repr=False)
    config_override: Any = field(default=None, repr=False)

    def get_value(self) -> Any:
        """Get the resolved value with override priority: env > config > default."""
        if self.env_override is not None:
            return self.env_override
        if self.config_override is not None:
            return self.config_override
        return self.default_value

    def is_enabled(self) -> bool:
        """Check if the gate is enabled (for boolean gates)."""
        value = self.get_value()
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "enabled")
        return bool(value)


@dataclass
class DynamicConfig:
    """Dynamic configuration entry with caching."""
    name: str
    value: Any
    source: str = "default"  # "growthbook", "env", "config", "default"
    fetched_at: float | None = None

    def __post_init__(self) -> None:
        import time
        if self.fetched_at is None:
            object.__setattr__(self, "fetched_at", time.time())


@dataclass
class GrowthBookAttributes:
    """
    User attributes for feature targeting.

    Mirrors TS GrowthBookUserAttributes structure.
    """
    id: str
    session_id: str
    device_id: str
    platform: str = "win32"
    api_base_url_host: str | None = None
    organization_uuid: str | None = None
    account_uuid: str | None = None
    user_type: str | None = None
    subscription_type: str | None = None
    rate_limit_tier: str | None = None
    first_token_time: int | None = None
    email: str | None = None
    app_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sessionId": self.session_id,
            "deviceID": self.device_id,
            "platform": self.platform,
            "apiBaseUrlHost": self.api_base_url_host,
            "organizationUUID": self.organization_uuid,
            "accountUUID": self.account_uuid,
            "userType": self.user_type,
            "subscriptionType": self.subscription_type,
            "rateLimitTier": self.rate_limit_tier,
            "firstTokenTime": self.first_token_time,
            "email": self.email,
            "appVersion": self.app_version,
        }


@dataclass
class EventSamplingConfig:
    """Configuration for event sampling."""
    enabled: bool = False
    sample_rate: float = 1.0  # 0.0 to 1.0
    min_sample_rate: float = 0.01


@dataclass
class AnalyticsConfig:
    """Analytics service configuration."""
    enabled: bool = True
    console_output: bool = False
    file_path: str | None = None
    sink_callback: Callable[[AnalyticsEvent], None] | None = None
    sampling: EventSamplingConfig = field(default_factory=EventSamplingConfig)
    cache_ttl_seconds: float = 3600.0  # 1 hour default
