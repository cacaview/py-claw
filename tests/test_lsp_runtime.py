"""
Tests for the LSP service layer.
"""
from __future__ import annotations

import pytest

from py_claw.services.lsp import (
    LSPClient,
    LSPServerInstance,
    LSPServerManager,
    LSPDiagnosticRegistry,
)
from py_claw.services.lsp.types import (
    LSPDiagnostic,
    LSPRange,
    LSPPosition,
    LSPTextDocumentItem,
    ScopedLspServerConfig,
)
from py_claw.services.lsp.config import load_lsp_configs_from_settings, BUILTIN_LSP_CONFIGS


class TestLSPDiagnosticRegistry:
    def test_register_and_filter_diagnostics(self):
        registry = LSPDiagnosticRegistry()

        diag1 = LSPDiagnostic(
            range=LSPRange(
                start=LSPPosition(line=0, character=0),
                end=LSPPosition(line=0, character=10),
            ),
            severity=1,
            message="error: undefined variable",
        )
        diag2 = LSPDiagnostic(
            range=LSPRange(
                start=LSPPosition(line=0, character=0),
                end=LSPPosition(line=0, character=10),
            ),
            severity=1,
            message="error: undefined variable",  # Same as diag1
        )
        diag3 = LSPDiagnostic(
            range=LSPRange(
                start=LSPPosition(line=1, character=0),
                end=LSPPosition(line=1, character=10),
            ),
            severity=2,
            message="warning: unused import",
        )

        uri = "file:///test.py"
        filtered = registry.register_pending(uri, [diag1, diag2, diag3])

        # diag1 and diag3 should pass (diag2 is duplicate within batch)
        assert len(filtered) == 2
        assert any(d.message == "error: undefined variable" for d in filtered)
        assert any(d.message == "warning: unused import" for d in filtered)

    def test_deduplicate_across_calls(self):
        registry = LSPDiagnosticRegistry()

        diag = LSPDiagnostic(
            range=LSPRange(
                start=LSPPosition(line=0, character=0),
                end=LSPPosition(line=0, character=10),
            ),
            severity=1,
            message="error: same",
        )
        uri = "file:///test.py"

        # Register same diagnostic twice (across any versions)
        first = registry.register_pending(uri, [diag])
        assert len(first) == 1

        second = registry.register_pending(uri, [diag])
        # Should be filtered since it was already seen
        assert len(second) == 0

    def test_clear_file(self):
        registry = LSPDiagnosticRegistry()

        diag = LSPDiagnostic(
            range=LSPRange(
                start=LSPPosition(line=0, character=0),
                end=LSPPosition(line=0, character=10),
            ),
            message="error",
        )
        uri = "file:///test.py"
        registry.register_pending(uri, [diag])
        registry.clear_file(uri)

        pending = registry.check_for_diagnostics(uri)
        assert len(pending) == 0


class TestLSPServerManager:
    def test_register_servers(self):
        manager = LSPServerManager()

        configs = [
            ScopedLspServerConfig(name="pylsp", command="pylsp", scope=".py"),
            ScopedLspServerConfig(name="rust-analyzer", command="rust-analyzer", scope=".rs"),
        ]
        manager.register_servers(configs)

        extensions = manager.get_all_extensions()
        assert ".py" in extensions
        assert ".rs" in extensions

    def test_get_server_for_file(self):
        manager = LSPServerManager()

        configs = [
            ScopedLspServerConfig(name="pylsp", command="pylsp", scope=".py"),
        ]
        manager.register_servers(configs)

        server = manager.get_server_for_file("test.py")
        assert server is not None
        assert server.config.name == "pylsp"

        no_server = manager.get_server_for_file("test.rb")
        assert no_server is None

    def test_path_to_uri(self):
        uri = LSPServerManager._path_to_uri("C:/projects/test.py")
        assert uri.startswith("file:///")

    def test_extension_to_lang(self):
        assert LSPServerManager._extension_to_lang(".py") == "python"
        assert LSPServerManager._extension_to_lang(".ts") == "typescript"
        assert LSPServerManager._extension_to_lang(".unknown") == "plaintext"


class TestLSPConfig:
    def test_load_from_settings(self):
        settings = {
            "lsp": {
                "servers": [
                    {
                        "name": "pylsp",
                        "command": "pylsp",
                        "scope": ".py",
                        "args": ["--verbose"],
                    }
                ]
            }
        }
        configs = load_lsp_configs_from_settings(settings)
        assert len(configs) == 1
        assert configs[0].name == "pylsp"
        assert configs[0].command == "pylsp"
        assert configs[0].scope == ".py"
        assert configs[0].args == ["--verbose"]

    def test_load_empty_settings(self):
        configs = load_lsp_configs_from_settings({})
        assert len(configs) == 0

    def test_load_settings_ignores_invalid(self):
        settings = {
            "lsp": {
                "servers": [
                    {"name": "bad", "command": ""},  # Missing command
                    {"command": "good"},  # Missing name
                    {"name": "good", "command": "good"},
                ]
            }
        }
        configs = load_lsp_configs_from_settings(settings)
        assert len(configs) == 1
        assert configs[0].name == "good"


class TestLSPServerInstance:
    def test_default_capabilities_structure(self):
        caps = LSPServerInstance._default_client_capabilities()
        assert "textDocument" in caps
        assert "workspace" in caps
        assert caps["textDocument"]["sync"]["openClose"] is True
        assert caps["textDocument"]["sync"]["change"] == 1
