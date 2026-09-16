"""Model executor for speculation mode in child subprocess.

This module runs inside the forked child process (child_main.py) during speculation.
It executes a real model turn with tool execution, applying speculation
constraints to each tool call.

Mirrors the TypeScript runForkedAgent() with canUseTool callback.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# Avoid importing py_claw top-level to prevent circular imports in subprocess
# Only import the SDK client minimally


# ─── Constants ────────────────────────────────────────────────────────────────


WRITE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})
SAFE_READ_ONLY_TOOLS = frozenset({
    "Read", "Glob", "Grep", "ToolSearch", "LSP", "TaskGet", "TaskList",
})

READ_ONLY_COMMANDS = frozenset({
    "cat", "head", "tail", "less", "more", "sort", "uniq", "wc",
    "cut", "paste", "column", "tr", "file", "stat", "diff",
    "awk", "strings", "hexdump", "od", "base64", "nl",
    "grep", "rg", "jq", "ls", "pwd", "whoami", "id", "date",
    "echo", "printf", "true", "false", "which", "type",
    "command", "builtin", "cal", "uptime", "basename", "dirname",
    "realpath", "readlink", "nproc", "free", "df", "du",
})

MAX_SPECULATION_TURNS = 20
MAX_TOOL_CALLS = 100
# Max tool-call iterations within a single persistent (non-speculation) turn.
MAX_AGENT_TURNS = 20
DEFAULT_MODEL = "claude-sonnet-4-20250514"
# Fallback model for the OpenAI-compatible path (matches ApiQueryBackend's
# default in py_claw.query.backend); normally the parent config supplies one.
DEFAULT_OPENAI_MODEL = "gpt-5.4"

# Built-in tool definitions advertised to the model in the child subprocess.
# The child executes these locally (see _execute_tool); the set matches the
# tools the subprocess can actually run.
BUILTIN_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "Bash",
        "description": "Execute a bash command",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "Read",
        "description": "Read a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "Write",
        "description": "Write content to a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "Edit",
        "description": "Edit a file using a search/replace",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "Glob",
        "description": "Find files matching a glob pattern",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "Grep",
        "description": "Search for text in a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "max_results": {"type": "number"},
            },
            "required": ["pattern"],
        },
    },
]


def _builtin_tool_definitions(allowed_tools: list[str] | None = None) -> list[dict[str, Any]]:
    """Return built-in tool definitions, optionally filtered by allowed_tools."""
    if not allowed_tools:
        return list(BUILTIN_TOOL_DEFINITIONS)
    allowed = {str(t).strip() for t in allowed_tools if str(t).strip()}
    return [t for t in BUILTIN_TOOL_DEFINITIONS if t["name"] in allowed]


# ─── Tool Execution ──────────────────────────────────────────────────────────


def _check_tool_in_speculation(
    tool_name: str,
    arguments: dict,
    cwd: str,
    permission_mode: str,
    is_bypass_available: bool,
) -> tuple[bool, dict | None, dict | None]:
    """Check if a tool is allowed in speculation mode.

    Returns (allowed, updated_arguments, boundary_dict).
    """
    is_write_tool = tool_name in WRITE_TOOLS
    is_safe_read_only = tool_name in SAFE_READ_ONLY_TOOLS
    now_ms = int(time.time() * 1000)

    can_auto_accept_edits = (
        permission_mode in ("acceptEdits", "bypassPermissions")
        or (permission_mode == "plan" and is_bypass_available)
    )

    path_key = None
    file_path = None
    for key in ("notebook_path", "path", "file_path"):
        if key in arguments:
            path_key = key
            file_path = arguments[key]
            break

    if is_write_tool:
        if not can_auto_accept_edits:
            return False, None, {
                "type": "edit",
                "toolName": tool_name,
                "filePath": file_path or "",
                "completedAt": now_ms,
            }
        return True, None, None

    if is_safe_read_only:
        return True, None, None

    if tool_name == "Bash":
        command = arguments.get("command", "")
        check_result = _check_read_only_constraints(command, cwd)
        if check_result != "allow":
            return False, None, {
                "type": "bash",
                "command": command[:200],
                "completedAt": now_ms,
            }
        return True, None, None

    # Deny all other tools
    detail = str(
        arguments.get("url", arguments.get("path", ""))
    )[:200]
    return False, None, {
        "type": "denied_tool",
        "toolName": tool_name,
        "detail": detail,
        "completedAt": now_ms,
    }


def _check_read_only_constraints(command: str, cwd: str) -> str:
    """Check if bash command is read-only. Returns 'allow' or 'deny'."""
    if not command or not command.strip():
        return "allow"

    import re

    def extract_base(cmd: str) -> str:
        stripped = cmd.strip()
        for sep in (" | ", " && ", " || ", " > ", " >> ", " < "):
            if sep in stripped:
                stripped = stripped.split(sep)[0].strip()
        tokens = stripped.split()
        if not tokens:
            return ""
        return tokens[0].split("/")[-1]

    base_cmd = extract_base(command)
    if base_cmd in READ_ONLY_COMMANDS:
        return "allow"

    # Check compound commands
    parts = re.split(r"\|(?=(?:[^'\"]*'[^'\"]*')*[^'\"]*$)", command)
    for part in parts:
        part = part.strip()
        if " && " in part:
            sub_parts = part.split(" && ")
        elif " || " in part:
            sub_parts = part.split(" || ")
        else:
            sub_parts = [part]
        for sp in sub_parts:
            sp = sp.strip()
            base = extract_base(sp)
            if base not in READ_ONLY_COMMANDS and not (
                base == "git" and any(
                    g in sp for g in
                    ("status", "diff", "log", "show", "ls-files", "ls-tree",
                     "rev-parse", "describe", "branch", "tag", "stash")
                )
            ):
                return "deny"
    return "allow"


def _execute_tool(
    tool_name: str,
    arguments: dict,
    cwd: str,
) -> dict[str, Any]:
    """Execute a tool in the subprocess and return the result.

    For read-only tools, executes locally. For bash, uses subprocess.
    For write tools, executes in overlay path.
    """
    import subprocess
    import shutil

    if tool_name in SAFE_READ_ONLY_TOOLS:
        # Route to MCP server if available
        if "/" in tool_name:
            server_name, actual_tool = tool_name.split("/", 1)
            if server_name in sys.modules.get("_mcp_registry", {}):
                registry = sys.modules["_mcp_registry"]
                try:
                    result = registry.call_tool(server_name, actual_tool, arguments)
                    return {"content": [{"type": "text", "text": json.dumps(result)}]}
                except Exception as e:
                    return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}

        # Direct file read
        if tool_name == "Read":
            path = arguments.get("path", "")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                return {"content": [{"type": "text", "text": content}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Error reading {path}: {e}"}], "is_error": True}

        if tool_name == "Glob":
            import fnmatch
            pattern = arguments.get("pattern", "*")
            cwd_path = Path(cwd)
            matches = [str(p) for p in cwd_path.rglob(pattern)][:50]
            return {"content": [{"type": "text", "text": "\n".join(matches)}]}

        if tool_name == "Grep":
            import re
            pattern = arguments.get("pattern", "")
            path = arguments.get("path", cwd)
            max_results = arguments.get("max_results", 20)
            try:
                matches: list[str] = []
                with open(path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if re.search(pattern, line):
                            matches.append(f"{path}:{i+1}: {line.rstrip()}")
                            if len(matches) >= max_results:
                                break
                return {"content": [{"type": "text", "text": "\n".join(matches)}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}

    if tool_name == "Bash":
        command = arguments.get("command", "")
        timeout = arguments.get("timeout", 30)
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += "\n[stderr] " + result.stderr
            return {"content": [{"type": "text", "text": output}]}
        except subprocess.TimeoutExpired:
            return {"content": [{"type": "text", "text": f"Command timed out after {timeout}s"}], "is_error": True}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}

    if tool_name in WRITE_TOOLS:
        path = arguments.get("file_path") or arguments.get("path", "")
        content = arguments.get("content", "")
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"content": [{"type": "text", "text": f"Wrote {len(content)} chars to {path}"}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error writing {path}: {e}"}], "is_error": True}

    return {
        "content": [{"type": "text", "text": f"Tool {tool_name} not available in speculation mode"}],
        "is_error": True,
    }


# ─── Model Executor ───────────────────────────────────────────────────────────


def _get_api_key_and_url() -> tuple[str | None, str | None]:
    """Get API key and URL from environment."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("API_KEY")
    api_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    return api_key, api_url


