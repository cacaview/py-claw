from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from py_claw.services.config.types import GlobalConfig, ProjectConfig

logger = logging.getLogger(__name__)

# Re-entrancy guard: prevents get_config → log_event → get_config recursion
_inside_get_config = False

# Cache for global config
_global_config_cache: GlobalConfig | None = None
_config_cache_mtime: float = 0.0


def _get_claude_config_dir() -> Path:
    """Get the Claude config directory (~/.claude)."""
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base = Path.home()
    return base / ".claude"


def _get_global_config_path() -> Path:
    """Get the global config file path (~/.claude.json)."""
    return _get_claude_config_dir() / "settings.json"


def _get_backup_dir() -> Path:
    """Get the backup directory (~/.claude/backups)."""
    return _get_claude_config_dir() / "backups"


def _get_default_global_config() -> dict[str, Any]:
    """Create a fresh default global config dict."""
    return {
        "num_startups": 0,
        "install_method": None,
        "auto_updates": None,
        "auto_updates_channel": None,
        "theme": "dark",
        "verbose": False,
        "preferred_notif_channel": "auto",
        "shift_enter_key_binding_installed": False,
        "editor_mode": "normal",
        "has_used_backslash_return": False,
        "auto_compact_enabled": True,
        "show_turn_duration": True,
        "diff_tool": "auto",
        "env": {},
        "tips_history": {},
        "todo_feature_enabled": True,
        "show_expanded_todos": False,
        "message_idle_notif_threshold_ms": 60000,
        "auto_connect_ide": False,
        "auto_install_ide_extension": True,
        "file_checkpointing_enabled": True,
        "terminal_progress_bar_enabled": True,
        "show_status_in_terminal_tab": False,
        "task_complete_notif_enabled": False,
        "input_needed_notif_enabled": False,
        "agent_push_notif_enabled": False,
        "respect_gitignore": True,
        "claude_in_chrome_default_enabled": None,
        "has_completed_claude_in_chrome_onboarding": False,
        "lsp_recommendation_disabled": False,
        "lsp_recommendation_never_plugins": [],
        "lsp_recommendation_ignored_count": 0,
        "copy_full_response": False,
        "copy_on_select": None,
        "permission_explainer_enabled": True,
        "pr_status_footer_enabled": True,
        "remote_control_at_startup": None,
        "remote_dialog_seen": False,
        "cached_statsig_gates": {},
        "cached_dynamic_configs": {},
        "cached_growth_book_features": {},
        "oauth_account": None,
        "primary_api_key": None,
        "custom_api_key_responses": {"approved": [], "rejected": []},
        "has_acknowledged_cost_threshold": False,
        "mcp_servers": {},
        "claude_ai_mcp_ever_connected": [],
        "has_completed_onboarding": False,
        "memory_usage_count": 0,
        "prompt_queue_use_count": 0,
        "btw_use_count": 0,
        "has_seen_tasks_hint": False,
        "has_used_stash": False,
        "has_used_background_task": False,
        "queued_command_up_hint_count": 0,
        "github_repo_paths": {},
        "skill_usage": {},
        "chrome_extension": None,
        "cached_chrome_extension_installed": None,
        "experiments_notices_seen_count": {},
        "last_shown_emergency_tip": None,
        "speculation_enabled": True,
        "auto_permissions_notification_count": 0,
        "active_worktree_session": None,
        "remote_control_spawn_mode": None,
        "passes_upsell_seen_count": 0,
        "has_visited_passes": False,
        "passes_last_seen_remaining": None,
        "subscription_notice_count": 0,
        "has_available_subscription": False,
        "voice_notice_seen_count": 0,
        "voice_lang_hint_shown_count": 0,
        "voice_lang_hint_last_language": None,
        "voice_footer_hint_seen_count": 0,
        "desktop_upsell_seen_count": 0,
        "desktop_upsell_dismissed": False,
        "idle_return_dismissed": False,
        "opus_pro_migration_complete": False,
        "opus_pro_migration_timestamp": None,
        "sonnet_1m_45_migration_complete": False,
        "legacy_opus_migration_timestamp": None,
        "sonnet_45_to_46_migration_timestamp": None,
        "effort_callout_dismissed": False,
        "effort_callout_v2_dismissed": False,
        "model_switch_callout_dismissed": False,
        "model_switch_callout_last_shown": None,
        "model_switch_callout_version": None,
        "user_id": None,
        "first_start_time": None,
        "startup_prefetched_at": None,
        "cached_extra_usage_disabled_reason": None,
        "overage_credit_upsell_seen_count": 0,
        "has_visited_extra_usage": False,
        "passes_eligibility_cache": {},
        "grove_config_cache": {},
        "has_shown_s1m_welcome_v2": {},
        "s1m_access_cache": {},
        "s1m_non_subscriber_access_cache": {},
        "claude_code_first_token_date": None,
        "last_release_notes_seen": None,
        "changelog_last_fetched": None,
        "last_onboarding_version": None,
        "doctor_shown_at_session": None,
        "has_trust_dialog_accepted": False,
        "has_ide_onboarding_been_shown": {},
        "ide_hint_shown_count": 0,
        "has_ide_auto_connect_dialog_been_shown": False,
        "iterm2_setup_in_progress": False,
        "apple_terminal_setup_in_progress": False,
        "iterm2_it2_setup_complete": False,
        "prefer_tmux_over_iterm2": False,
        "deep_link_terminal": None,
        "migration_version": None,
        "client_data_cache": None,
        "additional_model_options_cache": [],
        "metrics_status_cache": None,
        "penguin_mode_org_enabled": None,
        "teammate_mode": None,
        "teammate_default_model": None,
    }


