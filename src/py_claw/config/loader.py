"""Configuration loader for py-claw.

Reads from ~/.config/py-claw/config.json (XDG Base Directory Specification).
Does NOT fall back to environment variables — config file is the single source of truth.
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ApiConfig:
    """API configuration for OpenAI/API-compatible endpoints."""

    api_key: str = ""
    api_url: str = ""
    model: str = ""

    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self.api_url)


@dataclass(slots=True)
class Config:
    """Root configuration object."""

    api: ApiConfig = field(default_factory=ApiConfig)
    # Reserved for future sections: model, permissions, ui, etc.
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _xdg_config_home() -> Path:
    """Return XDG_CONFIG_HOME or the platform default."""
    if platform.system() == "Windows":
        # %APPDATA% on Windows
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "py-claw"


def get_config_path() -> Path:
    """Return the default config file path."""
    return _xdg_config_home() / "config.json"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from JSON file.

    If config_path is None, uses the default XDG path (~/.config/py-claw/config.json).
    Returns an empty Config if the file does not exist or is invalid.

    Override the path via PY_CLAW_CONFIG_PATH environment variable (useful for testing).
    """
    if config_path is not None:
        path = config_path
    else:
        path_str = os.environ.get("PY_CLAW_CONFIG_PATH")
        path = Path(path_str) if path_str else get_config_path()

    if not path.exists():
        return Config()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        import logging

        logging.getLogger(__name__).warning("Failed to read config from %s: %s", path, exc)
        return Config()

    api_data = raw.get("api", {})
    extra = {k: v for k, v in raw.items() if k != "api"}

    api = ApiConfig(
        api_key=api_data.get("api_key", ""),
        api_url=api_data.get("api_url", ""),
        model=api_data.get("model", ""),
    )

    return Config(api=api, extra=extra)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def save_config(config: Config, config_path: Path | None = None) -> None:
    """Save configuration to JSON file."""
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    raw: dict[str, Any] = {"api": {}}
    if config.api.api_key:
        raw["api"]["api_key"] = config.api.api_key
    if config.api.api_url:
        raw["api"]["api_url"] = config.api.api_url
    if config.api.model:
        raw["api"]["model"] = config.api.model
    raw.update(config.extra)

    path.write_text(json.dumps(raw, indent=4, ensure_ascii=False), encoding="utf-8")
