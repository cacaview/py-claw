"""
IDE types and data structures for py-claw.

Based on ClaudeCode-main/src/utils/ide.ts
"""
from __future__ import annotations

import socket
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IdeType(str, Enum):
    """Supported IDE types."""

    CURSOR = "cursor"
    WINDSURF = "windsurf"
    VSCODE = "vscode"
    PYCHARM = "pycharm"
    INTELLIJ = "intellij"
    WEBSTORM = "webstorm"
    PHPSTORM = "phpstorm"
    RUBYMINE = "rubymine"
    CLION = "clion"
    GOLAND = "goland"
    RIDER = "rider"
    DATAGRIP = "datagrip"
    APPCODE = "appcode"
    DATASPELL = "dataspell"
    AQUA = "aqua"
    GATEWAY = "gateway"
    FLEET = "fleet"
    ANDROIDSTUDIO = "androidstudio"


class IdeKind(str, Enum):
    """IDE kind categories."""

    VSCODE = "vscode"
    JETBRAINS = "jetbrains"


@dataclass
class IdeConfig:
    """Configuration for an IDE type."""

    ide_kind: IdeKind
    display_name: str
    process_keywords_mac: list[str] = field(default_factory=list)
    process_keywords_windows: list[str] = field(default_factory=list)
    process_keywords_linux: list[str] = field(default_factory=list)


# IDE configurations mapping
SUPPORTED_IDE_CONFIGS: dict[IdeType, IdeConfig] = {
    IdeType.CURSOR: IdeConfig(
        ide_kind=IdeKind.VSCODE,
        display_name="Cursor",
        process_keywords_mac=["Cursor Helper", "Cursor.app"],
        process_keywords_windows=["cursor.exe"],
        process_keywords_linux=["cursor"],
    ),
    IdeType.WINDSURF: IdeConfig(
        ide_kind=IdeKind.VSCODE,
        display_name="Windsurf",
        process_keywords_mac=["Windsurf Helper", "Windsurf.app"],
        process_keywords_windows=["windsurf.exe"],
        process_keywords_linux=["windsurf"],
    ),
    IdeType.VSCODE: IdeConfig(
        ide_kind=IdeKind.VSCODE,
        display_name="VS Code",
        process_keywords_mac=["Visual Studio Code", "Code Helper"],
        process_keywords_windows=["code.exe"],
        process_keywords_linux=["code"],
    ),
    IdeType.INTELLIJ: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="IntelliJ IDEA",
        process_keywords_mac=["IntelliJ IDEA"],
        process_keywords_windows=["idea64.exe"],
        process_keywords_linux=["idea", "intellij"],
    ),
    IdeType.PYCHARM: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="PyCharm",
        process_keywords_mac=["PyCharm"],
        process_keywords_windows=["pycharm64.exe"],
        process_keywords_linux=["pycharm"],
    ),
    IdeType.WEBSTORM: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="WebStorm",
        process_keywords_mac=["WebStorm"],
        process_keywords_windows=["webstorm64.exe"],
        process_keywords_linux=["webstorm"],
    ),
    IdeType.PHPSTORM: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="PhpStorm",
        process_keywords_mac=["PhpStorm"],
        process_keywords_windows=["phpstorm64.exe"],
        process_keywords_linux=["phpstorm"],
    ),
    IdeType.RUBYMINE: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="RubyMine",
        process_keywords_mac=["RubyMine"],
        process_keywords_windows=["rubymine64.exe"],
        process_keywords_linux=["rubymine"],
    ),
    IdeType.CLION: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="CLion",
        process_keywords_mac=["CLion"],
        process_keywords_windows=["clion64.exe"],
        process_keywords_linux=["clion"],
    ),
    IdeType.GOLAND: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="GoLand",
        process_keywords_mac=["GoLand"],
        process_keywords_windows=["goland64.exe"],
        process_keywords_linux=["goland"],
    ),
    IdeType.RIDER: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="Rider",
        process_keywords_mac=["Rider"],
        process_keywords_windows=["rider64.exe"],
        process_keywords_linux=["rider"],
    ),
    IdeType.DATAGRIP: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="DataGrip",
        process_keywords_mac=["DataGrip"],
        process_keywords_windows=["datagrip64.exe"],
        process_keywords_linux=["datagrip"],
    ),
    IdeType.APPCODE: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="AppCode",
        process_keywords_mac=["AppCode"],
        process_keywords_windows=["appcode.exe"],
        process_keywords_linux=["appcode"],
    ),
    IdeType.DATASPELL: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="DataSpell",
        process_keywords_mac=["DataSpell"],
        process_keywords_windows=["dataspell64.exe"],
        process_keywords_linux=["dataspell"],
    ),
    IdeType.AQUA: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="Aqua",
        process_keywords_mac=[],
        process_keywords_windows=["aqua64.exe"],
        process_keywords_linux=[],
    ),
    IdeType.GATEWAY: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="Gateway",
        process_keywords_mac=[],
        process_keywords_windows=["gateway64.exe"],
        process_keywords_linux=[],
    ),
    IdeType.FLEET: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="Fleet",
        process_keywords_mac=[],
        process_keywords_windows=["fleet.exe"],
        process_keywords_linux=[],
    ),
    IdeType.ANDROIDSTUDIO: IdeConfig(
        ide_kind=IdeKind.JETBRAINS,
        display_name="Android Studio",
        process_keywords_mac=["Android Studio"],
        process_keywords_windows=["studio64.exe"],
        process_keywords_linux=["android-studio"],
    ),
}


