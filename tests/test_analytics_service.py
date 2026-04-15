"""
Tests for the analytics service.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from py_claw.services.analytics import (
    AnalyticsService,
    AnalyticsState,
    AnalyticsConfig,
    AnalyticsEvent,
    EventSamplingConfig,
    FeatureGate,
    GrowthBookAttributes,
    DynamicConfig,
    get_analytics_service,
    get_analytics_state,
    reset_analytics_service,
    reset_analytics_state,
    is_feature_enabled,
    get_feature_value,
    log_analytics_event,
    AnalyticsSink,
)
from py_claw.services.analytics.state import (
    load_cached_features,
    save_cached_features,
    load_cached_growthbook_features,
    save_cached_growthbook_features,
)
from py_claw.services.bridge.poll_config import (
    get_poll_interval_config,
    reset_poll_config_cache,
)
from py_claw.services.bridge.poll_config_defaults import DEFAULT_POLL_CONFIG


class TestAnalyticsState:
    """Tests for AnalyticsState."""

    def setup_method(self) -> None:
        reset_analytics_state()

    def teardown_method(self) -> None:
        reset_analytics_state()

    def test_singleton(self) -> None:
        state1 = get_analytics_state()
        state2 = get_analytics_state()
        assert state1 is state2

    def test_register_gate(self) -> None:
        state = get_analytics_state()
        gate = FeatureGate(name="test-feature", default_value=True)
        state.register_gate(gate)
        assert state.get_gate("test-feature") is gate

    def test_get_gate_value_default(self) -> None:
        state = get_analytics_state()
        gate = FeatureGate(name="test", default_value="default")
        state.register_gate(gate)
        assert state.get_gate_value("test") == "default"

    def test_get_gate_value_with_override(self) -> None:
        state = get_analytics_state()
        gate = FeatureGate(name="test", default_value="default")
        state.register_gate(gate)
        state.set_env_override("test", "env-value")
        assert state.get_gate_value("test") == "env-value"

    def test_env_override_priority_over_config(self) -> None:
        state = get_analytics_state()
        gate = FeatureGate(name="test", default_value="default")
        state.register_gate(gate)
        state.set_config_override("test", "config-value")
        state.set_env_override("test", "env-value")
        assert state.get_gate_value("test") == "env-value"

    def test_is_feature_enabled_bool(self) -> None:
        state = get_analytics_state()
        gate = FeatureGate(name="test", default_value=True)
        state.register_gate(gate)
        assert state.is_feature_enabled("test") is True
        gate.config_override = False
        assert state.is_feature_enabled("test") is False

    def test_is_feature_enabled_string(self) -> None:
        state = get_analytics_state()
        gate = FeatureGate(name="test", default_value="false")
        state.register_gate(gate)
        assert state.is_feature_enabled("test") is False
        gate.config_override = "true"
        assert state.is_feature_enabled("test") is True

    def test_event_queue(self) -> None:
        state = get_analytics_state()
        event = AnalyticsEvent(event_name="test", metadata={"key": "value"})
        state.enqueue_event(event)
        assert state.get_queue_size() == 1
        events = state.drain_event_queue()
        assert len(events) == 1
        assert events[0].event_name == "test"
        assert state.get_queue_size() == 0

    def test_dynamic_config(self) -> None:
        state = get_analytics_state()
        state.set_dynamic_config("test-config", {"key": "value"}, source="growthbook")
        cfg = state.get_dynamic_config("test-config")
        assert cfg is not None
        assert cfg.value == {"key": "value"}
        assert cfg.source == "growthbook"

    def test_dynamic_config_stale(self) -> None:
        state = get_analytics_state()
        state.set_dynamic_config("test-config", "value")
        assert state.is_dynamic_config_stale("test-config") is False
        assert state.is_dynamic_config_stale("nonexistent") is True

    def test_gb_attributes(self) -> None:
        state = get_analytics_state()
        attrs = GrowthBookAttributes(
            id="user-123",
            session_id="session-456",
            device_id="device-789",
        )
        state.set_gb_attributes(attrs)
        retrieved = state.get_gb_attributes()
        assert retrieved is attrs
        assert retrieved.id == "user-123"

    def test_clear(self) -> None:
        state = get_analytics_state()
        gate = FeatureGate(name="test", default_value=True)
        state.register_gate(gate)
        state.set_dynamic_config("cfg", "value")
        state.clear()
        assert state.get_gate("test") is None
        assert state.get_dynamic_config("cfg") is None


class TestFeatureGate:
    """Tests for FeatureGate."""

    def test_default_value(self) -> None:
        gate = FeatureGate(name="test", default_value="default")
        assert gate.get_value() == "default"

    def test_env_override(self) -> None:
        gate = FeatureGate(name="test", default_value="default", env_override="override")
        assert gate.get_value() == "override"

    def test_config_override(self) -> None:
        gate = FeatureGate(
            name="test",
            default_value="default",
            config_override="override",
        )
        assert gate.get_value() == "override"

    def test_priority_env_over_config(self) -> None:
        gate = FeatureGate(
            name="test",
            default_value="default",
            env_override="env",
            config_override="config",
        )
        assert gate.get_value() == "env"

    def test_is_enabled_bool_true(self) -> None:
        gate = FeatureGate(name="test", default_value=True)
        assert gate.is_enabled() is True

    def test_is_enabled_bool_false(self) -> None:
        gate = FeatureGate(name="test", default_value=False)
        assert gate.is_enabled() is False

    def test_is_enabled_truthy_string(self) -> None:
        gate = FeatureGate(name="test", default_value="true")
        assert gate.is_enabled() is True
        gate.config_override = "1"
        assert gate.is_enabled() is True

    def test_is_enabled_falsy_string(self) -> None:
        gate = FeatureGate(name="test", default_value="false")
        assert gate.is_enabled() is False
        gate.config_override = "0"
        assert gate.is_enabled() is False


class TestGrowthBookAttributes:
    """Tests for GrowthBookAttributes."""

    def test_to_dict(self) -> None:
        attrs = GrowthBookAttributes(
            id="user-123",
            session_id="session-456",
            device_id="device-789",
            platform="linux",
            email="test@example.com",
        )
        d = attrs.to_dict()
        assert d["id"] == "user-123"
        assert d["sessionId"] == "session-456"
        assert d["deviceID"] == "device-789"
        assert d["platform"] == "linux"
        assert d["email"] == "test@example.com"


class TestAnalyticsService:
    """Tests for AnalyticsService."""

    def setup_method(self) -> None:
        reset_analytics_service()

    def teardown_method(self) -> None:
        reset_analytics_service()

    def test_singleton(self) -> None:
        svc1 = get_analytics_service()
        svc2 = get_analytics_service()
        assert svc1 is svc2

    def test_initialize(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        assert svc.initialized

    def test_initialize_idempotent(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        svc.initialize()
        assert svc.initialized

    def test_default_features_registered(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        assert svc.is_feature_enabled("tengu_compact_enabled")
        assert svc.is_feature_enabled("tengu_skill_discovery_enabled")

    def test_env_override(self) -> None:
        # Register the gate first, then test env override
        svc = get_analytics_service()
        svc.initialize()
        svc.register_feature("test-gate", False, "Test gate")

        os.environ["CLAUDE_FEATURE_TEST_GATE"] = "true"
        try:
            # Re-apply env overrides by reinitializing
            svc2 = get_analytics_service()
            svc2._apply_env_overrides()
            assert svc2.is_feature_enabled("test-gate") is True
        finally:
            del os.environ["CLAUDE_FEATURE_TEST_GATE"]

    def test_attach_sink(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        events_logged = []

        def callback(event: AnalyticsEvent) -> None:
            events_logged.append(event)

        sink = AnalyticsSink(callback=callback)
        svc.attach_sink(sink)

        # Events queued before sink should be drained
        svc.log_event("queued-event", {"key": "value"})
        assert len(events_logged) == 1

    def test_log_event_no_sink(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        svc.log_event("test-event", {"key": "value"})
        state = get_analytics_state()
        assert state.get_queue_size() == 1

    def test_get_feature_value_default(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        value = svc.get_feature_value("tengu_compact_enabled", default=False)
        assert value is True

    def test_get_feature_value_nonexistent(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        value = svc.get_feature_value("nonexistent", default="default")
        assert value == "default"

    def test_set_feature_override(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        svc.set_feature_override("tengu_compact_enabled", False)
        assert svc.is_feature_enabled("tengu_compact_enabled") is False

    def test_register_feature(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        svc.register_feature("custom-feature", True, "A custom feature")
        assert svc.is_feature_enabled("custom-feature") is True

    def test_on_refresh(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        refresh_count = []

        def listener() -> None:
            refresh_count.append(1)

        unsub = svc.on_refresh(listener)
        svc.set_feature_override("tengu_compact_enabled", False)
        assert len(refresh_count) == 1

        unsub()
        svc.set_feature_override("tengu_compact_enabled", True)
        assert len(refresh_count) == 1  # Should not increase after unsubscribe


class TestAnalyticsSink:
    """Tests for AnalyticsSink."""

    def test_log_event_console(self, capsys: pytest.CaptureFixture) -> None:
        sink = AnalyticsSink(console=True)
        event = AnalyticsEvent(event_name="test", metadata={"key": "value"})
        sink.log_event(event)
        captured = capsys.readouterr()
        assert "ANALYTICS" in captured.err
        assert "test" in captured.err

    def test_log_event_callback(self) -> None:
        events = []

        def callback(event: AnalyticsEvent) -> None:
            events.append(event)

        sink = AnalyticsSink(callback=callback)
        event = AnalyticsEvent(event_name="test", metadata={"key": "value"})
        sink.log_event(event)
        assert len(events) == 1
        assert events[0].event_name == "test"


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self) -> None:
        reset_analytics_service()
        reset_poll_config_cache()

    def teardown_method(self) -> None:
        reset_analytics_service()
        reset_poll_config_cache()

    def test_is_feature_enabled(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        assert is_feature_enabled("tengu_compact_enabled") is True

    def test_get_feature_value(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        assert get_feature_value("tengu_compact_enabled") is True

    def test_log_analytics_event(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        log_analytics_event("test-event", {"key": "value"})
        state = get_analytics_state()
        assert state.get_queue_size() == 1

    def test_bridge_poll_config_reads_dynamic_config(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        svc.set_dynamic_config(
            "tengu_bridge_poll_interval_config",
            {
                "poll_interval_ms_not_at_capacity": 1500,
                "poll_interval_ms_at_capacity": 6000,
                "non_exclusive_heartbeat_interval_ms": 250,
                "multisession_poll_interval_ms_not_at_capacity": 1750,
                "multisession_poll_interval_ms_partial_capacity": 2750,
                "multisession_poll_interval_ms_at_capacity": 7000,
                "reclaim_older_than_ms": 8000,
                "session_keepalive_interval_v2_ms": 180000,
            },
        )

        config = get_poll_interval_config()

        assert config.poll_interval_ms_not_at_capacity == 1500
        assert config.poll_interval_ms_at_capacity == 6000
        assert config.non_exclusive_heartbeat_interval_ms == 250
        assert config.multisession_poll_interval_ms_at_capacity == 7000
        assert config.reclaim_older_than_ms == 8000
        assert config.session_keepalive_interval_v2_ms == 180000

    def test_bridge_poll_config_falls_back_on_invalid_dynamic_config(self) -> None:
        svc = get_analytics_service()
        svc.initialize()
        svc.set_dynamic_config(
            "tengu_bridge_poll_interval_config",
            {
                "poll_interval_ms_not_at_capacity": 50,
                "poll_interval_ms_at_capacity": 0,
                "non_exclusive_heartbeat_interval_ms": 0,
                "multisession_poll_interval_ms_at_capacity": 0,
            },
        )

        config = get_poll_interval_config()

        assert config == DEFAULT_POLL_CONFIG


class TestDiskCache:
    """Tests for disk cache functions."""

    def test_save_and_load_cached_features(self, tmp_path: Path) -> None:
        from py_claw.services.analytics.state import _get_cache_path
        original = str(_get_cache_path())

        # Use a temp path
        cache_file = tmp_path / "test_cache.json"
        import py_claw.services.analytics.state as state_module
        original_cache = state_module.CACHE_FILE
        state_module.CACHE_FILE = str(cache_file)

        try:
            features = {"feature1": True, "feature2": {"nested": "value"}}
            save_cached_features(features)
            loaded = load_cached_features()
            assert loaded["feature1"] is True
            assert loaded["feature2"]["nested"] == "value"
        finally:
            state_module.CACHE_FILE = original_cache

    def test_save_and_load_growthbook_cache(self, tmp_path: Path) -> None:
        from py_claw.services.analytics.state import _get_cache_path
        original = str(_get_cache_path())

        cache_file = tmp_path / "test_cache.json"
        import py_claw.services.analytics.state as state_module
        original_cache = state_module.CACHE_FILE
        state_module.CACHE_FILE = str(cache_file)

        try:
            features = {"gb_feature1": True, "gb_feature2": 123}
            save_cached_growthbook_features(features)
            loaded = load_cached_growthbook_features()
            assert loaded["gb_feature1"] is True
            assert loaded["gb_feature2"] == 123
        finally:
            state_module.CACHE_FILE = original_cache


class TestEventSamplingConfig:
    """Tests for EventSamplingConfig."""

    def test_defaults(self) -> None:
        config = EventSamplingConfig()
        assert config.enabled is False
        assert config.sample_rate == 1.0
        assert config.min_sample_rate == 0.01


class TestAnalyticsConfig:
    """Tests for AnalyticsConfig."""

    def test_defaults(self) -> None:
        config = AnalyticsConfig()
        assert config.enabled is True
        assert config.console_output is False
        assert config.file_path is None
        assert config.sink_callback is None
        assert isinstance(config.sampling, EventSamplingConfig)


class TestAnalyticsEvent:
    """Tests for AnalyticsEvent."""

    def test_timestamp_auto_set(self) -> None:
        import time
        before = time.time()
        event = AnalyticsEvent(event_name="test", metadata={})
        after = time.time()
        assert before <= event.timestamp <= after

    def test_timestamp_provided(self) -> None:
        event = AnalyticsEvent(event_name="test", metadata={}, timestamp=12345.0)
        assert event.timestamp == 12345.0
