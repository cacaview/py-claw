"""
LSP (Language Server Protocol) type definitions.

Minimal set of types needed for py-claw's LSP integration.
Based on vscode-languageserver-protocol.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# JSON-RPC message types
JSON = dict[str, object] | list[object] | str | int | float | bool | None


@dataclass
class LSPPosition:
    line: int
    character: int


@dataclass
class LSPRange:
    start: LSPPosition
    end: LSPPosition


@dataclass
class LSPDiagnostic:
    range: LSPRange
    severity: int | None = None
    code: int | str | None = None
    source: str | None = None
    message: str = ""
    relatedInformation: list[Any] | None = None


@dataclass
class LSPTextDocumentIdentifier:
    uri: str


@dataclass
class LSPTextDocumentItem:
    uri: str
    languageId: str
    version: int
    text: str


@dataclass
class LSPInitializeParams:
    processId: int | None = None
    rootUri: str | None = None
    workspaceFolders: list[Any] | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass
class LSPInitializeResult:
    capabilities: dict[str, Any] = field(default_factory=dict)
    serverInfo: dict[str, Any] | None = None


@dataclass
class ServerCapabilities:
    textDocumentSync: int | dict[str, Any] | None = None
    hoverProvider: bool | dict[str, Any] | None = None
    definitionProvider: bool | dict[str, Any] | None = None
    referencesProvider: bool | dict[str, Any] | None = None
    documentFormattingProvider: bool | dict[str, Any] | None = None
    completionProvider: dict[str, Any] | None = None


# Notification handler type
LSPNotificationHandler = Callable[[dict[str, Any]], None]
LSPRequestHandler = Callable[[dict[str, Any]], Any]


@dataclass
class ScopedLspServerConfig:
    """LSP server configuration for a given scope/file type."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    scope: str | None = None  # e.g., ".py", ".ts", file extension or language id
    restartOnCrash: bool = True
    shutdownTimeout: int = 5000
    env: dict[str, str] | None = None
    cwd: str | None = None


@dataclass
class PendingLSPDiagnostic:
    """A pending LSP diagnostic to be delivered to the client."""

    file_uri: str
    diagnostics: list[LSPDiagnostic]
    version: int | None = None
