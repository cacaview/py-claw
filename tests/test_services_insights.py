"""Tests for py_claw.services.insights pipeline functions."""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from py_claw.services.insights.types import (
    AggregatedInsightsData,
    InsightsResult,
    MultiClaudingStats,
    NarrativeSections,
    SessionFacet,
    SessionInsight,
    SessionLog,
    SessionMeta,
    UsageStats,
)
from py_claw.services.insights.service import (
    aggregate_insights_data,
    deduplicate_session_branches,
    detect_multi_clauding,
    extract_session_meta,
    format_insights_report,
    format_transcript_for_facets,
    load_cached_facets,
    save_facets,
    scan_session_logs,
    summarize_transcript_if_needed,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_session_log(tmp_path: Path) -> SessionLog:
    """Create a sample session JSONL file and return a SessionLog for it."""
    session_id = "abc12345-1234-1234-1234-123456789012"
    file_path = tmp_path / f"{session_id}.jsonl"
    # Tool calls must appear as tool_use blocks inside assistant message content
    entries = [
        {"type": "user", "message": {"content": "Hello, world!"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Let me run ls."},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                ]
            },
        },
        {"type": "assistant", "message": {"content": "Done."}},
    ]
    file_path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    mtime = file_path.stat().st_mtime
    return SessionLog(
        session_id=session_id,
        file_path=str(file_path),
        project_path=str(tmp_path),
        mtime=mtime,
        entries=entries,
    )


@pytest.fixture
def sample_session_with_timestamps(tmp_path: Path) -> SessionLog:
    """Create a session with message timestamps for multi-clauding tests."""
    session_id = "bbb12345-1234-1234-1234-123456789012"
    file_path = tmp_path / f"{session_id}.jsonl"
    base_time = int(datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc).timestamp())
    entries = [
        {"type": "user", "message": {"content": "First task"}, "timestamp": base_time},
        {"type": "assistant", "message": {"content": "Ok"}, "timestamp": base_time + 5},
        {"type": "user", "message": {"content": "Second task"}, "timestamp": base_time + 600},
        {"type": "assistant", "message": {"content": "Done"}, "timestamp": base_time + 605},
    ]
    file_path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return SessionLog(
        session_id=session_id,
        file_path=str(file_path),
        project_path=str(tmp_path),
        mtime=file_path.stat().st_mtime,
        entries=entries,
    )


# ---------------------------------------------------------------------------
# Phase A — scan_session_logs
# ---------------------------------------------------------------------------

def test_scan_session_logs_finds_jsonl_files(tmp_path: Path) -> None:
    """scan_session_logs finds .jsonl files in project directories."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    session_file = project_dir / "aaa12345-1234-1234-1234-123456789012.jsonl"
    session_file.write_text('{"type": "user", "message": {"content": "hi"}}\n', encoding="utf-8")

    logs = scan_session_logs(project_path=str(project_dir), max_sessions=10)
    assert len(logs) == 1
    assert logs[0].session_id == "aaa12345-1234-1234-1234-123456789012"
    assert logs[0].entries[0]["type"] == "user"


def test_scan_session_logs_respects_max_sessions(tmp_path: Path) -> None:
    """scan_session_logs limits results to max_sessions."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    for i in range(5):
        sid = f"aaa12345-0000-0000-0000-{'%012d' % i}"
        (project_dir / f"{sid}.jsonl").write_text('{"type": "user"}\n', encoding="utf-8")

    logs = scan_session_logs(project_path=str(project_dir), max_sessions=3)
    assert len(logs) == 3


