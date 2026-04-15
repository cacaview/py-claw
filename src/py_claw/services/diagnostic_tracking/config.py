"""
Diagnostic Tracking configuration.

Service for tracking LSP diagnostics and reporting issues.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticTrackingConfig:
    """Configuration for DiagnosticTracking service."""

    enabled: bool = True
    # Track diagnostics across files
    track_across_files: bool = True
    # Maximum diagnostics to track
    max_tracked: int = 500
    # Report interval (seconds)
    report_interval: int = 300
    # Severity levels to track
    track_severities: list[str] = None  # "error", "warning", "info"
    # Auto-fix suggestions enabled
    auto_fix_suggestions: bool = True

    def __post_init__(self) -> None:
        if self.track_severities is None:
            self.track_severities = ["error", "warning"]

    @classmethod
    def from_settings(cls, settings: dict) -> DiagnosticTrackingConfig:
        """Create config from settings dictionary."""
        dt_settings = settings.get("diagnosticTracking", {})
        return cls(
            enabled=dt_settings.get("enabled", True),
            track_across_files=dt_settings.get("trackAcrossFiles", True),
            max_tracked=dt_settings.get("maxTracked", 500),
            report_interval=dt_settings.get("reportInterval", 300),
            track_severities=dt_settings.get("trackSeverities", ["error", "warning"]),
            auto_fix_suggestions=dt_settings.get("autoFixSuggestions", True),
        )


# Global config instance
_config: DiagnosticTrackingConfig | None = None


def get_diagnostic_tracking_config() -> DiagnosticTrackingConfig:
    """Get the current DiagnosticTracking configuration."""
    global _config
    if _config is None:
        _config = DiagnosticTrackingConfig()
    return _config


def set_diagnostic_tracking_config(config: DiagnosticTrackingConfig) -> None:
    """Set the DiagnosticTracking configuration."""
    global _config
    _config = config
