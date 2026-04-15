"""
Plugin state management.

Manages the global plugin state including installed plugins, flagged plugins,
and known marketplaces. Persists to ~/.claude/plugins/installed_plugins.json.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .config import get_plugin_service_config
from .types import (
    FlaggedPlugin,
    InstallRecord,
    LoadedPlugin,
    MarketplaceConfig,
    PluginError,
    PluginErrorType,
    PluginScope,
)

if TYPE_CHECKING:
    from .types import PluginOperationResult


# ---------------------------------------------------------------------------
# State Storage
# ---------------------------------------------------------------------------


@dataclass
class PluginState:
    """Thread-safe global plugin state."""
    # plugin name -> list of installations at different scopes
    installed_plugins: dict[str, list[InstallRecord]] = field(default_factory=dict)
    # plugin name -> FlaggedPlugin
    flagged_plugins: dict[str, FlaggedPlugin] = field(default_factory=dict)
    # marketplace name -> MarketplaceConfig
    known_marketplaces: dict[str, MarketplaceConfig] = field(default_factory=dict)
    # loaded plugins (runtime)
    _loaded: dict[str, LoadedPlugin] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    # ------------------------------------------------------------------
    # Installation records
    # ------------------------------------------------------------------

    def add_install_record(self, plugin_name: str, record: InstallRecord) -> None:
        with self._lock:
            if plugin_name not in self.installed_plugins:
                self.installed_plugins[plugin_name] = []
            existing = self.installed_plugins[plugin_name]
            # Replace same scope
            for i, existing_record in enumerate(existing):
                if existing_record.scope == record.scope:
                    existing[i] = record
                    self._persist_installed()
                    return
            existing.append(record)
            self._persist_installed()

    def remove_install_record(self, plugin_name: str, scope: PluginScope) -> bool:
        with self._lock:
            records = self.installed_plugins.get(plugin_name)
            if records is None:
                return False
            original_len = len(records)
            records = [r for r in records if r.scope != scope]
            if len(records) == original_len:
                return False
            if records:
                self.installed_plugins[plugin_name] = records
            else:
                self.installed_plugins.pop(plugin_name, None)
            self._persist_installed()
            return True

    def get_install_records(self, plugin_name: str) -> list[InstallRecord]:
        with self._lock:
            return list(self.installed_plugins.get(plugin_name, []))

    def get_all_install_records(self) -> dict[str, list[InstallRecord]]:
        with self._lock:
            return dict(self.installed_plugins)

    # ------------------------------------------------------------------
    # Runtime loaded plugins
    # ------------------------------------------------------------------

    def add_loaded(self, plugin: LoadedPlugin) -> None:
        with self._lock:
            self._loaded[plugin.name] = plugin

    def get_loaded(self, name: str) -> LoadedPlugin | None:
        with self._lock:
            return self._loaded.get(name)

    def get_all_loaded(self) -> list[LoadedPlugin]:
        with self._lock:
            return list(self._loaded.values())

    def clear_loaded(self) -> None:
        with self._lock:
            self._loaded.clear()

    # ------------------------------------------------------------------
    # Flagged plugins
    # ------------------------------------------------------------------

    def add_flagged(self, plugin_name: str, flagged: FlaggedPlugin) -> None:
        with self._lock:
            self.flagged_plugins[plugin_name] = flagged
            self._persist_flagged()

    def is_flagged(self, plugin_name: str) -> bool:
        with self._lock:
            return plugin_name in self.flagged_plugins

    def get_flagged(self, plugin_name: str) -> FlaggedPlugin | None:
        with self._lock:
            return self.flagged_plugins.get(plugin_name)

    # ------------------------------------------------------------------
    # Marketplaces
    # ------------------------------------------------------------------

    def add_marketplace(self, config: MarketplaceConfig) -> None:
        with self._lock:
            self.known_marketplaces[config.name] = config
            self._persist_marketplaces()

    def remove_marketplace(self, name: str) -> bool:
        with self._lock:
            if name in self.known_marketplaces:
                self.known_marketplaces.pop(name)
                self._persist_marketplaces()
                return True
            return False

    def get_marketplace(self, name: str) -> MarketplaceConfig | None:
        with self._lock:
            return self.known_marketplaces.get(name)

    def list_marketplaces(self) -> list[MarketplaceConfig]:
        with self._lock:
            return list(self.known_marketplaces.values())

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _get_plugins_dir(self) -> Path:
        config = get_plugin_service_config()
        plugins_dir = Path(os.path.expanduser(config.cache_dir)).parent
        return plugins_dir

    def _installed_plugins_path(self) -> Path:
        return self._get_plugins_dir() / "installed_plugins.json"

    def _flagged_plugins_path(self) -> Path:
        return self._get_plugins_dir() / "flagged_plugins.json"

    def _marketplaces_path(self) -> Path:
        return self._get_plugins_dir() / "known_marketplaces.json"

    def _persist_installed(self) -> None:
        path = self._installed_plugins_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            name: [r.to_dict() for r in records]
            for name, records in self.installed_plugins.items()
        }
        path.write_text(json.dumps({"version": 2, "plugins": data}, indent=2), encoding="utf-8")

    def _persist_flagged(self) -> None:
        path = self._flagged_plugins_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            name: {"flaggedAt": f.flagged_at, "seenAt": f.seen_at}
            for name, f in self.flagged_plugins.items()
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _persist_marketplaces(self) -> None:
        path = self._marketplaces_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            name: m.to_dict()
            for name, m in self.known_marketplaces.items()
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_from_disk(self) -> None:
        """Load persisted state from disk."""
        with self._lock:
            # Load installed plugins
            path = self._installed_plugins_path()
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    plugins = data.get("plugins", {})
                    for name, records in plugins.items():
                        self.installed_plugins[name] = [
                            InstallRecord(
                                scope=PluginScope(r.get("scope", "user")),
                                install_path=r["installPath"],
                                version=r.get("version"),
                                project_path=r.get("projectPath"),
                            )
                            for r in records
                        ]
                except Exception:
                    pass

            # Load flagged plugins
            path = self._flagged_plugins_path()
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    for name, fdata in data.items():
                        self.flagged_plugins[name] = FlaggedPlugin(
                            flagged_at=fdata["flaggedAt"],
                            seen_at=fdata.get("seenAt"),
                        )
                except Exception:
                    pass

            # Load known marketplaces
            path = self._marketplaces_path()
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    for name, mdata in data.items():
                        self.known_marketplaces[name] = MarketplaceConfig(
                            name=mdata["name"],
                            url=mdata["url"],
                            owner=mdata.get("owner"),
                            description=mdata.get("description"),
                        )
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Global state singleton
# ---------------------------------------------------------------------------

_state: PluginState | None = None


def get_plugin_state() -> PluginState:
    """Get the global plugin state singleton."""
    global _state
    if _state is None:
        _state = PluginState()
        _state.load_from_disk()
    return _state


def reset_plugin_state() -> None:
    """Reset the global plugin state (for testing)."""
    global _state
    _state = None
