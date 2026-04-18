"""Shared constants for speculation execution.

Mirrors ClaudeCode-main/src/services/PromptSuggestion/speculation.ts constants.
"""

from __future__ import annotations

# Tools that trigger an edit boundary in speculation
WRITE_TOOLS: frozenset[str] = frozenset({"Edit", "Write", "NotebookEdit"})

# Read-only tools allowed during speculation (safe to redirect to overlay)
SAFE_READ_ONLY_TOOLS = frozenset({
    "Read",
    "Glob",
    "Grep",
    "ToolSearch",
    "LSP",
    "TaskGet",
    "TaskList",
})

# Bash commands considered read-only (safe to execute during speculation)
READ_ONLY_COMMANDS = frozenset({
    "cat",
    "head",
    "tail",
    "less",
    "more",
    "sort",
    "uniq",
    "wc",
    "cut",
    "paste",
    "column",
    "tr",
    "file",
    "stat",
    "diff",
    "awk",
    "strings",
    "hexdump",
    "od",
    "base64",
    "nl",
    "grep",
    "rg",
    "jq",
    "ls",
    "pwd",
    "whoami",
    "id",
    "date",
    "echo",
    "printf",
    "true",
    "false",
    "which",
    "type",
    "command",
    "builtin",
    "cal",
    "uptime",
    "basename",
    "dirname",
    "realpath",
    "readlink",
    "nproc",
    "free",
    "df",
    "du",
    "locale",
    "groups",
    "getconf",
    "seq",
    "tsort",
    "pr",
    "tac",
    "rev",
    "fold",
    "expand",
    "unexpand",
    "comm",
    "cmp",
    "numfmt",
    "sleep",
    "alias",
    "arch",
    "env",
    "printenv",
})

# Maximum speculation turns before forced stop
MAX_SPECULATION_TURNS = 20

# Maximum messages accumulated during speculation
MAX_SPECULATION_MESSAGES = 100
