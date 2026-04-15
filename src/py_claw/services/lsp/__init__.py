"""
LSP (Language Server Protocol) service layer.

Provides LSP server lifecycle management, multi-server routing,
and diagnostics handling for language intelligence features.
"""
from __future__ import annotations

from py_claw.services.lsp.client import LSPClient
from py_claw.services.lsp.server import LSPServerInstance
from py_claw.services.lsp.manager import LSPServerManager
from py_claw.services.lsp.diagnostics import LSPDiagnosticRegistry

__all__ = [
    "LSPClient",
    "LSPServerInstance",
    "LSPServerManager",
    "LSPDiagnosticRegistry",
]
