"""
Backend registry for swarm team orchestration.

Based on ClaudeCode-main/src/utils/swarm/backends/registry.ts

Provides backend detection and selection for teammate execution.
"""
from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from .types import (
    BackendType,
    PaneBackend,
    TeammateExecutor,
)

if TYPE_CHECKING:
    from .types import BackendDetectionResult


# In-memory registry of available backends
_registered_backends: dict[BackendType, type[PaneBackend | TeammateExecutor]] = {}


def register_backend(
    backend_type: BackendType,
    backend_class: type[PaneBackend | TeammateExecutor],
) -> None:
    """
    Register a backend class for a given type.

    Args:
        backend_type: The type identifier for this backend
        backend_class: The backend class to register
    """
    _registered_backends[backend_type] = backend_class


def get_backend(backend_type: BackendType) -> type[PaneBackend | TeammateExecutor] | None:
    """
    Get a registered backend class by type.

    Args:
        backend_type: The type identifier

    Returns:
        The backend class or None if not registered
    """
    return _registered_backends.get(backend_type)


def is_tmux_available() -> bool:
    """Check if tmux is available on the system."""
    return shutil.which("tmux") is not None


def is_iterm2_available() -> bool:
    """Check if iTerm2 is available on the system."""
    # iTerm2 availability is more complex - need to check if it2 CLI is installed
    # For now, just check if we're on macOS
    import platform
    return platform.system() == "Darwin"


async def detect_backend() -> "BackendDetectionResult | None":
    """
    Detect the best backend to use for the current environment.

    Returns:
        BackendDetectionResult with the best backend, or None if no backends available
    """
    # Import here to avoid circular deps
    from .tmux_backend import TmuxBackend

    # Check tmux first
    if is_tmux_available():
        backend = TmuxBackend()
        is_running = await backend.is_running_inside()
        return BackendDetectionResult(
            backend=backend,
            is_native=is_running,
            needs_it2_setup=False,
        )

    # iTerm2 could be checked here if we had a proper implementation
    # For now, return None if tmux is not available
    return None


def get_available_backends() -> list[BackendType]:
    """
    Get list of available backend types.

    Returns:
        List of BackendType values that are available
    """
    available = []
    if is_tmux_available():
        available.append(BackendType.TMUX)
    if is_iterm2_available():
        available.append(BackendType.ITERM2)
    return available


# Initialize with backend info
BACKEND_INFO_MAP: dict[BackendType, dict] = {
    BackendType.TMUX: {
        "display_name": "tmux",
        "supports_hide_show": True,
    },
    BackendType.ITERM2: {
        "display_name": "iTerm2",
        "supports_hide_show": True,
    },
    BackendType.IN_PROCESS: {
        "display_name": "In-Process",
        "supports_hide_show": False,
    },
    BackendType.WEB: {
        "display_name": "Web",
        "supports_hide_show": False,
    },
}


__all__ = [
    "BACKEND_INFO_MAP",
    "BackendType",
    "detect_backend",
    "get_available_backends",
    "get_backend",
    "is_iterm2_available",
    "is_tmux_available",
    "register_backend",
]
