"""
Swarm backends module.

Backend implementations for team orchestration.

Based on ClaudeCode-main/src/utils/swarm/backends/
"""
from py_claw.swarm.backends.registry import (
    BACKEND_INFO_MAP,
    detect_backend,
    get_available_backends,
    get_backend,
    is_iterm2_available,
    is_tmux_available,
    register_backend,
)
from py_claw.swarm.backends.tmux_backend import TmuxBackend
from py_claw.swarm.backends.types import (
    BackendInfo,
    BackendType,
    BackendDetectionResult,
    CreatePaneResult,
    is_pane_backend,
    PaneBackend,
    PaneBackendType,
    PaneId,
    TeammateExecutor,
    TeammateIdentity,
    TeammateMessage,
    TeammateSpawnConfig,
    TeammateSpawnResult,
)
from py_claw.swarm.backends.detection import (
    is_inside_tmux,
    is_inside_tmux_sync,
    get_leader_pane_id,
    is_in_iterm2,
    is_iterm2_cli_available,
    reset_detection_cache,
    detect_backend_type,
)
from py_claw.swarm.backends.in_process_backend import (
    InProcessBackend,
    create_in_process_backend,
)
from py_claw.swarm.backends.it2_setup import (
    detect_python_package_manager,
    install_it2,
    verify_it2_setup,
    get_python_api_instructions,
    is_macos,
)
from py_claw.swarm.backends.iterm_backend import (
    ITermBackend,
    register_iterm_backend,
)
from py_claw.swarm.backends.pane_backend_executor import (
    PaneBackendExecutor,
    create_pane_backend_executor,
)
from py_claw.swarm.backends.teammate_mode_snapshot import (
    set_cli_teammate_mode_override,
    get_cli_teammate_mode_override,
    clear_cli_teammate_mode_override,
    capture_teammate_mode_snapshot,
    get_teammate_mode_from_snapshot,
)


__all__ = [
    # Registry
    "BACKEND_INFO_MAP",
    "detect_backend",
    "get_available_backends",
    "get_backend",
    "is_iterm2_available",
    "is_tmux_available",
    "register_backend",
    # Backends
    "TmuxBackend",
    "InProcessBackend",
    "create_in_process_backend",
    "ITermBackend",
    "register_iterm_backend",
    "PaneBackendExecutor",
    "create_pane_backend_executor",
    # Detection
    "is_inside_tmux",
    "is_inside_tmux_sync",
    "get_leader_pane_id",
    "is_in_iterm2",
    "is_iterm2_cli_available",
    "reset_detection_cache",
    "detect_backend_type",
    # it2 setup
    "detect_python_package_manager",
    "install_it2",
    "verify_it2_setup",
    "get_python_api_instructions",
    "is_macos",
    # Teammate mode snapshot
    "set_cli_teammate_mode_override",
    "get_cli_teammate_mode_override",
    "clear_cli_teammate_mode_override",
    "capture_teammate_mode_snapshot",
    "get_teammate_mode_from_snapshot",
    # Types
    "BackendDetectionResult",
    "BackendInfo",
    "BackendType",
    "CreatePaneResult",
    "is_pane_backend",
    "PaneBackend",
    "PaneBackendType",
    "PaneId",
    "TeammateExecutor",
    "TeammateIdentity",
    "TeammateMessage",
    "TeammateSpawnConfig",
    "TeammateSpawnResult",
]
