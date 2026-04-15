from __future__ import annotations

from typing import Any, Literal

from py_claw.schemas.common import (
    AccountInfo,
    AgentDefinition,
    AgentInfo,
    EffortLevel,
    ElicitationAction,
    ElicitationMode,
    FastModeState,
    HookEvent,
    JSONDict,
    McpServerConfigForProcessTransport,
    McpServerStatusModel,
    McpSetServersResult,
    ModelInfo,
    PermissionMode,
    PermissionUpdate,
    PyClawBaseModel,
    RewindFilesResult,
    SDKMessage,
    SDKPostTurnSummaryMessage,
    SDKStreamlinedTextMessage,
    SDKStreamlinedToolUseSummaryMessage,
    SDKUserMessage,
    SDKUserMessageReplay,
    SlashCommand,
)


ControlSettingsSource = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
]


class SDKHookCallbackMatcher(PyClawBaseModel):
    matcher: str | None = None
    hookCallbackIds: list[str]
    timeout: float | None = None


class SDKControlInitializeRequest(PyClawBaseModel):
    subtype: Literal["initialize"]
    hooks: dict[HookEvent, list[SDKHookCallbackMatcher]] | None = None
    sdkMcpServers: list[str] | None = None
    jsonSchema: JSONDict | None = None
    systemPrompt: str | None = None
    appendSystemPrompt: str | None = None
    agents: dict[str, AgentDefinition] | None = None
    promptSuggestions: bool | None = None
    agentProgressSummaries: bool | None = None


class SDKControlInitializeResponse(PyClawBaseModel):
    commands: list[SlashCommand]
    agents: list[AgentInfo]
    output_style: str
    available_output_styles: list[str]
    models: list[ModelInfo]
    account: AccountInfo
    mcpServers: list[McpServerStatusModel] | None = None
    pid: int | None = None
    fast_mode_state: FastModeState | None = None


class SDKControlInterruptRequest(PyClawBaseModel):
    subtype: Literal["interrupt"]


class SDKControlPermissionRequest(PyClawBaseModel):
    subtype: Literal["can_use_tool"]
    tool_name: str
    input: JSONDict
    permission_suggestions: list[PermissionUpdate] | None = None
    blocked_path: str | None = None
    decision_reason: str | None = None
    title: str | None = None
    display_name: str | None = None
    tool_use_id: str
    agent_id: str | None = None
    description: str | None = None


class SDKControlSetPermissionModeRequest(PyClawBaseModel):
    subtype: Literal["set_permission_mode"]
    mode: PermissionMode
    ultraplan: bool | None = None


class SDKControlSetModelRequest(PyClawBaseModel):
    subtype: Literal["set_model"]
    model: str | None = None


class SDKControlSetMaxThinkingTokensRequest(PyClawBaseModel):
    subtype: Literal["set_max_thinking_tokens"]
    max_thinking_tokens: int | None


class SDKControlMcpStatusRequest(PyClawBaseModel):
    subtype: Literal["mcp_status"]


class SDKControlMcpStatusResponse(PyClawBaseModel):
    mcpServers: list[McpServerStatusModel]


class SDKControlGetContextUsageRequest(PyClawBaseModel):
    subtype: Literal["get_context_usage"]


class ContextCategory(PyClawBaseModel):
    name: str
    tokens: int
    color: str
    isDeferred: bool | None = None


class ContextGridSquare(PyClawBaseModel):
    color: str
    isFilled: bool
    categoryName: str
    tokens: int
    percentage: float
    squareFullness: float


class MemoryFileUsage(PyClawBaseModel):
    path: str
    type: str
    tokens: int


class McpToolUsage(PyClawBaseModel):
    name: str
    serverName: str
    tokens: int
    isLoaded: bool | None = None


class BuiltinToolUsage(PyClawBaseModel):
    name: str
    tokens: int
    isLoaded: bool | None = None


class AgentUsage(PyClawBaseModel):
    agentType: str
    source: str
    tokens: int


