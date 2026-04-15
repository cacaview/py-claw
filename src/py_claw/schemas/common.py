from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PyClawBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


JSONDict = dict[str, Any]
StringMap = dict[str, str]

OutputFormatType = Literal["json_schema"]
ApiKeySource = Literal["user", "project", "org", "temporary", "oauth"]
ApiProvider = Literal["firstParty", "bedrock", "vertex", "foundry"]
ConfigScope = Literal["local", "user", "project", "dynamic", "enterprise", "claudeai", "managed"]
SettingSource = Literal["user", "project", "local"]
SdkBeta = Literal["context-1m-2025-08-07"]
EffortLevel = Literal["low", "medium", "high", "max"]
PermissionBehavior = Literal["allow", "deny", "ask"]
PermissionDecisionClassification = Literal["user_temporary", "user_permanent", "user_reject"]
PermissionUpdateDestination = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
    "session",
    "cliArg",
]
PermissionMode = Literal[
    "default",
    "acceptEdits",
    "bypassPermissions",
    "plan",
    "dontAsk",
]
McpServerStatus = Literal["connected", "failed", "needs-auth", "pending", "disabled"]
McpTransportType = Literal["stdio", "sse", "sse-ide", "http", "ws", "ws-ide", "sdk", "claudeai-proxy"]
ElicitationMode = Literal["form", "url"]
ElicitationAction = Literal["accept", "decline", "cancel"]
HookEvent = Literal[
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "UserPromptSubmit",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "PermissionRequest",
    "PermissionDenied",
    "Setup",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "Elicitation",
    "ElicitationResult",
    "ConfigChange",
    "WorktreeCreate",
    "WorktreeRemove",
    "InstructionsLoaded",
    "CwdChanged",
    "FileChanged",
]

HOOK_EVENTS: tuple[str, ...] = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "UserPromptSubmit",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "PermissionRequest",
    "PermissionDenied",
    "Setup",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "Elicitation",
    "ElicitationResult",
    "ConfigChange",
    "WorktreeCreate",
    "WorktreeRemove",
    "InstructionsLoaded",
    "CwdChanged",
    "FileChanged",
)

SHELL_TYPES: tuple[str, ...] = ("bash", "powershell")


class JsonSchemaOutputFormat(PyClawBaseModel):
    type: Literal["json_schema"]
    schema_: JSONDict = Field(alias="schema")


class ModelUsage(PyClawBaseModel):
    inputTokens: int
    outputTokens: int
    cacheReadInputTokens: int
    cacheCreationInputTokens: int
    webSearchRequests: int
    costUSD: float
    contextWindow: int
    maxOutputTokens: int


class PermissionRuleValue(PyClawBaseModel):
    toolName: str
    ruleContent: str | None = None


class PermissionUpdateAddRules(PyClawBaseModel):
    type: Literal["addRules"]
    rules: list[PermissionRuleValue]
    behavior: PermissionBehavior
    destination: PermissionUpdateDestination


class PermissionUpdateReplaceRules(PyClawBaseModel):
    type: Literal["replaceRules"]
    rules: list[PermissionRuleValue]
    behavior: PermissionBehavior
    destination: PermissionUpdateDestination


class PermissionUpdateRemoveRules(PyClawBaseModel):
    type: Literal["removeRules"]
    rules: list[PermissionRuleValue]
    behavior: PermissionBehavior
    destination: PermissionUpdateDestination


class PermissionUpdateSetMode(PyClawBaseModel):
    type: Literal["setMode"]
    mode: PermissionMode
    destination: PermissionUpdateDestination


class PermissionUpdateAddDirectories(PyClawBaseModel):
    type: Literal["addDirectories"]
    directories: list[str]
    destination: PermissionUpdateDestination


class PermissionUpdateRemoveDirectories(PyClawBaseModel):
    type: Literal["removeDirectories"]
    directories: list[str]
    destination: PermissionUpdateDestination


PermissionUpdate = (
    PermissionUpdateAddRules
    | PermissionUpdateReplaceRules
    | PermissionUpdateRemoveRules
    | PermissionUpdateSetMode
    | PermissionUpdateAddDirectories
    | PermissionUpdateRemoveDirectories
)


