from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import sys

from py_claw.mcp.runtime import McpRuntime
from py_claw.schemas.common import McpClaudeAIProxyServerConfig, McpHttpServerConfig, McpSSEServerConfig, McpSdkServerConfig, McpStdioServerConfig
from py_claw.settings.loader import SettingsLoadResult
from py_claw.settings.merge import merge_settings


def _settings_with_sources(*entries: tuple[str, dict[str, object]]) -> SettingsLoadResult:
    effective: dict[str, object] = {}
    sources: list[dict[str, object]] = []
    for source_name, settings in entries:
        sources.append({"source": source_name, "settings": settings})
        effective = merge_settings(effective, settings)
    return SettingsLoadResult(effective=effective, sources=sources)


@contextmanager
def _serve_http(handler_type: type[BaseHTTPRequestHandler]):
    server = HTTPServer(("127.0.0.1", 0), handler_type)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


class _McpSuccessHandler(BaseHTTPRequestHandler):
    response_payload = {"jsonrpc": "2.0", "result": {"ok": True}}

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
        self.server.last_request = json.loads(body)
        payload = json.dumps(self.response_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


class _McpUnauthorizedHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.dumps({"error": {"code": 401, "message": "Unauthorized"}}).encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


class _McpResourceHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
        request = json.loads(body)
        self.server.last_request = request
        if request.get("method") == "resources/list":
            payload = {
                "jsonrpc": "2.0",
                "result": {
                    "resources": [
                        {
                            "uri": "file://docs/readme.md",
                            "name": "README",
                            "description": "Project readme",
                            "mimeType": "text/markdown",
                        }
                    ]
                },
            }
        else:
            payload = {
                "jsonrpc": "2.0",
                "result": {
                    "contents": [
                        {
                            "uri": request.get("params", {}).get("uri", ""),
                            "mimeType": "text/plain",
                            "text": "hello from mcp",
                        }
                    ]
                },
            }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_set_servers_tracks_added_and_removed_names() -> None:
    runtime = McpRuntime()

    first = runtime.set_servers({"local": McpStdioServerConfig(command="python", args=["-m", "server"])})
    second = runtime.set_servers({"remote": McpHttpServerConfig(type="http", url="https://example.com/mcp")})

    assert first == {"added": ["local"], "removed": [], "errors": {}}
    assert second == {"added": ["remote"], "removed": ["local"], "errors": {}}
    assert sorted(runtime.runtime_servers) == ["remote"]



def test_build_statuses_uses_latest_settings_source_scope() -> None:
    runtime = McpRuntime()
    settings = _settings_with_sources(
        ("userSettings", {"mcp": {"shared": {"type": "http", "url": "https://user.example.com/mcp"}}}),
        ("projectSettings", {"mcp": {"shared": {"type": "http", "url": "https://project.example.com/mcp"}}}),
    )

    statuses = runtime.build_statuses(settings)

    assert [status.name for status in statuses] == ["shared"]
    assert statuses[0].status == "pending"
    assert statuses[0].scope == "project"
    assert statuses[0].config is not None
    assert statuses[0].config.url == "https://project.example.com/mcp"



def test_build_statuses_runtime_servers_override_settings() -> None:
    runtime = McpRuntime(
        runtime_servers={"shared": McpHttpServerConfig(type="http", url="https://runtime.example.com/mcp")}
    )
    settings = _settings_with_sources(
        ("userSettings", {"mcp": {"user": {"command": "python", "args": ["-m", "user_server"]}}}),
        ("projectSettings", {"mcp": {"shared": {"type": "http", "url": "https://project.example.com/mcp"}}}),
    )

    statuses = runtime.build_statuses(settings)
    by_name = {status.name: status for status in statuses}

    assert [status.name for status in statuses] == ["shared", "user"]
    assert by_name["shared"].scope == "local"
    assert by_name["shared"].config is not None
    assert by_name["shared"].config.url == "https://runtime.example.com/mcp"
    assert by_name["user"].scope == "user"
    assert all(status.status == "pending" for status in statuses)



def test_http_transport_send_message_updates_live_state() -> None:
    class _HttpMcpHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            request = json.loads(body)
            self.server.last_request = request
            payload = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "serverInfo": {"name": "demo", "version": "1.0"},
                        "capabilities": {"experimental": {"http": True}},
                        "tools": [{"name": "demo-tool", "description": "Demo tool"}],
                        "echo": request,
                    },
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    with _serve_http(_HttpMcpHandler) as base_url:
        runtime = McpRuntime(runtime_servers={"remote": McpHttpServerConfig(type="http", url=f"{base_url}/mcp")})
        settings = _settings_with_sources(
            ("localSettings", {"mcp": {"remote": {"type": "http", "url": f"{base_url}/mcp"}}})
        )

        response = runtime.send_message("remote", {"jsonrpc": "2.0", "id": 1, "method": "ping"}, settings)
        statuses = runtime.build_statuses(settings)

    assert response["result"]["echo"] == {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert statuses[0].status == "connected"
    assert statuses[0].serverInfo is not None
    assert statuses[0].serverInfo.name == "demo"
    assert statuses[0].serverInfo.version == "1.0"
    assert statuses[0].capabilities is not None
    assert statuses[0].capabilities.experimental == {"http": True}
    assert [tool.name for tool in statuses[0].tools or []] == ["demo-tool"]



def test_http_transport_unauthorized_response_marks_needs_auth() -> None:
    with _serve_http(_McpUnauthorizedHandler) as base_url:
        runtime = McpRuntime(runtime_servers={"remote": McpHttpServerConfig(type="http", url=f"{base_url}/mcp")})
        settings = _settings_with_sources(
            ("localSettings", {"mcp": {"remote": {"type": "http", "url": f"{base_url}/mcp"}}})
        )

        response = runtime.send_message("remote", {"jsonrpc": "2.0", "id": 1, "method": "ping"}, settings)
        statuses = runtime.build_statuses(settings)

    assert response == {"error": {"code": 401, "message": "Unauthorized"}}
    assert statuses[0].status == "needs-auth"
    assert statuses[0].error == "Unauthorized"


def test_sse_transport_send_message() -> None:
    class _SseMcpHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            request = json.loads(body)
            self.server.last_request = request
            payload = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "serverInfo": {"name": "sse-server", "version": "1.0"},
                        "capabilities": {},
                        "tools": [],
                        "echo": request,
                    },
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    with _serve_http(_SseMcpHandler) as base_url:
        runtime = McpRuntime(
            runtime_servers={"sse-remote": McpSSEServerConfig(type="sse", url=f"{base_url}/mcp")}
        )
        settings = _settings_with_sources(
            ("localSettings", {"mcp": {"sse-remote": {"type": "sse", "url": f"{base_url}/mcp"}}})
        )

        response = runtime.send_message(
            "sse-remote",
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            settings,
        )

    assert response["result"]["echo"] == {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert response["result"]["serverInfo"]["name"] == "sse-server"


def test_initialize_handshake_updates_live_state() -> None:
    class _InitMcpHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            request = json.loads(body)
            self.server.last_request = request
            payload = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "init-test", "version": "2.0"},
                        "capabilities": {"tools": {}, "resources": {}},
                    },
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    with _serve_http(_InitMcpHandler) as base_url:
        runtime = McpRuntime(
            runtime_servers={"init-server": McpHttpServerConfig(type="http", url=f"{base_url}/mcp")}
        )
        settings = _settings_with_sources(
            ("localSettings", {"mcp": {"init-server": {"type": "http", "url": f"{base_url}/mcp"}}})
        )

        state = runtime.initialize("init-server", settings)

    assert state.status == "connected"
    assert state.initialized is True
    assert state.server_info is not None
    assert state.server_info.name == "init-test"
    assert state.server_info.version == "2.0"


