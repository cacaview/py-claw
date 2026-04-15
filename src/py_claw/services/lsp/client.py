"""
LSP stdio JSON-RPC client.

Manages communication with an LSP server process via stdin/stdout.
Based on ClaudeCode-main/src/services/lsp/LSPClient.ts.
"""
from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any

from py_claw.services.lsp.types import (
    LSPInitializeParams,
    LSPInitializeResult,
    LSPNotificationHandler,
    LSPRequestHandler,
)


@dataclass
class LSPClient:
    """LSP client for communicating with a language server over stdio.

    Uses JSON-RPC protocol as specified in the LSP.
    """

    _process: subprocess.Popen[str] | None = field(default=None, init=False)
    _capabilities: dict[str, Any] | None = field(default=None, init=False)
    _is_initialized: bool = field(default=False, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _read_thread: threading.Thread | None = field(default=None, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _next_id: int = field(default=1, init=False)
    _pending: dict[int, threading.Event] = field(default_factory=dict, init=False)
    _results: dict[int, Any] = field(default_factory=dict, init=False)
    _notif_handlers: dict[str, LSPNotificationHandler] = field(default_factory=dict, init=False)
    _req_handlers: dict[str, LSPRequestHandler] = field(default_factory=dict, init=False)

    @property
    def capabilities(self) -> dict[str, Any] | None:
        return self._capabilities

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    async def start(
        self,
        command: str,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        """Start the LSP server process."""
        with self._lock:
            if self._process is not None:
                await self.stop()

            self._stop_event.clear()
            self._process = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=cwd,
                text=True,
            )
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()

    def _read_loop(self) -> None:
        """Background thread to read responses from the LSP server."""
        process = self._process
        if process is None:
            return

        buffer = ""
        while not self._stop_event.is_set():
            try:
                chunk = process.stdout.read(1) if process.stdout else ""
                if not chunk:
                    break
                buffer += chunk

                # Try to parse complete JSON-RPC messages
                while "\n" in buffer:
                    newline_idx = buffer.index("\n")
                    line = buffer[:newline_idx].strip()
                    buffer = buffer[newline_idx + 1:]
                    if line:
                        self._handle_message(line)
            except Exception:
                break

        # Process exited
        with self._lock:
            proc = self._process
            if proc is not None and proc.poll() is not None:
                self._process = None

    def _handle_message(self, raw: str) -> None:
        """Handle an incoming JSON-RPC message."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_id = msg.get("id")
        if msg.get("method"):
            # Request or notification from server
            method = msg["method"]
            params = msg.get("params")
            if msg.get("id") is not None:
                # Server -> client request (we should respond)
                handler = self._req_handlers.get(method)
                if handler:
                    try:
                        result = handler(params)
                        response = {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "result": result,
                        }
                        self._send_raw(json.dumps(response))
                    except Exception:
                        response = {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {"code": -32603, "message": "Internal error"},
                        }
                        self._send_raw(json.dumps(response))
            else:
                # Server -> client notification
                handler = self._notif_handlers.get(method)
                if handler:
                    handler(params or {})
        elif msg_id is not None:
            # Response to our request
            evt = self._pending.pop(msg_id, None)
            if "result" in msg:
                self._results[msg_id] = msg["result"]
            elif "error" in msg:
                self._results[msg_id] = msg["error"]
            if evt:
                evt.set()

    def _send_raw(self, data: str) -> None:
        """Send a raw JSON-RPC message."""
        proc = self._process
        if proc is None or proc.stdin is None:
            return
        try:
            proc.stdin.write(data + "\n")
            proc.stdin.flush()
        except Exception:
            pass

    def _send_request(self, method: str, params: dict[str, Any] | None) -> int:
        """Send a JSON-RPC request and return its id."""
        msg_id = self._next_id
        self._next_id += 1
        evt = threading.Event()
        self._pending[msg_id] = evt
        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._send_raw(json.dumps(msg))
        return msg_id

    def _send_notification(self, method: str, params: dict[str, Any] | None) -> None:
        """Send a JSON-RPC notification."""
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send_raw(json.dumps(msg))

    def _wait_for_result(self, msg_id: int, timeout: float = 30.0) -> Any:
        """Wait for a response to a request."""
        evt = self._pending.get(msg_id)
        if evt is None:
            return None
        evt.wait(timeout=timeout)
        return self._results.pop(msg_id, None)

    async def initialize(self, params: LSPInitializeParams) -> LSPInitializeResult:
        """Send initialize request and return server capabilities."""
        if self._is_initialized:
            return LSPInitializeResult(capabilities=self._capabilities or {})

        params_dict: dict[str, Any] = {}
        if params.processId is not None:
            params_dict["processId"] = params.processId
        if params.rootUri is not None:
            params_dict["rootUri"] = params.rootUri
        if params.workspaceFolders is not None:
            params_dict["workspaceFolders"] = params.workspaceFolders
        if params.capabilities:
            params_dict["capabilities"] = params.capabilities

        msg_id = self._send_request("initialize", params_dict)
        result = self._wait_for_result(msg_id)

        if isinstance(result, dict):
            self._capabilities = result.get("capabilities", {})
            self._is_initialized = True
            # Send initialized notification
            self._send_notification("initialized", {})
            return LSPInitializeResult(
                capabilities=self._capabilities,
                serverInfo=result.get("serverInfo"),
            )

        raise RuntimeError(f"LSP initialize failed: {result}")

    def send_request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send an RPC request and wait for the response."""
        if not self._is_initialized and method != "initialize":
            raise RuntimeError("LSP client not initialized")

        msg_id = self._send_request(method, params)
        return self._wait_for_result(msg_id)

    def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send an RPC notification (no response expected)."""
        if not self._is_initialized and method not in ("initialize", "initialized"):
            raise RuntimeError("LSP client not initialized")
        self._send_notification(method, params)

    def on_notification(self, method: str, handler: LSPNotificationHandler) -> None:
        """Register a handler for server notifications."""
        self._notif_handlers[method] = handler

    def on_request(self, method: str, handler: LSPRequestHandler) -> None:
        """Register a handler for server requests."""
        self._req_handlers[method] = handler

    async def stop(self) -> None:
        """Stop the LSP server."""
        with self._lock:
            if self._process is None:
                return

            self._stop_event.set()

            try:
                # Send shutdown request
                if self._is_initialized:
                    try:
                        self._send_request("shutdown", None)
                    except Exception:
                        pass

                # Send exit notification
                self._send_notification("exit", None)

                # Wait briefly for graceful exit
                proc = self._process
                if proc is not None:
                    proc.wait(timeout=2.0)
                    if proc.poll() is None:
                        proc.kill()
            except Exception:
                pass

            self._process = None
            self._is_initialized = False
            self._capabilities = None

            # Clear pending
            for evt in self._pending.values():
                evt.set()
            self._pending.clear()
            self._results.clear()