class PermissionResultAllow(PyClawBaseModel):
    behavior: Literal["allow"]
    updatedInput: JSONDict | None = None
    updatedPermissions: list[PermissionUpdate] | None = None
    toolUseID: str | None = None
    decisionClassification: PermissionDecisionClassification | None = None


class PermissionResultDeny(PyClawBaseModel):
    behavior: Literal["deny"]
    message: str
    interrupt: bool | None = None
    toolUseID: str | None = None
    decisionClassification: PermissionDecisionClassification | None = None


PermissionResult = PermissionResultAllow | PermissionResultDeny
FastModeState = Literal["off", "cooldown", "on"]


class SlashCommand(PyClawBaseModel):
    name: str
    description: str
    argumentHint: str


class AgentDefinition(PyClawBaseModel):
    name: str | None = None
    description: str
    prompt: str
    tools: list[str] | None = None
    disallowedTools: list[str] | None = None
    model: str | None = None
    mcpServers: list[str | JSONDict] | None = None
    criticalSystemReminder_EXPERIMENTAL: str | None = None
    skills: list[str] | None = None
    initialPrompt: str | None = None
    maxTurns: int | None = None
    background: bool | None = None
    memory: Literal["user", "project", "local"] | None = None
    effort: EffortLevel | int | None = None
    permissionMode: PermissionMode | None = None


class AgentInfo(PyClawBaseModel):
    name: str
    description: str
    model: str | None = None


class ModelInfo(PyClawBaseModel):
    value: str
    displayName: str
    description: str
    supportsEffort: bool | None = None
    supportedEffortLevels: list[EffortLevel] | None = None
    supportsAdaptiveThinking: bool | None = None
    supportsFastMode: bool | None = None
    supportsAutoMode: bool | None = None


class AccountInfo(PyClawBaseModel):
    email: str | None = None
    organization: str | None = None
    subscriptionType: str | None = None
    tokenSource: str | None = None
    apiKeySource: str | None = None
    apiProvider: ApiProvider | None = None


class McpStdioServerConfig(PyClawBaseModel):
    type: Literal["stdio"] | None = None
    command: str
    args: list[str] | None = None
    env: dict[str, str] | None = None


class McpSSEServerConfig(PyClawBaseModel):
    type: Literal["sse"]
    url: str
    headers: dict[str, str] | None = None


class McpHttpServerConfig(PyClawBaseModel):
    type: Literal["http"]
    url: str
    headers: dict[str, str] | None = None


class McpSdkServerConfig(PyClawBaseModel):
    type: Literal["sdk"]
    name: str


class McpClaudeAIProxyServerConfig(PyClawBaseModel):
    type: Literal["claudeai-proxy"]
    url: str
    id: str


class McpWebSocketServerConfig(PyClawBaseModel):
    type: Literal["websocket"]
    url: str
    headers: dict[str, str] | None = None
    ping_interval_seconds: float | None = None


class McpOAuthConfig(PyClawBaseModel):
    """OAuth configuration for MCP servers."""
    clientId: str | None = None
    callbackPort: int | None = None
    authServerMetadataUrl: str | None = None
    xaa: bool | None = None


class McpSSEIDEServerConfig(PyClawBaseModel):
    """Internal-only server type for IDE extensions via SSE."""
    type: Literal["sse-ide"]
    url: str
    ideName: str
    ideRunningInWindows: bool | None = None


class McpWebSocketIDEServerConfig(PyClawBaseModel):
    """Internal-only server type for IDE extensions via WebSocket."""
    type: Literal["ws-ide"]
    url: str
    ideName: str
    authToken: str | None = None
    ideRunningInWindows: bool | None = None


class McpSSEConfigWithOAuth(PyClawBaseModel):
    """SSE config with optional OAuth support."""
    type: Literal["sse"]
    url: str
    headers: dict[str, str] | None = None
    headersHelper: str | None = None
    oauth: McpOAuthConfig | None = None


class McpHttpConfigWithOAuth(PyClawBaseModel):
    """HTTP config with optional OAuth support."""
    type: Literal["http"]
    url: str
    headers: dict[str, str] | None = None
    headersHelper: str | None = None
    oauth: McpOAuthConfig | None = None


class McpWebSocketConfigExtended(PyClawBaseModel):
    """WebSocket config with optional headersHelper."""
    type: Literal["ws"]
    url: str
    headers: dict[str, str] | None = None
    headersHelper: str | None = None