@dataclass
class IdeLockfileInfo:
    """Information from an IDE lockfile."""

    workspace_folders: list[str] = field(default_factory=list)
    port: int = 0
    pid: int | None = None
    ide_name: str | None = None
    use_web_socket: bool = False
    running_in_windows: bool = False
    auth_token: str | None = None


@dataclass
class DetectedIDEInfo:
    """Information about a detected IDE."""

    name: str
    port: int
    workspace_folders: list[str] = field(default_factory=list)
    url: str = ""
    is_valid: bool = False
    auth_token: str | None = None
    ide_running_in_windows: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "port": self.port,
            "workspace_folders": self.workspace_folders,
            "url": self.url,
            "is_valid": self.is_valid,
            "auth_token": self.auth_token,
            "ide_running_in_windows": self.ide_running_in_windows,
        }


@dataclass
class IDEExtensionInstallationStatus:
    """Status of IDE extension installation."""

    installed: bool = False
    error: str | None = None
    installed_version: str | None = None
    ide_type: IdeType | None = None


# Editor display names for terminal commands
EDITOR_DISPLAY_NAMES: dict[str, str] = {
    "code": "VS Code",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "antigravity": "Antigravity",
    "vi": "Vim",
    "vim": "Vim",
    "nano": "nano",
    "notepad": "Notepad",
    "start /wait notepad": "Notepad",
    "emacs": "Emacs",
    "subl": "Sublime Text",
    "atom": "Atom",
}


def is_vscode_ide(ide: IdeType | None) -> bool:
    """Check if an IDE type is VS Code-like."""
    if ide is None:
        return False
    config = SUPPORTED_IDE_CONFIGS.get(ide)
    return config is not None and config.ide_kind == IdeKind.VSCODE


def is_jetbrains_ide(ide: IdeType | None) -> bool:
    """Check if an IDE type is JetBrains."""
    if ide is None:
        return False
    config = SUPPORTED_IDE_CONFIGS.get(ide)
    return config is not None and config.ide_kind == IdeKind.JETBRAINS


def to_ide_display_name(terminal: str | None) -> str:
    """Convert a terminal identifier to IDE display name."""
    if not terminal:
        return "IDE"

    # Try as IdeType first
    try:
        config = SUPPORTED_IDE_CONFIGS[IdeType(terminal)]
        return config.display_name
    except (ValueError, KeyError):
        pass

    # Check editor command names
    editor_name = EDITOR_DISPLAY_NAMES.get(terminal.lower().strip())
    if editor_name:
        return editor_name

    # Extract command name from path/arguments
    command = terminal.split(" ")[0]
    if command:
        command_name = command.split("/")[-1].split("\\")[-1].lower()
        mapped_name = EDITOR_DISPLAY_NAMES.get(command_name)
        if mapped_name:
            return mapped_name
        # Fallback: capitalize
        return command_name.capitalize()

    return terminal.capitalize()


def check_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check if a port is open on a host."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except (socket.error, OSError):
        return False
