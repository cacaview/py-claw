"""
MagicDocs configuration.

Automatically maintains markdown files marked with # MAGIC DOC: header.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MagicDocsConfig:
    """Configuration for MagicDocs service."""

    enabled: bool = True
    # Directories to scan for magic docs
    scan_directories: list[str] = None
    # File patterns to include
    include_patterns: list[str] = None
    # Whether to auto-create docs for new topics
    auto_create: bool = False
    # Auto-update interval (seconds)
    auto_update_interval: int = 300
    # Maximum docs to maintain
    max_docs: int = 50

    def __post_init__(self) -> None:
        if self.scan_directories is None:
            self.scan_directories = ["."]
        if self.include_patterns is None:
            self.include_patterns = ["**/*.md"]

    @classmethod
    def from_settings(cls, settings: dict) -> MagicDocsConfig:
        """Create config from settings dictionary."""
        magic_docs_settings = settings.get("magicDocs", {})
        return cls(
            enabled=magic_docs_settings.get("enabled", True),
            scan_directories=magic_docs_settings.get("scanDirectories", ["."]),
            include_patterns=magic_docs_settings.get("includePatterns", ["**/*.md"]),
            auto_create=magic_docs_settings.get("autoCreate", False),
            auto_update_interval=magic_docs_settings.get("autoUpdateInterval", 300),
            max_docs=magic_docs_settings.get("maxDocs", 50),
        )


# Global config instance
_config: MagicDocsConfig | None = None


def get_magic_docs_config() -> MagicDocsConfig:
    """Get the current MagicDocs configuration."""
    global _config
    if _config is None:
        _config = MagicDocsConfig()
    return _config


def set_magic_docs_config(config: MagicDocsConfig) -> None:
    """Set the MagicDocs configuration."""
    global _config
    _config = config


# Magic DOC marker
MAGIC_DOC_HEADER = "# MAGIC DOC:"