def _get_default_project_config() -> dict[str, Any]:
    """Create a fresh default project config dict."""
    return {
        "allowed_tools": [],
        "mcp_context_uris": [],
        "mcp_servers": {},
        "last_api_duration": None,
        "last_api_duration_without_retries": None,
        "last_tool_duration": None,
        "last_cost": None,
        "last_duration": None,
        "last_lines_added": None,
        "last_lines_removed": None,
        "last_total_input_tokens": None,
        "last_total_output_tokens": None,
        "last_total_cache_creation_input_tokens": None,
        "last_total_cache_read_input_tokens": None,
        "last_total_web_search_requests": None,
        "last_fps_average": None,
        "last_fps_low_1pct": None,
        "last_session_id": None,
        "last_model_usage": {},
        "last_session_metrics": {},
        "example_files": [],
        "example_files_generated_at": None,
        "has_trust_dialog_accepted": False,
        "has_completed_project_onboarding": False,
        "project_onboarding_seen_count": 0,
        "has_claude_md_external_includes_approved": False,
        "has_claude_md_external_includes_warning_shown": False,
        "enabled_mcp_json_servers": [],
        "disabled_mcp_json_servers": [],
        "enable_all_project_mcp_servers": False,
        "disabled_mcp_servers": [],
        "enabled_mcp_servers": [],
        "active_worktree_session": None,
        "remote_control_spawn_mode": None,
    }


def _merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two config dicts, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value
    return result


def _would_lose_auth_state(fresh: dict[str, Any]) -> bool:
    """Check if writing fresh would lose auth state that cache still has."""
    global _global_config_cache
    if _global_config_cache is None:
        return False
    cached = _global_config_cache.model_dump()
    lost_oauth = cached.get("oauth_account") is not None and fresh.get("oauth_account") is None
    lost_onboarding = cached.get("has_completed_onboarding") is True and fresh.get("has_completed_onboarding") is not True
    return lost_oauth or lost_onboarding


def _load_config_from_file(path: Path) -> tuple[dict[str, Any] | None, float]:
    """Load config from file, returns (config_dict, mtime) or (None, 0) if not found."""
    if not path.exists():
        return None, 0.0
    try:
        stat = path.stat()
        content = path.read_text(encoding="utf-8")
        # Strip BOM if present
        if content.startswith("\ufeff"):
            content = content[1:]
        config = json.loads(content)
        if not isinstance(config, dict):
            logger.error(f"Config file {path} is not a valid JSON object")
            return None, 0.0
        return config, stat.st_mtime
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse config file {path}: {e}")
        _backup_corrupted_config(path)
        return None, 0.0
    except OSError as e:
        logger.error(f"Failed to read config file {path}: {e}")
        return None, 0.0


def _backup_corrupted_config(path: Path) -> None:
    """Backup a corrupted config file."""
    if not path.exists():
        return
    backup_dir = _get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    corrupted_files = list(backup_dir.glob(f"{path.name}.corrupted.*"))
    current_content = path.read_text(encoding="utf-8")
    # Check if already backed up
    for bf in corrupted_files:
        try:
            if bf.read_text(encoding="utf-8") == current_content:
                return  # Already backed up
        except OSError:
            pass
    backup_path = backup_dir / f"{path.name}.corrupted.{int(datetime.now().timestamp() * 1000)}"
    try:
        shutil.copy2(path, backup_path)
        logger.info(f"Backed up corrupted config to {backup_path}")
    except OSError as e:
        logger.warning(f"Failed to backup corrupted config: {e}")


