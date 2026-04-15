"""Child process entry point for forked agent execution.

This module is invoked via: python -m py_claw.fork.child_main
It runs in an isolated subprocess and communicates with the parent
via NDJSON on stdio.

Supports persistent multi-turn mode with optional per-agent MCP servers.

Note: This module intentionally avoids top-level imports from py_claw.query
to prevent circular import issues when spawned as a subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from typing import Any


# ─── MCP Server Process ───────────────────────────────────────────────────────


class _McpServerProcess:
    """Manages a single stdio MCP server subprocess.

    Communicates via JSON-RPC 2.0 over stdin/stdout.
    Thread-safe for concurrent requests.
    """

    def __init__(self, name: str, command: str, args: list[str] | None = None, env: dict[str, str] | None = None) -> None:
        self.name = name
        full_env = dict(os.environ)
        if env:
            full_env.update(env)
        self._process = subprocess.Popen(
            [command, *(args or [])],
            env=full_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._lock = threading.Lock()
        self._request_id = 0
        self._stderr = sys.stderr

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Send a tools/call JSON-RPC request and return the result."""
        with self._lock:
            self._request_id += 1
            req_id = self._request_id
            request = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }
            line = json.dumps(request) + "\n"
            self._process.stdin.write(line)
            self._process.stdin.flush()

            # Read response
            while True:
                resp_line = self._process.stdout.readline()
                if not resp_line:
                    raise RuntimeError(f"MCP server '{self.name}' stdout closed")
                try:
                    resp = json.loads(resp_line)
                    if resp.get("id") == req_id:
                        if "error" in resp:
                            raise RuntimeError(f"MCP error: {resp['error']}")
                        return resp.get("result")
                except json.JSONDecodeError:
                    # Log and continue looking for our response
                    self._stderr.write(f"[MCP {self.name}] Invalid JSON: {resp_line[:100]}\n")
                    self._stderr.flush()

    def list_tools(self) -> list[dict[str, Any]]:
        """Send a tools/list JSON-RPC request and return the tool list."""
        with self._lock:
            self._request_id += 1
            req_id = self._request_id
            request = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/list",
                "params": {},
            }
            line = json.dumps(request) + "\n"
            self._process.stdin.write(line)
            self._process.stdin.flush()

            while True:
                resp_line = self._process.stdout.readline()
                if not resp_line:
                    raise RuntimeError(f"MCP server '{self.name}' stdout closed")
                try:
                    resp = json.loads(resp_line)
                    if resp.get("id") == req_id:
                        if "error" in resp:
                            raise RuntimeError(f"MCP error listing tools: {resp['error']}")
                        return resp.get("result", {})
                except json.JSONDecodeError:
                    continue

    def close(self) -> None:
        """Terminate the MCP server subprocess."""
        try:
            self._process.stdin.close()
            self._process.wait(timeout=3)
        except Exception:
            try:
                self._process.kill()
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._process.poll() is None


# ─── MCP Server Registry ───────────────────────────────────────────────────────


