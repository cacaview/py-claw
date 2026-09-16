"""Compatibility layer between transcript message shapes and compact input.

The query engine stores transcript entries as SDK message objects (pydantic
models). The compact service reads ``.type``, ``.id`` and ``.message`` via
``getattr`` and, for dict-backed entries, via ``dict(...)``. Plain dict keys
are invisible to ``getattr``, and the engine's SDK messages carry no
per-round ``id`` field, so neither shape works with
``group_messages_by_api_round`` out of the box.

This module normalizes any transcript entry into ``CompactMessage`` — a
dict-backed object exposing attribute-style fields — which satisfies both
access styles used by the compact service. It also converts a
``CompactionResult`` back into that shape so the result can be written
straight into the engine transcript (the backend converter reads ``.type``
/ ``.message`` attributes; session persistence accepts plain dicts).
"""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from .compressor import build_post_compact_messages
from .types import CompactionResult


class CompactMessage(dict):
    """A dict-backed message exposing the attribute fields compact reads."""

    @property
    def type(self) -> Any:  # noqa: A003 - mirrors Message.type duck typing
        return self.get("type")

    @property
    def id(self) -> Any:  # noqa: A003
        return self.get("id")

    @property
    def uuid(self) -> Any:  # noqa: A003
        return self.get("uuid")

    @property
    def message(self) -> Any:
        return self.get("message", {})


def _message_to_dict(msg: Any) -> dict[str, Any]:
    """Extract a plain dict from a dict or SDK/pydantic message object."""
    if isinstance(msg, dict):
        return dict(msg)
    dump = getattr(msg, "model_dump", None)
    if callable(dump):
        try:
            data = dump(by_alias=True, exclude_none=True)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    data: dict[str, Any] = {}
    for key in ("type", "subtype", "uuid", "session_id", "message", "content"):
        value = getattr(msg, key, None)
        if value is not None:
            data[key] = value
    return data


def normalize_compact_messages(messages: list[Any]) -> list[CompactMessage]:
    """Convert transcript entries into ``CompactMessage`` for the compact service.

    Each assistant message gets a stable per-message ``id`` (falling back to
    its ``uuid``) so ``group_messages_by_api_round`` can detect API-round
    boundaries. Original messages are not mutated.
    """
    normalized: list[CompactMessage] = []
    for index, msg in enumerate(messages):
        cm = CompactMessage(_message_to_dict(msg))
        msg_id = cm.get("id")
        if msg_id is None:
            inner = cm.get("message")
            if isinstance(inner, dict) and inner.get("id"):
                msg_id = inner["id"]
        if msg_id is None:
            msg_id = cm.get("uuid") or f"compact-msg-{index}"
        cm["id"] = msg_id
        if cm.get("uuid") is None:
            cm["uuid"] = str(uuid4())
        normalized.append(cm)
    return normalized


def ensure_compact_message(msg: Any) -> CompactMessage:
    """Wrap a compact result item (dict or object) as a ``CompactMessage``."""
    if isinstance(msg, CompactMessage):
        return msg
    if isinstance(msg, dict):
        cm = CompactMessage(msg)
    else:
        cm = CompactMessage(_message_to_dict(msg))
    if cm.get("uuid") is None:
        cm["uuid"] = str(uuid4())
    return cm


def build_compact_transcript(result: CompactionResult) -> list[CompactMessage]:
    """Convert a ``CompactionResult`` into messages for the engine transcript.

    Reuses the ``build_post_compact_messages`` ordering (boundary marker,
    summary messages, messages to keep, attachments, hook results) and wraps
    every item in ``CompactMessage`` so both attribute-style readers (the
    query backend's transcript converter) and dict-style readers (session
    persistence) handle the post-compact transcript.
    """
    return [ensure_compact_message(msg) for msg in build_post_compact_messages(result)]


def estimate_message_tokens(messages: list[Any]) -> int:
    """Rough token estimate (~4 chars per token) over serialized messages.

    Good enough for compact's before/after reporting; avoids a token API
    round-trip on the manual path.
    """
    total = 0
    for msg in messages:
        try:
            text = json.dumps(msg, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(msg)
        total += max(1, len(text) // 4)
    return total