McpServerConfigForProcessTransport = (
    McpStdioServerConfig | McpSSEServerConfig | McpHttpServerConfig | McpSdkServerConfig | McpWebSocketServerConfig | McpClaudeAIProxyServerConfig | McpSSEIDEServerConfig | McpWebSocketIDEServerConfig | McpSSEConfigWithOAuth | McpHttpConfigWithOAuth | McpWebSocketConfigExtended
)
McpServerStatusConfig = McpServerConfigForProcessTransport | McpClaudeAIProxyServerConfig


class McpToolAnnotation(PyClawBaseModel):
    readOnly: bool | None = None
    destructive: bool | None = None
    openWorld: bool | None = None


class McpToolInfo(PyClawBaseModel):
    name: str
    description: str | None = None
    annotations: McpToolAnnotation | None = None


class McpServerInfo(PyClawBaseModel):
    name: str
    version: str


class McpCapabilities(PyClawBaseModel):
    experimental: dict[str, Any] | None = None


class McpServerStatusModel(PyClawBaseModel):
    name: str
    status: McpServerStatus
    serverInfo: McpServerInfo | None = None
    error: str | None = None
    config: McpServerStatusConfig | None = None
    scope: str | None = None
    tools: list[McpToolInfo] | None = None
    capabilities: McpCapabilities | None = None


class McpSetServersResult(PyClawBaseModel):
    added: list[str]
    removed: list[str]
    errors: dict[str, str]


# MCP server connection state types (mirrors TypeScript types.ts)
class ConnectedMcpServer(PyClawBaseModel):
    """Represents a connected MCP server."""
    name: str
    type: Literal["connected"] = "connected"
    capabilities: McpCapabilities | None = None
    serverInfo: McpServerInfo | None = None
    instructions: str | None = None


class FailedMcpServer(PyClawBaseModel):
    """Represents a failed MCP server."""
    name: str
    type: Literal["failed"] = "failed"
    error: str | None = None


class NeedsAuthMcpServer(PyClawBaseModel):
    """Represents an MCP server that needs authentication."""
    name: str
    type: Literal["needs-auth"] = "needs-auth"


class PendingMcpServer(PyClawBaseModel):
    """Represents a pending MCP server connection."""
    name: str
    type: Literal["pending"] = "pending"
    reconnectAttempt: int | None = None
    maxReconnectAttempts: int | None = None


class DisabledMcpServer(PyClawBaseModel):
    """Represents a disabled MCP server."""
    name: str
    type: Literal["disabled"] = "disabled"


McpServerConnection = ConnectedMcpServer | FailedMcpServer | NeedsAuthMcpServer | PendingMcpServer | DisabledMcpServer


# Serialized MCP tool type
class SerializedTool(PyClawBaseModel):
    """Serialized MCP tool for CLI state."""
    name: str
    description: str | None = None
    inputJsonSchema: dict[str, Any] | None = None
    isMcp: bool | None = None
    originalToolName: str | None = None


# MCP CLI state for serialization
class McpCliState(PyClawBaseModel):
    """MCP CLI state for cross-process communication."""
    clients: list[dict[str, Any]]
    configs: dict[str, dict[str, Any]]
    tools: list[SerializedTool]
    resources: dict[str, list[dict[str, Any]]]
    normalizedNames: dict[str, str] | None = None


# Server resource type
class ServerResource(PyClawBaseModel):
    """MCP server resource with server attribution."""
    uri: str
    name: str | None = None
    description: str | None = None
    mimeType: str | None = None
    server: str | None = None


class RewindFilesResult(PyClawBaseModel):
    canRewind: bool
    error: str | None = None
    filesChanged: list[str] | None = None
    insertions: int | None = None
    deletions: int | None = None