class _McpRegistry:
    """Manages MCP server processes for the child subprocess."""

    def __init__(self) -> None:
        self._servers: dict[str, _McpServerProcess] = {}
        self._tools: dict[str, dict[str, Any]] = {}  # server_name → tool info

    def add_server(self, name: str, config: dict[str, Any]) -> None:
        """Start and register an MCP server from its config.

        Supports stdio servers with 'command', 'args', 'env' fields.
        """
        if name in self._servers:
            return  # Already started

        server_type = config.get("type", "stdio")
        if server_type != "stdio":
            # For now, only stdio servers are supported in the subprocess
            sys.stderr.write(f"[MCP] Skipping non-stdio server '{name}' (type={server_type})\n")
            sys.stderr.flush()
            return

        command = config.get("command")
        if not command:
            sys.stderr.write(f"[MCP] Server '{name}' has no 'command' field\n")
            sys.stderr.flush()
            return

        args = config.get("args")
        env = config.get("env")
        try:
            server = _McpServerProcess(name=name, command=command, args=args, env=env)
            # Initialize the server (send initialize notification)
            self._send_init_notification(server)
            self._servers[name] = server

            # List available tools
            try:
                tools_result = server.list_tools()
                tools = tools_result.get("tools", []) if isinstance(tools_result, dict) else []
                for tool in tools:
                    self._tools[f"{name}/{tool.get('name', '')}"] = tool
            except Exception as exc:
                sys.stderr.write(f"[MCP] Failed to list tools for server '{name}': {exc}\n")
                sys.stderr.flush()

            sys.stderr.write(f"[MCP] Started server '{name}' (command={command})\n")
            sys.stderr.flush()
        except Exception as exc:
            sys.stderr.write(f"[MCP] Failed to start server '{name}': {exc}\n")
            sys.stderr.flush()

    def _send_init_notification(self, server: _McpServerProcess) -> None:
        """Send JSON-RPC initialize notification to the server."""
        init_req = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {
                    "name": "py-claw-fork",
                    "version": "0.1.0",
                },
            },
        }
        with server._lock:
            line = json.dumps(init_req) + "\n"
            server._process.stdin.write(line)
            server._process.stdin.flush()
            # Read the response (id=0)
            resp_line = server._process.stdout.readline()
            if resp_line:
                try:
                    json.loads(resp_line)
                except json.JSONDecodeError:
                    pass
            # Send notifications/initialized
            notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            line2 = json.dumps(notif) + "\n"
            server._process.stdin.write(line2)
            server._process.stdin.flush()

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on a named MCP server."""
        server = self._servers.get(server_name)
        if server is None:
            raise RuntimeError(f"Unknown MCP server: '{server_name}'")
        return server.call_tool(tool_name, arguments)

    def list_all_tools(self) -> list[dict[str, Any]]:
        """Return all tools from all registered servers."""
        return list(self._tools.values())

    def close_all(self) -> None:
        """Stop all MCP server subprocesses."""
        for name, server in list(self._servers.items()):
            try:
                server.close()
            except Exception:
                pass
        self._servers.clear()
        self._tools.clear()


# ─── Placeholder Result Builder ────────────────────────────────────────────────


def _make_placeholder_result(
    query_text: str,
    system_prompt: str,
    worktree_notice: str | None = None,
) -> dict[str, Any]:
    """Build a minimal backend result dict without needing py_claw imports."""
    full_prompt = query_text
    if worktree_notice:
        full_prompt = f"{worktree_notice}\n\n{full_prompt}"
    return {
        "assistant_text": (
            f"[Placeholder Agent] Received query: {full_prompt[:200]}. "
            f"Set --sdk-url or configure sdk_url in settings to enable real model inference."
        ),
        "stop_reason": "end_turn",
        "usage": {"backendType": "placeholder"},
        "model_usage": {},
        "tool_calls": [],
    }


# ─── Main ──────────────────────────────────────────────────────────────────────


def _main() -> int:
    """Main loop for child process — supports persistent multi-turn mode with MCP servers."""
    parser = _ChildParser()
    mcp_registry: _McpRegistry | None = None

    # Initialize - read init message
    init_msg = parser.read_message()
    if init_msg is None or init_msg.get("type") != "init":
        _send_error("Expected 'init' message first")
        return 1

    session_id = init_msg.get("session_id", "")
    system_prompt = init_msg.get("system_prompt", "")
    model = init_msg.get("model")
    allowed_tools = init_msg.get("allowed_tools")
    cwd = init_msg.get("cwd", ".")
    mcp_configs = init_msg.get("mcp_servers") or []
    isolation_config = init_msg.get("isolation") or {}

    # Parse isolation context
    worktree_notice: str | None = None
    parent_cwd = isolation_config.get("parent_cwd")
    worktree_cwd = isolation_config.get("worktree_cwd")
    if parent_cwd and worktree_cwd:
        worktree_notice = _build_worktree_notice(parent_cwd, worktree_cwd)

    # Initialize MCP servers
    if mcp_configs:
        mcp_registry = _McpRegistry()
        for mcp_config in mcp_configs:
            if isinstance(mcp_config, dict):
                server_name = mcp_config.get("name") or mcp_config.get("command", "unnamed")
                mcp_registry.add_server(server_name, mcp_config)

    # Persistent mode: subprocess stays alive across turns, accumulates history
    exchanges: list[dict[str, str]] = []
    turn_count = 0

    while True:
        msg = parser.read_message()
        if msg is None:
            break

        msg_type = msg.get("type")

        if msg_type == "turn":
            query_text = msg.get("query_text", "")
            incoming_turn_count = msg.get("turn_count", turn_count)

            result = _handle_turn_persistent(
                query_text=query_text,
                system_prompt=system_prompt,
                exchanges=exchanges,
                worktree_notice=worktree_notice,
            )

            # Accumulate in history
            exchanges.append({
                "user_message": query_text,
                "assistant_text": result.get("assistant_text", ""),
            })

            # Echo turn_count back so parent can route result
            result["turn_count"] = incoming_turn_count
            _send_result(result)
            turn_count += 1

        elif msg_type == "mcp_call":
            # Handle MCP tool call from parent
            server_name = msg.get("server_name", "")
            tool_name = msg.get("tool_name", "")
            arguments = msg.get("arguments", {})
            call_id = msg.get("call_id", "")

            if mcp_registry is None:
                _send_mcp_result(call_id, None, f"No MCP registry initialized")
            else:
                try:
                    result = mcp_registry.call_tool(server_name, tool_name, arguments)
                    _send_mcp_result(call_id, result, None)
                except Exception as exc:
                    _send_mcp_result(call_id, None, str(exc))

        elif msg_type == "history":
            # Parent syncs history after reconnection
            new_exchanges = msg.get("exchanges", [])
            if new_exchanges:
                exchanges = new_exchanges

        elif msg_type == "stop":
            break
        else:
            _send_error(f"Unknown message type: {msg_type}")

    # Cleanup MCP servers
    if mcp_registry is not None:
        mcp_registry.close_all()

    return 0


def _handle_turn_persistent(
    query_text: str,
    system_prompt: str,
    exchanges: list[dict[str, str]],
    worktree_notice: str | None = None,
) -> dict[str, Any]:
    """Handle a turn with conversation history context."""
    history_context = _build_history_context(exchanges)
    enriched_query = (
        (history_context + "\n\n" if history_context else "")
        + f"User: {query_text}"
    )

    try:
        result = _make_placeholder_result(enriched_query, system_prompt, worktree_notice)
        return result
    except Exception as exc:
        return {
            "assistant_text": f"Error: {str(exc)}",
            "stop_reason": "end_turn",
            "usage": {},
            "model_usage": {},
            "tool_calls": [],
        }


def _build_history_context(exchanges: list[dict[str, str]]) -> str:
    """Build a conversation context string from accumulated exchanges."""
    if not exchanges:
        return ""
    parts = ["=== CONVERSATION HISTORY ==="]
    for i, ex in enumerate(exchanges, 1):
        parts.append(f"[Turn {i}] User: {ex.get('user_message', '')}")
        parts.append(f"[Turn {i}] Assistant: {ex.get('assistant_text', '')}")
    parts.append("=== END HISTORY ===")
    return "\n".join(parts)


def _build_worktree_notice(parent_cwd: str, worktree_cwd: str) -> str:
    """Build worktree notice for forked agents running in isolation."""
    return f"""You've inherited the conversation context above from a parent agent working in {parent_cwd}. You are operating in an isolated git worktree at {worktree_cwd} — same repository, same relative file structure, separate working copy.

