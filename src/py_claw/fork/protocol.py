"""NDJSON protocol for fork subprocess parent-child communication."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ─── Message Types ──────────────────────────────────────────────────────────────


@dataclass
class ForkMessage:
    """Base class for fork protocol messages."""
    type: str


@dataclass
class ForkInitMessage(ForkMessage):
    """Init message from parent to child."""
    type: Literal["init"] = "init"
    session_id: str = ""
    system_prompt: str = ""
    model: str | None = None
    allowed_tools: list[str] | None = None
    cwd: str = ""
    mcp_servers: list[dict[str, Any]] | None = None
    # Isolation context
    isolation: dict[str, Any] | None = None  # ForkIsolationContext serialized


@dataclass
class ForkTurnMessage(ForkMessage):
    """Turn message from parent to child."""
    type: Literal["turn"] = "turn"
    query_text: str = ""
    turn_count: int = 0


@dataclass
class ForkStopMessage(ForkMessage):
    """Stop message from parent to child."""
    type: Literal["stop"] = "stop"


@dataclass
class ForkOutputMessage(ForkMessage):
    """Streaming output from child to parent."""
    type: Literal["output"] = "output"
    delta: str = ""


@dataclass
class ForkResultMessage(ForkMessage):
    """Final result from child to parent."""
    type: Literal["result"] = "result"
    assistant_text: str = ""
    stop_reason: str = "end_turn"
    usage: dict[str, object] = field(default_factory=dict)
    model_usage: dict[str, object] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
    boundary: dict[str, object] | None = None
    output_tokens: int = 0


@dataclass
class ForkSpeculationStartMessage(ForkMessage):
    """Start speculation mode in child subprocess."""
    type: Literal["speculation_start"] = "speculation_start"
    overlay_path: str = ""
    main_cwd: str = ""
    max_turns: int = 20


@dataclass
class ForkErrorMessage(ForkMessage):
    """Error message from child to parent."""
    type: Literal["error"] = "error"
    message: str = ""


@dataclass
class ForkHistoryMessage(ForkMessage):
    """History sync from parent to child during persistent mode."""
    type: Literal["history"] = "history"
    exchanges: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ForkMcpCallMessage(ForkMessage):
    """MCP tool call from parent to child (for agent-managed MCP servers)."""
    type: Literal["mcp_call"] = "mcp_call"
    server_name: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


@dataclass
class ForkMcpResultMessage(ForkMessage):
    """MCP tool result from child to parent."""
    type: Literal["mcp_result"] = "mcp_result"
    call_id: str = ""
    result: Any = None
    error: str | None = None


# ─── NDJSON Parser ─────────────────────────────────────────────────────────────


class NDJSONParser:
    """Parser for newline-delimited JSON streams.

    Mirrors the pattern from services/bridge/session_runner.py.
    """

    def __init__(self) -> None:
        self._buffer: str = ""

    def parse(self, data: str) -> list[dict[str, Any]]:
        """Parse NDJSON data, yielding complete JSON objects."""
        self._buffer += data
        lines = self._buffer.split("\n")
        self._buffer = lines.pop() if lines[-1] else ""

        results: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Failed to parse NDJSON line: %s", line[:100])
        return results


# ─── Helpers ───────────────────────────────────────────────────────────────────


def build_fork_boilerplate(
    parent_session_id: str,
    child_session_id: str,
    transcript: list[dict[str, Any]],
) -> str:
    """Build the fork directive/boilerplate text.

    Mirrors buildForkedMessages() and buildChildMessage() from TypeScript.

    The boilerplate establishes:
    - This is a forked subagent
    - No further sub-agents may be spawned
    - Direct execution is required
    - Parent context is provided for cache-friendly API prefixes
    """
    lines: list[str] = [
        "[FORK SUBAGENT - EXECUTE DIRECTLY]",
        f"[PARENT SESSION: {parent_session_id}]",
        f"[THIS SESSION: {child_session_id}]",
        "",
        "You are a forked subagent. You must:",
        "1. Execute the user's request directly without spawning sub-agents",
        "2. Use the inherited conversation context below for prompt cache friendliness",
        "3. Report results directly to the parent session",
        "",
        "=== INHERITED CONVERSATION CONTEXT ===",
    ]

    for msg in transcript[-10:]:  # Last 10 messages for context
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") if isinstance(c, dict) else str(c) for c in content
            )
        lines.append(f"[{role.upper()}]")
        lines.append(str(content)[:500])  # Truncate long messages
        lines.append("")

    lines.append("=== END INHERITED CONTEXT ===")
    return "\n".join(lines)
