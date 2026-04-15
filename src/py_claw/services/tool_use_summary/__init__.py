"""
Tool use summary service - generates human-readable summaries of completed tool batches.

This service uses Haiku to generate brief summaries of what tools accomplished,
showing them as single-line labels (like git commit subjects).
"""
from __future__ import annotations

from .service import generate_tool_use_summary

__all__ = ["generate_tool_use_summary"]
