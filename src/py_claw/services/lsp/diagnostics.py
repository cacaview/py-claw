"""
LSP diagnostics registry.

Handles textDocument/publishDiagnostics notifications with deduplication
and rate-limiting to prevent unbounded growth in long sessions.
Based on ClaudeCode-main/src/services/lsp/LSPDiagnosticRegistry.ts.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from py_claw.services.lsp.types import LSPDiagnostic, LSPRange, LSPPosition


@dataclass
class DiagnosticEntry:
    """A single diagnostic entry for deduplication."""

    message: str
    severity: int | None
    range: LSPRange
    source: str | None
    code: int | str | None


class LSPDiagnosticRegistry:
    """Registry for tracking and deduplicating LSP diagnostics.

    Maintains a per-file history of diagnostics to:
    1. Deduplicate across rounds (same diagnostic key = skip)
    2. Rate-limit total diagnostics per file
    3. Track delivery status
    """

    # Limits
    MAX_DIAGNOSTICS_PER_FILE = 100
    MAX_DELIVERY_BATCH_SIZE = 50
    DEDUP_WINDOW_SECONDS = 300

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # file_uri -> set of seen diagnostic keys (for global deduplication across versions)
        self._seen_keys: dict[str, set[tuple[Any, ...]]] = {}
        # file_uri -> list of pending diagnostics to deliver
        self._pending: dict[str, list[LSPDiagnostic]] = {}
        # file_uri -> last delivery time
        self._last_delivery: dict[str, float] = {}

    def _diag_key(self, diag: LSPDiagnostic) -> tuple[Any, ...]:
        """Create a tuple key for deduplication."""
        return (
            diag.message,
            diag.severity,
            self._range_key(diag.range),
            diag.source,
            diag.code,
        )

    def register_pending(
        self,
        file_uri: str,
        diagnostics: list[LSPDiagnostic],
        version: int | None = None,
    ) -> list[LSPDiagnostic]:
        """Register diagnostics and return the ones that are new/different.

        Deduplication logic:
        - Compare diagnostics by (message, severity, range, source, code)
        - Skip diagnostics already seen for this file (across all versions)
        - Within a single call, skip duplicate diagnostics
        """
        del version  # Kept for API compatibility; dedup is global per file

        with self._lock:
            if file_uri not in self._seen_keys:
                self._seen_keys[file_uri] = set()

            seen = self._seen_keys[file_uri]
            pending = []
            seen_this_batch: set[tuple[Any, ...]] = set()

            for diag in diagnostics[: self.MAX_DIAGNOSTICS_PER_FILE]:
                key = self._diag_key(diag)
                if key in seen or key in seen_this_batch:
                    continue
                seen_this_batch.add(key)
                seen.add(key)
                pending.append(diag)

            if pending:
                # Prepend to pending (most recent first)
                self._pending[file_uri] = pending + self._pending.get(file_uri, [])

            return pending

    def check_for_diagnostics(self, file_uri: str) -> list[LSPDiagnostic]:
        """Return pending diagnostics for a file that should be delivered."""
        with self._lock:
            pending = self._pending.get(file_uri, [])
            batch = pending[: self.MAX_DELIVERY_BATCH_SIZE]
            return batch

    def acknowledge(self, file_uri: str, count: int) -> None:
        """Acknowledge delivery of diagnostics (removes from pending)."""
        with self._lock:
            if file_uri in self._pending:
                self._pending[file_uri] = self._pending[file_uri][count:]
                if not self._pending[file_uri]:
                    del self._pending[file_uri]
            self._last_delivery[file_uri] = time.monotonic()

    def clear_file(self, file_uri: str) -> None:
        """Clear all diagnostics for a file."""
        with self._lock:
            if file_uri in self._seen_keys:
                del self._seen_keys[file_uri]
            if file_uri in self._pending:
                del self._pending[file_uri]
            if file_uri in self._last_delivery:
                del self._last_delivery[file_uri]

    def clear_old_entries(self, max_age_seconds: int = DEDUP_WINDOW_SECONDS) -> None:
        """Clear seen keys older than max_age_seconds.

        Called periodically to prevent unbounded memory growth.
        We only clear entries that haven't been updated recently.
        """
        with self._lock:
            cutoff = time.monotonic() - max_age_seconds
            for file_uri in list(self._last_delivery.keys()):
                if self._last_delivery[file_uri] < cutoff:
                    self._seen_keys.pop(file_uri, None)
                    self._pending.pop(file_uri, None)

    @staticmethod
    def _range_key(range: LSPRange) -> str:
        """Create a string key for a range for deduplication."""
        return f"{range.start.line}:{range.start.character}-{range.end.line}:{range.end.character}"
