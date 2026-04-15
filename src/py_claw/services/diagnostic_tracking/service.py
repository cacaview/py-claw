"""
Diagnostic Tracking service.

Tracks LSP diagnostics and reports issues across the codebase.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from py_claw.services.diagnostic_tracking.config import (
    get_diagnostic_tracking_config,
)

from .types import (
    DiagnosticEntry,
    DiagnosticReport,
    DiagnosticSeverity,
    DiagnosticStatus,
    DiagnosticTrackingState,
    get_tracking_state,
)

if TYPE_CHECKING:
    from py_claw.services.lsp.types import LSPDiagnostic


def create_entry_from_lsp(diagnostic: LSPDiagnostic, source: str = "lsp") -> DiagnosticEntry:
    """Create a DiagnosticEntry from an LSP diagnostic.

    Args:
        diagnostic: LSP diagnostic object
        source: Source of the diagnostic (e.g., "lsp", "eslint")

    Returns:
        DiagnosticEntry object
    """
    from py_claw.services.lsp.types import LSPRange

    # Extract location
    file_path = ""
    line = 0
    column = 0

    if hasattr(diagnostic, "file_path"):
        file_path = diagnostic.file_path
    elif hasattr(diagnostic, "uri"):
        file_path = diagnostic.uri

    if hasattr(diagnostic, "range") and diagnostic.range:
        range_obj = diagnostic.range
        if hasattr(range_obj, "start") and range_obj.start:
            line = getattr(range_obj.start, "line", 0)
            column = getattr(range_obj.start, "character", 0)

    # Extract severity
    severity = DiagnosticSeverity.WARNING
    if hasattr(diagnostic, "severity"):
        sev = diagnostic.severity
        if sev == 1:
            severity = DiagnosticSeverity.ERROR
        elif sev == 2:
            severity = DiagnosticSeverity.WARNING
        elif sev == 3:
            severity = DiagnosticSeverity.INFO
        elif sev == 4:
            severity = DiagnosticSeverity.HINT

    # Extract message
    message = ""
    if hasattr(diagnostic, "message"):
        message = diagnostic.message
    elif hasattr(diagnostic, "content"):
        message = diagnostic.content
    elif hasattr(diagnostic, "text"):
        message = diagnostic.text

    # Extract code
    code = None
    if hasattr(diagnostic, "code"):
        code = str(diagnostic.code) if diagnostic.code else None

    return DiagnosticEntry(
        file_path=file_path,
        line=line,
        column=column,
        severity=severity,
        message=message,
        source=source,
        code=code,
    )


def track_diagnostics(
    diagnostics: list[LSPDiagnostic],
    source: str = "lsp",
) -> int:
    """Track diagnostics from LSP or other sources.

    Args:
        diagnostics: List of diagnostic objects
        source: Source of diagnostics

    Returns:
        Number of new diagnostics tracked
    """
    config = get_diagnostic_tracking_config()
    state = get_tracking_state()

    if not config.enabled:
        return 0

    # Create entries from diagnostics
    new_entries = []
    for diag in diagnostics:
        entry = create_entry_from_lsp(diag, source)

        # Check severity filter
        if entry.severity.value not in config.track_severities:
            continue

        # Check if already tracked (by file, line, column, message hash)
        is_new = True
        for existing in state.entries.values():
            if (
                existing.file_path == entry.file_path
                and existing.line == entry.line
                and existing.column == entry.column
                and existing.message == entry.message
            ):
                is_new = False
                break

        if is_new:
            state.add(entry)
            new_entries.append(entry)

    # Clear old entries beyond max
    if len(state.entries) > config.max_tracked:
        # Remove oldest entries
        excess = len(state.entries) - config.max_tracked
        entries_to_remove = list(state.entries.keys())[:excess]
        for key in entries_to_remove:
            del state.entries[key]

    return len(new_entries)


def generate_report() -> DiagnosticReport:
    """Generate a diagnostic report.

    Returns:
        DiagnosticReport with summary statistics
    """
    state = get_tracking_state()

    by_severity: dict[str, int] = {}
    by_source: dict[str, int] = {}
    most_recent: datetime | None = None

    for entry in state.entries.values():
        # By severity
        sev = entry.severity.value
        by_severity[sev] = by_severity.get(sev, 0) + 1

        # By source
        src = entry.source
        by_source[src] = by_source.get(src, 0) + 1

        # Most recent
        if entry.created_at:
            if most_recent is None or entry.created_at > most_recent:
                most_recent = entry.created_at

    # Count newly introduced (created in last hour)
    one_hour_ago = datetime.now(timezone.utc).timestamp() - 3600
    newly_introduced = sum(
        1 for e in state.entries.values()
        if e.created_at and e.created_at.timestamp() > one_hour_ago
    )

    return DiagnosticReport(
        total_diagnostics=len(state.entries),
        by_severity=by_severity,
        by_source=by_source,
        most_recent=most_recent,
        newly_introduced=newly_introduced,
        newly_fixed=state.fixed_count,
    )


def acknowledge_diagnostic(entry_id: str) -> bool:
    """Acknowledge a diagnostic entry.

    Args:
        entry_id: ID of the entry to acknowledge

    Returns:
        True if acknowledged, False if not found
    """
    state = get_tracking_state()
    return state.acknowledge(entry_id)


def mark_diagnostic_fixed(entry_id: str) -> bool:
    """Mark a diagnostic as fixed.

    Args:
        entry_id: ID of the entry to mark as fixed

    Returns:
        True if marked, False if not found
    """
    state = get_tracking_state()
    return state.mark_fixed(entry_id)


def ignore_diagnostic(entry_id: str) -> bool:
    """Ignore a diagnostic entry.

    Args:
        entry_id: ID of the entry to ignore

    Returns:
        True if ignored, False if not found
    """
    state = get_tracking_state()
    return state.ignore(entry_id)


def get_diagnostics_summary() -> dict:
    """Get a summary of current diagnostics.

    Returns:
        Dictionary with diagnostic summary
    """
    state = get_tracking_state()
    config = get_diagnostic_tracking_config()

    return {
        "enabled": config.enabled,
        "total_tracked": len(state.entries),
        "fixed_total": state.fixed_count,
        "max_tracked": config.max_tracked,
        "track_severities": config.track_severities,
        "auto_fix_suggestions": config.auto_fix_suggestions,
    }