class SlashCommandUsage(PyClawBaseModel):
    totalCommands: int
    includedCommands: int
    tokens: int


class SkillFrontmatterUsage(PyClawBaseModel):
    name: str
    source: str
    tokens: int
    argumentHint: str | None = None
    whenToUse: str | None = None
    version: str | None = None
    model: str | None = None
    allowedTools: list[str] | None = None
    effort: str | None = None
    userInvocable: bool | None = None
    disableModelInvocation: bool | None = None


class SkillUsage(PyClawBaseModel):
    totalSkills: int
    includedSkills: int
    tokens: int
    skillFrontmatter: list[SkillFrontmatterUsage]


class TokenCountByName(PyClawBaseModel):
    name: str
    tokens: int


class ToolCallBreakdown(PyClawBaseModel):
    name: str
    callTokens: int
    resultTokens: int


class MessageBreakdown(PyClawBaseModel):
    toolCallTokens: int
    toolResultTokens: int
    attachmentTokens: int
    assistantMessageTokens: int
    userMessageTokens: int
    toolCallsByType: list[ToolCallBreakdown]
    attachmentsByType: list[TokenCountByName]


class APIUsage(PyClawBaseModel):
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


class SDKControlGetContextUsageResponse(PyClawBaseModel):
    categories: list[ContextCategory]
    totalTokens: int
    maxTokens: int
    rawMaxTokens: int
    percentage: float
    gridRows: list[list[ContextGridSquare]]
    model: str
    memoryFiles: list[MemoryFileUsage]
    mcpTools: list[McpToolUsage]
    deferredBuiltinTools: list[BuiltinToolUsage] | None = None
    systemTools: list[TokenCountByName] | None = None
    systemPromptSections: list[TokenCountByName] | None = None
    agents: list[AgentUsage]
    slashCommands: SlashCommandUsage | None = None
    skills: SkillUsage | None = None
    autoCompactThreshold: int | None = None
    isAutoCompactEnabled: bool
    messageBreakdown: MessageBreakdown | None = None
    apiUsage: APIUsage | None = None


class SDKControlRewindFilesRequest(PyClawBaseModel):
    subtype: Literal["rewind_files"]
    user_message_id: str
    dry_run: bool | None = None


class SDKControlRewindFilesResponse(RewindFilesResult):
    pass


class SDKControlCancelAsyncMessageRequest(PyClawBaseModel):
    subtype: Literal["cancel_async_message"]
    message_uuid: str


class SDKControlCancelAsyncMessageResponse(PyClawBaseModel):
    cancelled: bool


class SDKControlSeedReadStateRequest(PyClawBaseModel):
    subtype: Literal["seed_read_state"]
    path: str
    mtime: float


class SDKControlMcpMessageRequest(PyClawBaseModel):
    subtype: Literal["mcp_message"]
    server_name: str
    message: Any


class SDKControlMcpSetServersRequest(PyClawBaseModel):
    subtype: Literal["mcp_set_servers"]
    servers: dict[str, McpServerConfigForProcessTransport]


class SDKControlMcpSetServersResponse(McpSetServersResult):
    pass


class PluginInfo(PyClawBaseModel):
    name: str
    path: str
    source: str | None = None


class SDKControlReloadPluginsRequest(PyClawBaseModel):
    subtype: Literal["reload_plugins"]


class SDKControlReloadPluginsResponse(PyClawBaseModel):
    commands: list[SlashCommand]
    agents: list[AgentInfo]
    plugins: list[PluginInfo]
    mcpServers: list[McpServerStatusModel]
    error_count: int


class SDKControlMcpReconnectRequest(PyClawBaseModel):
    subtype: Literal["mcp_reconnect"]
    serverName: str


class SDKControlMcpToggleRequest(PyClawBaseModel):
    subtype: Literal["mcp_toggle"]
    serverName: str
    enabled: bool


