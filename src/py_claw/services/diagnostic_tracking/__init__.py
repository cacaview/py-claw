"""
Diagnostic Tracking service.

Tracks LSP diagnostics and reports issues across the codebase.
"""
from py_claw.services.diagnostic_tracking.config import (
    DiagnosticTrackingConfig,
    get_diagnostic_tracking_config,
    set_diagnostic_tracking_config,
)
from py_claw.services.diagnostic_tracking.service import (
    acknowledge_diagnostic,
    create_entry_from_lsp,
    generate_report,
    get_diagnostics_summary,
    ignore_diagnostic,
    mark_diagnostic_fixed,
    track_diagnostics,
)
from py_claw.services.diagnostic_tracking.types import (
    DiagnosticEntry,
    DiagnosticReport,
    DiagnosticSeverity,
    DiagnosticStatus,
    DiagnosticTrackingState,
    get_tracking_state,
)


__all__ = [
    "DiagnosticTrackingConfig",
    "DiagnosticEntry",
    "DiagnosticReport",
    "DiagnosticSeverity",
    "DiagnosticStatus",
    "DiagnosticTrackingState",
    "get_diagnostic_tracking_config",
    "set_diagnostic_tracking_config",
    "create_entry_from_lsp",
    "track_diagnostics",
    "generate_report",
    "acknowledge_diagnostic",
    "mark_diagnostic_fixed",
    "ignore_diagnostic",
    "get_diagnostics_summary",
    "get_tracking_state",
]
