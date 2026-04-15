"""Insights service — deeper pipeline backed by session_storage."""
from py_claw.services.insights.service import (
    aggregate_insights_data,
    deduplicate_session_branches,
    detect_multi_clauding,
    extract_session_meta,
    format_insights_report,
    format_transcript_for_facets,
    generate_insights_report,
    generate_narrative_sections,
    get_insights_config,
    load_cached_facets,
    save_facets,
    scan_session_logs,
    summarize_transcript_if_needed,
    write_html_insights,
)
from py_claw.services.insights.types import (
    AggregatedInsightsData,
    InsightsConfig,
    InsightsResult,
    MultiClaudingStats,
    NarrativeSections,
    SessionFacet,
    SessionInsight,
    SessionLog,
    SessionMeta,
    UsageStats,
)

__all__ = [
    # Config
    "get_insights_config",
    # Pipeline phases (public for testability)
    "scan_session_logs",
    "extract_session_meta",
    "deduplicate_session_branches",
    "format_transcript_for_facets",
    "summarize_transcript_if_needed",
    "load_cached_facets",
    "save_facets",
    "aggregate_insights_data",
    "detect_multi_clauding",
    "generate_narrative_sections",
    # Top-level
    "generate_insights_report",
    "format_insights_report",
    "write_html_insights",
    # Types
    "AggregatedInsightsData",
    "InsightsConfig",
    "InsightsResult",
    "MultiClaudingStats",
    "NarrativeSections",
    "SessionFacet",
    "SessionInsight",
    "SessionLog",
    "SessionMeta",
    "UsageStats",
]
