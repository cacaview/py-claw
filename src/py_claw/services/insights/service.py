"""
Insights service — deeper pipeline backed by session_storage.

Based on ClaudeCode-main/src/commands/insights.ts and src/services/insights.ts.

Pipeline phases (mirroring TS reference):
  A. Scan ~/.claude/projects/*/*.jsonl  → SessionLog[]
  B. Extract per-session metadata        → SessionMeta[]
  C. Deduplicate branches (same session_id, keep highest-message branch)
  D. Format transcripts + optional LLM summarization
  E. Load / save per-session facet cache (~/.claude/usage-data/facets/)
  F. Aggregate across sessions
  G. Detect multi-clauding overlap
  H. Generate narrative sections (LLM-driven, deferred)
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import (
    AggregatedInsightsData,
    InsightsConfig,
    InsightsResult,
    MultiClaudingStats,
    NarrativeSections,
    SessionFacet,
    SessionLog,
    SessionMeta,
    SessionInsight,
    UsageStats,
)

logger = logging.getLogger(__name__)

_insights_config = InsightsConfig()

# ---------------------------------------------------------------------------
# Extension → language map (inlined to keep service dependency-free on commands.py)
# ---------------------------------------------------------------------------
_EXT_TO_LANG: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".jsx": "JavaScript (JSX)",
    ".tsx": "TypeScript (TSX)", ".java": "Java", ".go": "Go", ".rs": "Rust",
    ".rb": "Ruby", ".c": "C", ".cpp": "C++", ".cc": "C++", ".cxx": "C++",
    ".h": "C Header", ".hpp": "C++ Header", ".cs": "C#", ".swift": "Swift",
    ".kt": "Kotlin", ".kts": "Kotlin", ".php": "PHP", ".lua": "Lua",
    ".r": "R", ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang",
    ".scala": "Scala", ".groovy": "Groovy", ".gradle": "Gradle",
    ".vue": "Vue", ".svelte": "Svelte", ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sass": "Sass", ".less": "Less",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".xml": "XML", ".md": "Markdown", ".rst": "reStructuredText",
    ".sh": "Shell", ".bash": "Bash", ".zsh": "Zsh", ".fish": "Fish",
    ".ps1": "PowerShell", ".psm1": "PowerShell",
    ".sql": "SQL", ".duckdb": "SQL",
    ".tf": "Terraform", ".hcl": "HCL",
    ".dockerfile": "Dockerfile", ".dockerignore": "Docker",
    ".gitignore": "Git", ".gitattributes": "Git",
    ".pem": "PEM", ".key": "Key", ".crt": "Certificate",
    ".svg": "SVG", ".png": "Image", ".jpg": "Image", ".jpeg": "Image",
    ".gif": "Image", ".webp": "Image", ".ico": "Icon",
    ".pdf": "PDF", ".zip": "Archive", ".tar": "Archive", ".gz": "Archive",
    ".mp4": "Video", ".mov": "Video", ".avi": "Video",
    ".mp3": "Audio", ".wav": "Audio", ".flac": "Audio",
    ".ttf": "Font", ".otf": "Font", ".woff": "Font", ".woff2": "Font",
    ".csv": "CSV", ".tsv": "TSV", ".parquet": "Parquet",
    ".ipynb": "Jupyter Notebook",
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def get_insights_config() -> InsightsConfig:
    """Get the insights configuration."""
    return _insights_config


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _get_config_home() -> Path:
    if "CLAUDE_CONFIG_DIR" in os.environ:
        return Path(os.environ["CLAUDE_CONFIG_DIR"])
    return Path.home() / ".claude"


def _get_projects_dir() -> Path:
    return _get_config_home() / "projects"


def _get_facets_cache_dir() -> Path:
    d = _get_config_home() / "usage-data" / "facets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_usage_data_dir() -> Path:
    d = _get_config_home() / "usage-data"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Phase A — scan session logs
# ---------------------------------------------------------------------------


def scan_session_logs(
    project_path: str | None = None,
    max_sessions: int = 100,
) -> list[SessionLog]:
    """Scan session JSONL files from the projects tree.

    Args:
        project_path: Optional specific project path to scan.
                     If None, scans all projects under ~/.claude/projects/.
        max_sessions: Maximum number of session files to return (most-recent first).

    Returns:
        List of SessionLog objects sorted by mtime descending.
    """
    logs: list[SessionLog] = []

    if project_path:
        projects_to_scan = [(str(project_path), Path(project_path))]
    else:
        projects_dir = _get_projects_dir()
        if projects_dir.exists():
            projects_to_scan = [
                (str(p.name), p) for p in projects_dir.iterdir() if p.is_dir()
            ]
        else:
            projects_to_scan = []

    for _proj_name, proj_dir in projects_to_scan:
        if not proj_dir.exists():
            continue
        try:
            for entry in sorted(proj_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if not entry.name.endswith(".jsonl"):
                    continue
                session_id = entry.name[: -len(".jsonl")]
                if not _is_valid_session_id(session_id):
                    continue
                try:
                    stat = entry.stat()
                    entries = _load_jsonl_entries(str(entry))
                    logs.append(
                        SessionLog(
                            session_id=session_id,
                            file_path=str(entry),
                            project_path=str(proj_dir),
                            mtime=stat.st_mtime,
                            entries=entries,
                        )
                    )
                    if len(logs) >= max_sessions:
                        return logs
                except OSError:
                    continue
        except OSError:
            continue

    # Sort all by mtime descending
    logs.sort(key=lambda l: l.mtime, reverse=True)
    return logs[:max_sessions]


def _is_valid_session_id(session_id: str) -> bool:
    if len(session_id) != 36:
        return False
    parts = session_id.split("-")
    return len(parts) == 5 and len(parts[0]) == 8


def _load_jsonl_entries(file_path: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except (IOError, OSError):
        pass
    return entries


# ---------------------------------------------------------------------------
# Phase B — extract per-session metadata
# ---------------------------------------------------------------------------


def extract_session_meta(log: SessionLog) -> SessionMeta:
    """Derive SessionMeta from a raw SessionLog.

    Mirrors ClaudeCode-main/src/commands/insights.ts extractToolStats + logToSessionMeta.
    """
    user_msg_count = 0
    assistant_msg_count = 0
    input_tokens = 0
    output_tokens = 0
    tool_counts: dict[str, int] = defaultdict(int)
    languages: dict[str, int] = defaultdict(int)
    files_modified: list[str] = []
    lines_added = 0
    lines_removed = 0
    git_commits = 0
    git_pushes = 0
    timestamps: list[float] = []
    message_hours: list[int] = []
    first_prompt: str | None = None
    custom_title: str | None = None
    tag: str | None = None

    for entry in log.entries:
        etype = entry.get("type", "")

        if etype == "user":
            user_msg_count += 1
            # Extract first prompt
            if first_prompt is None and not _is_meta_entry(entry):
                content = entry.get("message", {}).get("content", "")
                if isinstance(content, str) and content.strip():
                    first_prompt = content.strip()[:200]
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                first_prompt = text[:200]
                                break

            ts = _extract_timestamp(entry)
            if ts:
                timestamps.append(ts)
                message_hours.append(datetime.fromtimestamp(ts).hour)

        elif etype == "assistant":
            assistant_msg_count += 1
            usage = entry.get("message", {}).get("usage", {})
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)

            content = entry.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_counts[tool_name] += 1

                        inp = block.get("input", {})
                        file_path = inp.get("file_path", "")
                        if file_path:
                            lang = _EXT_TO_LANG.get(Path(file_path).suffix.lower())
                            if lang:
                                languages[lang] += 1
                            if tool_name in ("Edit", "Write"):
                                files_modified.append(file_path)
                            if tool_name == "Edit":
                                old_str = inp.get("old_string", "") or ""
                                new_str = inp.get("new_string", "") or ""
                                lines_added += new_str.count("\n") + (1 if new_str and not new_str.endswith("\n") else 0)
                                lines_removed += old_str.count("\n") + (1 if old_str and not old_str.endswith("\n") else 0)
                            elif tool_name == "Write":
                                content_str = inp.get("content", "") or ""
                                lines_added += content_str.count("\n") + (1 if content_str else 0)

                        cmd = inp.get("command", "")
                        if "git commit" in cmd:
                            git_commits += 1
                        if "git push" in cmd:
                            git_pushes += 1

        elif etype == "session_start":
            custom_title = entry.get("customTitle") or custom_title
            tag = entry.get("tag") or tag

        ts = _extract_timestamp(entry)
        if ts:
            timestamps.append(ts)

    # Duration
    duration_minutes = 0.0
    if timestamps:
        duration_minutes = (max(timestamps) - min(timestamps)) / 60.0

    # Active days
    active_days = sorted(set(
        datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        for ts in timestamps
    ))

    return SessionMeta(
        session_id=log.session_id,
        file_path=log.file_path,
        project_path=log.project_path,
        user_message_count=user_msg_count,
        assistant_message_count=assistant_msg_count,
        total_messages=user_msg_count + assistant_msg_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_minutes=duration_minutes,
        tool_counts=dict(tool_counts),
        languages=dict(languages),
        files_modified=files_modified,
        lines_added=lines_added,
        lines_removed=lines_removed,
        git_commits=git_commits,
        git_pushes=git_pushes,
        message_hours=message_hours,
        message_timestamps=timestamps,
        active_days=active_days,
        first_prompt=first_prompt,
        custom_title=custom_title,
        tag=tag,
    )


def _extract_timestamp(entry: dict[str, Any]) -> float | None:
    ts = entry.get("timestamp")
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _is_meta_entry(entry: dict[str, Any]) -> bool:
    return bool(
        entry.get("isMeta") or entry.get("isCompactSummary") or entry.get("type") == "system"
    )


# ---------------------------------------------------------------------------
# Phase C — branch deduplication
# ---------------------------------------------------------------------------


def deduplicate_session_branches(
    metas: list[SessionMeta],
) -> list[SessionMeta]:
    """Deduplicate session branches, keeping the most-active branch per session_id.

    Mirrors ClaudeCode-main/src/commands/insights.ts deduplicateSessionBranches.

    Tie-breaking order:
      1. Higher user_message_count
      2. Longer duration_minutes
    """
    # Group by session_id
    by_id: dict[str, list[SessionMeta]] = defaultdict(list)
    for m in metas:
        by_id[m.session_id].append(m)

    result: list[SessionMeta] = []
    for _sid, branches in by_id.items():
        if len(branches) == 1:
            result.append(branches[0])
        else:
            best = max(
                branches,
                key=lambda m: (m.user_message_count, m.duration_minutes),
            )
            result.append(best)
    return result


# ---------------------------------------------------------------------------
# Phase D — transcript formatting
# ---------------------------------------------------------------------------


def format_transcript_for_facets(meta: SessionMeta) -> str:
    """Build a plain-text transcript suitable for facet extraction.

    Mirrors ClaudeCode-main/src/commands/insights.ts formatTranscriptForFacets.
    """
    lines: list[str] = []
    lines.append(f"=== Session {meta.session_id} ===")
    if meta.first_prompt:
        lines.append(f"First prompt: {meta.first_prompt}")

    # Re-parse entries to format
    entries = _load_jsonl_entries(meta.file_path)
    for entry in entries:
        etype = entry.get("type", "")
        if etype == "user":
            content = _entry_text_content(entry)
            if content:
                lines.append(f"[User]: {content}")
        elif etype == "assistant":
            content = _entry_text_content(entry)
            if content:
                lines.append(f"[Assistant]: {content}")
        elif etype == "system":
            subtype = entry.get("subtype", "")
            if subtype:
                lines.append(f"[System/{subtype}]")
        elif etype == "tool":
            name = entry.get("name", "?")
            inp = entry.get("input", {})
            summary = inp.get("description") or inp.get("command") or str(inp)[:80]
            lines.append(f"[Tool: {name}]: {summary}")

    return "\n".join(lines)


def _entry_text_content(entry: dict[str, Any]) -> str:
    content = entry.get("message", {}).get("content", "") or ""
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    parts.append(f"[tool: {block.get('name', '?')}]")
        content = " ".join(parts)
    return str(content).strip()


def summarize_transcript_if_needed(
    transcript: str,
    config: InsightsConfig | None = None,
) -> str:
    """Truncate transcript if under char limit; placeholder for LLM summarization.

    When a real LLM client is wired in (future), this performs chunk summarization
    per ClaudeCode-main/src/commands/insights.ts summarizeTranscriptChunk.
    For now, truncate to avoid losing context.

    Args:
        transcript: Plain-text transcript.
        config: InsightsConfig controlling thresholds.

    Returns:
        The (possibly truncated/summarized) transcript.
    """
    cfg = config or _insights_config
    limit = cfg.transcript_summary_char_limit
    chunk_size = cfg.transcript_summary_chunk_size

    if len(transcript) <= limit:
        return transcript

    # Split into chunks and take first + last portion (cheap approximation)
    # Real implementation would call LLM summarization per chunk.
    head = transcript[:chunk_size]
    tail = transcript[-chunk_size:]
    overlap = "\n... [session truncated] ...\n"
    return head + overlap + tail


# ---------------------------------------------------------------------------
# Phase E — facet cache
# ---------------------------------------------------------------------------


def get_facet_cache_path(session_id: str) -> Path:
    """Path to the per-session facet JSON cache file."""
    return _get_facets_cache_dir() / f"{session_id}.json"


def load_cached_facets(session_id: str) -> SessionFacet | None:
    """Load cached facets for a session, or None if missing / corrupt."""
    cache_path = get_facet_cache_path(session_id)
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)
        # Basic validation: must have session_id and required string fields
        if not isinstance(data, dict) or data.get("session_id") != session_id:
            cache_path.unlink(missing_ok=True)
            return None
        return SessionFacet(
            session_id=data.get("session_id", session_id),
            underlying_goal=data.get("underlying_goal", ""),
            goal_categories=data.get("goal_categories") or [],
            outcome=data.get("outcome", "unknown"),
            friction_counts=data.get("friction_counts") or {},
            brief_summary=data.get("brief_summary", ""),
            user_instructions_to_claude=data.get("user_instructions_to_claude") or [],
        )
    except Exception:
        cache_path.unlink(missing_ok=True)
        return None


def save_facets(facet: SessionFacet) -> None:
    """Persist a SessionFacet to the per-session cache file."""
    cache_path = get_facet_cache_path(facet.session_id)
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "session_id": facet.session_id,
                    "underlying_goal": facet.underlying_goal,
                    "goal_categories": facet.goal_categories,
                    "outcome": facet.outcome,
                    "friction_counts": facet.friction_counts,
                    "brief_summary": facet.brief_summary,
                    "user_instructions_to_claude": facet.user_instructions_to_claude,
                },
                f,
                indent=2,
            )
    except Exception as e:
        logger.warning("Failed to save facet cache for %s: %s", facet.session_id, e)


# ---------------------------------------------------------------------------
# Phase F — aggregate
# ---------------------------------------------------------------------------


def aggregate_insights_data(
    metas: list[SessionMeta],
    facets: list[SessionFacet],
) -> AggregatedInsightsData:
    """Aggregate per-session metadata + facets into report-wide stats.

    Mirrors ClaudeCode-main/src/commands/insights.ts aggregateData.
    """
    total_sessions = len(metas)
    total_messages = sum(m.total_messages for m in metas)
    total_input = sum(m.input_tokens for m in metas)
    total_output = sum(m.output_tokens for m in metas)
    total_tokens = total_input + total_output
    total_cost = (total_input / 1_000_000 * 0.5) + (total_output / 1_000_000 * 2.5)
    total_duration = sum(m.duration_minutes for m in metas)
    avg_length = total_messages / total_sessions if total_sessions else 0.0

    git_commits = sum(m.git_commits for m in metas)
    git_pushes = sum(m.git_pushes for m in metas)
    lines_added = sum(m.lines_added for m in metas)
    lines_removed = sum(m.lines_removed for m in metas)
    files_modified = len({f for m in metas for f in m.files_modified})

    # Tool / language / project counts
    tool_counts: dict[str, int] = defaultdict(int)
    languages: dict[str, int] = defaultdict(int)
    projects: dict[str, int] = defaultdict(int)
    for m in metas:
        for t, c in m.tool_counts.items():
            tool_counts[t] += c
        for lang, c in m.languages.items():
            languages[lang] += c
        if m.project_path:
            projects[m.project_path] += 1

    # Active days
    all_days = sorted(set(d for m in metas for d in m.active_days))
    active_days = len(all_days)

    # Hour histogram
    hour_hist: dict[int, int] = defaultdict(int)
    for m in metas:
        for h in m.message_hours:
            hour_hist[h] += 1

    # Facet-derived distributions
    goal_categories: dict[str, int] = defaultdict(int)
    outcomes: dict[str, int] = defaultdict(int)
    friction_counts: dict[str, int] = defaultdict(int)
    for f in facets:
        for cat in f.goal_categories:
            goal_categories[cat] += 1
        if f.outcome:
            outcomes[f.outcome] += 1
        for ff, cnt in f.friction_counts.items():
            friction_counts[ff] += cnt

    # Summaries / instructions
    summaries = [f.brief_summary for f in facets if f.brief_summary]
    user_instructions = [inst for f in facets for inst in f.user_instructions_to_claude]

    return AggregatedInsightsData(
        total_sessions=total_sessions,
        total_messages=total_messages,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_tokens,
        total_cost=total_cost,
        average_session_length=avg_length,
        total_duration_minutes=total_duration,
        git_commits=git_commits,
        git_pushes=git_pushes,
        lines_added=lines_added,
        lines_removed=lines_removed,
        files_modified=files_modified,
        tool_counts=dict(tool_counts),
        languages=dict(languages),
        projects=dict(projects),
        active_days=active_days,
        active_hours=dict(hour_hist),
        goal_categories=dict(goal_categories),
        outcomes=dict(outcomes),
        friction_counts=dict(friction_counts),
        summaries=summaries,
        user_instructions=user_instructions,
        multi_clauding=MultiClaudingStats(),
    )


# ---------------------------------------------------------------------------
# Phase G — multi-clauding detection
# ---------------------------------------------------------------------------


def detect_multi_clauding(metas: list[SessionMeta]) -> MultiClaudingStats:
    """Detect overlapping session activity across time.

    Uses a 30-minute sliding window.  Mirrors ClaudeCode-main/src/commands/insights.ts
    detectMultiClauding.
    """
    # Collect all (session_id, timestamp) pairs sorted by time
    events: list[tuple[float, str]] = []
    for m in metas:
        for ts in m.message_timestamps:
            events.append((ts, m.session_id))
    events.sort(key=lambda x: x[0])

    if not events:
        return MultiClaudingStats()

    WINDOW = 30 * 60  # 30 minutes in seconds
    overlap_events = 0
    involved_sessions: set[str] = set()
    user_msgs_during = 0

    i = 0
    while i < len(events):
        window_start = events[i][0]
        window_end = window_start + WINDOW
        # Find all sessions active in this window
        active: set[str] = set()
        j = i
        while j < len(events) and events[j][0] <= window_end:
            active.add(events[j][1])
            j += 1
        if len(active) > 1:
            overlap_events += 1
            involved_sessions.update(active)
            # Count user messages in this window
            k = i
            while k < len(events) and events[k][0] <= window_end:
                # Find the meta for this event's session
                sid = events[k][1]
                for m in metas:
                    if m.session_id == sid:
                        # Approximate: count proportionally
                        user_msgs_during += 1
                        break
                k += 1
        i += 1

    return MultiClaudingStats(
        overlap_events=overlap_events,
        sessions_involved=len(involved_sessions),
        user_messages_during=min(user_msgs_during, 9999),
    )


# ---------------------------------------------------------------------------
# Phase H — narrative generation (stub, future LLM)
# ---------------------------------------------------------------------------


def generate_narrative_sections(
    data: AggregatedInsightsData,
    facets: list[SessionFacet],
) -> NarrativeSections:
    """Generate human-readable narrative sections from aggregated data.

    This is a pure-text stub for now.  The full TS implementation calls an LLM
    per section with JSON-only output.  When a model client is wired in, replace
    the stubs below with actual async calls.
    """
    # Basic fallback narratives
    top_tool = max(data.tool_counts, key=data.tool_counts.get) if data.tool_counts else None
    top_lang = max(data.languages, key=data.languages.get) if data.languages else None

    at_a_glance = (
        f"You've had {data.total_sessions} sessions across {data.active_days} active days, "
        f"processing {data.total_messages:,} messages."
        + (f" Your most-used tool was {top_tool}." if top_tool else "")
        + (f" You coded mostly in {top_lang}." if top_lang else "")
    )

    suggestions = []
    if data.total_messages > 500:
        suggestions.append("Consider using /compact regularly to keep context fresh.")
    if data.lines_added > 5000:
        suggestions.append("High code output detected — consider reviewing changes with /diff.")
    if not suggestions:
        suggestions.append("Keep up the productive sessions!")

    return NarrativeSections(
        at_a_glance=at_a_glance,
        what_works="Consistent tool usage and session patterns suggest a solid workflow.",
        friction_analysis=_summarize_friction(data.friction_counts),
        suggestions="\n".join(f"- {s}" for s in suggestions),
    )


def _summarize_friction(friction: dict[str, int]) -> str:
    if not friction:
        return "No significant friction points detected."
    top = sorted(friction.items(), key=lambda x: x[1], reverse=True)[:3]
    parts = [f"{cause} ({cnt}x)" for cause, cnt in top]
    return "Top friction: " + ", ".join(parts) if parts else "Low friction."


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def generate_insights_report(
    project_path: str | None = None,
) -> InsightsResult:
    """Run the full insights pipeline and return structured results.

    Args:
        project_path: Optional project to scope the report to.

    Returns:
        InsightsResult containing sessions, facets, aggregates, and insights.
    """
    try:
        # Phase A: scan
        logs = scan_session_logs(project_path=project_path, max_sessions=_insights_config.max_sessions)
        if not logs:
            return InsightsResult(
                success=True,
                message="No session data found.",
            )

        # Phase B: extract metadata
        metas = [extract_session_meta(log) for log in logs]

        # Phase C: deduplicate
        metas = deduplicate_session_branches(metas)

        # Phase D: format + summarize transcripts for facet extraction
        transcripts: dict[str, str] = {}
        for m in metas:
            raw = format_transcript_for_facets(m)
            transcripts[m.session_id] = summarize_transcript_if_needed(raw)

        # Phase E: load/create facets
        facets: list[SessionFacet] = []
        for m in metas:
            cached = load_cached_facets(m.session_id)
            if cached:
                facets.append(cached)
            else:
                # Future: call LLM to extract facets here
                facet = _stub_facet_for_session(m.session_id)
                save_facets(facet)
                facets.append(facet)

        # Phase F: aggregate
        agg = aggregate_insights_data(metas, facets)
        agg.multi_clauding = detect_multi_clauding(metas)

        # Phase H: narratives (stub)
        agg.narratives = generate_narrative_sections(agg, facets)

        # Build legacy UsageStats + SessionInsight for backwards compat
        usage_stats = UsageStats(
            total_sessions=agg.total_sessions,
            total_messages=agg.total_messages,
            total_tokens=agg.total_tokens,
            total_cost=agg.total_cost,
            average_session_length=agg.average_session_length,
        )

        insights = _build_insights(agg)

        return InsightsResult(
            success=True,
            message="Insights generated successfully.",
            insights=insights,
            usage_stats=usage_stats,
            sessions=metas,
            facets=facets,
            aggregated=agg,
        )

    except Exception as e:
        logger.exception("Error generating insights")
        return InsightsResult(success=False, message=f"Error: {e}")


def _stub_facet_for_session(session_id: str) -> SessionFacet:
    """Return a stub facet when LLM extraction is not wired in yet."""
    return SessionFacet(
        session_id=session_id,
        underlying_goal="",
        goal_categories=[],
        outcome="unknown",
        friction_counts={},
        brief_summary="",
        user_instructions_to_claude=[],
    )


def _build_insights(agg: AggregatedInsightsData) -> list[SessionInsight]:
    """Derive SessionInsight list from aggregated data (legacy + new)."""
    insights: list[SessionInsight] = []

    if agg.total_sessions == 0:
        insights.append(SessionInsight(
            category="Getting Started",
            title="No sessions yet",
            description="Start using Claude Code to see insights about your usage patterns.",
        ))
        return insights

    if agg.active_days > 5:
        insights.append(SessionInsight(
            category="Engagement",
            title="Active user",
            description=f"You've been active on {agg.active_days} different days. Keep it up!",
            metric=agg.active_days,
            unit="days",
        ))

    top_tool = max(agg.tool_counts, key=agg.tool_counts.get, default=None) if agg.tool_counts else None
    if top_tool:
        count = agg.tool_counts[top_tool]
        insights.append(SessionInsight(
            category="Tools",
            title=f"Most used: {top_tool}",
            description=f"You've used {top_tool} {count} times across all sessions.",
            metric=count,
            unit="uses",
        ))

    if agg.total_messages > 100:
        insights.append(SessionInsight(
            category="Productivity",
            title="High message volume",
            description=f"You've processed {agg.total_messages:,} messages. Consider /compact for long sessions.",
            metric=agg.total_messages,
            unit="messages",
        ))

    if agg.total_tokens > 100_000:
        insights.append(SessionInsight(
            category="Context Usage",
            title="Heavy context user",
            description="Your sessions use significant context. Regular compaction helps.",
            metric=agg.total_tokens,
            unit="tokens",
        ))

    if agg.multi_clauding.overlap_events > 0:
        insights.append(SessionInsight(
            category="Multi-Session",
            title="Overlapping sessions detected",
            description=f"{agg.multi_clauding.overlap_events} overlap events across "
                       f"{agg.multi_clauding.sessions_involved} sessions.",
            metric=agg.multi_clauding.overlap_events,
            unit="overlaps",
        ))

    return insights


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def format_insights_report(
    result: InsightsResult,
    fmt: str = "text",
) -> str:
    """Format an InsightsResult for CLI output.

    Args:
        result: The pipeline result.
        fmt: 'text' (default), 'json', or 'html'.

    Returns:
        Formatted string.
    """
    if not result.success:
        return f"Error: {result.message}"

    if fmt == "json":
        return _format_insights_json(result)
    if fmt == "html":
        return _format_insights_html(result)

    return _format_insights_text(result)


def _format_insights_text(result: InsightsResult) -> str:
    agg = result.aggregated
    if agg is None:
        return "No data to display."

    def fmt(n):
        return f"{n:,}"

    lines = [
        "╭──────────────────────────────────────────────────────────────────╮",
        "│                    Claude Code Insights                          │",
        "├──────────────────────────────────────────────────────────────────┤",
        "│                                                                   │",
        f"│   Total Sessions:        {fmt(agg.total_sessions):>10}                      │",
        f"│   Total Messages:        {fmt(agg.total_messages):>10}                      │",
        f"│   Total Input Tokens:    {fmt(agg.total_input_tokens):>10}                      │",
        f"│   Total Output Tokens:   {fmt(agg.total_output_tokens):>10}                      │",
        f"│   Total Tokens:         {fmt(agg.total_tokens):>10}                      │",
        f"│   Estimated Cost:          ${agg.total_cost:>10.2f}                      │",
        f"│   Active Days:           {fmt(agg.active_days):>10}                      │",
        "│                                                                   │",
        "├──────────────────────────────────────────────────────────────────┤",
        "│                      Git Activity                                │",
        "├──────────────────────────────────────────────────────────────────┤",
        f"│   Commits:              {fmt(agg.git_commits):>10}                      │",
        f"│   Pushes:               {fmt(agg.git_pushes):>10}                      │",
        "│                                                                   │",
        "├──────────────────────────────────────────────────────────────────┤",
        "│                      Code Changes                               │",
        "├──────────────────────────────────────────────────────────────────┤",
        f"│   Lines Added:          {fmt(agg.lines_added):>10}                      │",
        f"│   Lines Removed:         {fmt(agg.lines_removed):>10}                      │",
        f"│   Files Modified:        {fmt(agg.files_modified):>10}                      │",
        "│                                                                   │",
    ]

    top_langs = sorted(agg.languages.items(), key=lambda x: x[1], reverse=True)[:5]
    if top_langs:
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        lines.append("│                  Top Languages                                  │")
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        for i, (lang, cnt) in enumerate(top_langs, 1):
            bar = "█" * min(cnt // 10, 25)
            lines.append(f"│   {i}. {lang:<15} {bar} ({fmt(cnt)})  │")
        lines.append("│                                                                   │")

    top_tools = sorted(agg.tool_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    if top_tools:
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        lines.append("│                    Top Tools                                     │")
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        for i, (tool, cnt) in enumerate(top_tools, 1):
            lines.append(f"│   {i}. {tool:<25} {fmt(cnt):>10}  │")
        lines.append("│                                                                   │")

    top_projects = sorted(agg.projects.items(), key=lambda x: x[1], reverse=True)[:5]
    if top_projects:
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        lines.append("│                    Top Projects                                 │")
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        for i, (proj, cnt) in enumerate(top_projects, 1):
            proj_name = Path(proj).name or proj
            if len(proj_name) > 25:
                proj_name = proj_name[:22] + "..."
            lines.append(f"│   {i}. {proj_name:<25} {fmt(cnt):>10}  │")
        lines.append("│                                                                   │")

    if agg.narratives.at_a_glance:
        lines.append("╰──────────────────────────────────────────────────────────────────╯")
        lines.append("")
        lines.append("─── At a Glance ───────────────────────────────────────────")
        lines.append(agg.narratives.at_a_glance)
        if agg.narratives.suggestions:
            lines.append("")
            lines.append("─── Suggestions ─────────────────────────────────────────")
            lines.append(agg.narratives.suggestions)
        if agg.narratives.friction_analysis:
            lines.append("")
            lines.append("─── Friction Analysis ───────────────────────────────────")
            lines.append(agg.narratives.friction_analysis)
    else:
        lines.append("╰──────────────────────────────────────────────────────────────────╯")

    return "\n".join(lines)


def _format_insights_json(result: InsightsResult) -> str:
    agg = result.aggregated
    sessions = result.sessions
    facets = result.facets

    obj: dict[str, Any] = {
        "total_sessions": agg.total_sessions if agg else 0,
        "total_messages": agg.total_messages if agg else 0,
        "total_tokens": agg.total_tokens if agg else 0,
        "estimated_cost": agg.total_cost if agg else 0.0,
        "active_days": agg.active_days if agg else 0,
        "git_commits": agg.git_commits if agg else 0,
        "git_pushes": agg.git_pushes if agg else 0,
        "lines_added": agg.lines_added if agg else 0,
        "lines_removed": agg.lines_removed if agg else 0,
        "files_modified": agg.files_modified if agg else 0,
        "tool_counts": agg.tool_counts if agg else {},
        "languages": agg.languages if agg else {},
        "projects": agg.projects if agg else {},
        "multi_clauding": {
            "overlap_events": agg.multi_clauding.overlap_events if agg else 0,
            "sessions_involved": agg.multi_clauding.sessions_involved if agg else 0,
            "user_messages_during": agg.multi_clauding.user_messages_during if agg else 0,
        } if agg else {},
        "narratives": {
            "at_a_glance": agg.narratives.at_a_glance if agg else "",
            "what_works": agg.narratives.what_works if agg else "",
            "friction_analysis": agg.narratives.friction_analysis if agg else "",
            "suggestions": agg.narratives.suggestions if agg else "",
        } if agg else {},
    }
    if sessions is not None:
        obj["sessions"] = [
            {
                "session_id": s.session_id,
                "user_messages": s.user_message_count,
                "assistant_messages": s.assistant_message_count,
                "duration_minutes": s.duration_minutes,
                "tool_counts": s.tool_counts,
                "languages": s.languages,
            }
            for s in sessions
        ]
    if facets is not None:
        obj["facets"] = [
            {
                "session_id": f.session_id,
                "outcome": f.outcome,
                "brief_summary": f.brief_summary,
            }
            for f in facets
        ]
    return json.dumps(obj, indent=2)


def _format_insights_html(result: InsightsResult) -> str:
    agg = result.aggregated
    if agg is None:
        return "<p>No data available.</p>"

    top_langs = sorted(agg.languages.items(), key=lambda x: x[1], reverse=True)[:10]
    top_tools = sorted(agg.tool_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    top_projects = sorted(agg.projects.items(), key=lambda x: x[1], reverse=True)[:10]

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Claude Code Insights</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; background: #1a1a2e; color: #eee; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        h1 {{ color: #f4a261; text-align: center; }}
        h2 {{ color: #e9c46a; border-bottom: 1px solid #333; padding-bottom: 8px; margin-top: 30px; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 20px 0; }}
        .stat {{ background: #16213e; padding: 16px; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 1.8em; color: #f4a261; font-weight: bold; }}
        .stat-label {{ color: #888; margin-top: 4px; font-size: 0.85em; }}
        table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ color: #f4a261; }}
        .narrative {{ background: #16213e; padding: 16px; border-radius: 8px; margin-top: 20px; line-height: 1.6; }}
        .suggestions li {{ margin: 4px 0; }}
    </style>
</head>
<body>
<div class="container">
    <h1>Claude Code Insights</h1>
    <div class="stats">
        <div class="stat"><div class="stat-value">{agg.total_sessions:,}</div><div class="stat-label">Sessions</div></div>
        <div class="stat"><div class="stat-value">{agg.total_messages:,}</div><div class="stat-label">Messages</div></div>
        <div class="stat"><div class="stat-value">{agg.total_tokens:,}</div><div class="stat-label">Total Tokens</div></div>
        <div class="stat"><div class="stat-value">{agg.active_days:,}</div><div class="stat-label">Active Days</div></div>
        <div class="stat"><div class="stat-value">+{agg.lines_added:,}</div><div class="stat-label">Lines Added</div></div>
        <div class="stat"><div class="stat-value">-{agg.lines_removed:,}</div><div class="stat-label">Lines Removed</div></div>
        <div class="stat"><div class="stat-value">{agg.git_commits:,}</div><div class="stat-label">Commits</div></div>
        <div class="stat"><div class="stat-value">{agg.git_pushes:,}</div><div class="stat-label">Pushes</div></div>
    </div>
"""
    if top_langs:
        html += "<h2>Languages</h2><table><tr><th>Language</th><th>Count</th></tr>"
        html += "".join(f"<tr><td>{l}</td><td>{c:,}</td></tr>" for l, c in top_langs)
        html += "</table>"
    if top_tools:
        html += "<h2>Tools</h2><table><tr><th>Tool</th><th>Count</th></tr>"
        html += "".join(f"<tr><td>{t}</td><td>{c:,}</td></tr>" for t, c in top_tools)
        html += "</table>"
    if top_projects:
        html += "<h2>Projects</h2><table><tr><th>Project</th><th>Sessions</th></tr>"
        html += "".join(f"<tr><td>{p}</td><td>{c:,}</td></tr>" for p, c in top_projects)
        html += "</table>"
    if agg.narratives.at_a_glance:
        html += f"""
    <h2>Narrative</h2>
    <div class="narrative">
        <p><strong>At a Glance:</strong> {agg.narratives.at_a_glance}</p>
        {('<p><strong>What Works:</strong> ' + agg.narratives.what_works + '</p>') if agg.narratives.what_works else ''}
        {('<p><strong>Friction:</strong> ' + agg.narratives.friction_analysis + '</p>') if agg.narratives.friction_analysis else ''}
        {('<p><strong>Suggestions:</strong></p><ul class="suggestions">' + ''.join(f'<li>{s}</li>' for s in agg.narratives.suggestions.splitlines() if s.strip()) + '</ul>') if agg.narratives.suggestions else ''}
    </div>
"""
    html += "</div></body></html>"
    return html


def write_html_insights(result: InsightsResult, path: str | None = None) -> str:
    """Write insights HTML report to disk.

    Args:
        result: Insights pipeline result.
        path: Optional output path. Defaults to ~/.claude/usage-data/insights.html.

    Returns:
        The absolute path where the file was written.
    """
    if path is None:
        path = str(_get_usage_data_dir() / "insights.html")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_format_insights_html(result))
    return path

