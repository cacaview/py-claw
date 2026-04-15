"""
Analytics and feature gate service.

Provides:
- Event logging with typed metadata and sink management
- Feature gates with environment/config overrides
- Dynamic configuration with caching
- GrowthBook-style user attribute targeting

Basic usage:

    from py_claw.services.analytics import is_feature_enabled, log_analytics_event

    # Check if a feature is enabled
    if is_feature_enabled("tengu_auto_memory_enabled"):
        ...

    # Log an event
    log_analytics_event("skill_invoked", {"skill_name": "debug"})
"""
from __future__ import annotations

from .types import (
    AnalyticsConfig,
    AnalyticsEvent,
    EventSinkType,
    DynamicConfig,
    EventSamplingConfig,
    FeatureGate,
    GrowthBookAttributes,
)
from .state import (
    AnalyticsState,
    get_analytics_state,
    reset_analytics_state,
)
from .service import (
    AnalyticsService,
    AnalyticsSink,
    get_analytics_service,
    reset_analytics_service,
    is_feature_enabled,
    get_feature_value,
    log_analytics_event,
)

__all__ = [
    # Types
    "AnalyticsConfig",
    "AnalyticsEvent",
    "EventSinkType",
    "DynamicConfig",
    "EventSamplingConfig",
    "FeatureGate",
    "GrowthBookAttributes",
    # State
    "AnalyticsState",
    "get_analytics_state",
    "reset_analytics_state",
    # Service
    "AnalyticsService",
    "AnalyticsSink",
    "get_analytics_service",
    "reset_analytics_service",
    # Convenience
    "is_feature_enabled",
    "get_feature_value",
    "log_analytics_event",
]