def _build_speculation_system_prompt(overlay_path: str | None, cwd: str) -> str:
    """Build the system prompt for speculation mode."""
    parts = [
        "You are Claude Code, a CLI assistant. Execute the user's request using available tools.",
        "Important: You are in SPEULATION MODE. All file writes go to an isolated overlay directory.",
        "Read files from the overlay if they've been written there; otherwise read from the main directory.",
        f"Main working directory: {cwd}",
    ]
    if overlay_path:
        parts.append(f"Overlay directory: {overlay_path}")
    parts.append("When editing files, write to the overlay path provided.")
    parts.append("After completing your work, report what you did succinctly.")
    return "\n".join(parts)


async def _call_anthropic_api(
    messages: list[dict],
    system_prompt: str,
    model: str,
    api_key: str,
    api_url: str,
    max_tokens: int = 4096,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call Anthropic API with messages."""
    import urllib.request
    import urllib.error

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": messages,
        "tools": tools if tools is not None else BUILTIN_TOOL_DEFINITIONS,
    }

    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{api_url}/v1/messages",
        data=data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        return {"error": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"error": str(e)}


def _anthropic_tool_to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert one built-in/MCP tool definition (Anthropic shape) to OpenAI shape."""
    return {
        "type": "function",
        "function": {
            "name": tool.get("name") or "",
            "description": tool.get("description") or "",
            "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
        },
    }


def _openai_tool_definitions(
    allowed_tools: list[str] | None = None,
    mcp_registry: Any | None = None,
) -> list[dict[str, Any]]:
    """OpenAI-format tool list for the child's locally executable tools."""
    tools = [_anthropic_tool_to_openai_tool(t) for t in _builtin_tool_definitions(allowed_tools)]
    if mcp_registry is not None:
        try:
            tools = tools + mcp_registry.openai_tool_definitions()
        except Exception:
            pass  # MCP tool listing is best-effort
    return tools


def _tool_result_text(tool_result: dict[str, Any]) -> str:
    """Render a local tool result (Anthropic-style content blocks) as one string."""
    content = tool_result.get("content", [])
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        elif isinstance(block, str):
            parts.append(block)
        else:
            parts.append(json.dumps(block, ensure_ascii=False, default=str))
    return "\n".join(part for part in parts if part)


async def _call_openai_api(
    messages: list[dict[str, Any]],
    system_prompt: str,
    model: str,
    api_key: str,
    api_url: str,
    max_tokens: int = 4096,
    tools: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Call an OpenAI-compatible chat/completions endpoint (streaming SSE).

    Reuses the main-process OpenAI backend's wire format and parsing
    (py_claw.query.backend: _post_sse / _parse_sse_payload /
    _normalize_chat_completions_url / _openai_usage_to_keys) so the child
    speaks byte-compatible requests with the parent. The system prompt is
    sent as a role=system message — OpenAI-compatible servers such as vLLM
    drop a top-level "system" body field.

    Returns a dict with text / stop_reason / tool_calls / usage, or
    {"error": ...} on transport/API failure (mirroring _call_anthropic_api).
    """
    from py_claw.query.backend import (
        _normalize_chat_completions_url,
        _openai_usage_to_keys,
        _parse_sse_payload,
        _post_sse,
    )

    messages = list(messages)
    if system_prompt:
        messages = [{"role": "system", "content": system_prompt}] + messages

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if tools:
        body["tools"] = tools
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    try:
        sse_text = _post_sse(
            _normalize_chat_completions_url(api_url), body, headers, timeout_seconds
        )
    except Exception as exc:
        return {"error": str(exc)}

    parsed = _parse_sse_payload(sse_text)
    return {
        "text": parsed.text,
        "stop_reason": parsed.stop_reason,
        "tool_calls": [
            {"id": tc.tool_use_id, "name": tc.tool_name, "arguments": tc.arguments or {}}
            for tc in parsed.tool_calls
        ],
        "usage": _openai_usage_to_keys(parsed.usage),
    }


async def run_speculation_turn(
    query_text: str,
    cwd: str,
    overlay_path: str | None,
    model: str | None,
    permission_mode: str = "ask",
    is_bypass_available: bool = False,
    max_turns: int = MAX_SPECULATION_TURNS,
) -> dict[str, Any]:
    """Run a full speculation turn with tool execution.

    This is called from child_main.py when in speculation mode.
    Executes the model with tools, applying speculation constraints
    to each tool call.

    Args:
        query_text: User message
        cwd: Main working directory
        overlay_path: Overlay directory for copy-on-write
        model: Model to use
        permission_mode: Permission mode for edit tools
        is_bypass_available: Whether bypass is available in plan mode
        max_turns: Maximum tool-call turns

    Returns:
        Result dict with assistant_text, stop_reason, tool_calls, boundary
    """
    api_key, api_url = _get_api_key_and_url()

    if not api_key:
        # No API key - use placeholder
        return {
            "assistant_text": f"[Speculation] No API key available. Suggestion: {query_text[:100]}",
            "stop_reason": "end_turn",
            "usage": {"backendType": "no_api_key"},
            "tool_calls": [],
            "boundary": None,
        }

    system_prompt = _build_speculation_system_prompt(overlay_path, cwd)
    messages = [{"role": "user", "content": query_text}]
    tool_calls: list[dict] = []
    turn_count = 0
    boundary: dict | None = None

    while turn_count < max_turns:
        model_name = model or "claude-sonnet-4-20250514"

        result = await _call_anthropic_api(
            messages=messages,
            system_prompt=system_prompt,
            model=model_name,
            api_key=api_key,
            api_url=api_url,
        )

        if "error" in result:
            return {
                "assistant_text": f"API error: {result['error']}",
                "stop_reason": "end_turn",
                "tool_calls": tool_calls,
                "boundary": None,
            }

        # Extract response content
        content = result.get("content", [])
        stop_reason = result.get("stop_reason", "end_turn")

        # Build assistant text
        assistant_text_parts = []
        for block in content:
            if block.get("type") == "text":
                assistant_text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id"),
                    "tool_name": block.get("name"),
                    "arguments": block.get("input", {}),
                    "type": "tool_use",
                })

        assistant_text = "\n".join(assistant_text_parts)

        if stop_reason != "tool_use":
            # Done - no more tool calls
            return {
                "assistant_text": assistant_text,
                "stop_reason": stop_reason,
                "tool_calls": tool_calls,
                "boundary": None,
                "output_tokens": result.get("usage", {}).get("output_tokens", 0),
            }

        # Execute tool calls
        tool_results: list[dict] = []
        for tc in content:
            if tc.get("type") != "tool_use":
                continue
            tool_name = tc.get("name")
            arguments = tc.get("input", {})
            tool_use_id = tc.get("id")

            # Apply speculation constraint check
            allowed, updated_args, boundary_dict = _check_tool_in_speculation(
                tool_name, arguments, cwd, permission_mode, is_bypass_available
            )

            if not allowed and boundary_dict is not None:
                # Speculation hit a boundary
                boundary = boundary_dict
                return {
                    "assistant_text": assistant_text,
                    "stop_reason": "tool_use",
                    "tool_calls": tool_calls,
                    "boundary": boundary,
                }

            # Execute the tool
            tool_result = _execute_tool(tool_name, arguments, cwd)

            # Route MCP tool calls through registry
            if "/" in tool_name and not allowed:
                pass  # Already handled above

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": tool_result.get("content", []),
                "is_error": tool_result.get("is_error", False),
            })

        # Add assistant message and tool results to conversation
        messages.append({
            "role": "assistant",
            "content": content,
        })
        messages.append({
            "role": "user",
            "content": tool_results,
        })

        turn_count += 1

    # Hit max turns
    return {
        "assistant_text": assistant_text,
        "stop_reason": "tool_use",
        "tool_calls": tool_calls,
        "boundary": {"type": "max_turns", "completedAt": int(time.time() * 1000)},
    }


# ─── Persistent Agent Turn (real model execution) ─────────────────────────────


def _execute_agent_tool(
    tool_name: str,
    arguments: dict,
    cwd: str,
    mcp_registry: Any | None = None,
) -> dict[str, Any]:
    """Execute a tool for a persistent agent turn.

    MCP tools (named "server/tool") are routed through the child's MCP
    registry; everything else goes to the local built-in executor
    (_execute_tool), which returns an error result for unknown tools.
    """
    if mcp_registry is not None and "/" in tool_name:
        server_name, actual_tool = tool_name.split("/", 1)
        try:
            result = mcp_registry.call_tool(server_name, actual_tool, arguments)
            return {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
                ]
            }
        except Exception as e:
            return {
                "content": [
                    {"type": "text", "text": f"Error calling MCP tool {tool_name}: {e}"}
                ],
                "is_error": True,
            }
    return _execute_tool(tool_name, arguments, cwd)


def _agent_degraded_result(
    query_text: str,
    reason: str,
    backend_type: str,
    tool_calls: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a degraded (non-crashing) result when the model call is unavailable or fails."""
    return {
        "assistant_text": (
            f"[Fork agent] {reason}Received query: {query_text[:200]}"
        ),
        "stop_reason": "end_turn",
        "usage": {"backendType": backend_type},
        "model_usage": {},
        "tool_calls": tool_calls or [],
    }


def _exchanges_to_messages(exchanges: list[dict[str, str]] | None) -> list[dict[str, Any]]:
    """Convert accumulated user/assistant exchanges into API messages."""
    messages: list[dict[str, Any]] = []
    for exchange in exchanges or []:
        if not isinstance(exchange, dict):
            continue
        user_message = (exchange.get("user_message") or "").strip()
        assistant_text = (exchange.get("assistant_text") or "").strip()
        if user_message:
            messages.append({"role": "user", "content": user_message})
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})
    return messages


