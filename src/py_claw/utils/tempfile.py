"""
Temporary file utilities.

Provides functions for generating temporary file paths with optional
content-hash based naming for stable paths across processes.

Reference: ClaudeCode-main/src/utils/tempfile.ts
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def generate_temp_file_path(
    prefix: str = "claude-prompt",
    extension: str = ".md",
    *,
    content_hash: str | None = None,
) -> str:
    """
    Generate a temporary file path.

    Args:
        prefix: Optional prefix for the temp file name
        extension: Optional file extension (defaults to '.md')
        content_hash: When provided, the identifier is derived from a
            SHA-256 hash of this string (first 16 hex chars). This produces
            a path that is stable across process boundaries — any process
            with the same content will get the same path. Use this when
            the path ends up in content sent to the Anthropic API (e.g.,
            sandbox deny lists in tool descriptions), because a random
            UUID would change on every subprocess spawn and invalidate
            the prompt cache prefix.

    Returns:
        Temp file path
    """
    if content_hash:
        file_id = hashlib.sha256(content_hash.encode()).hexdigest()[:16]
    else:
        import uuid
        file_id = str(uuid.uuid4())

    return str(Path(tempfile.gettempdir()) / f"{prefix}-{file_id}{extension}")
