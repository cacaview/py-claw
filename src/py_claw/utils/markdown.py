"""
Markdown rendering utilities for CLI output.

Provides Markdown parsing and formatting for terminal output with
support for code highlighting, blockquotes, links, and theme-aware
styling.

Reference: ClaudeCode-main/src/utils/markdown.ts
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable

# Block quote bar character
BLOCKQUOTE_BAR = "│"

# ANSI escape codes for styling
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_ITALIC = "\033[3m"


@dataclass
class MarkdownConfig:
    """Configuration for Markdown rendering."""
    theme: str = "light"
    highlight: bool = True


def apply_markdown(
    content: str,
    theme: str = "light",
    highlight: Callable[[str, str], str] | None = None,
) -> str:
    """
    Apply Markdown formatting to content.

    Args:
        content: Markdown content to format
        theme: Theme name ('light' or 'dark')
        highlight: Optional code highlighter function(language, code)

    Returns:
        Formatted string with ANSI styling
    """
    content = _strip_prompt_xml_tags(content)
    lines = _tokenize_lines(content)
    result_lines = []
    in_code_block = False
    code_language = ""
    code_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Code block start/end
        if line.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_language = line[3:].strip()
                code_lines = []
            else:
                # End code block
                result_lines.append(_format_code_block(
                    code_language, code_lines, theme, highlight
                ))
                in_code_block = False
                code_language = ""
                code_lines = []
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # Inline processing
        formatted = _format_line(line, theme, highlight)
        result_lines.append(formatted)
        i += 1

    return "\n".join(result_lines).strip()


def _strip_prompt_xml_tags(content: str) -> str:
    """Remove prompt XML tags from content."""
    # Remove common prompt XML tags
    patterns = [
        r"</?[^>]+>",
        r"<result>.*?</result>",
        r"<thinking>.*?</thinking>",
    ]
    for pattern in patterns:
        content = re.sub(pattern, "", content, flags=re.DOTALL)
    return content


def _tokenize_lines(content: str) -> list[str]:
    """Split content into lines, preserving code blocks."""
    lines = []
    current = []
    in_fence = False
    fence_char = ""

    for line in content.split("\n"):
        if not in_fence:
            if line.startswith("```"):
                if current:
                    lines.extend(current)
                    current = []
                in_fence = True
                fence_char = line[:4]  # Include all backticks
                lines.append(line)
            elif line.startswith("#"):
                # Headers
                lines.append(line)
            elif line.startswith(">"):
                # Blockquotes
                lines.append(line)
            elif line.strip().startswith(("- ", "* ")):
                # Unordered list items
                lines.append(line)
            elif re.match(r"^\d+\.", line):
                # Ordered list items
                lines.append(line)
            elif line.strip() == "---" or line.strip() == "***":
                # Horizontal rules
                lines.append(line)
            else:
                current.append(line)
        else:
            if line == fence_char or (line.strip() == fence_char.strip() and line.startswith("```")):
                in_fence = False
                lines.append(line)
            else:
                lines.append(line)

    if current:
        lines.extend(current)

    return lines


def _format_line(
    line: str,
    theme: str,
    highlight: Callable[[str, str], str] | None,
) -> str:
    """Format a single line of Markdown."""
    # Headers
    if line.startswith("# "):
        return f"{ANSI_BOLD}{line}{ANSI_RESET}"
    if line.startswith("## "):
        return f"{ANSI_BOLD}{line}{ANSI_RESET}"
    if line.startswith("### "):
        return f"{ANSI_BOLD}{line}{ANSI_RESET}"

    # Blockquote
    if line.startswith("> "):
        inner = _format_inline(line[2:], theme)
        return f"{ANSI_DIM}{BLOCKQUOTE_BAR} {ANSI_ITALIC}{inner}{ANSI_RESET}"

    # Horizontal rule
    if line.strip() in ("---", "***"):
        return f"{ANSI_DIM}{'─' * 40}{ANSI_RESET}"

    # Inline formatting
    return _format_inline(line, theme)


def _format_inline(text: str, theme: str) -> str:
    """Format inline Markdown elements."""
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", f"{ANSI_BOLD}\\1{ANSI_RESET}", text)
    text = re.sub(r"__(.+?)__", f"{ANSI_BOLD}\\1{ANSI_RESET}", text)

    # Italic: *text* or _text_ (but not __bold__)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", f"{ANSI_ITALIC}\\1{ANSI_RESET}", text)
    text = re.sub(r"(?<!_)_([^_]+?)_(?!_)", f"{ANSI_ITALIC}\\1{ANSI_RESET}", text)

    # Inline code: `code`
    text = re.sub(r"`([^`]+)`", f"{ANSI_DIM}\\1{ANSI_RESET}", text)

    # Links: [text](url) - show as text (ANSI can't show links directly)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", "\\1", text)

    return text


def _format_code_block(
    language: str,
    lines: list[str],
    theme: str,
    highlight: Callable[[str, str], str] | None,
) -> str:
    """Format a code block."""
    if highlight and language:
        highlighted_lines = []
        for line in lines:
            try:
                highlighted = highlight(language, line)
                highlighted_lines.append(highlighted)
            except Exception:
                highlighted_lines.append(line)
        code_content = "\n".join(highlighted_lines)
    else:
        code_content = "\n".join(lines)

    return f"{ANSI_DIM}{code_content}{ANSI_RESET}\n"


def configure_marked() -> None:
    """
    Configure the Markdown parser.

    Currently a no-op in Python as we use regex-based parsing.
    Kept for API compatibility with TypeScript version.
    """
    pass
