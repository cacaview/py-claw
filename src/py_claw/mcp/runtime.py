from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable, Iterator
import json
import subprocess
import threading
import time
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import TypeAdapter

from py_claw.mcp.resources import extract_error_payload, extract_result_payload, normalize_resource_contents, normalize_resource_list
from py_claw.schemas.common import (
    McpCapabilities,
    McpClaudeAIProxyServerConfig,
    McpHttpServerConfig,
    McpSSEIDEServerConfig,
    McpSdkServerConfig,
    McpServerConfigForProcessTransport,
    McpServerInfo,
    McpServerStatusModel,
    McpSSEServerConfig,
    McpStdioServerConfig,
    McpToolInfo,
    McpWebSocketIDEServerConfig,
    McpWebSocketServerConfig,
)
from py_claw.settings.loader import SettingsLoadResult

_MCP_SERVER_CONFIG_ADAPTER = TypeAdapter(McpServerConfigForProcessTransport)
_SCOPE_BY_SETTINGS_SOURCE = {
    "userSettings": "user",
    "projectSettings": "project",
    "localSettings": "local",
    "flagSettings": "local",
    "policySettings": "local",
}

# MCP protocol version supported
MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass(slots=True)
class _PersistentStdioMcpProcess:
    """Persistent stdio transport that reuses a single subprocess.

    Unlike _StdioMcpProcess which spawns a new process per request,
    this class keeps the subprocess alive and communicates via
    stdin/stdout pipes for efficient message exchange.
    """
    command: str
    args: list[str] | None = None
    env: dict[str, str] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _process: subprocess.Popen | None = field(default=None, repr=False)
    _request_id: int = field(default=0)

    def request(self, message: Any) -> Any:
        """Send a JSON-RPC request and wait for response."""
        with self._lock:
            # Ensure process is running
            if self._process is None or self._process.poll() is not None:
                self._start_process()

            # Assign request ID if not present
            if isinstance(message, dict) and "id" not in message:
                self._request_id += 1
                message["id"] = self._request_id

            # Write request
            request_line = json.dumps(message) + "\n"
            self._process.stdin.write(request_line)
            self._process.stdin.flush()

            # Read response line
            try:
                response_line = self._process.stdout.readline()
                if not response_line:
                    # Process died, try restarting once
                    self._start_process()
                    raise RuntimeError("MCP stdio process terminated during response")
                return json.loads(response_line)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Invalid MCP JSON response") from exc

    def _start_process(self) -> None:
        """Start or restart the subprocess."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = subprocess.Popen(
            [self.command, *(self.args or [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
            bufsize=1,
        )

    def close(self) -> None:
        """Terminate the subprocess."""
        with self._lock:
            if self._process and self._process.poll() is None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=2)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


@dataclass(slots=True)
class _WebSocketMcpTransport:
    """WebSocket transport for MCP servers.

    Provides bidirectional JSON-RPC communication over WebSocket.
    Supports ping/pong keepalive if ping_interval_seconds is set.
    """
    url: str
    headers: dict[str, str] | None = None
    ping_interval_seconds: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _ws: Any = field(default=None, repr=False)

    def request(self, message: Any) -> Any:
        """Send a JSON-RPC request over WebSocket and wait for response.

        Creates a new WebSocket connection per request for simplicity.
        For high-frequency usage, a persistent connection pool would be more efficient.
        """
        import wsproto
        import wsproto.extensions
        import wsproto.frame_protocol as fp
        from urllib.parse import urlparse
        from urllib import request as urllib_request
        import socket
        import ssl

        parsed = urlparse(self.url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        use_tls = parsed.scheme in ("wss", "https")

        # Build HTTP upgrade request
        request_lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            "Sec-WebSocket-Version: 13",
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",  # Fixed key for simplicity
        ]
        if self.headers:
            for k, v in self.headers.items():
                if k.lower() not in ("host", "upgrade", "connection", "sec-websocket-version", "sec-websocket-key"):
                    request_lines.append(f"{k}: {v}")
        request_lines.append("")
        request_lines.append("")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if use_tls:
                ctx = ssl.create_default_context()
                sock = ctx.wrap_socket(sock, server_hostname=host)
            sock.settimeout(30.0)
            sock.connect((host, port))

            # Send HTTP upgrade request
            http_request = "\r\n".join(request_lines).encode("utf-8")
            sock.sendall(http_request)

            # Read HTTP upgrade response
            response = b""
            while b"\r\n\r\n" not in response:
                response += sock.recv(4096)
            response_text = response.decode("utf-8", errors="replace")
            if "101" not in response_text:
                raise RuntimeError(f"WebSocket upgrade failed: {response_text[:200]}")

            # Initialize wsproto connection
            ws_conn = wsproto.WSConnection(wsproto.ConnectionType.CLIENT)
            sock.settimeout(30.0)

            # Send JSON-RPC request as text frame
            json_payload = json.dumps(message).encode("utf-8")
            ws_conn.send_data(json_payload)
            sock.sendall(ws_conn.bytes_to_send())

            # Receive response
            response_data = b""
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                response_data += chunk

                ws_conn.receive_data(chunk)
                for event in ws_conn.events():
                    if isinstance(event, wsproto.events.Message):
                        if event.data:
                            return json.loads(event.data.decode("utf-8"))
                if ws_conn.state == wsproto.utilities.State.CLOSED:
                    break

            return {}
        finally:
            sock.close()

    def close(self) -> None:
        """Close the WebSocket connection."""
        with self._lock:
            if self._ws is not None:
                try:
                    self._ws.close()
                except Exception:
                    pass
                self._ws = None


class _SdkMcpTransport:
    """SDK (Software Development Kit) transport for MCP servers.

    Communicates with a local SDK process via stdin/stdout JSON-RPC messages.
    The SDK process is spawned as a subprocess and kept alive for the duration
    of the session for efficient message exchange.
    """

    def __init__(self, name: str, message_handler: Callable[[str, Any], Any] | None = None) -> None:
        self._name = name
        self._message_handler = message_handler
        self._lock = threading.Lock()
        self._connected = False

    def set_message_handler(self, handler: Callable[[str, Any], Any]) -> None:
        """Set the message handler for SDK communication."""
        with self._lock:
            self._message_handler = handler

    def request(self, message: Any) -> Any:
        """Send a JSON-RPC request via SDK message handler.

        The SDK transport requires sdk_message_handler to be set on McpRuntime.
        This handler provides the communication bridge to the external SDK process.

        Args:
            message: JSON-RPC message dict

        Returns:
            Response from SDK handler

        Raises:
            NotImplementedError: If no sdk_message_handler is configured on McpRuntime.
        """
        with self._lock:
            if self._message_handler is None:
                raise NotImplementedError(
                    f"SDK transport for '{self._name}' requires sdk_message_handler to be set on McpRuntime. "
                    "Use McpRuntime.set_sdk_message_handler() to provide an SDK message bridge. "
                    "SDK transport cannot operate without a message handler."
                )
            response = self._message_handler(self._name, message)
            return {} if response is None else response

    def notification(self, message: Any) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        with self._lock:
            if self._message_handler is None:
                return
            self._message_handler(self._name, message)


class _ClaudeAIProxyMcpTransport:
    """Claude AI Proxy transport for MCP servers.

    Communicates with a Claude AI proxy server via HTTP/SSE.
    The proxy URL is used for both request/response and streaming.
    """

    def __init__(self, url: str, proxy_id: str, headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._proxy_id = proxy_id
        self._headers = headers or {}
        self._sse_transport = _SseMcpTransport(url, headers)

    def request(self, message: Any) -> Any:
        """Send a JSON-RPC request to the Claude AI proxy.

        Args:
            message: JSON-RPC message dict

        Returns:
            Response from proxy
        """
        # Add proxy_id to message for routing
        enhanced_message = {**message}
        if "params" not in enhanced_message:
            enhanced_message["params"] = {}
        enhanced_message["params"]["_proxy_id"] = self._proxy_id

        return self._sse_transport.request(enhanced_message)

    def stream_messages(self, message: Any) -> Iterator[dict[str, Any]]:
        """Send a request and yield SSE events from proxy.

        Args:
            message: JSON-RPC message dict

        Yields:
            Parsed JSON objects from SSE data events
        """
        enhanced_message = {**message}
        if "params" not in enhanced_message:
            enhanced_message["params"] = {}
        enhanced_message["params"]["_proxy_id"] = self._proxy_id

        return self._sse_transport.stream_messages(enhanced_message)

    def notification(self, message: Any) -> None:
        """Send a JSON-RPC notification to proxy."""
        enhanced_message = {**message}
        if "params" not in enhanced_message:
            enhanced_message["params"] = {}
        enhanced_message["params"]["_proxy_id"] = self._proxy_id
        try:
            self._sse_transport.request(enhanced_message)
        except Exception:
            pass  # Notifications don't expect responses


class _SseMcpTransport:
    """SSE (Server-Sent Events) transport for MCP servers.

    Uses HTTP POST for sending requests and SSE for receiving responses.
    Some MCP servers (e.g., Claude.ai proxy) use SSE for streaming responses.
    """
    url: str
    headers: dict[str, str]

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self.url = url
        self.headers = headers or {}
        self.headers.setdefault("Accept", "application/json")

    def request(self, message: Any) -> Any:
        """Send a JSON-RPC request and receive a JSON response.

        Note: This implements basic request-response. For true SSE streaming,
        use stream_messages() instead which parses SSE event format.
        """
        all_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }
        data = json.dumps(message).encode("utf-8")
        request = urllib_request.Request(
            self.url,
            data=data,
            headers=all_headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=30) as response:
                payload = response.read().decode("utf-8")
                if not payload.strip():
                    return {}
                return json.loads(payload)
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if body.strip():
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    pass
            return {"error": {"code": exc.code, "message": body or str(exc.reason)}}
        except urllib_error.URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc

    def stream_messages(self, message: Any) -> Iterator[dict[str, Any]]:
        """Send a request and yield SSE events as they arrive.

        Yields parsed JSON objects from 'data:' lines in SSE format.
        """
        all_headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            **self.headers,
        }
        data = json.dumps(message).encode("utf-8")
        request = urllib_request.Request(
            self.url,
            data=data,
            headers=all_headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=60) as response:
                # Read SSE stream line by line
                buffer = ""
                while True:
                    chunk = response.read(4096).decode("utf-8")
                    if not chunk:
                        break
                    buffer += chunk
                    # Process complete lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_content = line[6:]  # Strip "data: " prefix
                            if data_content == "[DONE]":
                                return
                            try:
                                yield json.loads(data_content)
                            except json.JSONDecodeError:
                                continue
        except urllib_error.URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc


@dataclass(slots=True)
class _StdioMcpProcess:
    command: str
    args: list[str] | None = None
    env: dict[str, str] | None = None

    def request(self, message: Any) -> Any:
        completed = subprocess.run(
            [self.command, *(self.args or [])],
            input=json.dumps(message),
            capture_output=True,
            text=True,
            timeout=30,
            env=self.env,
        )
        if completed.returncode != 0:
            error_message = completed.stderr.strip() or completed.stdout.strip() or f"MCP stdio process exited with code {completed.returncode}"
            raise RuntimeError(error_message)
        if not completed.stdout.strip():
            return {}
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Invalid MCP JSON response") from exc

    def notify(self, message: Any) -> None:
        """Send a notification without waiting for a response.

        Used for JSON-RPC notifications which are fire-and-forget.
        Spawns a new process since persistent stdio would need to
        avoid waiting for a response.
        """
        subprocess.run(
            [self.command, *(self.args or [])],
            input=json.dumps(message),
            capture_output=True,
            text=True,
            timeout=5,
            env=self.env,
            check=False,  # Don't fail if server exits
        )


@dataclass(slots=True)
class McpLiveServerState:
    status: str = "pending"
    error: str | None = None
    server_info: McpServerInfo | None = None
    capabilities: McpCapabilities | None = None
    tools: list[McpToolInfo] = field(default_factory=list)
    initialized: bool = field(default=False)
    last_error_code: int | None = None
    consecutive_failures: int = 0
    last_activity: float = field(default_factory=time.time)


@dataclass(slots=True)
class McpRuntime:
    runtime_servers: dict[str, McpServerConfigForProcessTransport] = field(default_factory=dict)
    disabled_servers: set[str] = field(default_factory=set)
    live_states: dict[str, McpLiveServerState] = field(default_factory=dict)
    sdk_message_handler: Callable[[str, Any], Any] | None = None
    _request_ids: Any = field(default_factory=lambda: count(1), repr=False)

    def set_servers(self, servers: dict[str, McpServerConfigForProcessTransport]) -> dict[str, object]:
        previous = set(self.runtime_servers)
        current = set(servers)
        self.runtime_servers = dict(servers)
        for name in previous - current:
            self.live_states.pop(name, None)
            self.disabled_servers.discard(name)
        for name in current:
            self._ensure_live_state(name)
        return {
            "added": sorted(current - previous),
            "removed": sorted(previous - current),
            "errors": {},
        }

    def set_sdk_message_handler(self, handler: Callable[[str, Any], Any]) -> None:
        """Set the SDK message handler for SDK/claudeai-proxy transports.

        This handler is called when SDK or claudeai-proxy MCP servers
        receive messages. The handler should communicate with the
        external SDK process and return the response.

        Args:
            handler: A callable that takes (server_name: str, message: dict)
                    and returns the response dict, or None for notifications.
        """
        self.sdk_message_handler = handler

    def has_server(self, name: str, settings: SettingsLoadResult) -> bool:
        return name in self._configured_servers(settings)

    def set_server_enabled(self, name: str, enabled: bool, settings: SettingsLoadResult) -> None:
        self._require_server(name, settings)
        self._ensure_live_state(name)
        if enabled:
            self.disabled_servers.discard(name)
            return
        self.disabled_servers.add(name)

    def reconnect_server(self, name: str, settings: SettingsLoadResult) -> None:
        """Reset live state for a server to trigger reconnection on next request.

        Note: This only resets local status state. Actual transport reconnection
        happens on the next send_message() call, which will re-establish the connection.
        """
        self._require_server(name, settings)
        if name in self.disabled_servers:
            raise ValueError(f"Server is disabled: {name}")
        state = self._ensure_live_state(name)
        state.status = "pending"
        state.error = None
        state.server_info = None
        state.capabilities = None
        state.tools = []
        state.initialized = False

    def send_message(self, name: str, message: Any, settings: SettingsLoadResult) -> Any:
        config, _scope = self._require_server(name, settings)
        if name in self.disabled_servers:
            raise ValueError(f"Server is disabled: {name}")
        try:
            response = self._dispatch_message(config, message)
        except Exception as exc:
            self._record_transport_failure(name, str(exc))
            raise
        self._record_message_result(name, response)
        return response

    def list_resources(self, name: str, settings: SettingsLoadResult) -> list[dict[str, Any]]:
        response = self.send_message(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "resources/list",
                "params": {},
            },
            settings,
        )
        return normalize_resource_list(response)

    def read_resource(self, name: str, uri: str, settings: SettingsLoadResult) -> list[dict[str, Any]]:
        response = self.send_message(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "resources/read",
                "params": {"uri": uri},
            },
            settings,
        )
        return normalize_resource_contents(response)

    def list_tools(self, name: str, settings: SettingsLoadResult) -> list[dict[str, Any]]:
        """List available tools from an MCP server.

        Sends tools/list and returns the tools array from the response.
        Updates the server's live_state with discovered tools.
        """
        response = self.send_message(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "tools/list",
                "params": {},
            },
            settings,
        )
        payload = extract_result_payload(response)
        if not isinstance(payload, dict):
            return []
        tools = payload.get("tools")
        if not isinstance(tools, list):
            return []
        state = self._ensure_live_state(name)
        normalized_tools: list[McpToolInfo] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            try:
                normalized_tools.append(McpToolInfo.model_validate(tool))
            except Exception:
                continue
        state.tools = normalized_tools
        return tools

    def call_tool(self, name: str, tool_name: str, arguments: dict[str, Any], settings: SettingsLoadResult) -> dict[str, Any]:
        """Call an MCP tool by name.

        Sends tools/call and returns the result content.
        Raises on error response or transport failure.
        """
        response = self.send_message(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
            settings,
        )
        error_payload = extract_error_payload(response)
        if error_payload is not None:
            raise RuntimeError(f"MCP tool '{tool_name}' failed: {_error_message(error_payload)}")
        payload = extract_result_payload(response)
        if not isinstance(payload, dict):
            return {}
        # Return the structured result for further processing
        return payload

    def send_notification(self, name: str, method: str, params: dict[str, Any] | None, settings: SettingsLoadResult) -> None:
        """Send a JSON-RPC notification to an MCP server.

        Notifications are one-way messages that do not expect a response.
        This is used for protocol-level notifications like:
        - notifications/cancelled: cancel a previous request
        - notifications/progress: report progress on a request
        - (server-side) notifications/tool-list-changed
        - (server-side) notifications/resource-list-changed
        """
        config, _scope = self._require_server(name, settings)
        if name in self.disabled_servers:
            raise ValueError(f"Server is disabled: {name}")
        try:
            notification = {
                "jsonrpc": "2.0",
                "method": method,
            }
            if params is not None:
                notification["params"] = params
            self._dispatch_notification(config, notification)
        except Exception as exc:
            self._record_transport_failure(name, str(exc))
            raise

    def cancel_request(self, name: str, request_id: int, settings: SettingsLoadResult) -> None:
        """Cancel a previously sent request.

        Sends notifications/cancelled to inform the server that a specific
        request ID should be cancelled.
        """
        self.send_notification(
            name,
            "notifications/cancelled",
            {"requestId": request_id},
            settings,
        )

    def _dispatch_message(self, config: McpServerConfigForProcessTransport, message: Any) -> Any:
        if isinstance(config, McpSdkServerConfig):
            return self._dispatch_sdk_message(config, message)
        if isinstance(config, McpClaudeAIProxyServerConfig):
            return self._dispatch_claudeai_proxy_message(config, message)
        if isinstance(config, McpSSEIDEServerConfig):
            # IDE extensions use SSE transport with the configured URL
            sse_transport = _SseMcpTransport(config.url, None)
            return sse_transport.request(message)
        if isinstance(config, McpWebSocketIDEServerConfig):
            # IDE extensions use WebSocket transport with the configured URL and optional auth token
            headers = {"Authorization": f"Bearer {config.authToken}"} if config.authToken else None
            ws_transport = _WebSocketMcpTransport(
                url=config.url,
                headers=headers,
                ping_interval_seconds=None,
            )
            return ws_transport.request(message)
        if isinstance(config, McpHttpServerConfig):
            return _send_http_message(config, message)
        if isinstance(config, McpSSEServerConfig):
            sse_transport = _SseMcpTransport(config.url, config.headers)
            return sse_transport.request(message)
        if isinstance(config, McpWebSocketServerConfig):
            ws_transport = _WebSocketMcpTransport(
                url=config.url,
                headers=config.headers,
                ping_interval_seconds=config.ping_interval_seconds,
            )
            return ws_transport.request(message)
        if getattr(config, "type", None) in (None, "stdio"):
            stdio_config = config
            return _StdioMcpProcess(
                command=stdio_config.command,
                args=stdio_config.args,
                env=stdio_config.env,
            ).request(message)
        transport_type = getattr(config, "type", None) or "stdio"
        supported = ["http", "sse", "sse-ide", "websocket", "ws-ide", "stdio", "sdk", "claudeai-proxy"]
        raise NotImplementedError(
            f"MCP transport '{transport_type}' is not implemented. Supported transports: {', '.join(supported)}. "
            "SDK and claudeai-proxy transports require sdk_message_handler to be set on McpRuntime."
        )


    def _dispatch_notification(self, config: McpServerConfigForProcessTransport, message: Any) -> None:
        """Dispatch a notification without waiting for a response."""
        if isinstance(config, McpSdkServerConfig):
            self._dispatch_sdk_notification(config, message)
            return
        if isinstance(config, McpClaudeAIProxyServerConfig):
            self._dispatch_claudeai_proxy_notification(config, message)
            return
        if isinstance(config, McpSSEIDEServerConfig):
            sse_transport = _SseMcpTransport(config.url, None)
            try:
                sse_transport.request(message)
            except Exception:
                pass
            return
        if isinstance(config, McpWebSocketIDEServerConfig):
            headers = {"Authorization": f"Bearer {config.authToken}"} if config.authToken else None
            ws_transport = _WebSocketMcpTransport(
                url=config.url,
                headers=headers,
                ping_interval_seconds=None,
            )
            try:
                ws_transport.request(message)
            except Exception:
                pass
            return
        if isinstance(config, McpHttpServerConfig):
            # HTTP servers typically don't process notifications, but we can try
            try:
                _send_http_message(config, message)
            except Exception:
                pass
            return
        if isinstance(config, McpSSEServerConfig):
            sse_transport = _SseMcpTransport(config.url, config.headers)
            try:
                sse_transport.request(message)
            except Exception:
                pass
            return
        if isinstance(config, McpWebSocketServerConfig):
            ws_transport = _WebSocketMcpTransport(
                url=config.url,
                headers=config.headers,
                ping_interval_seconds=config.ping_interval_seconds,
            )
            try:
                ws_transport.request(message)
            except Exception:
                pass
            return
        if getattr(config, "type", None) in (None, "stdio"):
            stdio_config = config
            _StdioMcpProcess(
                command=stdio_config.command,
                args=stdio_config.args,
                env=stdio_config.env,
            ).notify(message)
            return

    def _dispatch_sdk_message(self, config: McpSdkServerConfig, message: Any) -> Any:
        """Dispatch to SDK transport.

        Uses the sdk_message_handler if set, which enables SDK↔CLI inter-process
        communication. If no handler is set, falls back to a transport-based approach.
        """
        if self.sdk_message_handler is not None:
            response = self.sdk_message_handler(config.name, message)
            return {} if response is None else response

        # Fallback: use SDK transport with configured handler
        transport = _SdkMcpTransport(config.name, self.sdk_message_handler)
        return transport.request(message)

    def _dispatch_sdk_notification(self, config: McpSdkServerConfig, message: Any) -> None:
        """Dispatch SDK notification."""
        if self.sdk_message_handler is not None:
            self.sdk_message_handler(config.name, message)
            return
        transport = _SdkMcpTransport(config.name, self.sdk_message_handler)
        transport.notification(message)

    def _dispatch_claudeai_proxy_message(self, config: McpClaudeAIProxyServerConfig, message: Any) -> Any:
        """Dispatch to Claude AI Proxy transport.

        Uses sdk_message_handler if set (for direct SDK↔CLI communication),
        otherwise falls back to HTTP/SSE transport to the proxy URL.
        """
        if self.sdk_message_handler is not None:
            response = self.sdk_message_handler(config.id, message)
            return {} if response is None else response

        # Fallback: use HTTP transport to proxy URL
        transport = _ClaudeAIProxyMcpTransport(
            url=config.url,
            proxy_id=config.id,
            headers=None,
        )
        return transport.request(message)

    def _dispatch_claudeai_proxy_notification(self, config: McpClaudeAIProxyServerConfig, message: Any) -> None:
        """Dispatch Claude AI Proxy notification."""
        if self.sdk_message_handler is not None:
            self.sdk_message_handler(config.id, message)
            return
        # Fallback: use HTTP transport
        transport = _ClaudeAIProxyMcpTransport(
            url=config.url,
            proxy_id=config.id,
            headers=None,
        )
        transport.notification(message)

    def initialize(self, name: str, settings: SettingsLoadResult) -> McpLiveServerState:
        """Perform MCP initialization handshake with a server.

        Sends the initialize request with protocol version and client info,
        then sends the notifications/initialized notification to complete handshake.

        Updates the server's live_state with serverInfo and capabilities.
        Raises on transport or protocol errors.
        """
        config, _scope = self._require_server(name, settings)
        if name in self.disabled_servers:
            raise ValueError(f"Server is disabled: {name}")

        state = self._ensure_live_state(name)
        state.status = "connecting"
        state.error = None

        try:
            # Send initialization request
            response = self._dispatch_message(config, {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                    },
                    "clientInfo": {
                        "name": "py-claw",
                        "version": "0.1.0",
                    },
                },
            })

            # Check for error response
            error_payload = extract_error_payload(response)
            if error_payload is not None:
                state.status = "failed"
                state.error = _error_message(error_payload)
                raise RuntimeError(f"MCP initialize failed: {_error_message(error_payload)}")

            # Extract server info and capabilities from result
            payload = extract_result_payload(response)
            if isinstance(payload, dict):
                server_info = payload.get("serverInfo")
                if isinstance(server_info, dict):
                    try:
                        state.server_info = McpServerInfo.model_validate(server_info)
                    except Exception:
                        state.server_info = None
                capabilities = payload.get("capabilities")
                if isinstance(capabilities, dict):
                    try:
                        state.capabilities = McpCapabilities.model_validate(capabilities)
                    except Exception:
                        state.capabilities = None

            # Send notifications/initialized to complete handshake
            self._dispatch_message(config, {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            })

            state.status = "connected"
            state.initialized = True
            return state

        except Exception as exc:
            state.status = "failed"
            state.error = str(exc)
            raise

    def list_prompts(self, name: str, settings: SettingsLoadResult) -> list[dict[str, Any]]:
        """List available prompts from an MCP server.

        Sends prompts/list and returns the prompts array from the response.
        """
        response = self.send_message(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "prompts/list",
                "params": {},
            },
            settings,
        )
        error_payload = extract_error_payload(response)
        if error_payload is not None:
            raise RuntimeError(f"MCP prompts/list failed: {_error_message(error_payload)}")
        payload = extract_result_payload(response)
        if not isinstance(payload, dict):
            return []
        prompts = payload.get("prompts")
        if not isinstance(prompts, list):
            return []
        return prompts

    def get_prompt(
        self, name: str, prompt_name: str, arguments: dict[str, Any] | None, settings: SettingsLoadResult
    ) -> dict[str, Any]:
        """Get a prompt from an MCP server by name.

        Sends prompts/get and returns the result containing messages.
        """
        params: dict[str, Any] = {"name": prompt_name}
        if arguments:
            params["arguments"] = arguments

        response = self.send_message(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "prompts/get",
                "params": params,
            },
            settings,
        )
        error_payload = extract_error_payload(response)
        if error_payload is not None:
            raise RuntimeError(f"MCP prompts/get failed: {_error_message(error_payload)}")
        payload = extract_result_payload(response)
        if not isinstance(payload, dict):
            return {}
        return payload

    def list_resource_templates(self, name: str, settings: SettingsLoadResult) -> list[dict[str, Any]]:
        """List available resource templates from an MCP server.

        Sends resources/templates/list and returns the templates array.
        """
        response = self.send_message(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "resources/templates/list",
                "params": {},
            },
            settings,
        )
        error_payload = extract_error_payload(response)
        if error_payload is not None:
            raise RuntimeError(f"MCP resources/templates/list failed: {_error_message(error_payload)}")
        payload = extract_result_payload(response)
        if not isinstance(payload, dict):
            return []
        templates = payload.get("resourceTemplates")
        if not isinstance(templates, list):
            return []
        return templates

    def _configured_servers(
        self, settings: SettingsLoadResult
    ) -> dict[str, tuple[McpServerConfigForProcessTransport, str]]:
        configured = self._build_settings_servers(settings)
        configured.update({name: (config, "local") for name, config in self.runtime_servers.items()})
        return configured

    def _build_settings_servers(
        self, settings: SettingsLoadResult
    ) -> dict[str, tuple[McpServerConfigForProcessTransport, str]]:
        configured: dict[str, tuple[McpServerConfigForProcessTransport, str]] = {}
        for source in settings.sources:
            raw_settings = source.get("settings")
            if not isinstance(raw_settings, dict):
                continue
            raw_mcp = raw_settings.get("mcp")
            if not isinstance(raw_mcp, dict):
                continue
            scope = _SCOPE_BY_SETTINGS_SOURCE.get(str(source.get("source")), "local")
            for name, config in raw_mcp.items():
                if not isinstance(config, dict):
                    continue
                try:
                    configured[name] = (_MCP_SERVER_CONFIG_ADAPTER.validate_python(config), scope)
                except Exception:
                    continue
        return configured

    def build_statuses(self, settings: SettingsLoadResult) -> list[McpServerStatusModel]:
        configured = self._configured_servers(settings)
        self.disabled_servers.intersection_update(configured)
        return [self._build_status(name, config, scope) for name, (config, scope) in sorted(configured.items())]

    def _build_status(
        self,
        name: str,
        config: McpServerConfigForProcessTransport,
        scope: str,
    ) -> McpServerStatusModel:
        state = self._ensure_live_state(name)
        status = "disabled" if name in self.disabled_servers else state.status
        return McpServerStatusModel(
            name=name,
            status=status,
            serverInfo=state.server_info,
            error=state.error,
            config=config,
            scope=scope,
            tools=state.tools or None,
            capabilities=state.capabilities,
        )

    def _require_server(
        self, name: str, settings: SettingsLoadResult
    ) -> tuple[McpServerConfigForProcessTransport, str]:
        configured = self._configured_servers(settings)
        if name not in configured:
            raise KeyError(f"Server not found: {name}")
        return configured[name]

    def _ensure_live_state(self, name: str) -> McpLiveServerState:
        state = self.live_states.get(name)
        if state is None:
            state = McpLiveServerState()
            self.live_states[name] = state
        return state

    def _next_request_id(self) -> int:
        return next(self._request_ids)

    def _record_transport_failure(self, name: str, error: str) -> None:
        state = self._ensure_live_state(name)
        state.status = "failed"
        state.error = error
        state.consecutive_failures += 1
        state.last_activity = time.time()

    def _record_success(self, name: str) -> None:
        """Record a successful operation and reset failure counters."""
        state = self._ensure_live_state(name)
        state.status = "connected"
        state.error = None
        state.consecutive_failures = 0
        state.last_activity = time.time()

    def is_session_expired(self, name: str, max_idle_seconds: float = 3600.0) -> bool:
        """Check if a server session has expired due to inactivity.

        Args:
            name: Server name
            max_idle_seconds: Maximum seconds without activity before considering
                the session expired. Default 1 hour.

        Returns:
            True if the session is considered expired due to inactivity.
        """
        state = self._ensure_live_state(name)
        if not state.initialized:
            return False
        idle_time = time.time() - state.last_activity
        return idle_time > max_idle_seconds

    def reconnect_if_expired(self, name: str, settings: SettingsLoadResult, max_idle_seconds: float = 3600.0) -> bool:
        """Reconnect a server if its session has expired due to inactivity.

        Args:
            name: Server name
            settings: Settings load result
            max_idle_seconds: Maximum seconds without activity before reconnecting

        Returns:
            True if reconnection was triggered, False if session is still active
            or server is disabled/not found.
        """
        if not self.is_session_expired(name, max_idle_seconds):
            return False
        if name in self.disabled_servers:
            return False
        try:
            self.reconnect_server(name, settings)
            self.initialize(name, settings)
            self._record_success(name)
            return True
        except Exception:
            return False

    def _record_message_result(self, name: str, response: Any) -> None:
        state = self._ensure_live_state(name)
        error_payload = extract_error_payload(response)
        if error_payload is not None:
            state.status = _status_for_error(error_payload)
            state.error = _error_message(error_payload)
            return
        # Success - update last activity
        self._record_success(name)
        payload = extract_result_payload(response)
        if not isinstance(payload, dict):
            return
        server_info = payload.get("serverInfo")
        if isinstance(server_info, dict):
            try:
                state.server_info = McpServerInfo.model_validate(server_info)
            except Exception:
                state.server_info = None
        capabilities = payload.get("capabilities")
        if isinstance(capabilities, dict):
            try:
                state.capabilities = McpCapabilities.model_validate(capabilities)
            except Exception:
                state.capabilities = None
        tools = payload.get("tools")
        if isinstance(tools, list):
            normalized_tools: list[McpToolInfo] = []
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                try:
                    normalized_tools.append(McpToolInfo.model_validate(tool))
                except Exception:
                    continue
            state.tools = normalized_tools



def _send_http_message(config: McpHttpServerConfig, message: Any) -> Any:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if config.headers:
        headers.update(config.headers)
    request = urllib_request.Request(
        config.url,
        data=json.dumps(message).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if body.strip():
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                pass
        return {"error": {"code": exc.code, "message": body or str(exc.reason)}}
    except urllib_error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc
    if not payload.strip():
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid MCP JSON response") from exc



def _status_for_error(error_payload: dict[str, Any]) -> str:
    code = error_payload.get("code")
    message = str(error_payload.get("message") or "")
    normalized = message.lower()
    if code == 401 or "unauthorized" in normalized or "auth" in normalized:
        return "needs-auth"
    return "failed"



def _error_message(error_payload: dict[str, Any]) -> str:
    message = error_payload.get("message")
    if isinstance(message, str) and message:
        return message
    code = error_payload.get("code")
    return f"MCP request failed ({code})" if code is not None else "MCP request failed"