SessionStartSource = Literal["startup", "resume", "clear", "compact"]
SetupTrigger = Literal["init", "maintenance"]
CompactTrigger = Literal["manual", "auto"]
ConfigChangeSource = Literal[
    "user_settings",
    "project_settings",
    "local_settings",
    "policy_settings",
    "skills",
]
InstructionsLoadReason = Literal[
    "session_start",
    "nested_traversal",
    "path_glob_match",
    "include",
    "compact",
]
InstructionsMemoryType = Literal["User", "Project", "Local", "Managed"]
FileChangedEvent = Literal["change", "add", "unlink"]
ExitReason = Literal[
    "clear",
    "resume",
    "logout",
    "prompt_input_exit",
    "other",
    "bypass_permissions_disabled",
]
SDKAssistantMessageError = Literal[
    "authentication_failed",
    "billing_error",
    "rate_limit",
    "invalid_request",
    "server_error",
    "unknown",
    "max_output_tokens",
]
SDKStatus = Literal["compacting"] | None
RateLimitStatus = Literal["allowed", "allowed_warning", "rejected"]
RateLimitType = Literal[
    "five_hour",
    "seven_day",
    "seven_day_opus",
    "seven_day_sonnet",
    "overage",
]
OverageDisabledReason = Literal[
    "overage_not_provisioned",
    "org_level_disabled",
    "org_level_disabled_until",
    "out_of_credits",
    "seat_tier_level_disabled",
    "member_level_disabled",
    "seat_tier_zero_credit_limit",
    "group_zero_credit_limit",
    "member_zero_credit_limit",
    "org_service_level_disabled",
    "org_service_zero_credit_limit",
    "no_limits_configured",
    "unknown",
]
SDKResultErrorSubtype = Literal[
    "error_during_execution",
    "error_max_turns",
    "error_max_budget_usd",
    "error_max_structured_output_retries",
]
HookOutcome = Literal["success", "error", "cancelled"]
TaskStatus = Literal["completed", "failed", "stopped"]
SessionState = Literal["idle", "running", "requires_action"]
PostTurnStatusCategory = Literal[
    "blocked",
    "waiting",
    "completed",
    "review_ready",
    "failed",
]


class BaseHookInput(PyClawBaseModel):
    session_id: str
    transcript_path: str
    cwd: str
    permission_mode: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None


class PreToolUseHookInput(BaseHookInput):
    hook_event_name: Literal["PreToolUse"]
    tool_name: str
    tool_input: Any
    tool_use_id: str


class PermissionRequestHookInput(BaseHookInput):
    hook_event_name: Literal["PermissionRequest"]
    tool_name: str
    tool_input: Any
    permission_suggestions: list[PermissionUpdate] | None = None


class PostToolUseHookInput(BaseHookInput):
    hook_event_name: Literal["PostToolUse"]
    tool_name: str
    tool_input: Any
    tool_response: Any
    tool_use_id: str


class PostToolUseFailureHookInput(BaseHookInput):
    hook_event_name: Literal["PostToolUseFailure"]
    tool_name: str
    tool_input: Any
    tool_use_id: str
    error: str
    is_interrupt: bool | None = None


class PermissionDeniedHookInput(BaseHookInput):
    hook_event_name: Literal["PermissionDenied"]
    tool_name: str
    tool_input: Any
    tool_use_id: str
    reason: str


class NotificationHookInput(BaseHookInput):
    hook_event_name: Literal["Notification"]
    message: str
    title: str | None = None
    notification_type: str


class UserPromptSubmitHookInput(BaseHookInput):
    hook_event_name: Literal["UserPromptSubmit"]
    prompt: str


class SessionStartHookInput(BaseHookInput):
    hook_event_name: Literal["SessionStart"]
    source: SessionStartSource
    model: str | None = None


class SetupHookInput(BaseHookInput):
    hook_event_name: Literal["Setup"]
    trigger: SetupTrigger


class StopHookInput(BaseHookInput):
    hook_event_name: Literal["Stop"]
    stop_hook_active: bool
    last_assistant_message: str | None = None


class StopFailureHookInput(BaseHookInput):
    hook_event_name: Literal["StopFailure"]
    error: SDKAssistantMessageError
    error_details: str | None = None
    last_assistant_message: str | None = None


class SubagentStartHookInput(BaseHookInput):
    hook_event_name: Literal["SubagentStart"]
    agent_id: str
    agent_type: str


class SubagentStopHookInput(BaseHookInput):
    hook_event_name: Literal["SubagentStop"]
    stop_hook_active: bool
    agent_id: str
    agent_transcript_path: str
    agent_type: str
    last_assistant_message: str | None = None


class PreCompactHookInput(BaseHookInput):
    hook_event_name: Literal["PreCompact"]
    trigger: CompactTrigger
    custom_instructions: str | None


