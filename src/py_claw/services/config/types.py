from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GlobalConfig(BaseModel):
    """Global configuration stored in ~/.claude/settings.json."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # Core settings
    theme: str = "dark"
    verbose: bool = False
    auto_compact_enabled: bool = True
    show_turn_duration: bool = True
    diff_tool: str = "auto"
    editor_mode: str = "normal"

    # Notification settings
    preferred_notif_channel: str = "auto"
    task_complete_notif_enabled: bool = False
    input_needed_notif_enabled: bool = False
    agent_push_notif_enabled: bool = False

    # Environment variables
    env: dict[str, str] = Field(default_factory=dict)

    # Tracking counters
    num_startups: int = 0
    memory_usage_count: int = 0
    prompt_queue_use_count: int = 0
    btw_use_count: int = 0
    queued_command_up_hint_count: int = 0

    # Feature flags
    todo_feature_enabled: bool = True
    show_expanded_todos: bool = False
    show_spinner_tree: bool = False
    file_checkpointing_enabled: bool = True
    terminal_progress_bar_enabled: bool = True
    respect_gitignore: bool = True

    # Copy behavior
    copy_full_response: bool = False
    copy_on_select: bool | None = None

    # Onboarding & trust
    has_completed_onboarding: bool = False
    has_trust_dialog_accepted: bool = False
    has_used_stash: bool = False
    has_used_background_task: bool = False
    has_seen_tasks_hint: bool = False

    # IDE settings
    auto_connect_ide: bool = False
    auto_install_ide_extension: bool = True
    has_ide_onboarding_been_shown: dict[str, bool] = Field(default_factory=dict)
    ide_hint_shown_count: int = 0
    has_ide_auto_connect_dialog_been_shown: bool = False

    # Terminal setup
    shift_enter_key_binding_installed: bool = False
    option_as_meta_key_installed: bool = False
    iterm2_setup_in_progress: bool = False
    apple_terminal_setup_in_progress: bool = False

    # Tips history (tipId -> numStartups when last shown)
    tips_history: dict[str, int] = Field(default_factory=dict)

    # MCP servers
    mcp_servers: dict[str, dict] = Field(default_factory=dict)
    claude_ai_mcp_ever_connected: list[str] = Field(default_factory=list)

    # OAuth account info
    oauth_account: dict | None = None

    # API key
    primary_api_key: str | None = None
    custom_api_key_responses: dict[str, list[str]] = Field(
        default_factory=lambda: {"approved": [], "rejected": []}
    )
    has_acknowledged_cost_threshold: bool = False

    # Permissions mode
    bypass_permissions_mode_accepted: bool = False
    permission_explainer_enabled: bool = True

    # Teammate settings
    teammate_mode: str | None = None  # 'auto', 'tmux', 'in-process'
    teammate_default_model: str | None = None

    # Cache for Statsig/GrowthBook
    cached_statsig_gates: dict[str, bool] = Field(default_factory=dict)
    cached_dynamic_configs: dict[str, dict] = Field(default_factory=dict)
    cached_growth_book_features: dict[str, dict] = Field(default_factory=dict)

    # Install & update
    install_method: str | None = None  # 'local', 'native', 'global', 'unknown'
    auto_updates: bool | None = None
    auto_updates_channel: str | None = None  # 'stable', 'latest', or explicit version channel
    auto_updates_protected_for_native: bool = False

    # Release tracking
    last_release_notes_seen: str | None = None
    changelog_last_fetched: int | None = None

    # Session metrics
    doctor_shown_at_session: int | None = None
    last_onboarding_version: str | None = None

    # Privacy
    custom_notify_command: str | None = None

    # Message idle notification threshold (ms)
    message_idle_notif_threshold_ms: int = 60000

    # Key: owner/repo (lowercase), Value: list of absolute paths
    github_repo_paths: dict[str, list[str]] = Field(default_factory=dict)

    # Skill usage tracking
    skill_usage: dict[str, dict[str, int]] = Field(default_factory=dict)

    # Chrome extension
    has_completed_claude_in_chrome_onboarding: bool = False
    claude_in_chrome_default_enabled: bool | None = None
    cached_chrome_extension_installed: bool | None = None
    chrome_extension: dict | None = None

    # LSP
    lsp_recommendation_disabled: bool = False
    lsp_recommendation_never_plugins: list[str] = Field(default_factory=list)
    lsp_recommendation_ignored_count: int = 0

    # Claude Code hints
    claude_code_hints: dict | None = None

    # PR status footer
    pr_status_footer_enabled: bool = True

    # Remote control
    remote_control_at_startup: bool | None = None
    remote_dialog_seen: bool = False
    bridge_oauth_dead_expires_at: int | None = None
    bridge_oauth_dead_fail_count: int | None = None

    # Migration version
    migration_version: int | None = None

    # Deep link terminal
    deep_link_terminal: str | None = None

    # iTerm2 / tmux preference
    iterm2_it2_setup_complete: bool = False
    prefer_tmux_over_iterm2: bool = False

    # Subscriptions & passes
    has_available_subscription: bool = False
    subscription_notice_count: int = 0
    passes_upsell_seen_count: int = 0
    has_visited_passes: bool = False
    passes_last_seen_remaining: int | None = None

    # Voice mode
    voice_notice_seen_count: int = 0
    voice_lang_hint_shown_count: int = 0
    voice_lang_hint_last_language: str | None = None
    voice_footer_hint_seen_count: int = 0

    # Desktop upsell
    desktop_upsell_seen_count: int = 0
    desktop_upsell_dismissed: bool = False

    # Idle return
    idle_return_dismissed: bool = False

    # Migration tracking
    opus_pro_migration_complete: bool = False
    opus_pro_migration_timestamp: int | None = None
    sonnet_1m_45_migration_complete: bool = False
    legacy_opus_migration_timestamp: int | None = None
    sonnet_45_to_46_migration_timestamp: int | None = None

    # Effort callout
    effort_callout_dismissed: bool = False
    effort_callout_v2_dismissed: bool = False

    # Model switch callout
    model_switch_callout_dismissed: bool = False
    model_switch_callout_last_shown: int | None = None
    model_switch_callout_version: str | None = None

    # User ID
    user_id: str | None = None

    # First start time
    first_start_time: str | None = None

    # Startup prefetch
    startup_prefetched_at: int | None = None

    # Extra usage
    cached_extra_usage_disabled_reason: str | None = None
    overage_credit_upsell_seen_count: int = 0
    has_visited_extra_usage: bool = False

    # Guest passes
    passes_eligibility_cache: dict[str, dict] = Field(default_factory=dict)

    # Grove config cache
    grove_config_cache: dict[str, dict] = Field(default_factory=dict)

    # Sonnet 1M
    has_shown_s1m_welcome_v2: dict[str, bool] = Field(default_factory=dict)
    s1m_access_cache: dict[str, dict] = Field(default_factory=dict)
    s1m_non_subscriber_access_cache: dict[str, dict] = Field(default_factory=dict)

    # Claude Code usage
    claude_code_first_token_date: str | None = None

    # Experiment notices
    experiment_notices_seen_count: dict[str, int] = Field(default_factory=dict)

    # OpusPlan
    has_shown_opus_plan_welcome: dict[str, bool] = Field(default_factory=dict)

    # Emergency tip
    last_shown_emergency_tip: str | None = None

    # Speculation (ant-only)
    speculation_enabled: bool = True

    # Auto permissions notification (ant-only)
    auto_permissions_notification_count: int = 0

    # Client data cache
    client_data_cache: dict | None = None

    # Additional model options cache
    additional_model_options_cache: list[dict] = Field(default_factory=list)

    # Metrics status cache
    metrics_status_cache: dict | None = None

    # Cached org-level fast mode status
    penguin_mode_org_enabled: bool | None = None

    # Worktree session management
    active_worktree_session: dict | None = None

    # Remote control spawn mode
    remote_control_spawn_mode: str | None = None  # 'same-dir' | 'worktree'

    # Projects (keyed by normalized project path)
    projects: dict[str, dict] = Field(default_factory=dict)


class ProjectConfig(BaseModel):
    """Project-level configuration stored within GlobalConfig.projects."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    allowed_tools: list[str] = Field(default_factory=list)
    mcp_context_uris: list[str] = Field(default_factory=list)
    mcp_servers: dict[str, dict] = Field(default_factory=dict)

    # Session metrics
    last_api_duration: float | None = None
    last_api_duration_without_retries: float | None = None
    last_tool_duration: float | None = None
    last_cost: float | None = None
    last_duration: float | None = None
    last_lines_added: int | None = None
    last_lines_removed: int | None = None
    last_total_input_tokens: int | None = None
    last_total_output_tokens: int | None = None
    last_total_cache_creation_input_tokens: int | None = None
    last_total_cache_read_input_tokens: int | None = None
    last_total_web_search_requests: int | None = None
    last_fps_average: float | None = None
    last_fps_low_1pct: float | None = None
    last_session_id: str | None = None
    last_model_usage: dict[str, dict] = Field(default_factory=dict)
    last_session_metrics: dict[str, float] = Field(default_factory=dict)

    # Example files
    example_files: list[str] = Field(default_factory=list)
    example_files_generated_at: int | None = None

    # Trust & onboarding
    has_trust_dialog_accepted: bool = False
    has_completed_project_onboarding: bool = False
    project_onboarding_seen_count: int = 0
    has_claude_md_external_includes_approved: bool = False
    has_claude_md_external_includes_warning_shown: bool = False

    # MCP server enable/disable lists
    enabled_mcp_json_servers: list[str] = Field(default_factory=list)
    disabled_mcp_json_servers: list[str] = Field(default_factory=list)
    enable_all_project_mcp_servers: bool = False
    disabled_mcp_servers: list[str] = Field(default_factory=list)
    enabled_mcp_servers: list[str] = Field(default_factory=list)

    # Worktree session
    active_worktree_session: dict | None = None

    # Remote control spawn mode
    remote_control_spawn_mode: str | None = None