class SDKControlStopTaskRequest(PyClawBaseModel):
    subtype: Literal["stop_task"]
    task_id: str


class SDKControlApplyFlagSettingsRequest(PyClawBaseModel):
    subtype: Literal["apply_flag_settings"]
    settings: JSONDict


class SDKControlGetSettingsRequest(PyClawBaseModel):
    subtype: Literal["get_settings"]


class SettingsSourceEntry(PyClawBaseModel):
    source: ControlSettingsSource
    settings: JSONDict


class AppliedSettings(PyClawBaseModel):
    model: str
    effort: EffortLevel | None = None


class SDKControlGetSettingsResponse(PyClawBaseModel):
    effective: JSONDict
    sources: list[SettingsSourceEntry]
    applied: AppliedSettings | None = None


class SDKControlElicitationRequest(PyClawBaseModel):
    subtype: Literal["elicitation"]
    mcp_server_name: str
    message: str
    mode: ElicitationMode | None = None
    url: str | None = None
    elicitation_id: str | None = None
    requested_schema: JSONDict | None = None


class SDKControlElicitationResponse(PyClawBaseModel):
    action: ElicitationAction
    content: JSONDict | None = None


class SDKControlRequestEnvelope(PyClawBaseModel):
    type: Literal["control_request"]
    request_id: str
    request: "SDKControlRequest"


class ControlResponseSuccess(PyClawBaseModel):
    subtype: Literal["success"]
    request_id: str
    response: dict[str, Any] | None = None


class ControlResponseError(PyClawBaseModel):
    subtype: Literal["error"]
    request_id: str
    error: str
    pending_permission_requests: list[SDKControlRequestEnvelope] | None = None


class SDKControlResponseEnvelope(PyClawBaseModel):
    type: Literal["control_response"]
    response: ControlResponseSuccess | ControlResponseError


class SDKControlCancelRequest(PyClawBaseModel):
    type: Literal["control_cancel_request"]
    request_id: str


class SDKKeepAliveMessage(PyClawBaseModel):
    type: Literal["keep_alive"]


class SDKUpdateEnvironmentVariablesMessage(PyClawBaseModel):
    type: Literal["update_environment_variables"]
    variables: dict[str, str]


SDKControlRequest = (
    SDKControlInitializeRequest
    | SDKControlInterruptRequest
    | SDKControlPermissionRequest
    | SDKControlSetPermissionModeRequest
    | SDKControlSetModelRequest
    | SDKControlSetMaxThinkingTokensRequest
    | SDKControlMcpStatusRequest
    | SDKControlGetContextUsageRequest
    | SDKControlRewindFilesRequest
    | SDKControlCancelAsyncMessageRequest
    | SDKControlSeedReadStateRequest
    | SDKControlMcpMessageRequest
    | SDKControlMcpSetServersRequest
    | SDKControlReloadPluginsRequest
    | SDKControlMcpReconnectRequest
    | SDKControlMcpToggleRequest
    | SDKControlStopTaskRequest
    | SDKControlApplyFlagSettingsRequest
    | SDKControlGetSettingsRequest
    | SDKControlElicitationRequest
)

ControlResponse = ControlResponseSuccess | ControlResponseError
StdoutMessage = (
    SDKMessage
    | SDKStreamlinedTextMessage
    | SDKStreamlinedToolUseSummaryMessage
    | SDKPostTurnSummaryMessage
    | SDKControlResponseEnvelope
    | SDKControlRequestEnvelope
    | SDKControlCancelRequest
    | SDKKeepAliveMessage
)
StdinMessage = (
    SDKUserMessage
    | SDKUserMessageReplay
    | SDKControlRequestEnvelope
    | SDKControlResponseEnvelope
    | SDKKeepAliveMessage
    | SDKUpdateEnvironmentVariablesMessage
)


SDKControlRequestEnvelope.model_rebuild()
ControlResponseError.model_rebuild()
SDKControlResponseEnvelope.model_rebuild()
