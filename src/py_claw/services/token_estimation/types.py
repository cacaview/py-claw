"""
Token estimation types.

Provides centralized token counting across different backends.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TokenEstimationResult:
    """Result of token estimation."""
    input_tokens: int
    method: str = "estimation"  # "api", "bedrock", "estimation"
    model: str | None = None


@dataclass
class TokenEstimateForMessage:
    """Token estimate for a single message."""
    role: str
    content: str
    tokens: int


@dataclass
class TokenEstimateForMessages:
    """Token estimate for multiple messages."""
    total_tokens: int
    message_tokens: list[TokenEstimateForMessage]
    tool_tokens: int = 0
    method: str = "estimation"


# Characters per token ratio for rough estimation
DEFAULT_CHARS_PER_TOKEN = 4
JSON_CHARS_PER_TOKEN = 2
CODE_CHARS_PER_TOKEN = 3


def bytes_per_token_for_file_type(file_extension: str) -> float:
    """
    Returns estimated bytes-per-token ratio for a given file extension.

    Dense JSON has many single-character tokens ({, }, :, ,, ")
    which makes the real ratio closer to 2 rather than the default 4.
    """
    ext = file_extension.lower().lstrip(".")
    if ext in ("json", "jsonl", "jsonc"):
        return JSON_CHARS_PER_TOKEN
    # Code files tend to be more token-dense than prose
    if ext in ("py", "js", "ts", "jsx", "tsx", "java", "c", "cpp", "h", "hpp",
               "rs", "go", "rb", "php", "cs", "swift", "kt", "scala", "lua",
               "sh", "bash", "zsh", "ps1", "yml", "yaml", "toml", "ini", "cfg",
               "conf", "xml", "html", "css", "scss", "sass", "less", "vue",
               "svelte", "jsx", "tsx", "md", "rst"):
        return CODE_CHARS_PER_TOKEN
    return DEFAULT_CHARS_PER_TOKEN