class PostCompactHookInput(BaseHookInput):
    hook_event_name: Literal["PostCompact"]
    trigger: CompactTrigger
    compact_summary: str


class TeammateIdleHookInput(BaseHookInput):
    hook_event_name: Literal["TeammateIdle"]
    teammate_name: str
    team_name: str


class TaskCreatedHookInput(BaseHookInput):
    hook_event_name: Literal["TaskCreated"]
    task_id: str
    task_subject: str
    task_description: str | None = None
    teammate_name: str | None = None
    team_name: str | None = None


class TaskCompletedHookInput(BaseHookInput):
    hook_event_name: Literal["TaskCompleted"]
    task_id: str
    task_subject: str
    task_description: str | None = None
    teammate_name: str | None = None
    team_name: str | None = None


class ElicitationHookInput(BaseHookInput):
    hook_event_name: Literal["Elicitation"]
    mcp_server_name: str
    message: str
    mode: ElicitationMode | None = None
    url: str | None = None
    elicitation_id: str | None = None
    requested_schema: JSONDict | None = None


class ElicitationResultHookInput(BaseHookInput):
    hook_event_name: Literal["ElicitationResult"]
    mcp_server_name: str
    elicitation_id: str | None = None
    mode: ElicitationMode | None = None
    action: ElicitationAction
    content: JSONDict | None = None


class ConfigChangeHookInput(BaseHookInput):
    hook_event_name: Literal["ConfigChange"]
    source: ConfigChangeSource
    file_path: str | None = None


class InstructionsLoadedHookInput(BaseHookInput):
    hook_event_name: Literal["InstructionsLoaded"]
    file_path: str
    memory_type: InstructionsMemoryType
    load_reason: InstructionsLoadReason
    globs: list[str] | None = None
    trigger_file_path: str | None = None
    parent_file_path: str | None = None


class WorktreeCreateHookInput(BaseHookInput):
    hook_event_name: Literal["WorktreeCreate"]
    name: str


class WorktreeRemoveHookInput(BaseHookInput):
    hook_event_name: Literal["WorktreeRemove"]
    worktree_path: str


class CwdChangedHookInput(BaseHookInput):
    hook_event_name: Literal["CwdChanged"]
    old_cwd: str
    new_cwd: str


class FileChangedHookInput(BaseHookInput):
    hook_event_name: Literal["FileChanged"]
    file_path: str
    event: FileChangedEvent


class SessionEndHookInput(BaseHookInput):
    hook_event_name: Literal["SessionEnd"]
    reason: ExitReason


HookInput = (
    PreToolUseHookInput
    | PostToolUseHookInput
    | PostToolUseFailureHookInput
    | PermissionDeniedHookInput
    | NotificationHookInput
    | UserPromptSubmitHookInput
    | SessionStartHookInput
    | SessionEndHookInput
    | StopHookInput
    | StopFailureHookInput
    | SubagentStartHookInput
    | SubagentStopHookInput
    | PreCompactHookInput
    | PostCompactHookInput
    | PermissionRequestHookInput
    | SetupHookInput
    | TeammateIdleHookInput
    | TaskCreatedHookInput
    | TaskCompletedHookInput
    | ElicitationHookInput
    | ElicitationResultHookInput
    | ConfigChangeHookInput
    | InstructionsLoadedHookInput
    | WorktreeCreateHookInput
    | WorktreeRemoveHookInput
    | CwdChangedHookInput
    | FileChangedHookInput
)


class AsyncHookJSONOutput(PyClawBaseModel):
    async_: Literal[True] = Field(alias="async")
    asyncTimeout: float | None = None


class PreToolUseHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["PreToolUse"]
    permissionDecision: PermissionBehavior | None = None
    permissionDecisionReason: str | None = None
    updatedInput: JSONDict | None = None
    additionalContext: str | None = None


class UserPromptSubmitHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["UserPromptSubmit"]
    additionalContext: str | None = None


class SessionStartHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["SessionStart"]
    additionalContext: str | None = None
    initialUserMessage: str | None = None
    watchPaths: list[str] | None = None


class SetupHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["Setup"]
    additionalContext: str | None = None


class SubagentStartHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["SubagentStart"]
    additionalContext: str | None = None


class PostToolUseHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["PostToolUse"]
    additionalContext: str | None = None
    updatedMCPToolOutput: Any | None = None


class PostToolUseFailureHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["PostToolUseFailure"]
    additionalContext: str | None = None


class PermissionDeniedHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["PermissionDenied"]
    retry: bool | None = None


class NotificationHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["Notification"]
    additionalContext: str | None = None


class PermissionRequestHookDecisionAllow(PyClawBaseModel):
    behavior: Literal["allow"]
    updatedInput: JSONDict | None = None
    updatedPermissions: list[PermissionUpdate] | None = None


class PermissionRequestHookDecisionDeny(PyClawBaseModel):
    behavior: Literal["deny"]
    message: str | None = None
    interrupt: bool | None = None


PermissionRequestHookDecision = PermissionRequestHookDecisionAllow | PermissionRequestHookDecisionDeny


class PermissionRequestHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["PermissionRequest"]
    decision: PermissionRequestHookDecision


class ElicitationHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["Elicitation"]
    action: ElicitationAction | None = None
    content: JSONDict | None = None


class ElicitationResultHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["ElicitationResult"]
    action: ElicitationAction | None = None
    content: JSONDict | None = None


class CwdChangedHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["CwdChanged"]
    watchPaths: list[str] | None = None


class FileChangedHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["FileChanged"]
    watchPaths: list[str] | None = None


class WorktreeCreateHookSpecificOutput(PyClawBaseModel):
    hookEventName: Literal["WorktreeCreate"]
    worktreePath: str


HookSpecificOutput = (
    PreToolUseHookSpecificOutput
    | UserPromptSubmitHookSpecificOutput
    | SessionStartHookSpecificOutput
    | SetupHookSpecificOutput
    | SubagentStartHookSpecificOutput
    | PostToolUseHookSpecificOutput
    | PostToolUseFailureHookSpecificOutput
    | PermissionDeniedHookSpecificOutput
    | NotificationHookSpecificOutput
    | PermissionRequestHookSpecificOutput
    | ElicitationHookSpecificOutput
    | ElicitationResultHookSpecificOutput
    | CwdChangedHookSpecificOutput
    | FileChangedHookSpecificOutput
    | WorktreeCreateHookSpecificOutput
)


class SyncHookJSONOutput(PyClawBaseModel):
    continue_: bool | None = Field(default=None, alias="continue")
    suppressOutput: bool | None = None
    stopReason: str | None = None
    decision: Literal["approve", "block"] | None = None
    systemMessage: str | None = None
    reason: str | None = None
    hookSpecificOutput: HookSpecificOutput | None = None


HookJSONOutput = AsyncHookJSONOutput | SyncHookJSONOutput


class PromptRequestOption(PyClawBaseModel):
    key: str
    label: str
    description: str | None = None


class PromptRequest(PyClawBaseModel):
    prompt: str
    message: str
    options: list[PromptRequestOption]


class PromptResponse(PyClawBaseModel):
    prompt_response: str
    selected: str


class SDKRateLimitInfo(PyClawBaseModel):
    status: RateLimitStatus
    resetsAt: int | None = None
    rateLimitType: RateLimitType | None = None
    utilization: float | None = None
    overageStatus: RateLimitStatus | None = None
    overageResetsAt: int | None = None
    overageDisabledReason: OverageDisabledReason | None = None
    isUsingOverage: bool | None = None
    surpassedThreshold: float | None = None


class SDKPermissionDenial(PyClawBaseModel):
    tool_name: str
    tool_use_id: str
    tool_input: JSONDict


class SDKUserMessage(PyClawBaseModel):
    type: Literal["user"]
    message: Any
    parent_tool_use_id: str | None
    isSynthetic: bool | None = None
    tool_use_result: Any | None = None
    priority: Literal["now", "next", "later"] | None = None
    timestamp: str | None = None
    uuid: str | None = None
    session_id: str | None = None


class SDKUserMessageReplay(PyClawBaseModel):
    type: Literal["user"]
    message: Any
    parent_tool_use_id: str | None
    isSynthetic: bool | None = None
    tool_use_result: Any | None = None
    priority: Literal["now", "next", "later"] | None = None
    timestamp: str | None = None
    uuid: str
    session_id: str
    isReplay: Literal[True]


class SDKAssistantMessage(PyClawBaseModel):
    type: Literal["assistant"]
    message: Any
    parent_tool_use_id: str | None
    error: SDKAssistantMessageError | None = None
    uuid: str
    session_id: str