def _find_most_recent_backup(config_path: Path) -> Path | None:
    """Find the most recent backup file for a config."""
    backup_dir = _get_backup_dir()
    file_base = config_path.name
    # Check new backup dir
    if backup_dir.exists():
        backups = sorted(backup_dir.glob(f"{file_base}.backup.*"), reverse=True)
        if backups:
            return backups[0]
    # Fall back to legacy location (next to config file)
    legacy_backups = sorted(config_path.parent.glob(f"{file_base}.backup.*"), reverse=True)
    if legacy_backups:
        return legacy_backups[0]
    # Check for legacy backup without timestamp
    legacy = config_path.with_suffix(config_path.suffix + ".backup")
    if legacy.exists():
        return legacy
    return None


def _read_global_config() -> dict[str, Any]:
    """Read global config from file with all defaults applied."""
    global _inside_get_config
    if _inside_get_config:
        return _get_default_global_config()

    config_path = _get_global_config_path()
    config, mtime = _load_config_from_file(config_path)

    if config is None:
        # Check for backup
        backup_path = _find_most_recent_backup(config_path)
        if backup_path:
            print(f"\nClaude configuration file not found at: {config_path}")
            print(f"A backup file exists at: {backup_path}")
            print(f"You can manually restore it by running: copy \"{backup_path}\" \"{config_path}\"\n")
        return _get_default_global_config()

    # Merge with defaults
    default_config = _get_default_global_config()
    merged = _merge_config(default_config, config)
    return merged


def get_global_config() -> GlobalConfig:
    """
    Get the global configuration.

    This reads from ~/.claude.json with memory caching and write-through
    on saves. Other processes' writes are picked up by file watching.
    """
    global _global_config_cache, _config_cache_mtime, _inside_get_config

    # Fast path: memory cache
    if _global_config_cache is not None:
        return _global_config_cache

    _inside_get_config = True
    try:
        config_path = _get_global_config_path()
        config_dict = _read_global_config()
        _global_config_cache = GlobalConfig(**config_dict)

        try:
            stat = config_path.stat()
            _config_cache_mtime = stat.st_mtime
        except OSError:
            _config_cache_mtime = 0.0

        return _global_config_cache
    finally:
        _inside_get_config = False


def save_global_config(updater: Callable[[GlobalConfig], GlobalConfig]) -> None:
    """
    Save global config with an updater function.

    The updater receives the current config and returns the new config.
    Uses file locking to prevent concurrent write issues.
    """
    global _global_config_cache, _config_cache_mtime

    config_path = _get_global_config_path()
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    # Read current config
    current_dict = _read_global_config()
    current_config = GlobalConfig(**current_dict)

    # Apply updater
    new_config = updater(current_config)

    # Skip if no changes
    if new_config is current_config:
        return

    # Check auth-loss guard
    if _would_lose_auth_state(new_config.model_dump()):
        logger.error("Refusing to write config: would lose auth state")
        return

    # Prepare data - filter out defaults
    new_dict = _filter_defaults(new_config.model_dump(), _get_default_global_config())

    # Create backup before writing
    _create_backup(config_path)

    # Write config
    try:
        config_path.write_text(json.dumps(new_dict, indent=2, ensure_ascii=False), encoding="utf-8")
        # Write-through cache
        _global_config_cache = new_config
        try:
            _config_cache_mtime = config_path.stat().st_mtime
        except OSError:
            pass
    except OSError as e:
        logger.error(f"Failed to write config: {e}")
        raise