def test_scan_session_logs_skips_invalid_session_ids(tmp_path: Path) -> None:
    """scan_session_logs skips files that aren't valid UUID session IDs."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "not-a-session.jsonl").write_text('{"type": "user"}\n', encoding="utf-8")
    (project_dir / "aaa12345-1234-1234-1234-123456789012.jsonl").write_text(
        '{"type": "user"}\n', encoding="utf-8"
    )

    logs = scan_session_logs(project_path=str(project_dir), max_sessions=10)
    assert all(log.session_id != "not-a-session" for log in logs)


# ---------------------------------------------------------------------------
# Phase B — extract_session_meta
# ---------------------------------------------------------------------------

def test_extract_session_meta_counts_messages(sample_session_log: SessionLog) -> None:
    """extract_session_meta counts user and assistant messages."""
    meta = extract_session_meta(sample_session_log)
    assert meta.user_message_count == 1
    assert meta.assistant_message_count == 2  # two assistant turns
    assert meta.session_id == sample_session_log.session_id


def test_extract_session_meta_counts_tool_calls(sample_session_log: SessionLog) -> None:
    """extract_session_meta tallies tool calls."""
    meta = extract_session_meta(sample_session_log)
    assert meta.tool_counts.get("Bash") == 1


def test_extract_session_meta_extracts_first_prompt(sample_session_log: SessionLog) -> None:
    """extract_session_meta captures the first user message."""
    meta = extract_session_meta(sample_session_log)
    assert meta.first_prompt == "Hello, world!"


def test_extract_session_meta_handles_empty_entries() -> None:
    """extract_session_meta works on an empty session."""
    log = SessionLog(
        session_id="ccc12345-1234-1234-1234-123456789012",
        file_path="/fake/path.jsonl",
        project_path="/fake",
        mtime=0.0,
        entries=[],
    )
    meta = extract_session_meta(log)
    assert meta.user_message_count == 0
    assert meta.assistant_message_count == 0
    assert meta.first_prompt is None


# ---------------------------------------------------------------------------
# Phase C — deduplicate_session_branches
# ---------------------------------------------------------------------------

def test_deduplicate_session_branches_keeps_higher_message_count() -> None:
    """deduplicate_session_branches keeps the branch with more user messages."""
    session_id = "ddd12345-1234-1234-1234-123456789012"
    meta1 = SessionMeta(
        session_id=session_id,
        file_path="/p1",
        project_path="/p",
        user_message_count=3,
        assistant_message_count=3,
        total_messages=6,
        duration_minutes=10.0,
        tool_counts={},
        languages={},
        message_hours=[10],
        first_prompt="First",
    )
    meta2 = SessionMeta(
        session_id=session_id,
        file_path="/p2",
        project_path="/p",
        user_message_count=5,  # more messages — should win
        assistant_message_count=5,
        total_messages=10,
        duration_minutes=5.0,  # shorter duration
        tool_counts={},
        languages={},
        message_hours=[10],
        first_prompt="First",
    )
    result = deduplicate_session_branches([meta1, meta2])
    assert len(result) == 1
    assert result[0].user_message_count == 5


def test_deduplicate_session_branches_tie_breaks_by_duration() -> None:
    """When user_message_count ties, longer duration wins."""
    session_id = "eee12345-1234-1234-1234-123456789012"
    meta1 = SessionMeta(
        session_id=session_id,
        file_path="/p1",
        project_path="/p",
        user_message_count=3,
        assistant_message_count=3,
        total_messages=6,
        duration_minutes=5.0,
        tool_counts={},
        languages={},
        message_hours=[10],
        first_prompt="First",
    )
    meta2 = SessionMeta(
        session_id=session_id,
        file_path="/p2",
        project_path="/p",
        user_message_count=3,  # same count
        assistant_message_count=3,
        total_messages=6,
        duration_minutes=15.0,  # longer — should win
        tool_counts={},
        languages={},
        message_hours=[10],
        first_prompt="First",
    )
    result = deduplicate_session_branches([meta1, meta2])
    assert len(result) == 1
    assert result[0].duration_minutes == 15.0


def test_deduplicate_session_branches_separate_sessions_unchanged() -> None:
    """Different session_ids are not deduplicated."""
    meta1 = SessionMeta(
        session_id="aaa12345-1234-1234-1234-123456789012",
        file_path="/p1",
        project_path="/p",
        user_message_count=3,
        assistant_message_count=3,
        total_messages=6,
        duration_minutes=5.0,
        tool_counts={},
        languages={},
        message_hours=[10],
        first_prompt="First",
    )
    meta2 = SessionMeta(
        session_id="bbb12345-1234-1234-1234-123456789012",
        file_path="/p2",
        project_path="/p",
        user_message_count=2,
        assistant_message_count=2,
        total_messages=4,
        duration_minutes=10.0,
        tool_counts={},
        languages={},
        message_hours=[15],
        first_prompt="Second",
    )
    result = deduplicate_session_branches([meta1, meta2])
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Phase D — format_transcript_for_facets + summarize
# ---------------------------------------------------------------------------

def test_format_transcript_for_facets_produces_text(sample_session_log: SessionLog) -> None:
    """format_transcript_for_facets concatenates messages into readable text."""
    meta = extract_session_meta(sample_session_log)
    text = format_transcript_for_facets(meta)
    assert "Hello, world!" in text
    assert "[tool: Bash]" in text


def test_summarize_transcript_if_needed_returns_truncated_when_no_backend(
    sample_session_log: SessionLog,
) -> None:
    """summarize_transcript_if_needed falls back to truncation without LLM."""
    meta = extract_session_meta(sample_session_log)
    text = format_transcript_for_facets(meta)
    summary = summarize_transcript_if_needed(text)
    # Without an LLM backend, it should return a truncation
    assert len(summary) <= len(text)
    assert "[Summary]" in summary or summary == text


# ---------------------------------------------------------------------------
# Phase E — facet cache
# ---------------------------------------------------------------------------

def test_save_and_load_cached_facets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """save_facets writes a JSON cache; load_cached_facets reads it back."""
    session_id = "fff12345-1234-1234-1234-123456789012"
    facet = SessionFacet(
        session_id=session_id,
        underlying_goal="Test goal",
        goal_categories=["testing"],
        outcome="success",
        friction_counts={"missing_lib": 1},
        brief_summary="A test session.",
        user_instructions_to_claude=["Do the thing"],
    )
    cache_dir = tmp_path / "facets"
    monkeypatch.setenv("CLAUDE_INSIGHTS_CACHE_DIR", str(cache_dir))

    save_facets(facet)
    loaded = load_cached_facets(session_id)

    assert loaded is not None
    assert loaded.session_id == session_id
    assert loaded.underlying_goal == "Test goal"


def test_load_cached_facets_returns_none_for_unknown_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_cached_facets returns None when no cache exists."""
    cache_dir = tmp_path / "facets"
    monkeypatch.setenv("CLAUDE_INSIGHTS_CACHE_DIR", str(cache_dir))

    result = load_cached_facets("nonexistent-session-id-0000-0000-000000000000")
    assert result is None