def test_list_prompts_returns_prompts_array() -> None:
    class _PromptsMcpHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            request = json.loads(body)
            self.server.last_request = request
            if request.get("method") == "prompts/list":
                payload = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {
                            "prompts": [
                                {"name": "greet", "description": "A greeting prompt"},
                                {"name": "farewell", "description": "A goodbye prompt"},
                            ]
                        },
                    }
                ).encode("utf-8")
            else:
                payload = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {
                            "messages": [{"role": "user", "content": {"type": "text", "text": "Hello!"}}]
                        },
                    }
                ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    with _serve_http(_PromptsMcpHandler) as base_url:
        runtime = McpRuntime(
            runtime_servers={"prompt-server": McpHttpServerConfig(type="http", url=f"{base_url}/mcp")}
        )
        settings = _settings_with_sources(
            ("localSettings", {"mcp": {"prompt-server": {"type": "http", "url": f"{base_url}/mcp"}}})
        )

        prompts = runtime.list_prompts("prompt-server", settings)

    assert len(prompts) == 2
    assert prompts[0]["name"] == "greet"
    assert prompts[1]["name"] == "farewell"


def test_get_prompt_with_arguments() -> None:
    class _GetPromptMcpHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            request = json.loads(body)
            self.server.last_request = request
            payload = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "messages": [
                            {"role": "user", "content": {"type": "text", "text": "Hello, World!"}}
                        ]
                    },
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    with _serve_http(_GetPromptMcpHandler) as base_url:
        runtime = McpRuntime(
            runtime_servers={"prompt-server": McpHttpServerConfig(type="http", url=f"{base_url}/mcp")}
        )
        settings = _settings_with_sources(
            ("localSettings", {"mcp": {"prompt-server": {"type": "http", "url": f"{base_url}/mcp"}}})
        )

        result = runtime.get_prompt("prompt-server", "greet", {"name": "World"}, settings)

    assert "messages" in result
    assert len(result["messages"]) == 1


