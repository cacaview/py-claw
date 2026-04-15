"""Config service - global and project configuration management.

This module provides configuration management inspired by the TypeScript
reference implementation's config.ts, supporting:
- Global config (~/.claude.json) with memory caching and write-through
- Project-level config stored within global config (keyed by git root)
- Auth-loss protection to prevent wiping OAuth/onboarding state
- Config backup and corruption recovery
- Trust dialog acceptance tracking across parent directories
"""

from py_claw.services.config.service import (
    get_global_config,
    save_global_config,
    get_current_project_config,
    save_current_project_config,
    get_project_path_for_config,
    get_theme,
    set_theme,
    is_auto_compact_enabled,
    increment_startup_count,
    get_oauth_account,
    set_oauth_account,
    get_or_create_user_id,
    record_first_start_time,
)
from py_claw.services.config.types import GlobalConfig, ProjectConfig

__all__ = [
    "GlobalConfig",
    "ProjectConfig",
    "get_global_config",
    "save_global_config",
    "get_current_project_config",
    "save_current_project_config",
    "get_project_path_for_config",
    "get_theme",
    "set_theme",
    "is_auto_compact_enabled",
    "increment_startup_count",
    "get_oauth_account",
    "set_oauth_account",
    "get_or_create_user_id",
    "record_first_start_time",
]