class SDKRateLimitEvent(PyClawBaseModel):
    type: Literal["rate_limit_event"]
    rate_limit_info: SDKRateLimitInfo
    uuid: str
    session_id: str


class SDKResultSuccess(PyClawBaseModel):
    type: Literal["result"]
    subtype: Literal["success"]
    duration_ms: float
    duration_api_ms: float
    is_error: bool
    num_turns: int
    result: str
    stop_reason: str | None
    total_cost_usd: float
    usage: Any
    modelUsage: dict[str, ModelUsage]
    permission_denials: list[SDKPermissionDenial]
    structured_output: Any | None = None
    fast_mode_state: FastModeState | None = None
    uuid: str
    session_id: str


class SDKResultError(PyClawBaseModel):
    type: Literal["result"]
    subtype: SDKResultErrorSubtype
    duration_ms: float
    duration_api_ms: float
    is_error: bool
    num_turns: int
    stop_reason: str | None
    total_cost_usd: float
    usage: Any
    modelUsage: dict[str, ModelUsage]
    permission_denials: list[SDKPermissionDenial]
    errors: list[str]
    fast_mode_state: FastModeState | None = None
    uuid: str
    session_id: str


SDKResultMessage = SDKResultSuccess | SDKResultError


class SDKSystemMcpServer(PyClawBaseModel):
    name: str
    status: str


class SDKPluginInfo(PyClawBaseModel):
    name: str
    path: str
    source: str | None = None


class SDKSystemMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["init"]
    agents: list[str] | None = None
    apiKeySource: ApiKeySource
    betas: list[str] | None = None
    claude_code_version: str
    cwd: str
    tools: list[str]
    mcp_servers: list[SDKSystemMcpServer]
    model: str
    permissionMode: PermissionMode
    slash_commands: list[str]
    output_style: str
    skills: list[str]
    plugins: list[SDKPluginInfo]
    fast_mode_state: FastModeState | None = None
    uuid: str
    session_id: str


class SDKRequestStartEvent(PyClawBaseModel):
    type: Literal["stream_request_start"]


class SDKRequestStartMessage(PyClawBaseModel):
    type: Literal["stream_event"]
    event: SDKRequestStartEvent
    uuid: str
    session_id: str


class SDKPartialAssistantMessage(PyClawBaseModel):
    type: Literal["stream_event"]
    event: Any
    parent_tool_use_id: str | None
    uuid: str
    session_id: str


class SDKCompactBoundaryPreservedSegment(PyClawBaseModel):
    head_uuid: str
    anchor_uuid: str
    tail_uuid: str


class SDKCompactBoundaryMetadata(PyClawBaseModel):
    trigger: CompactTrigger
    pre_tokens: int
    preserved_segment: SDKCompactBoundaryPreservedSegment | None = None


class SDKCompactBoundaryMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["compact_boundary"]
    compact_metadata: SDKCompactBoundaryMetadata
    uuid: str
    session_id: str


class SDKStatusMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["status"]
    status: SDKStatus
    permissionMode: PermissionMode | None = None
    uuid: str
    session_id: str


class SDKPostTurnSummaryMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["post_turn_summary"]
    summarizes_uuid: str
    status_category: PostTurnStatusCategory
    status_detail: str
    is_noteworthy: bool
    title: str
    description: str
    recent_action: str
    needs_action: str
    artifact_urls: list[str]
    uuid: str
    session_id: str


class SDKAPIRetryMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["api_retry"]
    attempt: int
    max_retries: int
    retry_delay_ms: int
    error_status: int | None
    error: SDKAssistantMessageError
    uuid: str
    session_id: str


class SDKLocalCommandOutputMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["local_command_output"]
    content: str
    uuid: str
    session_id: str


class SDKHookStartedMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["hook_started"]
    hook_id: str
    hook_name: str
    hook_event: str
    uuid: str
    session_id: str


class SDKHookProgressMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["hook_progress"]
    hook_id: str
    hook_name: str
    hook_event: str
    stdout: str
    stderr: str
    output: str
    uuid: str
    session_id: str


class SDKHookResponseMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["hook_response"]
    hook_id: str
    hook_name: str
    hook_event: str
    output: str
    stdout: str
    stderr: str
    exit_code: int | None = None
    outcome: HookOutcome
    uuid: str
    session_id: str


