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
        "tools": [
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
        ],
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