def _agent_model_usage(model_name: str, input_tokens: int, output_tokens: int) -> dict[str, Any]:
    return {
        model_name: {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "costUSD": 0.0,
        }
    }


async def _run_agent_turn_openai(
    query_text: str,
    system_prompt: str,
    exchanges: list[dict[str, str]] | None,
    cwd: str,
    model: str | None,
    allowed_tools: list[str] | None,
    mcp_registry: Any | None,
    max_turns: int,
    model_config: dict[str, Any],
) -> dict[str, Any]:
    """Persistent agent turn over an OpenAI-compatible chat/completions endpoint.

    Parallel to the Anthropic path in run_agent_turn with identical failure
    semantics: missing key/URL -> fast degraded result (child stays up and
    serves later turns), API error -> degraded result, tool calls executed
    locally and fed back as role=tool messages until the model stops or
    max_turns is hit.
    """
    api_key = str(model_config.get("api_key") or "").strip()
    api_url = str(model_config.get("api_url") or "").strip()
    if not api_key:
        return _agent_degraded_result(
            query_text,
            "No API key available - model call was not made. "
            "Configure the OpenAI-compatible backend (api.api_key / api.api_url "
            "in py-claw config) to enable real model execution. ",
            "no_api_key",
        )
    if not api_url:
        return _agent_degraded_result(
            query_text,
            "No OpenAI-compatible base URL available - model call was not made. "
            "Set api.api_url in py-claw config to enable real model execution. ",
            "no_api_key",
        )

    model_name = model or str(model_config.get("model") or "").strip() or DEFAULT_OPENAI_MODEL
    messages = _exchanges_to_messages(exchanges)
    messages.append({"role": "user", "content": query_text})

    tools = _openai_tool_definitions(allowed_tools, mcp_registry)
    temperature = model_config.get("temperature")
    top_p = model_config.get("top_p")
    timeout_seconds = float(model_config.get("timeout_seconds") or 120.0)

    tool_calls: list[dict] = []
    input_tokens = 0
    output_tokens = 0
    api_requests = 0
    assistant_text = ""

    try:
        for _ in range(max_turns):
            result = await _call_openai_api(
                messages=messages,
                system_prompt=system_prompt,
                model=model_name,
                api_key=api_key,
                api_url=api_url,
                tools=tools,
                temperature=temperature,
                top_p=top_p,
                timeout_seconds=timeout_seconds,
            )
            api_requests += 1

            if "error" in result:
                return _agent_degraded_result(
                    query_text,
                    f"Model API error: {result['error']}. ",
                    "model_error",
                    tool_calls,
                )

            usage = result.get("usage", {}) or {}
            input_tokens += int(usage.get("inputTokens", 0) or 0)
            output_tokens += int(usage.get("outputTokens", 0) or 0)

            openai_calls = result.get("tool_calls", []) or []
            assistant_text = result.get("text", "")

            if not openai_calls:
                return {
                    "assistant_text": assistant_text,
                    "stop_reason": result.get("stop_reason") or "end_turn",
                    "usage": {
                        "backendRequests": api_requests,
                        "backendType": "fork-model-openai",
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                    },
                    "model_usage": _agent_model_usage(model_name, input_tokens, output_tokens),
                    "tool_calls": tool_calls,
                }

            # Execute each tool call locally; feed results back as role=tool
            # messages (OpenAI requires the assistant message to carry the
            # matching tool_calls and the tool_call_id pairing).
            assistant_tool_calls = []
            for call in openai_calls:
                call_id = str(call.get("id") or f"call_{uuid.uuid4().hex}")
                call_name = call.get("name") or ""
                arguments = call.get("arguments") or {}
                tool_calls.append({
                    "id": call_id,
                    "tool_name": call_name,
                    "arguments": arguments,
                    "type": "tool_use",
                })
                assistant_tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": call_name,
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                })

            messages.append({
                "role": "assistant",
                "content": assistant_text or "",
                "tool_calls": assistant_tool_calls,
            })
            for call, call_id in zip(openai_calls, [tc["id"] for tc in assistant_tool_calls]):
                tool_result = _execute_agent_tool(
                    call.get("name") or "", call.get("arguments") or {}, cwd, mcp_registry
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": _tool_result_text(tool_result),
                })

        # Max tool-call iterations reached within this turn
        return {
            "assistant_text": (
                f"[Fork agent] Stopped after {max_turns} tool-call iterations (max turns). "
                + (assistant_text or "")
            ).strip(),
            "stop_reason": "max_turns",
            "usage": {
                "backendRequests": api_requests,
                "backendType": "fork-model-openai",
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
            },
            "model_usage": _agent_model_usage(model_name, input_tokens, output_tokens),
            "tool_calls": tool_calls,
        }
    except Exception as exc:
        import sys as _sys
        _sys.stderr.write(f"[Fork agent] Model turn error (openai): {exc}\n")
        _sys.stderr.flush()
        return _agent_degraded_result(
            query_text, f"Model turn failed: {exc}. ", "model_error", tool_calls
        )