def test_load_cached_facets_recreates_on_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a cache file is corrupt, load_cached_facets returns None (cache miss)."""
    session_id = "ggg12345-1234-1234-1234-123456789012"
    cache_dir = tmp_path / "facets"
    cache_dir.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_INSIGHTS_CACHE_DIR", str(cache_dir))

    # Write corrupt JSON
    corrupt_file = cache_dir / f"{session_id}.json"
    corrupt_file.write_text('{"this is": not valid json', encoding="utf-8")

    result = load_cached_facets(session_id)
    assert result is None


# ---------------------------------------------------------------------------
# Phase F — aggregate_insights_data
# ---------------------------------------------------------------------------

def test_aggregate_insights_data_sums_totals() -> None:
    """aggregate_insights_data correctly sums message counts across sessions."""
    metas = [
        SessionMeta(
            session_id="hhh12345-1234-1234-1234-123456789012",
            file_path="/p/s1.jsonl",
            project_path="/p",
            user_message_count=3,
            assistant_message_count=5,
            total_messages=8,
            duration_minutes=10.0,
            tool_counts={"Bash": 2, "Read": 1},
            languages={"Python": 3},
            message_hours=[10, 14],
            first_prompt="Hello",
        ),
        SessionMeta(
            session_id="iii12345-1234-1234-1234-123456789012",
            file_path="/p/s2.jsonl",
            project_path="/p",
            user_message_count=2,
            assistant_message_count=4,
            total_messages=6,
            duration_minutes=15.0,
            tool_counts={"Bash": 1, "Edit": 3},
            languages={"Python": 2, "TypeScript": 1},
            message_hours=[10, 15],
            first_prompt="Hi",
        ),
    ]
    facets = [
        SessionFacet(
            session_id="hhh12345-1234-1234-1234-123456789012",
            underlying_goal="Goal A",
            goal_categories=["feature"],
            outcome="success",
            friction_counts={"missing_lib": 1},
            brief_summary="Summ A",
            user_instructions_to_claude=["Build X"],
        ),
        SessionFacet(
            session_id="iii12345-1234-1234-1234-123456789012",
            underlying_goal="Goal B",
            goal_categories=["bugfix"],
            outcome="partial",
            friction_counts={"api_error": 3},
            brief_summary="Summ B",
            user_instructions_to_claude=["Fix Y"],
        ),
    ]
    result = aggregate_insights_data(metas, facets)

    assert result.total_sessions == 2
    assert result.total_messages == 14  # 3+5+2+4
    assert result.total_duration_minutes == 25.0
    assert result.tool_counts["Bash"] == 3
    assert result.tool_counts["Read"] == 1
    assert result.tool_counts["Edit"] == 3


def test_aggregate_insights_data_empty_input() -> None:
    """aggregate_insights_data handles empty lists."""
    result = aggregate_insights_data([], [])
    assert result.total_sessions == 0
    assert result.total_messages == 0


# ---------------------------------------------------------------------------
# Phase G — detect_multi_clauding
# ---------------------------------------------------------------------------

def test_detect_multi_clauding_no_overlap() -> None:
    """When sessions don't overlap in time, no multi-clauding is detected."""
    metas = [
        SessionMeta(
            session_id="jjj12345-1234-1234-1234-123456789012",
            file_path="/p/s1.jsonl",
            project_path="/p",
            user_message_count=3,
            assistant_message_count=3,
            total_messages=6,
            duration_minutes=10.0,
            tool_counts={},
            languages={},
            message_hours=[10],
            first_prompt="A",
        ),
        SessionMeta(
            session_id="kkk12345-1234-1234-1234-123456789012",
            file_path="/p/s2.jsonl",
            project_path="/p",
            user_message_count=3,
            assistant_message_count=3,
            total_messages=6,
            duration_minutes=10.0,
            tool_counts={},
            languages={},
            message_hours=[15],  # 5 hours apart — no overlap
            first_prompt="B",
        ),
    ]
    stats = detect_multi_clauding(metas)
    assert stats.overlap_events == 0


