"""
IDE integration service for py-claw.

Provides:
- types.py: IDE types, configurations, and data structures
- service.py: IDE detection, lockfile management, and connection handling

Based on ClaudeCode-main/src/utils/ide.ts
"""
from py_claw.services.ide.types import (
    EDITOR_DISPLAY_NAMES,
    IdeConfig,
    IdeKind,
    IdeLockfileInfo,
    IdeType,
    SUPPORTED_IDE_CONFIGS,
    DetectedIDEInfo,
    IDEExtensionInstallationStatus,
    check_port_open,
    is_jetbrains_ide,
    is_vscode_ide,
    to_ide_display_name,
)
from py_claw.services.ide.service import (
    cleanup_stale_lockfiles,
    detect_running_ides,
    detect_ides,
    find_available_ide,
    get_ide_kind,
    get_terminal_ide_type,
    is_supported_jetbrains_terminal,
    is_supported_terminal,
    is_supported_vscode_terminal,
)


__all__ = [
    # types
    "IdeType",
    "IdeKind",
    "IdeConfig",
    "IdeLockfileInfo",
    "SUPPORTED_IDE_CONFIGS",
    "DetectedIDEInfo",
    "IDEExtensionInstallationStatus",
    "EDITOR_DISPLAY_NAMES",
    "check_port_open",
    "is_vscode_ide",
    "is_jetbrains_ide",
    "to_ide_display_name",
    # service
    "detect_ides",
    "detect_running_ides",
    "find_available_ide",
    "cleanup_stale_lockfiles",
    "get_ide_kind",
    "get_terminal_ide_type",
    "is_supported_terminal",
    "is_supported_vscode_terminal",
    "is_supported_jetbrains_terminal",
]
