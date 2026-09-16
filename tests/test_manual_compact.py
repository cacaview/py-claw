"""Regression tests for P2-1: /compact manual compaction wiring.

Asserts that /compact really compacts the engine transcript through the
compact service (transcript shrinks, summary generated, boundary marker
written back), that /compact <instructions> injects instructions into the
summarization prompt, and that the pre-compact snapshot lets the user roll
back.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Ensure src is on path (conftest.py does this too, but be explicit)
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from py_claw.cli.runtime import RuntimeState
from py_claw.schemas.common import SDKAssistantMessage, SDKUserMessage
from py_claw.settings.loader import SettingsLoadResult


class FakeSummaryClient:
    """Duck-typed stand-in for the summary API client the compressor expects."""

    def __init__(self, summary: str = "SUMMARY: key decisions and state from earlier conversation.") -> None:
        self.summary = summary
        self.prompts: list[str] = []
        self.models: list[str] = []

    async def create_message(self, *, messages, model, max_tokens):
        self.prompts.append(messages[0]["content"])
        self.models.append(model)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.summary)])


def _make_runtime(runs: int = 4):
    """Create a QueryRuntime whose transcript holds ``runs`` user/assistant pairs."""
    from py_claw.query.engine import QueryRuntime

    rt = QueryRuntime(state=RuntimeState())
    for i in range(runs):
        rt._transcript.append(
            SDKUserMessage(
                type="user",
                message={"role": "user", "content": f"user question {i} " + "x" * 80},
                parent_tool_use_id="",
                uuid=f"u{i}",
                session_id="s1",
            )
        )
        rt._transcript.append(
            SDKAssistantMessage(
                type="assistant",
                message={"role": "assistant", "content": f"assistant answer {i} " + "y" * 80},
                parent_tool_use_id="",
                uuid=f"a{i}",
                session_id="s1",
            )
        )
    return rt


def _dumped(rt) -> list[dict]:
    return [m.model_dump() for m in rt.transcript]


def _call_compact(arguments: str = "", *, state=None, session_id="s1", transcript_size=None):
    from py_claw.commands import _compact_handler, CommandDefinition

    state = state if state is not None else MagicMock()
    rt = state.query_runtime
    if transcript_size is None:
        transcript_size = len(rt.transcript) if rt is not None else 0
    return _compact_handler(
        command=CommandDefinition(name="compact", description="test"),
        arguments=arguments,
        state=state,
        settings=SettingsLoadResult(effective={}, sources=[]),
        registry=MagicMock(),
        session_id=session_id,
        transcript_size=transcript_size,
    )


def _patch_api_client(monkeypatch, client) -> None:
    from py_claw.services import compact as compact_pkg

    monkeypatch.setattr(compact_pkg, "build_compact_api_client", lambda: client)


# ---------------------------------------------------------------------------
# Message compat (shape normalization + write-back)
# ---------------------------------------------------------------------------


class TestMessageCompat:
    def test_normalize_sdk_objects_group_into_rounds(self) -> None:
        from py_claw.services.compact import normalize_compact_messages
        from py_claw.services.compact.grouping import group_messages_by_api_round

        rt = _make_runtime(3)
        normalized = normalize_compact_messages(rt.transcript)
        groups = group_messages_by_api_round(normalized)
        # Without normalization the whole transcript collapses to 1 group;
        # with it, each API round is detected.
        assert len(groups) >= 4

    def test_normalize_dicts(self) -> None:
        from py_claw.services.compact import CompactMessage, normalize_compact_messages

        dics = [
            {"type": "user", "id": "u1", "message": {"id": "u1", "role": "user", "content": "hi"}},
            {"type": "assistant", "id": "a1", "message": {"id": "a1", "role": "assistant", "content": "hello"}},
            {"type": "user", "id": "u2", "message": {"id": "u2", "role": "user", "content": "more"}},
        ]
        normalized = normalize_compact_messages(dics)
        assert all(isinstance(m, CompactMessage) for m in normalized)
        # Attribute-style access, which is how the compact service reads messages.
        assert normalized[1].type == "assistant"
        assert normalized[1].id == "a1"
        assert normalized[1].message["content"] == "hello"
        # Original dicts are not mutated.
        assert "uuid" not in dics[0]

    def test_estimate_message_tokens(self) -> None:
        from py_claw.services.compact import estimate_message_tokens

        assert estimate_message_tokens([]) == 0
        assert estimate_message_tokens([{"type": "user", "message": {"content": "x" * 100}}]) > 0

    def test_build_compact_transcript_shapes(self) -> None:
        from py_claw.services.compact import CompactMessage, CompactionResult, build_compact_transcript

        result = CompactionResult(
            boundary_marker={"type": "system", "subtype": "compact_boundary", "compact_metadata": {}},
            summary_messages=[{"type": "user", "message": {"role": "user", "content": "S"}}],
            messages_to_keep=[{"type": "assistant", "uuid": "a1", "message": {"role": "assistant", "content": "A"}}],
        )
        out = build_compact_transcript(result)
        assert [m.get("type") for m in out] == ["system", "user", "assistant"]
        assert all(isinstance(m, CompactMessage) and m.get("uuid") for m in out)
        # Attribute-style access works on the post-compact transcript (what the
        # query backend's transcript converter relies on).
        assert out[1].type == "user"
        assert out[1].message["content"] == "S"


# ---------------------------------------------------------------------------
# Manual compact orchestration
# ---------------------------------------------------------------------------


class TestRunManualCompact:
    def test_compacts_and_summarizes(self) -> None:
        import asyncio

        from py_claw.services.compact import run_manual_compact

        rt = _make_runtime(4)
        fake = FakeSummaryClient()
        result = asyncio.run(run_manual_compact(rt.transcript, api_client=fake))

        assert len(fake.models) == 1
        assert result.summary_messages
        assert result.summary_messages[0]["message"]["content"] == fake.summary
        assert result.messages_to_keep and len(result.messages_to_keep) < len(rt.transcript)
        assert result.pre_compact_token_count is not None
        assert result.post_compact_token_count is not None
        assert result.post_compact_token_count < result.pre_compact_token_count

    def test_custom_instructions_injected_into_prompt(self) -> None:
        import asyncio

        from py_claw.services.compact import run_manual_compact

        rt = _make_runtime(4)
        fake = FakeSummaryClient()
        asyncio.run(
            run_manual_compact(
                rt.transcript,
                api_client=fake,
                custom_instructions="focus on the bug fix",
            )
        )
        assert len(fake.prompts) == 1
        assert "ADDITIONAL INSTRUCTIONS" in fake.prompts[0]
        assert "focus on the bug fix" in fake.prompts[0]

    def test_no_api_client_still_compacts_without_summary(self) -> None:
        import asyncio

        from py_claw.services.compact import run_manual_compact

        rt = _make_runtime(4)
        result = asyncio.run(run_manual_compact(rt.transcript, api_client=None))
        assert result.summary_messages == []
        assert result.messages_to_keep

    def test_too_few_messages_raises(self) -> None:
        import asyncio

        from py_claw.services.compact import run_manual_compact

        rt = _make_runtime(0)
        rt._transcript.append(
            SDKUserMessage(type="user", message={"role": "user", "content": "hi"}, parent_tool_use_id="", uuid="u0", session_id="s1")
        )
        with pytest.raises(ValueError):
            asyncio.run(run_manual_compact(rt.transcript, api_client=None))


# ---------------------------------------------------------------------------
# Engine snapshot / rollback (reuses saved-session store + replace_transcript)
# ---------------------------------------------------------------------------


class TestCompactSnapshot:
    def test_save_and_restore_roundtrip(self) -> None:
        rt = _make_runtime(3)
        original = _dumped(rt)
        rt.save_compact_snapshot("s1")
        rt.replace_transcript(rt.transcript[:2])
        ok, msg = rt.restore_compact_snapshot("s1")
        assert ok is True
        assert "restored 6 messages" in msg
        assert _dumped(rt) == original

    def test_restore_without_snapshot(self) -> None:
        rt = _make_runtime(1)
        ok, msg = rt.restore_compact_snapshot("nope")
        assert ok is False
        assert "no pre-compact snapshot" in msg
        assert rt.message_count() == 2

    def test_snapshot_consumed_after_restore(self) -> None:
        rt = _make_runtime(1)
        rt.save_compact_snapshot("s1")
        assert rt.restore_compact_snapshot("s1")[0] is True
        ok, _ = rt.restore_compact_snapshot("s1")
        assert ok is False

    def test_discard_drops_snapshot(self) -> None:
        rt = _make_runtime(1)
        rt.save_compact_snapshot("s1")
        rt.discard_compact_snapshot("s1")
        ok, _ = rt.restore_compact_snapshot("s1")
        assert ok is False

    def test_snapshot_keyed_by_session(self) -> None:
        rt = _make_runtime(1)
        rt.save_compact_snapshot("s1")
        ok, _ = rt.restore_compact_snapshot("s2")
        assert ok is False
        assert rt.restore_compact_snapshot("s1")[0] is True


# ---------------------------------------------------------------------------
# /compact command handler
# ---------------------------------------------------------------------------


class TestCompactHandler:
    def test_compact_shortens_transcript_and_reports_summary(self, monkeypatch) -> None:
        fake = FakeSummaryClient()
        _patch_api_client(monkeypatch, fake)

        rt = _make_runtime(4)
        state = MagicMock()
        state.query_runtime = rt
        before = rt.message_count()
        original = _dumped(rt)

        output = _call_compact(state=state)

        assert f"Compacted {before} messages -> {rt.message_count()} messages" in output
        assert rt.message_count() < before
        # Boundary marker written back first, generated summary second.
        new_t = rt.transcript
        assert new_t[0].get("type") == "system"
        assert new_t[0].get("subtype") == "compact_boundary"
        assert fake.summary in str(new_t[1].get("message"))
        assert "Summary:" in output
        assert fake.summary in output
        # Rollback path is reported and the snapshot actually works.
        assert "Rollback" in output
        ok, _ = rt.restore_compact_snapshot("s1")
        assert ok is True
        assert _dumped(rt) == original

    def test_compact_with_instructions(self, monkeypatch) -> None:
        fake = FakeSummaryClient()
        _patch_api_client(monkeypatch, fake)

        rt = _make_runtime(4)
        state = MagicMock()
        state.query_runtime = rt

        output = _call_compact(arguments="focus on the refactor", state=state)

        assert len(fake.prompts) == 1
        assert "ADDITIONAL INSTRUCTIONS" in fake.prompts[0]
        assert "focus on the refactor" in fake.prompts[0]
        assert "Applied custom instructions: focus on the refactor" in output

    def test_compact_without_api_client_degrades(self, monkeypatch) -> None:
        _patch_api_client(monkeypatch, None)

        rt = _make_runtime(4)
        state = MagicMock()
        state.query_runtime = rt

        output = _call_compact(state=state)

        assert "Compacted" in output
        assert "No summary generated" in output
        assert rt.message_count() < 8

    def test_rollback_restores_transcript(self, monkeypatch) -> None:
        fake = FakeSummaryClient()
        _patch_api_client(monkeypatch, fake)

        rt = _make_runtime(4)
        state = MagicMock()
        state.query_runtime = rt
        original = _dumped(rt)

        _call_compact(state=state)
        assert rt.message_count() < len(original)

        output = _call_compact(arguments="--rollback", state=state)

        assert "Rolled back" in output
        assert _dumped(rt) == original

    def test_rollback_without_snapshot(self) -> None:
        rt = _make_runtime(1)
        state = MagicMock()
        state.query_runtime = rt

        output = _call_compact(arguments="--rollback", state=state)

        assert "Cannot roll back" in output

    def test_rollback_without_runtime(self) -> None:
        state = MagicMock()
        state.query_runtime = None

        output = _call_compact(arguments="--rollback", state=state)

        assert "no active query runtime" in output

    def test_empty_transcript(self) -> None:
        state = MagicMock()
        state.query_runtime = None

        output = _call_compact(arguments="", state=state, transcript_size=0)

        assert "No conversation history to compact" in output

    def test_no_runtime(self) -> None:
        state = MagicMock()
        state.query_runtime = None

        output = _call_compact(arguments="", state=state, transcript_size=5)

        assert "no active query runtime" in output
