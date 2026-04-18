"""
Analytics and feature gate service.

Main facade for:
- Event logging (sync/async) with sink management
- Feature gates with env/config overrides
- Dynamic config with caching
- GrowthBook-style attribute targeting

Design: No external dependencies to avoid import cycles.
Events are queued until attach_sink() is called during initialization.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .state import (
    AnalyticsState,
    get_analytics_state,
    reset_analytics_state,
    load_cached_growthbook_features,
    save_cached_growthbook_features,
)
from .types import (
    AnalyticsConfig,
    AnalyticsEvent,
    EventSinkType,
    FeatureGate,
    GrowthBookAttributes,
)


# ------------------------------------------------------------------
# Default feature gates
# ------------------------------------------------------------------

DEFAULT_GATES: list[FeatureGate] = [
    FeatureGate(
        name="tengu_1p_event_logging",
        default_value=True,
        description="Enable first-party event logging",
    ),
    FeatureGate(
        name="tengu_analytics_enabled",
        default_value=True,
        description="Enable analytics collection",
    ),
    FeatureGate(
        name="tengu_growthbook_enabled",
        default_value=False,
        description="Enable GrowthBook feature gates (requires API access)",
    ),
    FeatureGate(
        name="tengu_auto_memory_enabled",
        default_value=False,
        description="Enable automatic memory extraction",
    ),
    FeatureGate(
        name="tengu_compact_enabled",
        default_value=True,
        description="Enable automatic context compaction",
    ),
    FeatureGate(
        name="tengu_skill_discovery_enabled",
        default_value=True,
        description="Enable dynamic skill discovery",
    ),
    FeatureGate(
        name="tengu_mcp_diagnostics_enabled",
        default_value=True,
        description="Enable MCP diagnostics",
    ),
    FeatureGate(
        name="tengu_lsp_enabled",
        default_value=True,
        description="Enable LSP server support",
    ),
    FeatureGate(
        name="tengu_voice_enabled",
        default_value=False,
        description="Enable voice mode",
    ),
    FeatureGate(
        name="tengu_plugin_marketplace_enabled",
        default_value=True,
        description="Enable plugin marketplace",
    ),
    FeatureGate(
        name="tengu_repl_mode",
        default_value=False,
        description="Enable REPL mode features",
    ),
    FeatureGate(
        name="tengu_agent_teammate_enabled",
        default_value=True,
        description="Enable agent teammate mode",
    ),
    FeatureGate(
        name="tengu_worktree_enabled",
        default_value=True,
        description="Enable git worktree isolation for agents",
    ),
    FeatureGate(
        name="tengu_speculation_enabled",
        default_value=False,
        description="Enable speculation/pipelined suggestions",
    ),
]


# ------------------------------------------------------------------
# Sink interface
# ------------------------------------------------------------------

class AnalyticsSink:
    """Sink for analytics events."""

    def __init__(
        self,
        console: bool = False,
        file_path: str | None = None,
        callback: Callable[[AnalyticsEvent], None] | None = None,
    ) -> None:
        self.console = console
        self.file_path = file_path
        self.callback = callback
        self._file_handle = None
        if file_path:
            try:
                self._file_handle = open(file_path, "a", encoding="utf-8")
            except OSError:
                pass

    def log_event(self, event: AnalyticsEvent) -> None:
        """Log a single event."""
        if self.console:
            print(
                f"[ANALYTICS] {event.event_name}: {json.dumps(event.metadata)}",
                file=sys.stderr,
            )
        if self.callback:
            try:
                self.callback(event)
            except Exception:
                pass
        if self._file_handle:
            try:
                self._file_handle.write(
                    json.dumps(
                        {
                            "event": event.event_name,
                            "metadata": event.metadata,
                            "timestamp": event.timestamp,
                        }
                    )
                    + "\n"
                )
                self._file_handle.flush()
            except Exception:
                pass

    def close(self) -> None:
        """Close the sink."""
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None


# ------------------------------------------------------------------
# Analytics service
# ------------------------------------------------------------------

class AnalyticsService:
    """
    Analytics and feature gate service.

    Provides:
    - Event logging with sink management
    - Feature gates with override priority: env > config > cache > default
    - Dynamic config with caching
    - GrowthBook-style attribute targeting
    """

    def __init__(self) -> None:
        self._state = get_analytics_state()
        self._sink: AnalyticsSink | None = None
        self._initialized = False
        self._refresh_listeners: list[Callable[[], None]] = []
        self._lock = threading.RLock()

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(
        self,
        config: AnalyticsConfig | None = None,
        load_cached: bool = True,
    ) -> None:
        """
        Initialize the analytics service.

        Args:
            config: Analytics configuration
            load_cached: Whether to load cached feature values
        """
        with self._lock:
            if self._initialized:
                return

            # Set default config
            if config is None:
                config = AnalyticsConfig()

            # Register default gates
            for gate in DEFAULT_GATES:
                if gate.name not in self._state.get_all_gates():
                    self._state.register_gate(gate)

            # Apply environment variable overrides
            self._apply_env_overrides()

            # Load cached GrowthBook features
            if load_cached:
                self._load_cached_features()

            self._state.update_config(config)
            self._initialized = True

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides for feature gates."""
        # Check for CLAUDE_INTERNAL_FC_OVERRIDES (like TS)
        overrides_raw = os.environ.get("CLAUDE_INTERNAL_FC_OVERRIDES")
        if overrides_raw and os.environ.get("USER_TYPE") == "ant":
            try:
                overrides = json.loads(overrides_raw)
                for name, value in overrides.items():
                    self._state.set_env_override(name, value)
            except json.JSONDecodeError:
                pass

        # Also check for individual feature flag env vars
        for name in self._state.get_all_gates():
            env_key = f"CLAUDE_FEATURE_{name.upper().replace('-', '_')}"
            env_val = os.environ.get(env_key)
            if env_val is not None:
                # Parse boolean/numeric values
                if env_val.lower() in ("true", "1", "yes", "enabled"):
                    self._state.set_env_override(name, True)
                elif env_val.lower() in ("false", "0", "no", "disabled"):
                    self._state.set_env_override(name, False)
                elif env_val.startswith("{") or env_val.startswith("["):
                    try:
                        self._state.set_env_override(name, json.loads(env_val))
                    except json.JSONDecodeError:
                        self._state.set_env_override(name, env_val)
                else:
                    # Try numeric
                    try:
                        self._state.set_env_override(name, float(env_val))
                    except ValueError:
                        self._state.set_env_override(name, env_val)

    def _load_cached_features(self) -> None:
        """Load cached GrowthBook features from disk."""
        try:
            cached = load_cached_growthbook_features()
            for name, value in cached.items():
                if self._state.get_gate(name) is None:
                    self._state.register_gate(FeatureGate(name=name, default_value=value))
                else:
                    self._state.set_dynamic_config(name, value, source="cache")
        except Exception:
            pass

    def attach_sink(self, sink: AnalyticsSink) -> None:
        """
        Attach an analytics sink.

        Queued events are drained asynchronously via queueMicrotask equivalent.

        Idempotent: if a sink is already attached, this is a no-op.
        """
        with self._lock:
            if self._sink is not None:
                return

            self._sink = sink

            # Drain queued events asynchronously
            def drain_queue() -> None:
                events = self._state.drain_event_queue()
                for event in events:
                    sink.log_event(event)

            # Use a thread to mimic queueMicrotask behavior
            thread = threading.Thread(target=drain_queue, daemon=True)
            thread.start()

    def log_event(
        self,
        event_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Log an event synchronously.

        Events are queued if no sink is attached.
        """
        event = AnalyticsEvent(
            event_name=event_name,
            metadata=metadata or {},
        )

        sink = self._sink
        if sink is None:
            self._state.enqueue_event(event)
        else:
            sink.log_event(event)

    async def log_event_async(
        self,
        event_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Log an event asynchronously.

        Events are queued if no sink is attached.
        """
        import asyncio

        event = AnalyticsEvent(
            event_name=event_name,
            metadata=metadata or {},
        )

        sink = self._sink
        if sink is None:
            self._state.enqueue_event(event)
        else:
            # In async context, run sync log in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, sink.log_event, event)

    # ------------------------------------------------------------------
    # Feature gates
    # ------------------------------------------------------------------

    def get_feature_value(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        """
        Get the value of a feature gate.

        Override priority: env > config > cached > default
        """
        return self._state.get_gate_value(name, default)

    def is_feature_enabled(self, name: str) -> bool:
        """Check if a feature gate is enabled."""
        return self._state.is_feature_enabled(name)

    def set_feature_override(
        self,
        name: str,
        value: Any,
        source: str = "config",
    ) -> None:
        """
        Set a feature gate override.

        Args:
            name: Feature gate name
            value: Override value
            source: Override source ("config" or "env")
        """
        if source == "env":
            self._state.set_env_override(name, value)
        else:
            self._state.set_config_override(name, value)
        self._notify_refresh()

    def clear_feature_override(self, name: str) -> None:
        """Clear a feature gate override."""
        self._state.clear_overrides(name)
        self._notify_refresh()

    def get_all_features(self) -> dict[str, Any]:
        """Get all feature gate values."""
        gates = self._state.get_all_gates()
        return {name: gate.get_value() for name, gate in gates.items()}

    def register_feature(
        self,
        name: str,
        default_value: Any,
        description: str | None = None,
    ) -> None:
        """Register a new feature gate."""
        if self._state.get_gate(name) is None:
            self._state.register_gate(FeatureGate(
                name=name,
                default_value=default_value,
                description=description,
            ))

    # ------------------------------------------------------------------
    # Dynamic config
    # ------------------------------------------------------------------

    def set_dynamic_config(
        self,
        name: str,
        value: Any,
        source: str = "growthbook",
    ) -> None:
        """Set a dynamic config value."""
        self._state.set_dynamic_config(name, value, source)
        if source == "growthbook":
            # Persist to disk cache
            try:
                cached = load_cached_growthbook_features()
                cached[name] = value
                save_cached_growthbook_features(cached)
            except Exception:
                pass
        self._notify_refresh()

    def get_dynamic_config(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        """Get a dynamic config value."""
        return self._state.get_dynamic_config_value(name, default)

    def is_config_stale(self, name: str, max_age: float = 3600) -> bool:
        """Check if a dynamic config value is stale."""
        return self._state.is_dynamic_config_stale(name, max_age)

    # ------------------------------------------------------------------
    # GrowthBook attributes
    # ------------------------------------------------------------------

    def set_user_attributes(self, attrs: GrowthBookAttributes) -> None:
        """Set GrowthBook user attributes for targeting."""
        self._state.set_gb_attributes(attrs)

    def get_user_attributes(self) -> GrowthBookAttributes | None:
        """Get GrowthBook user attributes."""
        return self._state.get_gb_attributes()

    # ------------------------------------------------------------------
    # Refresh listeners
    # ------------------------------------------------------------------

    def on_refresh(self, listener: Callable[[], None]) -> Callable[[], None]:
        """
        Register a listener for feature/config refresh events.

        Returns an unsubscribe function.
        """
        self._refresh_listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._refresh_listeners:
                self._refresh_listeners.remove(listener)

        return unsubscribe

    def _notify_refresh(self) -> None:
        """Notify all listeners of a refresh."""
        for listener in self._refresh_listeners:
            try:
                listener()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def get_config(self) -> AnalyticsConfig:
        """Get current analytics configuration."""
        return self._state.get_config()

    def update_config(self, config: AnalyticsConfig) -> None:
        """Update analytics configuration."""
        self._state.update_config(config)


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_service: AnalyticsService | None = None


def get_analytics_service() -> AnalyticsService:
    """Get the global analytics service instance."""
    global _service
    if _service is None:
        _service = AnalyticsService()
    return _service


def reset_analytics_service() -> None:
    """Reset the global analytics service (for testing)."""
    global _service
    _service = None
    reset_analytics_state()


# ------------------------------------------------------------------
# Convenience functions
# ------------------------------------------------------------------

def is_feature_enabled(name: str) -> bool:
    """Check if a feature is enabled."""
    return get_analytics_service().is_feature_enabled(name)


def get_feature_value(name: str, default: Any = None) -> Any:
    """Get a feature value."""
    return get_analytics_service().get_feature_value(name, default)


def log_analytics_event(event_name: str, metadata: dict[str, Any] | None = None) -> None:
    """Log an analytics event."""
    get_analytics_service().log_event(event_name, metadata)
