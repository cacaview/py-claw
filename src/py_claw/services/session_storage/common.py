"""Portable session storage utilities.

Re-implements ClaudeCode-main/src/utils/sessionStoragePortable.ts

Pure Python - no internal dependencies on logging, experiments, or feature
flags. Shared between the CLI and other consumers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Size of the head/tail buffer for lite metadata reads.
LITE_READ_BUF_SIZE = 65536

# Maximum length for a single filesystem path component.
MAX_SANITIZED_LENGTH = 200

# File size below which precompact filtering is skipped.
SKIP_PRECOMPACT_THRESHOLD = 5 * 1024 * 1024

# ---------------------------------------------------------------------------
# UUID validation
# ---------------------------------------------------------------------------

UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_uuid(maybe_uuid: str | None) -> str | None:
    """Validate a UUID string.

    Returns the UUID if valid, None otherwise.
    """
    if maybe_uuid is None:
        return None
    if not isinstance(maybe_uuid, str):
        return None
    if UUID_REGEX.match(maybe_uuid):
        return maybe_uuid
    return None


# ---------------------------------------------------------------------------
# JSON string field extraction - no full parse, works on truncated lines
# ---------------------------------------------------------------------------


def unescape_json_string(raw: str) -> str:
    """Unescape a JSON string value extracted as raw text.

    Only allocates a new string when escape sequences are present.
    """
    if "\\" not in raw:
        return raw
    try:
        return json.loads(f'"{raw}"')
    except (json.JSONDecodeError, ValueError):
        return raw


def extract_json_string_field(text: str, key: str) -> str | None:
    """Extracts a simple JSON string field value from raw text without full parsing.

    Looks for `"key":"value"` or `"key": "value"` patterns.
    Returns the first match, or None if not found.
    """
    patterns = [f'"{key}":"', f'"{key}": "']
    for pattern in patterns:
        idx = text.find(pattern)
        if idx < 0:
            continue

        value_start = idx + len(pattern)
        i = value_start
        while i < len(text):
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == '"':
                return unescape_json_string(text[value_start:i])
            i += 1
    return None


def extract_last_json_string_field(text: str, key: str) -> str | None:
    """Like extractJsonStringField but finds the LAST occurrence.

    Useful for fields that are appended (customTitle, tag, etc.).
    """
    patterns = [f'"{key}":"', f'"{key}": "']
    last_value: str | None = None
    for pattern in patterns:
        search_from = 0
        while True:
            idx = text.find(pattern, search_from)
            if idx < 0:
                break

            value_start = idx + len(pattern)
            i = value_start
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    last_value = unescape_json_string(text[value_start:i])
                    break
                i += 1
            search_from = i + 1
    return last_value


# ---------------------------------------------------------------------------
# First prompt extraction from head chunk
# ---------------------------------------------------------------------------

# Pattern matching auto-generated or system messages that should be skipped
SKIP_FIRST_PROMPT_PATTERN = re.compile(
    r"^(?:\s*<[a-z][\w-]*[\s>]|\[Request interrupted by user[^\]]*\])"
)

COMMAND_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>")


def extract_first_prompt_from_head(head: str) -> str:
    """Extracts the first meaningful user prompt from a JSONL head chunk.

    Skips tool_result messages, isMeta, isCompactSummary, command-name messages,
    and auto-generated patterns (session hooks, tick, IDE metadata, etc.).
    Truncates to 200 chars.
    """
    start = 0
    command_fallback = ""

    while start < len(head):
        newline_idx = head.find("\n", start)
        if newline_idx >= 0:
            line = head[start:newline_idx]
        else:
            line = head[start:]
            start = len(head)
        if newline_idx >= 0:
            start = newline_idx + 1

        if '"type":"user"' not in line and '"type": "user"' not in line:
            continue
        if '"tool_result"' in line:
            continue
        if '"isMeta":true' in line or '"isMeta": true' in line:
            continue
        if '"isCompactSummary":true' in line or '"isCompactSummary": true' in line:
            continue

        try:
            entry = json.loads(line)
            if entry.get("type") != "user":
                continue

            message = entry.get("message")
            if not message:
                continue

            content = message.get("content")
            texts: list[str] = []
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                        texts.append(block["text"])

            for raw in texts:
                result = raw.replace("\n", " ").strip()
                if not result:
                    continue

                # Skip slash-command messages but remember first as fallback
                cmd_match = COMMAND_NAME_RE.search(result)
                if cmd_match:
                    if not command_fallback:
                        command_fallback = cmd_match.group(1)
                    continue

                # Format bash input with ! prefix
                bash_match = re.search(r"<bash-input>([\s\S]*?)</bash-input>", result)
                if bash_match:
                    return f"! {bash_match.group(1).strip()}"

                if SKIP_FIRST_PROMPT_PATTERN.match(result):
                    continue

                if len(result) > 200:
                    result = result[:200].strip() + "\u2026"
                return result
        except (json.JSONDecodeError, RecursionError, ValueError):
            continue

    if command_fallback:
        return command_fallback
    return ""


# ---------------------------------------------------------------------------
# File I/O - read head and tail of a file
# ---------------------------------------------------------------------------


async def read_head_and_tail(
    file_path: str,
    file_size: int,
    buf: bytearray,
) -> tuple[str, str]:
    """Reads the first and last LITE_READ_BUF_SIZE bytes of a file.

    For small files where head covers tail, `tail == head`.
    Returns (head, tail).

    Args:
        file_path: Path to the file
        file_size: Size of the file
        buf: Buffer to use for reading

    Returns:
        Tuple of (head, tail) strings
    """
    try:
        with open(file_path, "rb") as fh:
            head_bytes_read = fh.readinto(buf)
            if head_bytes_read == 0:
                return ("", "")

            head = buf[:head_bytes_read].decode("utf-8")

            tail_offset = max(0, file_size - LITE_READ_BUF_SIZE)
            tail = head
            if tail_offset > 0:
                fh.seek(tail_offset)
                tail_bytes = fh.read(LITE_READ_BUF_SIZE)
                tail = tail_bytes.decode("utf-8")

            return (head, tail)
    except (OSError, IOError):
        return ("", "")


@dataclass(frozen=True, slots=True)
class LiteSessionFile:
    """Lightweight session file metadata."""

    mtime: float
    size: int
    head: str
    tail: str


async def read_session_lite(file_path: str) -> LiteSessionFile | None:
    """Opens a single session file, stats it, and reads head + tail.

    Args:
        file_path: Path to the session file

    Returns:
        LiteSessionFile with metadata, or None on error
    """
    try:
        stat_result = Path(file_path).stat()
        buf = bytearray(LITE_READ_BUF_SIZE)

        with open(file_path, "rb") as fh:
            head_result = fh.readinto(buf)
            if head_result == 0:
                return None

            head = buf[:head_result].decode("utf-8")
            tail_offset = max(0, stat_result.st_size - LITE_READ_BUF_SIZE)
            tail = head
            if tail_offset > 0:
                fh.seek(tail_offset)
                tail_bytes = fh.read(LITE_READ_BUF_SIZE)
                tail = tail_bytes.decode("utf-8")

            return LiteSessionFile(
                mtime=stat_result.st_mtime,
                size=stat_result.st_size,
                head=head,
                tail=tail,
            )
    except (OSError, IOError):
        return None


# ---------------------------------------------------------------------------
# Path sanitization
# ---------------------------------------------------------------------------


def simple_hash(s: str) -> str:
    """Simple string hash using djb2 algorithm."""
    h = 5381
    for c in s:
        h = ((h << 5) + h) + ord(c)
    return str(abs(h))


def sanitize_path(name: str) -> str:
    """Makes a string safe for use as a directory or file name.

    Replaces all non-alphanumeric characters with hyphens.
    For deeply nested paths that would exceed filesystem limits (255 bytes),
    truncates and appends a hash suffix for uniqueness.

    Args:
        name: The string to make safe (e.g., '/Users/foo/my-project')

    Returns:
        A safe name (e.g., '-Users-foo-my-project')
    """
    sanitized = re.sub(r"[^a-zA-Z0-9]", "-", name)
    if len(sanitized) <= MAX_SANITIZED_LENGTH:
        return sanitized

    # Hash for paths that exceed max length
    h = hashlib.new("md5")
    h.update(name.encode("utf-8"))
    hash_suffix = h.hexdigest()[:8]
    return f"{sanitized[:MAX_SANITIZED_LENGTH]}-{hash_suffix}"


# ---------------------------------------------------------------------------
# Project directory discovery
# ---------------------------------------------------------------------------


def get_claude_config_home_dir() -> Path:
    """Get the Claude configuration directory."""
    if "CLAUDE_CONFIG_DIR" in os.environ:
        return Path(os.environ["CLAUDE_CONFIG_DIR"])
    return Path.home() / ".claude"


def get_projects_dir() -> str:
    """Get the projects directory path."""
    return str(get_claude_config_home_dir() / "projects")


def get_project_dir(project_dir: str) -> str:
    """Get the sanitized project directory path."""
    return str(Path(get_projects_dir()) / sanitize_path(project_dir))


async def canonicalize_path(dir_path: str) -> str:
    """Resolves a directory path to its canonical form.

    Uses realpath + NFC normalization. Falls back to NFC-only if realpath fails.

    Args:
        dir_path: Directory path to canonicalize

    Returns:
        Canonical directory path
    """
    try:
        return Path(dir_path).resolve().resolve().as_posix()
    except OSError:
        return dir_path


async def find_project_dir(project_path: str) -> str | None:
    """Finds the project directory for a given path.

    Handles hash mismatches for long paths (>200 chars) where
    different hashing algorithms may produce different suffixes.

    Args:
        project_path: Original project path

    Returns:
        Found project directory path, or None if not found
    """
    exact = get_project_dir(project_path)
    try:
        if Path(exact).exists():
            return exact
    except OSError:
        pass

    # For short paths, no fallback needed
    sanitized = sanitize_path(project_path)
    if len(sanitized) <= MAX_SANITIZED_LENGTH:
        return None

    # For long paths, try prefix matching
    prefix = sanitized[:MAX_SANITIZED_LENGTH]
    projects_dir = Path(get_projects_dir())

    try:
        for entry in projects_dir.iterdir():
            if entry.is_dir() and entry.name.startswith(prefix + "-"):
                return str(entry)
    except OSError:
        pass

    return None


# ---------------------------------------------------------------------------
# Session file path resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CanonicalizedSessionFile:
    """Result of resolving a session file path."""

    file_path: str
    project_path: str | None
    file_size: int


async def resolve_session_file_path(
    session_id: str,
    dir_path: str | None = None,
) -> CanonicalizedSessionFile | None:
    """Resolve a sessionId to its on-disk JSONL file path.

    When `dir` is provided: canonicalize it, look in that project's directory
    (with findProjectDir fallback), then fall back to sibling git worktrees.

    When `dir` is omitted: scan all project directories.

    Args:
        session_id: Session UUID
        dir_path: Optional project directory to search in

    Returns:
        CanonicalizedSessionFile with resolved path, or None if not found
    """
    file_name = f"{session_id}.jsonl"

    if dir_path:
        canonical = await canonicalize_path(dir_path)
        project_dir = await find_project_dir(canonical)
        if project_dir:
            file_path = str(Path(project_dir) / file_name)
            try:
                s = Path(file_path).stat()
                if s.st_size > 0:
                    return CanonicalizedSessionFile(
                        file_path=file_path,
                        project_path=canonical,
                        file_size=s.st_size,
                    )
            except OSError:
                pass

        # Worktree fallback - sessions may live under a different worktree root
        worktree_paths = await _get_worktree_paths(canonical)
        for wt in worktree_paths:
            if wt == canonical:
                continue
            wt_project_dir = await find_project_dir(wt)
            if not wt_project_dir:
                continue
            file_path = str(Path(wt_project_dir) / file_name)
            try:
                s = Path(file_path).stat()
                if s.st_size > 0:
                    return CanonicalizedSessionFile(
                        file_path=file_path,
                        project_path=wt,
                        file_size=s.st_size,
                    )
            except OSError:
                pass
        return None

    # No dir - scan all project directories
    projects_dir = Path(get_projects_dir())
    try:
        for name in projects_dir.iterdir():
            if not name.is_dir():
                continue
            file_path = str(name / file_name)
            try:
                s = Path(file_path).stat()
                if s.st_size > 0:
                    return CanonicalizedSessionFile(
                        file_path=file_path,
                        project_path=None,
                        file_size=s.st_size,
                    )
            except OSError:
                continue
    except OSError:
        pass

    return None


async def _get_worktree_paths(cwd: str) -> list[str]:
    """Get git worktree paths for a repository.

    Args:
        cwd: Current working directory

    Returns:
        List of worktree paths
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []

        paths: list[str] = []
        for line in result.stdout.split("\n"):
            if line.startswith("worktree "):
                path = line[9:].strip()
                if path != cwd:
                    paths.append(path)
        return paths
    except (subprocess.SubprocessError, OSError):
        return []
