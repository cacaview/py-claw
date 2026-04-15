"""
CLI transports for remote session communication.

Provides transport implementations for connecting to remote
Claude Code sessions via different protocols.

Reference: ClaudeCode-main/src/cli/transports/
"""
from __future__ import annotations

from .base import Transport
from .websocket import WebSocketTransport
from .hybrid import HybridTransport
from .serial_batch import SerialBatchEventUploader, RetryableError
from .worker_state import WorkerStateUploader
from .ccr_client import CCRClient, CCRInitError

__all__ = [
    "Transport",
    "WebSocketTransport",
    "HybridTransport",
    "SerialBatchEventUploader",
    "RetryableError",
    "WorkerStateUploader",
    "CCRClient",
    "CCRInitError",
]