def test_sdk_transport_uses_message_handler_for_requests_and_notifications() -> None:
    runtime = McpRuntime(
        runtime_servers={"sdk-server": McpSdkServerConfig(type="sdk", name="sdk-server")},
        sdk_message_handler=lambda server_name, message: {"server": server_name, "message": message},
    )
    settings = _settings_with_sources(("localSettings", {"mcp": {"sdk-server": {"type": "sdk", "name": "sdk-server"}}}))

    response = runtime.send_message("sdk-server", {"jsonrpc": "2.0", "id": 1, "method": "ping"}, settings)
    runtime.send_notification("sdk-server", "notifications/initialized", {}, settings)

    assert response["server"] == "sdk-server"
    assert response["message"] == {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert runtime.build_statuses(settings)[0].status == "connected"


def test_claudeai_proxy_transport_uses_message_handler_for_requests_and_notifications() -> None:
    runtime = McpRuntime(
        runtime_servers={
            "proxy-server": McpClaudeAIProxyServerConfig(type="claudeai-proxy", url="https://example.com", id="proxy-id")
        },
        sdk_message_handler=lambda server_name, message: {"server": server_name, "message": message},
    )
    settings = _settings_with_sources(
        ("localSettings", {"mcp": {"proxy-server": {"type": "claudeai-proxy", "url": "https://example.com", "id": "proxy-id"}}})
    )

    response = runtime.send_message("proxy-server", {"jsonrpc": "2.0", "id": 1, "method": "ping"}, settings)
    runtime.send_notification("proxy-server", "notifications/initialized", {}, settings)

    assert response["server"] == "proxy-id"
    assert response["message"] == {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert runtime.build_statuses(settings)[0].config is not None
    assert runtime.build_statuses(settings)[0].config.type == "claudeai-proxy"