IMPORTANT:
1. Paths in the inherited context refer to the parent's working directory; translate them to this worktree root.
2. Re-read files before editing if the parent may have modified them since they appear in the context.
3. Your changes stay in this worktree and will not affect the parent's files.
"""


def _send_output(delta: str) -> None:
    """Send streaming output message."""
    msg = {"type": "output", "delta": delta}
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _send_result(result: dict[str, Any]) -> None:
    """Send result message."""
    msg = {
        "type": "result",
        "assistant_text": result.get("assistant_text", ""),
        "stop_reason": result.get("stop_reason", "end_turn"),
        "usage": result.get("usage", {}),
        "model_usage": result.get("model_usage", {}),
        "tool_calls": result.get("tool_calls", []),
        "turn_count": result.get("turn_count"),
    }
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _send_mcp_result(call_id: str, result: Any, error: str | None) -> None:
    """Send MCP tool result back to parent."""
    msg = {"type": "mcp_result", "call_id": call_id, "result": result}
    if error:
        msg["error"] = error
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _send_error(message: str) -> None:
    """Send error message."""
    msg = {"type": "error", "message": message}
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


class _ChildParser:
    """Reads newline-delimited JSON messages from stdin."""

    __slots__ = ("_buffer",)

    def __init__(self) -> None:
        self._buffer: str = ""

    def read_message(self) -> dict[str, Any] | None:
        """Read a single JSON message from stdin."""
        while "\n" not in self._buffer:
            chunk = sys.stdin.readline()
            if not chunk:
                return None
            self._buffer += chunk

        newline_idx = self._buffer.index("\n")
        line = self._buffer[:newline_idx]
        self._buffer = self._buffer[newline_idx + 1:]

        if not line.strip():
            return self.read_message()

        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None


if __name__ == "__main__":
    raise SystemExit(_main())
