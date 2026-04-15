"""
Analytics state management.

Thread-safe global state for analytics events, feature gates, and dynamic config.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import (
    AnalyticsConfig,
    AnalyticsEvent,
    DynamicConfig,
    EventSamplingConfig,
    FeatureGate,
    GrowthBookAttributes,
)


@dataclass
class AnalyticsState:
    """Thread-safe global state for analytics."""

    # Event queue (events logged before sink is attached)
    _event_queue: list[AnalyticsEvent] = field(default_factory=list)

    # Config
    _config: AnalyticsConfig = field(default_factory=AnalyticsConfig)

    # Feature gates (name -> FeatureGate)
    _gates: dict[str, FeatureGate] = field(default_factory=dict)

    # Dynamic config cache (name -> DynamicConfig)
    _dynamic_config: dict[str, DynamicConfig] = field(default_factory=dict)

    # GrowthBook attributes
    _gb_attributes: GrowthBookAttributes | None = None

    # Listeners for config changes
    _change_listeners: list[Any] = field(default_factory=list)

    # Lock for thread safety
    _lock: threading.RLock = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_lock", threading.RLock())

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def get_config(self) -> AnalyticsConfig:
        with self._lock:
            return self._config

    def update_config(self, config: AnalyticsConfig) -> None:
        with self._lock:
            old_config = self._config
            self._config = config
            if old_config != config:
                self._notify_change()

    # ------------------------------------------------------------------
    # Event queue
    # ------------------------------------------------------------------

    def enqueue_event(self, event: AnalyticsEvent) -> None:
        with self._lock:
            self._event_queue.append(event)

    def drain_event_queue(self) -> list[AnalyticsEvent]:
        with self._lock:
            events = list(self._event_queue)
            self._event_queue.clear()
            return events

    def get_queue_size(self) -> int:
        with self._lock:
            return len(self._event_queue)

    # ------------------------------------------------------------------
    # Feature gates
    # ------------------------------------------------------------------

    def register_gate(self, gate: FeatureGate) -> None:
        with self._lock:
            self._gates[gate.name] = gate

    def get_gate(self, name: str) -> FeatureGate | None:
        with self._lock:
            return self._gates.get(name)

    def get_gate_value(self, name: str, default: Any = None) -> Any:
        with self._lock:
            gate = self._gates.get(name)
            if gate is None:
                return default
            return gate.get_value()

    def is_feature_enabled(self, name: str) -> bool:
        with self._lock:
            gate = self._gates.get(name)
            if gate is None:
                return False
            return gate.is_enabled()

    def set_env_override(self, name: str, value: Any) -> None:
        with self._lock:
            if name in self._gates:
                self._gates[name].env_override = value
            else:
                self._gates[name] = FeatureGate(
                    name=name,
                    default_value=None,
                    env_override=value,
                )
            self._notify_change()

    def set_config_override(self, name: str, value: Any) -> None:
        with self._lock:
            if name in self._gates:
                self._gates[name].config_override = value
            else:
                self._gates[name] = FeatureGate(
                    name=name,
                    default_value=None,
                    config_override=value,
                )
            self._notify_change()

    def clear_overrides(self, name: str) -> None:
        with self._lock:
            if name in self._gates:
                self._gates[name].env_override = None
                self._gates[name].config_override = None
                self._notify_change()

    def get_all_gates(self) -> dict[str, FeatureGate]:
        with self._lock:
            return dict(self._gates)

    # ------------------------------------------------------------------
    # Dynamic config
    # ------------------------------------------------------------------

    def set_dynamic_config(
        self,
        name: str,
        value: Any,
        source: str = "growthbook",
    ) -> None:
        with self._lock:
            self._dynamic_config[name] = DynamicConfig(
                name=name,
                value=value,
                source=source,
            )

    def get_dynamic_config(self, name: str) -> DynamicConfig | None:
        with self._lock:
            return self._dynamic_config.get(name)

    def get_dynamic_config_value(self, name: str, default: Any = None) -> Any:
        with self._lock:
            cfg = self._dynamic_config.get(name)
            if cfg is None:
                return default
            return cfg.value

    def is_dynamic_config_stale(self, name: str, max_age_seconds: float = 3600) -> bool:
        with self._lock:
            cfg = self._dynamic_config.get(name)
            if cfg is None:
                return True
            if cfg.fetched_at is None:
                return True
            return (time.time() - cfg.fetched_at) > max_age_seconds

    # ------------------------------------------------------------------
    # GrowthBook attributes
    # ------------------------------------------------------------------

    def set_gb_attributes(self, attrs: GrowthBookAttributes) -> None:
        with self._lock:
            self._gb_attributes = attrs

    def get_gb_attributes(self) -> GrowthBookAttributes | None:
        with self._lock:
            return self._gb_attributes

    # ------------------------------------------------------------------
    # Change listeners
    # ------------------------------------------------------------------

    def add_change_listener(self, listener: Any) -> None:
        with self._lock:
            self._change_listeners.append(listener)

    def remove_change_listener(self, listener: Any) -> None:
        with self._lock:
            if listener in self._change_listeners:
                self._change_listeners.remove(listener)

    def _notify_change(self) -> None:
        for listener in self._change_listeners:
            try:
                listener()
            except Exception:
                pass  # Don't let listener errors break the system

    # ------------------------------------------------------------------
    # Clear/reset
    # ------------------------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._event_queue.clear()
            self._gates.clear()
            self._dynamic_config.clear()
            self._change_listeners.clear()


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_state: AnalyticsState | None = None


def get_analytics_state() -> AnalyticsState:
    """Get the global analytics state."""
    global _state
    if _state is None:
        _state = AnalyticsState()
    return _state


def reset_analytics_state() -> None:
    """Reset the global analytics state (for testing)."""
    global _state
    _state = None


# ------------------------------------------------------------------
# Disk cache for feature gates
# ------------------------------------------------------------------

CACHE_FILE = "~/.claude/analytics_cache.json"


def _get_cache_path() -> Path:
    return Path(CACHE_FILE).expanduser()


def load_cached_features() -> dict[str, Any]:
    """Load cached feature values from disk."""
    cache_path = _get_cache_path()
    if not cache_path.exists():
        return {}
    try:
        text = cache_path.read_text(encoding="utf-8")
        return json.loads(text)
    except (json.JSONDecodeError, OSError):
        return {}


def save_cached_features(features: dict[str, Any]) -> None:
    """Save feature values to disk cache."""
    cache_path = _get_cache_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(features, indent=2), encoding="utf-8")
    except OSError:
        pass  # Non-blocking, best effort


def load_cached_growthbook_features() -> dict[str, Any]:
    """Load cached GrowthBook feature values from disk."""
    cache = load_cached_features()
    return cache.get("growthbook_features", {})


def save_cached_growthbook_features(features: dict[str, Any]) -> None:
    """Save GrowthBook feature values to disk cache."""
    cache = load_cached_features()
    cache["growthbook_features"] = features
    save_cached_features(cache)
