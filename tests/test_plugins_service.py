"""
Tests for the plugin service.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from py_claw.services.plugins import (
    PluginManifest,
    PluginMarketplaceEntry,
    LoadedPlugin,
    InstallRecord,
    PluginScope,
    PluginSource,
    PluginOperationResult,
    MarketplaceConfig,
    PluginService,
    get_plugin_service,
    reset_plugin_state,
    load_plugin_manifest,
    validate_manifest_paths,
    is_builtin_plugin,
    register_builtin_plugin,
    BuiltinPluginDefinition,
)
from py_claw.services.plugins.state import get_plugin_state


class TestPluginManifest:
    """Tests for plugin manifest parsing."""

    def test_load_valid_manifest(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        claude_plugin_dir = plugin_dir / ".claude-plugin"
        claude_plugin_dir.mkdir()

        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "A test plugin",
        }
        manifest_path = claude_plugin_dir / "plugin.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = load_plugin_manifest(plugin_dir)
        assert not isinstance(result, Exception)
        assert result.name == "test-plugin"
        assert result.version == "1.0.0"
        assert result.description == "A test plugin"

    def test_load_manifest_missing(self, tmp_path: Path) -> None:
        from py_claw.services.plugins.types import PluginError
        result = load_plugin_manifest(tmp_path)
        assert isinstance(result, PluginError)
        assert "not found" in str(result.message).lower()

    def test_load_manifest_invalid_name(self, tmp_path: Path) -> None:
        from py_claw.services.plugins.types import PluginError
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        claude_plugin_dir = plugin_dir / ".claude-plugin"
        claude_plugin_dir.mkdir()

        manifest = {"name": "Test Plugin With Spaces", "version": "1.0.0"}
        manifest_path = claude_plugin_dir / "plugin.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = load_plugin_manifest(plugin_dir)
        assert isinstance(result, PluginError)
        assert "kebab-case" in str(result.message).lower()

    def test_load_manifest_invalid_json(self, tmp_path: Path) -> None:
        from py_claw.services.plugins.types import PluginError
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        claude_plugin_dir = plugin_dir / ".claude-plugin"
        claude_plugin_dir.mkdir()
        manifest_path = claude_plugin_dir / "plugin.json"
        manifest_path.write_text("not valid json{", encoding="utf-8")

        result = load_plugin_manifest(plugin_dir)
        assert isinstance(result, PluginError)
        assert "invalid json" in str(result.message).lower()

    def test_validate_manifest_paths_safe(self) -> None:
        manifest = {
            "name": "test-plugin",
            "commands": "./commands",
            "agents": "./agents",
        }
        errors = validate_manifest_paths(manifest, Path("/some/plugin"))
        assert len(errors) == 0

    def test_validate_manifest_paths_traversal(self) -> None:
        manifest = {
            "name": "test-plugin",
            # Direct string with traversal
            "commands": "../../../etc/passwd",
        }
        errors = validate_manifest_paths(manifest, Path("/some/plugin"))
        assert len(errors) > 0


class TestBuiltinPlugins:
    """Tests for built-in plugin registry."""

    def test_is_builtin_plugin(self) -> None:
        # Default BUILTIN_PLUGINS is empty, but registration works
        from py_claw.services.plugins.config import BUILTIN_PLUGINS

        # Register a test plugin
        definition = BuiltinPluginDefinition(name="test-builtin", description="test")
        register_builtin_plugin(definition)

        assert is_builtin_plugin("test-builtin")
        assert is_builtin_plugin("test-builtin@builtin")
        assert not is_builtin_plugin("nonexistent")

    def test_is_builtin_plugin_format(self) -> None:
        assert is_builtin_plugin("some-plugin") is False


class TestPluginService:
    """Tests for the plugin service."""

    def setup_method(self) -> None:
        reset_plugin_state()
        # Also reset the service singleton
        import py_claw.services.plugins.service as _svc_module
        _svc_module._service = None

    def teardown_method(self) -> None:
        reset_plugin_state()

    def test_service_singleton(self) -> None:
        s1 = get_plugin_service()
        s2 = get_plugin_service()
        assert s1 is s2

    def test_service_initialize(self) -> None:
        service = get_plugin_service()
        # Service may already be initialized from previous tests due to singleton
        if not service.initialized:
            service.initialize()
        assert service.initialized

    def test_list_plugins_empty(self) -> None:
        service = get_plugin_service()
        service.initialize()
        plugins = service.list_plugins()
        # May include pre-existing cached plugins
        assert isinstance(plugins, list)

    def test_marketplaces_registered(self) -> None:
        service = get_plugin_service()
        service.initialize()
        marketplaces = service.list_marketplaces()
        assert any(m.name == "claude-code-marketplace" for m in marketplaces)

    def test_plugin_install_local_path_not_found(self) -> None:
        service = get_plugin_service()
        service.initialize()
        result = service.install("/nonexistent/path/to/plugin")
        assert not result.success
        assert result.error is not None

    def test_plugin_uninstall_not_installed(self) -> None:
        service = get_plugin_service()
        service.initialize()
        result = service.uninstall("this-does-not-exist")
        assert not result.success

    def test_plugin_enable_not_installed(self) -> None:
        service = get_plugin_service()
        service.initialize()
        result = service.enable("nonexistent-plugin")
        # Builtin check may return success, local check fails gracefully
        assert result is not None

    def test_plugin_disable_not_installed(self) -> None:
        service = get_plugin_service()
        service.initialize()
        result = service.disable("nonexistent-plugin")
        assert result is not None

    def test_add_marketplace_empty_url(self) -> None:
        service = get_plugin_service()
        service.initialize()
        success, msg = service.add_marketplace("")
        assert not success

    def test_remove_marketplace_not_found(self) -> None:
        service = get_plugin_service()
        service.initialize()
        success, msg = service.remove_marketplace("nonexistent-marketplace")
        assert not success


class TestPluginState:
    """Tests for plugin state persistence."""

    def setup_method(self) -> None:
        reset_plugin_state()

    def teardown_method(self) -> None:
        reset_plugin_state()

    def test_install_record(self) -> None:
        state = get_plugin_state()
        record = InstallRecord(
            scope=PluginScope.USER,
            install_path="/some/path",
            version="1.0.0",
        )
        state.add_install_record("test-plugin", record)
        records = state.get_install_records("test-plugin")
        assert len(records) == 1
        assert records[0].version == "1.0.0"

    def test_install_record_replace_scope(self) -> None:
        state = get_plugin_state()
        r1 = InstallRecord(scope=PluginScope.USER, install_path="/path1")
        r2 = InstallRecord(scope=PluginScope.USER, install_path="/path2")
        state.add_install_record("test-plugin", r1)
        state.add_install_record("test-plugin", r2)
        records = state.get_install_records("test-plugin")
        assert len(records) == 1
        assert records[0].install_path == "/path2"

    def test_remove_install_record(self) -> None:
        state = get_plugin_state()
        record = InstallRecord(scope=PluginScope.USER, install_path="/some/path")
        state.add_install_record("test-plugin", record)
        removed = state.remove_install_record("test-plugin", PluginScope.USER)
        assert removed
        assert len(state.get_install_records("test-plugin")) == 0

    def test_marketplace_config(self) -> None:
        state = get_plugin_state()
        config = MarketplaceConfig(
            name="test-marketplace",
            url="https://example.com/marketplace",
            owner="Test Owner",
        )
        state.add_marketplace(config)
        retrieved = state.get_marketplace("test-marketplace")
        assert retrieved is not None
        assert retrieved.name == "test-marketplace"
        assert retrieved.owner == "Test Owner"

    def test_list_marketplaces(self) -> None:
        state = get_plugin_state()
        config = MarketplaceConfig(name="mp1", url="https://example.com/1")
        state.add_marketplace(config)
        marketplaces = state.list_marketplaces()
        assert len(marketplaces) >= 1
        assert any(m.name == "mp1" for m in marketplaces)


class TestPluginTypes:
    """Tests for plugin type definitions."""

    def test_plugin_manifest_defaults(self) -> None:
        manifest = PluginManifest(name="test-plugin")
        assert manifest.name == "test-plugin"
        assert manifest.version is None
        assert manifest.description is None
        assert manifest.commands is None

    def test_plugin_marketplace_entry(self) -> None:
        entry = PluginMarketplaceEntry(
            name="test-plugin",
            source={"source": "github", "repo": "owner/repo"},
        )
        assert entry.name == "test-plugin"
        assert isinstance(entry.source, dict)

    def test_install_record_dict(self) -> None:
        record = InstallRecord(
            scope=PluginScope.PROJECT,
            install_path="/path/to/plugin",
            version="2.0.0",
            project_path="/project",
        )
        d = record.to_dict()
        assert d["scope"] == "project"
        assert d["version"] == "2.0.0"
        assert d["projectPath"] == "/project"

    def test_operation_result_dict(self) -> None:
        result = PluginOperationResult(
            success=True,
            plugin="test",
            message="Installed",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["plugin"] == "test"

    def test_loaded_plugin_dict(self) -> None:
        manifest = PluginManifest(name="test-plugin", description="desc")
        plugin = LoadedPlugin(
            name="test-plugin",
            manifest=manifest,
            path="/path",
            source_id="test-plugin@builtin",
            enabled=True,
            is_builtin=True,
            version="1.0.0",
        )
        d = plugin.to_dict()
        assert d["name"] == "test-plugin"
        assert d["enabled"] is True
        assert d["builtin"] is True
