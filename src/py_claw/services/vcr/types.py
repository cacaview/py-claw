"""
Types for VCR (Video Cassette Recorder) test fixture service.

VCR records API responses to fixture files and replays them during tests,
providing deterministic test runs without real API calls.
"""
from __future__ import annotations

import os
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar, Generic

T = TypeVar("T")


@dataclass
class VCRConfig:
    """Configuration for VCR service."""
    enabled: bool = False  # Enabled in test mode
    fixtures_root: str | None = None  # Root directory for fixtures
    record_mode: bool = False  # If True, record new fixtures
    force_record: bool = False  # If True, ignore existing fixtures
    # Replacement patterns for normalizing dynamic values
    cwd_placeholder: str = "[CWD]"
    config_home_placeholder: str = "[CONFIG_HOME]"
    uuid_pattern: str = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    timestamp_pattern: str = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"


@dataclass
class Recording:
    """A recorded API response fixture."""
    input_data: Any = None
    output_data: Any = None
    recorded_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamingRecording:
    """A recorded streaming API response fixture."""
    events: list[dict[str, Any]] = field(default_factory=list)
    recorded_at: str | None = None
    cached_cost_usd: float | None = None


@dataclass
class TokenCountRecording:
    """A recorded token count fixture."""
    token_count: int | None = None
    recorded_at: str | None = None


# Module-level config
_vcr_config: VCRConfig | None = None


def get_vcr_config() -> VCRConfig:
    """Get the VCR configuration."""
    global _vcr_config
    if _vcr_config is None:
        _vcr_config = VCRConfig()
    return _vcr_config


def set_vcr_config(config: VCRConfig) -> None:
    """Set the VCR configuration."""
    global _vcr_config
    _vcr_config = config


def should_use_vcr() -> bool:
    """Check if VCR should be used.

    VCR is enabled when:
    - PYTHON_ENV=test
    - Or VCR_ENABLED=1 environment variable
    """
    env = os.environ.get
    if env("PYTHON_ENV") == "test":
        return True
    if env("VCR_ENABLED", "").lower() in ("1", "true", "yes"):
        return True
    return False


def _get_cwd() -> str:
    """Get current working directory."""
    return os.getcwd()


def _get_config_home() -> str:
    """Get config home directory."""
    if os.name == "nt":
        return os.environ.get("APPDATA", str(Path.home()))
    elif os.name == "posix":
        if os.environ.get("XDG_CONFIG_HOME"):
            return os.environ["XDG_CONFIG_HOME"]
        return str(Path.home() / ".config")
    return str(Path.home())


def _hash_input(data: Any) -> str:
    """Create a short hash of input data for fixture filename."""
    json_str = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha1(json_str.encode()).hexdigest()[:12]


def _get_fixtures_root() -> str:
    """Get the fixtures root directory."""
    config = get_vcr_config()
    if config.fixtures_root:
        return config.fixtures_root
    env_root = os.environ.get("CLAUDE_CODE_TEST_FIXTURES_ROOT")
    if env_root:
        return env_root
    return _get_cwd()