def _filter_defaults(config: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Filter out values that match the defaults."""
    result = {}
    for key, value in config.items():
        default_value = defaults.get(key)
        if isinstance(value, dict) and isinstance(default_value, dict):
            filtered = _filter_defaults(value, default_value)
            if filtered:
                result[key] = filtered
        elif value != default_value:
            result[key] = value
    return result


def _create_backup(config_path: Path) -> None:
    """Create a timestamped backup of the config file."""
    if not config_path.exists():
        return

    backup_dir = _get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    MIN_BACKUP_INTERVAL_MS = 60_000
    file_base = config_path.name

    # Check existing backups
    existing = sorted(backup_dir.glob(f"{file_base}.backup.*"), reverse=True)
    most_recent = existing[0] if existing else None
    if most_recent:
        try:
            timestamp = int(most_recent.suffix.lstrip("."))
            if datetime.now().timestamp() * 1000 - timestamp < MIN_BACKUP_INTERVAL_MS:
                return  # Recent backup exists
        except (ValueError, OSError):
            pass

    # Create new backup
    backup_path = backup_dir / f"{file_base}.backup.{int(datetime.now().timestamp() * 1000)}"
    try:
        shutil.copy2(config_path, backup_path)

        # Clean up old backups (keep 5 most recent)
        backups = sorted(backup_dir.glob(f"{file_base}.backup.*"), reverse=True)
        for old in backups[5:]:
            try:
                old.unlink()
            except OSError:
                pass
    except OSError as e:
        logger.warning(f"Failed to create backup: {e}")


def get_project_path_for_config(cwd: str | None = None) -> str:
    """
    Get the normalized project path for config lookup.

    Uses git root if available, otherwise falls back to cwd.
    Paths are normalized for consistent JSON key lookup across platforms.
    """
    import os
    from pathlib import Path as P

    original_cwd = cwd or os.getcwd()

    # Try to find git root
    path = P(original_cwd).resolve()
    while True:
        if (path / ".git").exists():
            return _normalize_path_for_config_key(str(path))
        parent = path.parent
        if parent == path:
            break
        path = parent

    # Not in a git repo, use original cwd
    return _normalize_path_for_config_key(original_cwd)


def _normalize_path_for_config_key(path: str) -> str:
    """Normalize path for consistent JSON key lookup."""
    return str(Path(path).resolve()).replace("\\", "/")


def get_current_project_config(cwd: str | None = None) -> ProjectConfig:
    """Get the current project config based on cwd."""
    project_path = get_project_path_for_config(cwd)
    global_config = get_global_config()

    projects = global_config.model_dump().get("projects", {})
    project_data = projects.get(project_path) or {}

    # Apply defaults
    default_project = _get_default_project_config()
    merged = _merge_config(default_project, project_data)

    return ProjectConfig(**merged)


def save_current_project_config(
    updater: Callable[[ProjectConfig], ProjectConfig],
    cwd: str | None = None,
) -> None:
    """Save project config with an updater function."""
    project_path = get_project_path_for_config(cwd)

    save_global_config(lambda global_config: _update_project_in_global(
        global_config, project_path, updater
    ))


def _update_project_in_global(
    global_config: GlobalConfig,
    project_path: str,
    updater: Callable[[ProjectConfig], ProjectConfig],
) -> GlobalConfig:
    """Update a project's config within the global config."""
    projects = global_config.model_dump().get("projects", {})
    default_project = _get_default_project_config()
    current_project_data = projects.get(project_path) or {}
    current_project = ProjectConfig(**_merge_config(default_project, current_project_data))

    new_project = updater(current_project)

    # Skip if no changes
    if new_project is current_project:
        return global_config

    # Update projects dict
    new_projects = dict(projects)
    new_projects[project_path] = new_project.model_dump()

    # Return new global config with updated projects
    return GlobalConfig(**{**global_config.model_dump(), "projects": new_projects})


# Convenience functions

def get_theme() -> str:
    """Get the current theme setting."""
    return get_global_config().theme


def set_theme(theme: str) -> None:
    """Set the theme setting."""
    save_global_config(lambda c: GlobalConfig(**{**c.model_dump(), "theme": theme}))


def is_auto_compact_enabled() -> bool:
    """Check if auto compact is enabled."""
    return get_global_config().auto_compact_enabled


def increment_startup_count() -> None:
    """Increment the startup counter."""
    save_global_config(lambda c: GlobalConfig(**{**c.model_dump(), "num_startups": c.num_startups + 1}))


def get_oauth_account() -> dict | None:
    """Get the OAuth account info."""
    return get_global_config().oauth_account


def set_oauth_account(account: dict | None) -> None:
    """Set the OAuth account info."""
    save_global_config(lambda c: GlobalConfig(**{**c.model_dump(), "oauth_account": account}))


def get_or_create_user_id() -> str:
    """Get or create a user ID."""
    config = get_global_config()
    if config.user_id:
        return config.user_id

    import secrets
    user_id = secrets.token_hex(32)
    save_global_config(lambda c: GlobalConfig(**{**c.model_dump(), "user_id": user_id}))
    return user_id


def record_first_start_time() -> None:
    """Record the first start time if not already recorded."""
    config = get_global_config()
    if not config.first_start_time:
        first_start_time = datetime.now().isoformat()
        save_global_config(lambda c: GlobalConfig(**{**c.model_dump(), "first_start_time": first_start_time}))
