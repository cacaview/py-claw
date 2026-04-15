"""
Doctor diagnostic service for py-claw.

Provides system diagnostics including:
- Installation type detection
- Environment validation
- Settings validation
- MCP server status
- Context warnings

Based on ClaudeCode-main/src/utils/doctorDiagnostic.ts
"""
from py_claw.services.doctor.types import (
    ContextWarning,
    ContextWarnings,
    DiagnosticInfo,
    DoctorCheckResult,
    InstallationType,
    RipgrepStatus,
)
from py_claw.services.doctor.service import (
    check_context_warnings,
    check_mcp_servers,
    get_diagnostic_summary,
    get_installation_info,
    run_diagnostics,
)


__all__ = [
    # types
    "InstallationType",
    "DiagnosticInfo",
    "RipgrepStatus",
    "ContextWarning",
    "ContextWarnings",
    "DoctorCheckResult",
    # service
    "run_diagnostics",
    "get_diagnostic_summary",
    "get_installation_info",
    "check_context_warnings",
    "check_mcp_servers",
]
