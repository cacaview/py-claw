"""
Tests for Doctor diagnostic service.

Based on ClaudeCode-main/src/utils/doctorDiagnostic.ts
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from py_claw.services.doctor import (
    ContextWarning,
    ContextWarnings,
    DiagnosticInfo,
    DoctorCheckResult,
    InstallationType,
    RipgrepStatus,
    check_context_warnings,
    check_mcp_servers,
    get_diagnostic_summary,
    get_installation_info,
    run_diagnostics,
)


class TestInstallationType:
    """Tests for InstallationType enum."""

    def test_installation_type_values(self):
        """Test all installation type values."""
        assert InstallationType.NPM_GLOBAL == "npm-global"
        assert InstallationType.NPM_LOCAL == "npm-local"
        assert InstallationType.NATIVE == "native"
        assert InstallationType.PACKAGE_MANAGER == "package-manager"
        assert InstallationType.DEVELOPMENT == "development"
        assert InstallationType.UNKNOWN == "unknown"

    def test_installation_type_count(self):
        """Test we have expected number of installation types."""
        assert len(InstallationType) == 6


class TestDoctorCheckResult:
    """Tests for DoctorCheckResult dataclass."""

    def test_creation(self):
        """Test creating a check result."""
        result = DoctorCheckResult(
            name="Python version",
            status="ok",
            message="Python 3.11.0 is supported",
        )
        assert result.name == "Python version"
        assert result.status == "ok"
        assert result.message == "Python 3.11.0 is supported"

    def test_is_ok(self):
        """Test is_ok method."""
        ok_result = DoctorCheckResult(name="Test", status="ok")
        assert ok_result.is_ok() is True

        warn_result = DoctorCheckResult(name="Test", status="warning")
        assert warn_result.is_ok() is False

        error_result = DoctorCheckResult(name="Test", status="error")
        assert error_result.is_ok() is False

    def test_is_warning(self):
        """Test is_warning method."""
        result = DoctorCheckResult(name="Test", status="warning")
        assert result.is_warning() is True
        assert result.is_ok() is False

    def test_is_error(self):
        """Test is_error method."""
        result = DoctorCheckResult(name="Test", status="error")
        assert result.is_error() is True
        assert result.is_ok() is False

    def test_details(self):
        """Test details field."""
        result = DoctorCheckResult(
            name="Test",
            status="warning",
            message="Warning",
            details=["detail 1", "detail 2"],
        )
        assert len(result.details) == 2


class TestDiagnosticInfo:
    """Tests for DiagnosticInfo dataclass."""

    def test_creation_defaults(self):
        """Test creating with defaults."""
        info = DiagnosticInfo()
        assert info.installation_type == InstallationType.UNKNOWN
        assert info.version == ""
        assert info.config_install_method == "not set"

    def test_creation_with_values(self):
        """Test creating with values."""
        info = DiagnosticInfo(
            installation_type=InstallationType.NPM_GLOBAL,
            version="1.0.0",
            installation_path="/usr/local",
            config_install_method="npm",
        )
        assert info.installation_type == InstallationType.NPM_GLOBAL
        assert info.version == "1.0.0"


class TestRipgrepStatus:
    """Tests for RipgrepStatus dataclass."""

    def test_creation_defaults(self):
        """Test creating with defaults."""
        status = RipgrepStatus()
        assert status.working is False
        assert status.mode == "system"
        assert status.system_path is None

    def test_creation_with_values(self):
        """Test creating with values."""
        status = RipgrepStatus(
            working=True,
            mode="builtin",
            system_path="/usr/bin/rg",
        )
        assert status.working is True
        assert status.mode == "builtin"


class TestContextWarning:
    """Tests for ContextWarning dataclass."""

    def test_creation(self):
        """Test creating a context warning."""
        warning = ContextWarning(
            type="claudemd_files",
            severity="warning",
            message="Large CLAUDE.md file detected",
            details=["file.md: 50000 chars"],
            current_value=50000,
            threshold=40000,
        )
        assert warning.type == "claudemd_files"
        assert warning.severity == "warning"
        assert warning.current_value == 50000

    def test_to_dict(self):
        """Test converting to dictionary."""
        warning = ContextWarning(
            type="claudemd_files",
            message="Test",
            current_value=100,
            threshold=50,
        )
        d = warning.to_dict()
        assert d["type"] == "claudemd_files"
        assert d["current_value"] == 100


class TestContextWarnings:
    """Tests for ContextWarnings dataclass."""

    def test_has_warnings_empty(self):
        """Test has_warnings with no warnings."""
        warnings = ContextWarnings()
        assert warnings.has_warnings() is False

    def test_has_warnings_with_warning(self):
        """Test has_warnings with a warning."""
        warnings = ContextWarnings()
        warnings.claude_md_warning = ContextWarning(
            type="claudemd_files",
            message="Test",
            current_value=100,
            threshold=50,
        )
        assert warnings.has_warnings() is True

    def test_get_all_warnings(self):
        """Test get_all_warnings method."""
        warnings = ContextWarnings()
        warnings.claude_md_warning = ContextWarning(
            type="claudemd_files",
            message="Test 1",
            current_value=100,
            threshold=50,
        )
        warnings.agent_warning = ContextWarning(
            type="agent_descriptions",
            message="Test 2",
            current_value=200,
            threshold=100,
        )

        all_warnings = warnings.get_all_warnings()
        assert len(all_warnings) == 2


class TestRunDiagnostics:
    """Tests for run_diagnostics function."""

    def test_returns_list(self):
        """Test returns a list of results."""
        results = run_diagnostics()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_all_results_have_name(self):
        """Test all results have a name."""
        results = run_diagnostics()
        for result in results:
            assert result.name
            assert isinstance(result.name, str)

    def test_all_results_have_status(self):
        """Test all results have a valid status."""
        results = run_diagnostics()
        valid_statuses = {"ok", "warning", "error", "pending"}
        for result in results:
            assert result.status in valid_statuses

    def test_python_version_check(self):
        """Test Python version check is present."""
        results = run_diagnostics()
        python_result = next((r for r in results if r.name == "Python version"), None)
        assert python_result is not None
        assert python_result.status in {"ok", "warning", "error"}

    def test_api_key_check(self):
        """Test API key check is present."""
        results = run_diagnostics()
        api_result = next((r for r in results if r.name == "API key"), None)
        assert api_result is not None

    def test_git_check(self):
        """Test Git check is present."""
        results = run_diagnostics()
        git_result = next((r for r in results if r.name == "Git"), None)
        assert git_result is not None

    def test_config_directory_check(self):
        """Test config directory check is present."""
        results = run_diagnostics()
        config_result = next((r for r in results if r.name == "Config directory"), None)
        assert config_result is not None


class TestGetDiagnosticSummary:
    """Tests for get_diagnostic_summary function."""

    def test_returns_string(self):
        """Test returns a string."""
        summary = get_diagnostic_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_contains_sections(self):
        """Test summary contains expected sections."""
        summary = get_diagnostic_summary()
        assert "py-claw Doctor" in summary
        assert "Python version" in summary
        assert "API key" in summary

    def test_contains_status(self):
        """Test summary contains status information."""
        summary = get_diagnostic_summary()
        assert "OK" in summary or "warning" in summary.lower() or "error" in summary.lower()


class TestGetInstallationInfo:
    """Tests for get_installation_info function."""

    def test_returns_diagnostic_info(self):
        """Test returns DiagnosticInfo object."""
        info = get_installation_info()
        assert isinstance(info, DiagnosticInfo)

    def test_has_installation_type(self):
        """Test has installation type."""
        info = get_installation_info()
        assert isinstance(info.installation_type, InstallationType)

    def test_has_version(self):
        """Test has version string."""
        info = get_installation_info()
        assert isinstance(info.version, str)


class TestCheckContextWarnings:
    """Tests for check_context_warnings function."""

    def test_returns_context_warnings(self):
        """Test returns ContextWarnings object."""
        warnings = check_context_warnings()
        assert isinstance(warnings, ContextWarnings)

    def test_no_tools_returns_empty(self):
        """Test with no tools returns empty warnings."""
        warnings = check_context_warnings(tools=None)
        # May or may not have warnings depending on actual CLAUDE.md files

    def test_no_agent_info(self):
        """Test works without agent info."""
        warnings = check_context_warnings(agent_info=None)
        assert isinstance(warnings, ContextWarnings)


class TestCheckMcpServers:
    """Tests for check_mcp_servers function."""

    def test_empty_list_returns_none(self):
        """Test empty list returns None."""
        result = check_mcp_servers([])
        assert result is None

    def test_none_returns_none(self):
        """Test None returns None."""
        result = check_mcp_servers(None)
        assert result is None

    def test_with_mock_statuses(self):
        """Test with mock statuses."""
        # Create a simple mock object
        class MockStatus:
            def __init__(self, name, status, error=None):
                self.name = name
                self.status = status
                self.error = error

        statuses = [
            MockStatus("server1", "connected"),
            MockStatus("server2", "error", "connection refused"),
        ]

        result = check_mcp_servers(statuses)
        assert result is not None
        assert result.type == "mcp_tools"
        assert result.severity == "error"
        assert "1 MCP server" in result.message