class SDKToolProgressMessage(PyClawBaseModel):
    type: Literal["tool_progress"]
    tool_use_id: str
    tool_name: str
    parent_tool_use_id: str | None
    elapsed_time_seconds: float
    task_id: str | None = None
    uuid: str
    session_id: str


class SDKAuthStatusMessage(PyClawBaseModel):
    type: Literal["auth_status"]
    isAuthenticating: bool
    output: list[str]
    error: str | None = None
    uuid: str
    session_id: str


class SDKPersistedFile(PyClawBaseModel):
    filename: str
    file_id: str


class SDKPersistedFileFailure(PyClawBaseModel):
    filename: str
    error: str


class SDKFilesPersistedEvent(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["files_persisted"]
    files: list[SDKPersistedFile]
    failed: list[SDKPersistedFileFailure]
    processed_at: str
    uuid: str
    session_id: str


class SDKTaskUsage(PyClawBaseModel):
    total_tokens: int
    tool_uses: int
    duration_ms: int


class SDKTaskNotificationMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["task_notification"]
    task_id: str
    tool_use_id: str | None = None
    status: TaskStatus
    output_file: str
    summary: str
    usage: SDKTaskUsage | None = None
    uuid: str
    session_id: str


class SDKTaskStartedMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["task_started"]
    task_id: str
    tool_use_id: str | None = None
    description: str
    task_type: str | None = None
    workflow_name: str | None = None
    prompt: str | None = None
    uuid: str
    session_id: str


class SDKSessionStateChangedMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["session_state_changed"]
    state: SessionState
    uuid: str
    session_id: str


class SDKTaskProgressMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["task_progress"]
    task_id: str
    tool_use_id: str | None = None
    description: str
    usage: SDKTaskUsage
    last_tool_name: str | None = None
    summary: str | None = None
    uuid: str
    session_id: str


class SDKToolUseSummaryMessage(PyClawBaseModel):
    type: Literal["tool_use_summary"]
    summary: str
    preceding_tool_use_ids: list[str]
    uuid: str
    session_id: str


class SDKStreamlinedTextMessage(PyClawBaseModel):
    type: Literal["streamlined_text"]
    text: str
    uuid: str
    session_id: str


class SDKStreamlinedToolUseSummaryMessage(PyClawBaseModel):
    type: Literal["streamlined_tool_use_summary"]
    tool_summary: str
    uuid: str
    session_id: str


class SDKElicitationCompleteMessage(PyClawBaseModel):
    type: Literal["system"]
    subtype: Literal["elicitation_complete"]
    mcp_server_name: str
    elicitation_id: str
    uuid: str
    session_id: str


class SDKPromptSuggestionMessage(PyClawBaseModel):
    type: Literal["prompt_suggestion"]
    suggestion: str
    uuid: str
    session_id: str


class SDKSessionInfo(PyClawBaseModel):
    sessionId: str
    summary: str
    lastModified: int
    fileSize: int | None = None
    customTitle: str | None = None
    firstPrompt: str | None = None
    gitBranch: str | None = None
    cwd: str | None = None
    tag: str | None = None
    createdAt: int | None = None


SDKMessage = (
    SDKAssistantMessage
    | SDKUserMessage
    | SDKUserMessageReplay
    | SDKResultSuccess
    | SDKResultError
    | SDKSystemMessage
    | SDKRequestStartMessage
    | SDKPartialAssistantMessage
    | SDKCompactBoundaryMessage
    | SDKStatusMessage
    | SDKAPIRetryMessage
    | SDKLocalCommandOutputMessage
    | SDKHookStartedMessage
    | SDKHookProgressMessage
    | SDKHookResponseMessage
    | SDKToolProgressMessage
    | SDKAuthStatusMessage
    | SDKTaskNotificationMessage
    | SDKTaskStartedMessage
    | SDKTaskProgressMessage
    | SDKSessionStateChangedMessage
    | SDKFilesPersistedEvent
    | SDKToolUseSummaryMessage
    | SDKStreamlinedTextMessage
    | SDKStreamlinedToolUseSummaryMessage
    | SDKRateLimitEvent
    | SDKElicitationCompleteMessage
    | SDKPromptSuggestionMessage
)
