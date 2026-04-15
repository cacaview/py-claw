"""
LSP server instance management.

Manages the lifecycle of a single LSP server process.
Based on ClaudeCode-main/src/services/lsp/LSPServerInstance.ts.
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any

from py_claw.services.lsp.client import LSPClient
from py_claw.services.lsp.types import (
    LSPInitializeParams,
    LSPNotificationHandler,
    LSPRequestHandler,
    ScopedLspServerConfig,
)


class LSPServerStatus:
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class LSPServerInstance:
    """Manages a single LSP server process."""

    config: ScopedLspServerConfig
    _client: LSPClient = field(default_factory=LSPClient, init=False)
    _status: str = field(default=LSPServerStatus.STOPPED, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _restart_count: int = field(default=0, init=False)
    _last_error: str | None = field(default=None, init=False)

    @property
    def status(self) -> str:
        return self._status

    @property
    def capabilities(self) -> dict[str, Any] | None:
        return self._client.capabilities

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def restart_count(self) -> int:
        return self._restart_count

    async def start(self, root_uri: str | None = None) -> None:
        """Start the LSP server process."""
        with self._lock:
            if self._status == LSPServerStatus.RUNNING:
                return

            self._status = LSPServerStatus.STARTING
            self._client = LSPClient()

            try:
                # Build environment
                env = dict(self.config.env) if self.config.env else None

                # Start the process
                await self._client.start(
                    self.config.command,
                    self.config.args,
                    env=env,
                    cwd=self.config.cwd,
                )

                # Initialize with LSP protocol
                params = LSPInitializeParams(
                    rootUri=root_uri,
                    capabilities=self._default_client_capabilities(),
                )
                result = await self._client.initialize(params)

                if result.capabilities:
                    self._status = LSPServerStatus.RUNNING
                    self._restart_count = 0
                else:
                    self._status = LSPServerStatus.ERROR
                    self._last_error = "Server returned no capabilities"

            except Exception as e:
                self._status = LSPServerStatus.ERROR
                self._last_error = str(e)
                await self._client.stop()

    async def stop(self) -> None:
        """Stop the LSP server process."""
        with self._lock:
            if self._status == LSPServerStatus.STOPPED:
                return

            try:
                await self._client.stop()
            except Exception:
                pass

            self._status = LSPServerStatus.STOPPED

    async def restart(self, root_uri: str | None = None) -> None:
        """Restart the LSP server."""
        with self._lock:
            self._restart_count += 1

        await self.stop()
        await asyncio.sleep(0.5)  # Brief delay before restart
        await self.start(root_uri)

    def send_request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a request to the LSP server."""
        if self._status != LSPServerStatus.RUNNING:
            raise RuntimeError(f"LSP server not running (status: {self._status})")
        return self._client.send_request(method, params)

    def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a notification to the LSP server."""
        if self._status != LSPServerStatus.RUNNING:
            return
        self._client.send_notification(method, params)

    def on_notification(self, method: str, handler: LSPNotificationHandler) -> None:
        """Register a notification handler."""
        self._client.on_notification(method, handler)

    def on_request(self, method: str, handler: LSPRequestHandler) -> None:
        """Register a request handler."""
        self._client.on_request(method, handler)

    @staticmethod
    def _default_client_capabilities() -> dict[str, Any]:
        """Return the default client capabilities to announce to the server."""
        return {
            "textDocument": {
                "sync": {"openClose": True, "change": 1},  # Full sync
                "hover": {},
                "definition": {},
                "references": {},
                "formatting": {},
                "codeAction": {},
                "completion": {
                    "triggerCharacters": [],
                    "resolveProvider": False,
                },
            },
            "workspace": {
                "applyEdit": True,
                "workspaceFolders": True,
            },
            "window": {
                "workDoneProgress": False,
            },
        }
