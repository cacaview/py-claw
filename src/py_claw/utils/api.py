"""
API-related utilities for tool schema normalization, system prompt handling,
and context metrics.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# -----------------------------------------------------------------------------
# Tool schema normalization
# -----------------------------------------------------------------------------

@dataclass
class ToolSchemaCache:
    """Simple in-memory cache for tool schemas."""

    _cache: dict[str, dict] = field(default_factory=dict)

    def get(self, key: str) -> dict | None:
        return self._cache.get(key)

    def set(self, key: str, value: dict) -> None:
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()


# Global tool schema cache
_tool_schema_cache = ToolSchemaCache()


def get_tool_schema_cache() -> ToolSchemaCache:
    """Get the global tool schema cache."""
    return _tool_schema_cache


def tool_to_api_schema(
    tool_name: str,
    description: str,
    input_schema: dict,
    *,
    strict: bool = False,
    eager_input_streaming: bool = False,
    defer_loading: bool = False,
    cache_control: dict | None = None,
) -> dict:
    """
    Convert a tool definition to the API schema format used by the Anthropic API.

    This is the Python equivalent of the TypeScript toolToAPISchema function.
    Applies caching, filtering, and schema transformations.
    """
    cache_key = f"{tool_name}:{json.dumps(input_schema, sort_keys=True)}"
    cached = _tool_schema_cache.get(cache_key)

    if cached:
        base = cached.copy()
    else:
        base = {
            "name": tool_name,
            "description": description,
            "input_schema": input_schema,
        }
        if strict:
            base["strict"] = True
        if eager_input_streaming:
            base["eager_input_streaming"] = True
        _tool_schema_cache.set(cache_key, base.copy())

    # Apply per-request options
    result = {
        "name": base["name"],
        "description": base["description"],
        "input_schema": base["input_schema"],
    }
    if base.get("strict"):
        result["strict"] = True
    if base.get("eager_input_streaming"):
        result["eager_input_streaming"] = True
    if defer_loading:
        result["defer_loading"] = True
    if cache_control:
        result["cache_control"] = cache_control

    return result


# -----------------------------------------------------------------------------
# System prompt splitting
# -----------------------------------------------------------------------------

# Billing header prefix
BILLING_HEADER_PREFIX = "x-anthropic-billing-header"

# Known CLI system prompt prefix strings
CLI_SYSPROMPT_PREFIXES: set[str] = set()


@dataclass
class SystemPromptBlock:
    """A block of system prompt text with its cache scope."""

    text: str
    cache_scope: str | None  # 'global', 'org', or None


def split_sys_prompt_prefix(
    system_prompt: list[str],
    *,
    skip_global_cache: bool = False,
) -> list[SystemPromptBlock]:
    """
    Split system prompt blocks by content type for API matching and cache control.

    Handles:
    1. Attribution header (cacheScope=null)
    2. System prompt prefix (cacheScope='org')
    3. Content blocks with appropriate cache scopes
    """
    attribution_header: str | None = None
    system_prompt_prefix: str | None = None
    rest: list[str] = []

    for block in system_prompt:
        if not block:
            continue
        if block.startswith(BILLING_HEADER_PREFIX):
            attribution_header = block
        elif block in CLI_SYSPROMPT_PREFIXES:
            system_prompt_prefix = block
        else:
            rest.append(block)

    result: list[SystemPromptBlock] = []
    if attribution_header:
        result.append(SystemPromptBlock(text=attribution_header, cache_scope=None))
    if system_prompt_prefix:
        result.append(SystemPromptBlock(text=system_prompt_prefix, cache_scope="org"))
    rest_joined = "\n\n".join(rest)
    if rest_joined:
        scope = None if skip_global_cache else "org"
        result.append(SystemPromptBlock(text=rest_joined, cache_scope=scope))

    return result


def append_system_context(
    system_prompt: list[str],
    context: dict[str, str],
) -> list[str]:
    """Append context key-value pairs to the system prompt."""
    if not context:
        return system_prompt
    context_str = "\n".join(f"{key}: {value}" for key, value in context.items())
    return [*system_prompt, context_str]


def prepend_user_context(
    messages: list[dict],
    context: dict[str, str],
) -> list[dict]:
    """
    Prepend a system-reminder user message with context.

    Used to inject contextual information into the message history.
    """
    if not context:
        return messages

    content = (
        "<system-reminder>\n"
        "As you answer the user's questions, you can use the following context:\n"
        + "\n".join(f"# {key}\n{value}" for key, value in context.items())
        + "\n\nIMPORTANT: this context may or may not be relevant to your tasks. "
        "You should not respond to this context unless it is highly relevant to your task.\n"
        "</system-reminder>\n"
    )

    user_message = {
        "type": "user",
        "message": {
            "content": content,
            "role": "user",
        },
        "isMeta": True,
    }

    return [user_message, *messages]


# -----------------------------------------------------------------------------
# Tool input normalization
# -----------------------------------------------------------------------------

def normalize_tool_input(tool_name: str, input_data: dict) -> dict:
    """
    Normalize tool input before sending to the API.

    Handles platform-specific path normalization, legacy parameter mapping, etc.
    """
    if tool_name == "BashTool" or tool_name == "bash":
        # Normalize cd prefix
        command = input_data.get("command", "")
        cwd = input_data.get("cwd", "")
        if cwd and command.startswith(f"cd {cwd} && "):
            command = command[len(f"cd {cwd} && ") :]
        return {
            "command": command,
            **{k: v for k, v in input_data.items() if k not in ("command",)},
        }

    return input_data


def normalize_tool_input_for_api(tool_name: str, input_data: dict) -> dict:
    """
    Strip fields added by normalizeToolInput before sending to API.

    Some fields (like plan from ExitPlanModeV2) have empty input schemas
    and shouldn't be sent.
    """
    if tool_name == "ExitPlanModeV2":
        return {k: v for k, v in input_data.items() if k not in ("plan", "planFilePath")}
    return input_data


# -----------------------------------------------------------------------------
# API prefix logging
# -----------------------------------------------------------------------------

def log_api_prefix(system_prompt: list[str]) -> None:
    """
    Log stats about first block for analyzing prefix matching config.

    Used for analytics on system prompt effectiveness.
    """
    if not system_prompt:
        return
    first_block = system_prompt[0] or ""
    snippet = first_block[:20]
    content_hash = hashlib.sha256(first_block.encode()).hexdigest()[:16]
    # Would log to analytics - placeholder
    return snippet, len(first_block), content_hash


# -----------------------------------------------------------------------------
# Context metrics
# -----------------------------------------------------------------------------

@dataclass
class ContextMetrics:
    """Metrics about context size for analytics."""

    git_status_size: int = 0
    claude_md_size: int = 0
    total_context_size: int = 0
    project_file_count_rounded: int = 0
    mcp_tools_count: int = 0
    mcp_servers_count: int = 0
    mcp_tools_tokens: int = 0
    non_mcp_tools_count: int = 0
    non_mcp_tools_tokens: int = 0


def calculate_context_metrics(
    tools: list[dict],
    mcp_tools: list[dict],
    user_context: dict,
    system_context: dict,
) -> ContextMetrics:
    """
    Calculate metrics about context size for logging.

    Used to understand context usage patterns.
    """
    metrics = ContextMetrics()

    # Extract context sizes
    git_status = system_context.get("gitStatus", "") or ""
    claude_md = user_context.get("claudeMd", "") or ""

    metrics.git_status_size = len(git_status)
    metrics.claude_md_size = len(claude_md)
    metrics.total_context_size = metrics.git_status_size + metrics.claude_md_size

    # Count MCP tools and servers
    metrics.mcp_tools_count = len(mcp_tools)
    metrics.non_mcp_tools_count = len(tools)

    # Extract unique server names from MCP tool names (format: mcp__servername__toolname)
    server_names = set()
    for tool in mcp_tools:
        name = tool.get("name", "")
        parts = name.split("__")
        if len(parts) >= 3 and parts[1]:
            server_names.add(parts[1])
    metrics.mcp_servers_count = len(server_names)

    return metrics
