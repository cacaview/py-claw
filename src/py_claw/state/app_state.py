"""
AppState dataclass definition.

Represents the global application state with 60+ fields.
Based on ClaudeCode-main/src/state/AppState.tsx and AppStateStore.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Sub-state structures
# ---------------------------------------------------------------------------


@dataclass
class TUIState:
    """TUI-specific state fields for Textual REPL UI."""
    # Prompt state
    prompt_mode: str = "normal"  # "normal" | "plan" | "auto" | "bypass"
    vim_mode: str = "INSERT"   # "INSERT" | "NORMAL" | "VISUAL"
    prompt_value: str = ""

    # Suggestion state
    has_suggestions: bool = False
    selected_suggestion_index: int = -1
    suggestion_count: int = 0

    # Queued / stashed prompts
    queued_prompts: list[str] = field(default_factory=list)
    stashed_prompt: str | None = None

    # Pasted content
    pasted_content_id: str | None = None
    pasted_content_label: str | None = None

    # Terminal dimensions
    narrow_terminal: bool = False

    # Overlay state (mirrors active_overlays at AppState level for quick access)
    # Note: active_overlays is already in AppState

    # Speculation state
    speculation_status: str = "idle"  # 'idle' | 'active'
    speculation_boundary: str = ""  # boundary type or ""
    speculation_tool_count: int = 0


@dataclass
class UIState:
    """UI-related state fields."""
    expanded_view: str = "none"
    view_selection_mode: str = "none"
    footer_selection: Optional[str] = None
    spinner_tip: Optional[str] = None
    show_turn_duration: bool = True


@dataclass
class MCPState:
    """MCP-related state fields."""
    clients: List[Any] = field(default_factory=list)
    tools: List[Any] = field(default_factory=list)
    commands: List[Any] = field(default_factory=list)
    resources: Dict[str, List[Any]] = field(default_factory=dict)
    plugin_reconnect_key: int = 0


@dataclass
class PluginState:
    """Plugin-related state fields."""
    enabled: List[Any] = field(default_factory=list)
    disabled: List[Any] = field(default_factory=list)
    commands: List[Any] = field(default_factory=list)
    errors: List[Any] = field(default_factory=list)
    # Installation status for background plugin/marketplace installation
    installation_status_marketplaces: List[Any] = field(default_factory=list)
    installation_status_plugins: List[Any] = field(default_factory=list)
    needs_refresh: bool = False


@dataclass
class NotificationState:
    """Notification state fields."""
    current: Optional[Any] = None
    queue: List[Any] = field(default_factory=list)


@dataclass
class ElicitationState:
    """Elicitation state fields."""
    queue: List[Any] = field(default_factory=list)


@dataclass
class PromptSuggestionState:
    """Prompt suggestion state fields."""
    text: Optional[str] = None
    prompt_id: Optional[str] = None  # 'user_intent' | 'stated_intent' | null
    shown_at: int = 0
    accepted_at: int = 0
    generation_request_id: Optional[str] = None


@dataclass
class SessionHooksState:
    """Session hooks state (Map-like)."""
    hooks: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionBoundary:
    """Boundary at which speculation stopped.

    Mirrors ClaudeCode-main/src/state/AppStateStore.ts CompletionBoundary.
    """
    type: str = "complete"  # 'complete' | 'bash' | 'edit' | 'denied_tool'
    tool_name: Optional[str] = None
    file_path: Optional[str] = None
    command: Optional[str] = None
    detail: Optional[str] = None
    completed_at: Optional[int] = None
    output_tokens: Optional[int] = None


@dataclass
class SpeculationState:
    """Speculation state for pipelined suggestions.

    Mirrors ClaudeCode-main/src/state/AppStateStore.ts SpeculationState.
    """
    status: str = "idle"  # 'idle' | 'active'
    id: Optional[str] = None
    start_time: Optional[int] = None
    boundary: Optional[CompletionBoundary] = None
    suggestion_length: int = 0
    tool_use_count: int = 0
    is_pipelined: bool = False
    pipelined_suggestion: Optional[Dict[str, Any]] = None
    # Messages accumulated during speculation
    messages: list[Any] = field(default_factory=list)
    # Relative paths written to overlay
    written_paths: list[str] = field(default_factory=list)
    # Overlay directory path for copy-on-write isolation
    overlay_path: Optional[str] = None


@dataclass
class FileHistoryState:
    """File history state."""
    snapshots: List[Any] = field(default_factory=list)
    tracked_files: Set[str] = field(default_factory=set)
    snapshot_sequence: int = 0


@dataclass
class AttributionState:
    """Attribution state."""
    pass  # Simplified


@dataclass
class AgentDefinitionsState:
    """Agent definitions state."""
    active_agents: List[Any] = field(default_factory=list)
    all_agents: List[Any] = field(default_factory=list)


@dataclass
class SkillImprovementState:
    """Skill improvement suggestion state."""
    suggestion: Optional[Dict[str, Any]] = None


@dataclass
class InitialMessageState:
    """Initial message state."""
    message: Optional[Any] = None
    clear_context: bool = False
    mode: Optional[str] = None
    allowed_prompts: List[Any] = field(default_factory=list)


@dataclass
class PendingPlanVerificationState:
    """Pending plan verification state."""
    plan: str = ""
    verification_started: bool = False
    verification_completed: bool = False


@dataclass
class WorkerSandboxPermissionsState:
    """Worker sandbox permissions state."""
    queue: List[Any] = field(default_factory=list)
    selected_index: int = 0


@dataclass
class PendingWorkerRequestState:
    """Pending worker request state."""
    tool_name: Optional[str] = None
    tool_use_id: Optional[str] = None
    description: Optional[str] = None


@dataclass
class PendingSandboxRequestState:
    """Pending sandbox request state."""
    request_id: Optional[str] = None
    host: Optional[str] = None


@dataclass
class ReplContextConsoleState:
    """REPL context console state."""
    stdout: str = ""
    stderr: str = ""


@dataclass
class ReplContextState:
    """REPL tool VM context state."""
    vm_context: Optional[Any] = None
    registered_tools: Dict[str, Any] = field(default_factory=dict)
    console: ReplContextConsoleState = field(default_factory=ReplContextConsoleState)


@dataclass
class TeammateInfo:
    """Individual teammate info."""
    name: str
    agent_type: Optional[str] = None
    color: Optional[str] = None
    tmux_session_name: str = ""
    tmux_pane_id: str = ""
    cwd: str = ""
    worktree_path: Optional[str] = None
    spawned_at: int = 0


@dataclass
class TeamContextState:
    """Team context for swarm sessions."""
    team_name: str = ""
    team_file_path: str = ""
    lead_agent_id: str = ""
    self_agent_id: Optional[str] = None
    self_agent_name: Optional[str] = None
    is_leader: bool = False
    self_agent_color: Optional[str] = None
    teammates: Dict[str, TeammateInfo] = field(default_factory=dict)


@dataclass
class StandaloneAgentContextState:
    """Standalone agent context for non-swarm sessions."""
    name: str = ""
    color: Optional[str] = None


@dataclass
class InboxMessage:
    """Inbox message structure."""
    id: str
    from_field: str
    text: str
    timestamp: str
    status: str = "pending"  # 'pending' | 'processing' | 'processed'
    color: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class InboxState:
    """Inbox state."""
    messages: List[InboxMessage] = field(default_factory=list)


@dataclass
class ComputerUseMcpState:
    """Computer use MCP state (Chicago session)."""
    allowed_apps: List[Dict[str, Any]] = field(default_factory=list)
    grant_flags: Optional[Dict[str, bool]] = None
    last_screenshot_dims: Optional[Dict[str, Any]] = None
    hidden_during_turn: Set[str] = field(default_factory=set)
    selected_display_id: Optional[int] = None
    display_pinned_by_model: bool = False
    display_resolved_for_apps: Optional[str] = None


@dataclass
class TungstenSessionState:
    """Tungsten/tmux session state."""
    session_name: str = ""
    socket_name: str = ""
    target: str = ""


@dataclass
class TungstenLastCommandState:
    """Tungsten last command state."""
    command: str = ""
    timestamp: int = 0


# ---------------------------------------------------------------------------
# Main AppState
# ---------------------------------------------------------------------------


@dataclass
class AppState:
    """
    Global application state.

    Contains 60+ fields organized into categories:
    - Settings & model
    - UI state (expanded view, footer, spinner)
    - Bridge state (always-on bridge)
    - Task state (tasks, foregrounded task)
    - MCP state (clients, tools, servers)
    - Plugin state (enabled plugins, errors)
    - Session state (hooks, thinking, bridge)
    - Companion state (reaction, pet)
    - Agent definitions & file history
    - Attribution & todos
    - Notifications & elicitation
    - Prompt suggestion
    - Speculation
    - Team / inbox / sandbox
    - Ultraplan
    - Auth
    - Permission state
    """

    # Settings & Model
    settings: Dict[str, Any] = field(default_factory=dict)
    verbose: bool = False
    main_loop_model: Optional[str] = None
    main_loop_model_for_session: Optional[str] = None
    status_line_text: Optional[str] = None

    # UI State
    expanded_view: str = "none"
    is_brief_only: bool = False
    show_teammate_message_preview: bool = False
    selected_ip_agent_index: int = -1
    coordinator_task_index: int = -1
    view_selection_mode: str = "none"
    footer_selection: Optional[str] = None
    tool_permission_context: Optional[Any] = None
    spinner_tip: Optional[str] = None
    agent: Optional[str] = None
    active_overlays: Set[str] = field(default_factory=set)

    # TUI State
    tui: TUIState = field(default_factory=TUIState)

    # Kairos / Remote Session
    kairos_enabled: bool = False
    remote_session_url: Optional[str] = None
    remote_connection_status: str = "disconnected"
    remote_background_task_count: int = 0

    # Always-On Bridge State
    repl_bridge_enabled: bool = False
    repl_bridge_explicit: bool = False
    repl_bridge_outbound_only: bool = False
    repl_bridge_connected: bool = False
    repl_bridge_session_active: bool = False
    repl_bridge_reconnecting: bool = False
    repl_bridge_connect_url: Optional[str] = None
    repl_bridge_session_url: Optional[str] = None
    repl_bridge_environment_id: Optional[str] = None
    repl_bridge_session_id: Optional[str] = None
    repl_bridge_error: Optional[str] = None
    repl_bridge_initial_name: Optional[str] = None
    repl_bridge_permission_callbacks: Optional[Any] = None
    show_remote_callout: bool = False

    # Task State
    tasks: Dict[str, Any] = field(default_factory=dict)
    agent_name_registry: Dict[str, str] = field(default_factory=dict)
    foregrounded_task_id: Optional[str] = None
    viewing_agent_task_id: Optional[str] = None

    # Companion State
    companion_reaction: Optional[str] = None
    companion_pet_at: Optional[int] = None

    # MCP State
    mcp: MCPState = field(default_factory=MCPState)

    # Plugin State
    plugins: PluginState = field(default_factory=PluginState)

    # Agent Definitions & History
    agent_definitions: AgentDefinitionsState = field(
        default_factory=AgentDefinitionsState
    )
    file_history: FileHistoryState = field(default_factory=FileHistoryState)
    attribution: AttributionState = field(default_factory=AttributionState)

    # Todos & Remote Suggestions
    todos: Dict[str, Any] = field(default_factory=dict)
    remote_agent_task_suggestions: List[Any] = field(default_factory=list)

    # Notifications & Elicitation
    notifications: NotificationState = field(default_factory=NotificationState)
    elicitation: ElicitationState = field(default_factory=ElicitationState)

    # Session State
    thinking_enabled: bool = False
    prompt_suggestion_enabled: bool = True
    session_hooks: SessionHooksState = field(default_factory=SessionHooksState)
    fast_mode: bool = False

    # Tungsten/Tmux State
    tungsten_active_session: Optional[TungstenSessionState] = None
    tungsten_last_captured_time: Optional[int] = None
    tungsten_last_command: Optional[TungstenLastCommandState] = None
    tungsten_panel_visible: bool = False
    tungsten_panel_auto_hidden: bool = False

    # Browser State (Bagel)
    bagel_active: bool = False
    bagel_url: Optional[str] = None
    bagel_panel_visible: bool = False

    # Computer Use MCP State (Chicago)
    computer_use_mcp_state: Optional[ComputerUseMcpState] = None

    # REPL Context
    repl_context: Optional[ReplContextState] = None

    # Team Context
    team_context: Optional[TeamContextState] = None

    # Standalone Agent Context
    standalone_agent_context: Optional[StandaloneAgentContextState] = None

    # Inbox
    inbox: InboxState = field(default_factory=InboxState)

    # Worker Sandbox Permissions
    worker_sandbox_permissions: WorkerSandboxPermissionsState = field(
        default_factory=WorkerSandboxPermissionsState
    )
    pending_worker_request: Optional[PendingWorkerRequestState] = None
    pending_sandbox_request: Optional[PendingSandboxRequestState] = None

    # Prompt Suggestion
    prompt_suggestion: PromptSuggestionState = field(
        default_factory=PromptSuggestionState
    )

    # Speculation
    speculation: SpeculationState = field(default_factory=SpeculationState)
    speculation_session_time_saved_ms: int = 0

    # Skill Improvement
    skill_improvement: SkillImprovementState = field(
        default_factory=SkillImprovementState
    )

    # Auth
    auth_version: int = 0

    # Initial Message
    initial_message: Optional[InitialMessageState] = None

    # Pending Plan Verification
    pending_plan_verification: Optional[PendingPlanVerificationState] = None

    # Denial Tracking
    denial_tracking: Optional[Any] = None

    # Ultraplan
    ultraplan_launching: bool = False
    ultraplan_session_url: Optional[str] = None
    ultraplan_pending_choice: Optional[Dict[str, str]] = None
    ultraplan_launch_pending: Optional[Dict[str, str]] = None
    is_ultraplan_mode: bool = False

    # Channel Permission Callbacks
    channel_permission_callbacks: Optional[Any] = None


def create_default_app_state() -> AppState:
    """
    Create default AppState instance.

    Returns:
        New AppState with default values
    """
    return AppState()