# Constants for keys that should be persisted at global level
GLOBAL_CONFIG_KEYS = [
    "theme",
    "verbose",
    "auto_compact_enabled",
    "show_turn_duration",
    "diff_tool",
    "editor_mode",
    "preferred_notif_channel",
    "task_complete_notif_enabled",
    "input_needed_notif_enabled",
    "agent_push_notif_enabled",
    "env",
    "tips_history",
    "todo_feature_enabled",
    "show_expanded_todos",
    "message_idle_notif_threshold_ms",
    "auto_connect_ide",
    "auto_install_ide_extension",
    "file_checkpointing_enabled",
    "terminal_progress_bar_enabled",
    "show_status_in_terminal_tab",
    "respect_gitignore",
    "claude_in_chrome_default_enabled",
    "has_completed_claude_in_chrome_onboarding",
    "lsp_recommendation_disabled",
    "lsp_recommendation_never_plugins",
    "lsp_recommendation_ignored_count",
    "copy_full_response",
    "copy_on_select",
    "permission_explainer_enabled",
    "pr_status_footer_enabled",
    "remote_control_at_startup",
    "remote_dialog_seen",
    "shift_enter_key_binding_installed",
]

PROJECT_CONFIG_KEYS = [
    "allowed_tools",
    "has_trust_dialog_accepted",
    "has_completed_project_onboarding",
]
