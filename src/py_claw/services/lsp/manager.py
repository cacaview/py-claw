"""
LSP server manager.

Manages multiple LSP server instances and routes requests by file extension.
Based on ClaudeCode-main/src/services/lsp/LSPServerManager.ts and manager.ts.
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py_claw.services.lsp.diagnostics import LSPDiagnosticRegistry
from py_claw.services.lsp.server import LSPServerInstance, LSPServerStatus
from py_claw.services.lsp.types import ScopedLspServerConfig


@dataclass
class FileState:
    """Tracks open file state for a given URI."""

    uri: str
    version: int = 1
    text: str = ""
    language_id: str | None = None


class LSPServerManager:
    """Manages multiple LSP server instances and routes requests by file extension.

    Responsibilities:
    - Load and register LSP server configurations
    - Route file operations to the appropriate server by extension
    - Lazy-start servers on first file type hit
    - Track open file state (didOpen/didChange/didSave/didClose)
    - Deliver diagnostics via registered callback
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._servers: dict[str, LSPServerInstance] = {}
        self._server_configs: list[ScopedLspServerConfig] = []
        # file URI -> FileState
        self._open_files: dict[str, FileState] = {}
        # extension -> server name
        self._extension_map: dict[str, str] = {}
        # extension -> list of server names (for multi-server support)
        self._extension_servers: dict[str, list[str]] = {}
        self._diagnostic_registry: LSPDiagnosticRegistry = field(
            default_factory=LSPDiagnosticRegistry, init=False
        )
        self._diagnostic_callback: callable | None = None
        self._root_uri: str | None = None

    @property
    def diagnostic_registry(self) -> LSPDiagnosticRegistry:
        return self._diagnostic_registry

    def set_root_uri(self, root_uri: str | None) -> None:
        """Set the workspace root URI."""
        self._root_uri = root_uri

    def set_diagnostic_callback(self, callback: callable) -> None:
        """Set a callback to be called when diagnostics are ready.

        Callback receives (file_uri: str, diagnostics: list[LSPDiagnostic]).
        """
        self._diagnostic_callback = callback

    def register_servers(self, configs: list[ScopedLspServerConfig]) -> None:
        """Register LSP server configurations.

        Servers are started lazily on first file access.
        """
        with self._lock:
            self._server_configs = configs
            self._extension_map.clear()
            self._extension_servers.clear()

            for config in configs:
                instance = LSPServerInstance(config=config)
                self._servers[config.name] = instance

                # Build extension map
                scope = config.scope or ""
                if scope.startswith("."):
                    # File extension
                    ext = scope.lower()
                    if ext not in self._extension_servers:
                        self._extension_servers[ext] = []
                    if config.name not in self._extension_servers[ext]:
                        self._extension_servers[ext].append(config.name)
                    self._extension_map[ext] = config.name
                else:
                    # Language ID
                    lang_ext_map = {
                        "python": ".py",
                        "javascript": ".js",
                        "typescript": ".ts",
                        "java": ".java",
                        "csharp": ".cs",
                        "cpp": ".cpp",
                        "c": ".c",
                        "go": ".go",
                        "rust": ".rs",
                        "ruby": ".rb",
                        "php": ".php",
                        "html": ".html",
                        "css": ".css",
                        "json": ".json",
                        "yaml": ".yaml",
                        "markdown": ".md",
                    }
                    ext = lang_ext_map.get(scope.lower(), f".{scope.lower()}")
                    if ext not in self._extension_servers:
                        self._extension_servers[ext] = []
                    if config.name not in self._extension_servers[ext]:
                        self._extension_servers[ext].append(config.name)
                    self._extension_map[ext] = config.name

    def get_server_for_file(self, file_path: str) -> LSPServerInstance | None:
        """Get the LSP server for a given file path."""
        ext = Path(file_path).suffix.lower()
        with self._lock:
            return self._get_server_by_ext_locked(ext)

    def _get_server_by_ext_locked(self, ext: str) -> LSPServerInstance | None:
        server_name = self._extension_map.get(ext)
        if server_name is None:
            return None
        return self._servers.get(server_name)

    async def ensure_server_started(self, file_path: str) -> LSPServerInstance | None:
        """Ensure the LSP server for a file is started, starting it if needed."""
        server = self.get_server_for_file(file_path)
        if server is None:
            return None

        if server.status == LSPServerStatus.STOPPED:
            await server.start(self._root_uri)

            # Register diagnostics handler
            async def on_publish_diagnostics(params: dict[str, Any]) -> None:
                await self._handle_publish_diagnostics(params)

            server.on_notification("textDocument/publishDiagnostics", on_publish_diagnostics)

        return server

    async def _handle_publish_diagnostics(self, params: dict[str, Any]) -> None:
        """Handle textDocument/publishDiagnostics notification."""
        uri = params.get("uri", "")
        diagnostics_data = params.get("diagnostics", [])

        # Parse diagnostics
        diagnostics = []
        for d in diagnostics_data:
            try:
                rng = d.get("range", {})
                start = rng.get("start", {})
                end = rng.get("end", {})
                diag = LSPDiagnostic(
                    range=LSPRange(
                        start=LSPPosition(line=start.get("line", 0), character=start.get("character", 0)),
                        end=LSPPosition(line=end.get("line", 0), character=end.get("character", 0)),
                    ),
                    severity=d.get("severity"),
                    code=d.get("code"),
                    source=d.get("source"),
                    message=d.get("message", ""),
                )
                diagnostics.append(diag)
            except Exception:
                continue

        # Register and filter diagnostics
        filtered = self._diagnostic_registry.register_pending(uri, diagnostics)
        if filtered and self._diagnostic_callback:
            try:
                self._diagnostic_callback(uri, filtered)
            except Exception:
                pass

    async def open_file(self, file_path: str, text: str, language_id: str | None = None) -> None:
        """Handle textDocument/didOpen for a file."""
        server = await self.ensure_server_started(file_path)
        if server is None:
            return

        uri = self._path_to_uri(file_path)
        version = 1

        with self._lock:
            self._open_files[uri] = FileState(
                uri=uri,
                version=version,
                text=text,
                language_id=language_id,
            )

        server.send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": language_id or self._extension_to_lang(Path(file_path).suffix),
                "version": version,
                "text": text,
            }
        })

    async def change_file(self, file_path: str, text: str) -> None:
        """Handle textDocument/didChange for a file."""
        server = self.get_server_for_file(file_path)
        if server is None:
            return

        uri = self._path_to_uri(file_path)
        with self._lock:
            if uri in self._open_files:
                state = self._open_files[uri]
                state.version += 1
                state.text = text
                version = state.version
            else:
                version = 1
                self._open_files[uri] = FileState(uri=uri, version=version, text=text)

        server.send_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": version},
            "contentChanges": [{"text": text}],
        })

    async def save_file(self, file_path: str) -> None:
        """Handle textDocument/didSave for a file."""
        server = self.get_server_for_file(file_path)
        if server is None:
            return

        uri = self._path_to_uri(file_path)
        server.send_notification("textDocument/didSave", {
            "textDocument": {"uri": uri},
        })

    async def close_file(self, file_path: str) -> None:
        """Handle textDocument/didClose for a file."""
        server = self.get_server_for_file(file_path)
        if server is None:
            return

        uri = self._path_to_uri(file_path)
        with self._lock:
            if uri in self._open_files:
                del self._open_files[uri]

        server.send_notification("textDocument/didClose", {
            "textDocument": {"uri": uri},
        })
        self._diagnostic_registry.clear_file(uri)

    def send_request(self, file_path: str, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a request to the appropriate server for a file."""
        server = self.get_server_for_file(file_path)
        if server is None:
            raise RuntimeError(f"No LSP server configured for: {file_path}")
        if server.status != LSPServerStatus.RUNNING:
            raise RuntimeError(f"LSP server not running for: {file_path}")
        return server.send_request(method, params)

    def get_all_servers(self) -> list[tuple[str, LSPServerInstance]]:
        """Return all registered servers and their status."""
        with self._lock:
            return [(name, inst) for name, inst in self._servers.items()]

    def get_all_extensions(self) -> list[str]:
        """Return all supported file extensions."""
        with self._lock:
            return list(self._extension_servers.keys())

    async def shutdown(self) -> None:
        """Shutdown all LSP servers."""
        with self._lock:
            servers = list(self._servers.values())

        for server in servers:
            try:
                await server.stop()
            except Exception:
                pass

        with self._lock:
            self._servers.clear()
            self._open_files.clear()

    @staticmethod
    def _path_to_uri(file_path: str) -> str:
        """Convert a local file path to a file:// URI."""
        path = Path(file_path).resolve()
        # Convert to URI
        uri = path.as_uri()
        return uri

    @staticmethod
    def _extension_to_lang(ext: str) -> str:
        """Map a file extension to a language ID."""
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".java": "java",
            ".cs": "csharp",
            ".cpp": "cpp",
            ".c": "c",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".html": "html",
            ".htm": "html",
            ".css": "css",
            ".scss": "scss",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".xml": "xml",
            ".sql": "sql",
        }
        return lang_map.get(ext.lower(), "plaintext")
