"""Session transcript writer.

The read side (``search``/``storage``) already understands the upstream
``~/.claude/projects/<project>/<session-uuid>.jsonl`` layout; this module is
the missing write side. QueryRuntime appends each transcript entry as it
completes a turn so ``/sessions`` and the Resume screen see real data.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from py_claw.services.session_storage.common import (
    get_project_dir,
    validate_uuid,
)


def _timestamp_iso(entry: dict[str, Any]) -> str:
    ts = entry.get("timestamp")
    if isinstance(ts, str) and ts:
        return ts
    return datetime.now(timezone.utc).isoformat()


def serialize_transcript_entry(entry: object, *, session_id: str, cwd: str) -> str:
    """Serialize one transcript message into an upstream-compatible JSONL line."""
    data: dict[str, Any]
    dump = getattr(entry, "model_dump", None)
    if callable(dump):
        data = dump(by_alias=True, exclude_none=True)
    elif isinstance(entry, dict):
        data = dict(entry)
    else:
        data = {"type": "unknown", "content": str(entry)}

    data.setdefault("sessionId", session_id)
    data.setdefault("cwd", cwd)
    data.setdefault("uuid", str(uuid.uuid4()))
    data["timestamp"] = _timestamp_iso(data)
    data.setdefault("isSidechain", False)
    if data.get("type") == "user":
        data.setdefault("userType", "external")
    return json.dumps(data, ensure_ascii=False, default=str)


def append_session_entries(
    session_id: str,
    cwd: str,
    entries: list[object],
) -> int:
    """Append transcript entries to the session JSONL file.

    Returns the number of lines written. Entries lacking a valid UUID session
    id are stored under a freshly generated UUID so the reader (which filters
    on UUID-named files) can still discover them.
    """
    if not entries:
        return 0

    file_session_id = validate_uuid(session_id) or str(uuid.uuid4())
    project_dir = Path(get_project_dir(cwd))
    try:
        project_dir.mkdir(parents=True, exist_ok=True)
        file_path = project_dir / f"{file_session_id}.jsonl"
        lines = [serialize_transcript_entry(entry, session_id=file_session_id, cwd=cwd) for entry in entries]
        with open(file_path, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
        return len(lines)
    except OSError:
        # Persistence is best-effort; a read-only home must not break turns.
        return 0