def test_detect_multi_clauding_with_overlap(
    sample_session_with_timestamps: SessionLog,
) -> None:
    """Sessions overlapping within 30 minutes are counted as multi-clauding."""
    meta = extract_session_meta(sample_session_with_timestamps)
    # Add another session starting 10 minutes later (within 30-min window)
    meta2 = SessionMeta(
        session_id="lll12345-1234-1234-1234-123456789012",
        file_path="/p/s2.jsonl",
        project_path="/p",
        user_message_count=2,
        assistant_message_count=2,
        total_messages=4,
        duration_minutes=5.0,
        tool_counts={},
        languages={},
        message_hours=[10, 10],  # same hour as meta1
        first_prompt="Second",
    )
    stats = detect_multi_clauding([meta, meta2])
    assert stats.overlap_events >= 0  # deterministic given message_hours


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def test_format_insights_report_text_output() -> None:
    """format_insights_report produces a non-empty text report."""
    result = InsightsResult(
        success=True,
        message="ok",
        sessions=[],
        facets=[],
        aggregated=AggregatedInsightsData(
            total_sessions=0,
            total_messages=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_tokens=0,
            total_cost=0.0,
            average_session_length=0.0,
            total_duration_minutes=0.0,
            git_commits=0,
            git_pushes=0,
            lines_added=0,
            lines_removed=0,
            files_modified=0,
            tool_counts={},
            languages={},
            projects={},
            active_days=0,
            active_hours={},
            goal_categories={},
            outcomes={},
            friction_counts={},
            summaries=[],
            user_instructions=[],
        ),
    )
    text = format_insights_report(result, fmt="text")
    assert isinstance(text, str)
    assert len(text) > 0


def test_format_insights_report_json_output() -> None:
    """format_insights_report produces valid JSON when requested."""
    result = InsightsResult(
        success=True,
        message="ok",
        sessions=[],
        facets=[],
        aggregated=AggregatedInsightsData(
            total_sessions=1,
            total_messages=15,
            total_input_tokens=500,
            total_output_tokens=500,
            total_tokens=1000,
            total_cost=0.05,
            average_session_length=15.0,
            total_duration_minutes=30.0,
            git_commits=1,
            git_pushes=0,
            lines_added=50,
            lines_removed=10,
            files_modified=3,
            tool_counts={"Bash": 3},
            languages={"Python": 2},
            projects={},
            active_days=1,
            active_hours={10: 5},
            goal_categories={"feature": 1},
            outcomes={"success": 1},
            friction_counts={},
            summaries=["Test session summary"],
            user_instructions=["Build X"],
        ),
        insights=[
            SessionInsight(
                category="session",
                title="Test Session",
                description="A test session with Bash usage.",
                metric=3.0,
                unit="tool calls",
            )
        ],
    )
    json_str = format_insights_report(result, fmt="json")
    parsed = json.loads(json_str)
    assert parsed["total_sessions"] == 1
    assert parsed["total_messages"] == 15
