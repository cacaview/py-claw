"""
Doctor service types and data structures.

Based on ClaudeCode-main/src/utils/doctorDiagnostic.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InstallationType(str, Enum):
    """Installation type for Claude Code."""

    NPM_GLOBAL = "npm-global"
    NPM_LOCAL = "npm-local"
    NATIVE = "native"
    PACKAGE_MANAGER = "package-manager"
    DEVELOPMENT = "development"
    UNKNOWN = "unknown"


@dataclass
class DiagnosticInfo:
    """System diagnostic information."""

    installation_type: InstallationType = InstallationType.UNKNOWN
    version: str = ""
    installation_path: str = ""
    invoked_binary: str = ""
    config_install_method: str = "not set"
    auto_updates: str = "unknown"
    has_update_permissions: bool | None = None
    multiple_installations: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    recommendation: str | None = None
    package_manager: str | None = None


@dataclass
class RipgrepStatus:
    """Ripgrep status information."""

    working: bool = False
    mode: str = "system"  # 'system' | 'builtin' | 'embedded'
    system_path: str | None = None


@dataclass
class ContextWarning:
    """A context warning from doctor checks."""

    type: str  # 'claudemd_files' | 'agent_descriptions' | 'mcp_tools' | 'unreachable_rules'
    severity: str = "warning"  # 'warning' | 'error'
    message: str = ""
    details: list[str] = field(default_factory=list)
    current_value: int = 0
    threshold: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
            "current_value": self.current_value,
            "threshold": self.threshold,
        }


@dataclass
class ContextWarnings:
    """Collection of context warnings."""

    claude_md_warning: ContextWarning | None = None
    agent_warning: ContextWarning | None = None
    mcp_warning: ContextWarning | None = None
    unreachable_rules_warning: ContextWarning | None = None

    def has_warnings(self) -> bool:
        """Check if any warnings are present."""
        return any(
            w is not None
            for w in [
                self.claude_md_warning,
                self.agent_warning,
                self.mcp_warning,
                self.unreachable_rules_warning,
            ]
        )

    def get_all_warnings(self) -> list[ContextWarning]:
        """Get all warnings as a list."""
        return [
            w
            for w in [
                self.claude_md_warning,
                self.agent_warning,
                self.mcp_warning,
                self.unreachable_rules_warning,
            ]
            if w is not None
        ]


@dataclass
class DoctorCheckResult:
    """Result of a doctor check."""

    name: str
    status: str = "pending"  # 'ok' | 'warning' | 'error' | 'pending'
    message: str = ""
    details: list[str] = field(default_factory=list)

    def is_ok(self) -> bool:
        return self.status == "ok"

    def is_warning(self) -> bool:
        return self.status == "warning"

    def is_error(self) -> bool:
        return self.status == "error"