async def run_agent_turn(
    query_text: str,
    system_prompt: str,
    exchanges: list[dict[str, str]] | None = None,
    cwd: str = ".",
    model: str | None = None,
    allowed_tools: list[str] | None = None,
    mcp_registry: Any | None = None,
    max_turns: int = MAX_AGENT_TURNS,
    model_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a real model turn for persistent (non-speculation) mode.

    Protocol dispatch: when the parent's init message carries a
    model_config with backend="openai", the turn runs over the
    OpenAI-compatible path (_run_agent_turn_openai, usage backendType
    "fork-model-openai"). Otherwise the existing Anthropic Messages path
    (usage backendType "fork-model") runs — using the parent config's
    Anthropic credentials when provided, else ANTHROPIC_API_KEY /
    ANTHROPIC_BASE_URL from the environment.

    Never raises: missing API key / transport / API failures produce a
    degraded result dict so the child process keeps serving subsequent turns.

    Returns a dict with: assistant_text, stop_reason, usage, model_usage,
    tool_calls.
    """
    model_config = model_config or {}
    backend = str(model_config.get("backend") or "").lower()
    if backend == "openai":
        return await _run_agent_turn_openai(
            query_text=query_text,
            system_prompt=system_prompt,
            exchanges=exchanges,
            cwd=cwd,
            model=model,
            allowed_tools=allowed_tools,
            mcp_registry=mcp_registry,
            max_turns=max_turns,
            model_config=model_config,
        )

    api_key, api_url = _get_api_key_and_url()
    if backend == "anthropic" and model_config:
        # Parent config credentials take precedence over environment.
        cfg_key = str(model_config.get("api_key") or "").strip()
        if cfg_key:
            api_key = cfg_key
        cfg_url = str(model_config.get("api_url") or "").rstrip("/")
        if cfg_url:
            if cfg_url.endswith("/v1"):
                cfg_url = cfg_url[: -len("/v1")]
            api_url = cfg_url
    if not api_key:
        return _agent_degraded_result(
            query_text,
            "No API key available - model call was not made. "
            "Set ANTHROPIC_API_KEY (optionally ANTHROPIC_BASE_URL) to enable real model execution. ",
            "no_api_key",
        )

    model_name = model or str(model_config.get("model") or "").strip() or DEFAULT_MODEL
    messages = _exchanges_to_messages(exchanges)
    messages.append({"role": "user", "content": query_text})

    tools = _builtin_tool_definitions(allowed_tools)
    if mcp_registry is not None:
        try:
            tools = tools + mcp_registry.anthropic_tool_definitions()
        except Exception:
            pass  # MCP tool listing is best-effort

    tool_calls: list[dict] = []
    input_tokens = 0
    output_tokens = 0
    api_requests = 0
    assistant_text = ""

    try:
        for _ in range(max_turns):
            result = await _call_anthropic_api(
                messages=messages,
                system_prompt=system_prompt,
                model=model_name,
                api_key=api_key,
                api_url=api_url,
                tools=tools,
            )
            api_requests += 1

            if "error" in result:
                return _agent_degraded_result(
                    query_text,
                    f"Model API error: {result['error']}. ",
                    "model_error",
                    tool_calls,
                )

            content = result.get("content", []) or []
            stop_reason = result.get("stop_reason", "end_turn")
            usage = result.get("usage", {}) or {}
            input_tokens += int(usage.get("input_tokens", 0) or 0)
            output_tokens += int(usage.get("output_tokens", 0) or 0)

            # Extract text and tool-use blocks
            text_parts: list[str] = []
            tool_use_blocks: list[dict] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
                    tool_use_blocks.append(block)
                    tool_calls.append({
                        "id": block.get("id"),
                        "tool_name": block.get("name"),
                        "arguments": block.get("input", {}),
                        "type": "tool_use",
                    })

            assistant_text = "\n".join(part for part in text_parts if part)

            if stop_reason != "tool_use" or not tool_use_blocks:
                return {
                    "assistant_text": assistant_text,
                    "stop_reason": stop_reason or "end_turn",
                    "usage": {
                        "backendRequests": api_requests,
                        "backendType": "fork-model",
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                    },
                    "model_usage": _agent_model_usage(model_name, input_tokens, output_tokens),
                    "tool_calls": tool_calls,
                }

            # Execute tool calls and feed results back to the model
            tool_results: list[dict] = []
            for block in tool_use_blocks:
                tool_name = block.get("name") or ""
                arguments = block.get("input", {}) or {}
                tool_result = _execute_agent_tool(tool_name, arguments, cwd, mcp_registry)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.get("id"),
                    "content": tool_result.get("content", []),
                    "is_error": tool_result.get("is_error", False),
                })

            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": tool_results})

        # Max tool-call iterations reached within this turn
        return {
            "assistant_text": (
                f"[Fork agent] Stopped after {max_turns} tool-call iterations (max turns). "
                + (assistant_text or "")
            ).strip(),
            "stop_reason": "max_turns",
            "usage": {
                "backendRequests": api_requests,
                "backendType": "fork-model",
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
            },
            "model_usage": _agent_model_usage(model_name, input_tokens, output_tokens),
            "tool_calls": tool_calls,
        }
    except Exception as exc:
        import sys as _sys
        _sys.stderr.write(f"[Fork agent] Model turn error: {exc}\n")
        _sys.stderr.flush()
        return _agent_degraded_result(
            query_text, f"Model turn failed: {exc}. ", "model_error", tool_calls
        )
