from __future__ import annotations

from typing import Any
import os

from py_claw.schemas.common import AccountInfo, ModelInfo

from py_claw.permissions.engine import PermissionEngine
from py_claw.schemas.common import PermissionResultAllow, PermissionResultDeny
from py_claw.schemas.control import (
    BuiltinToolUsage,
    SDKControlCancelAsyncMessageRequest,
    SDKControlElicitationRequest,
    SDKControlGetContextUsageResponse,
    SDKControlInitializeResponse,
    SDKControlMcpMessageRequest,
    SDKControlMcpReconnectRequest,
    SDKControlMcpToggleRequest,
    SDKControlPermissionRequest,
    SDKControlReloadPluginsResponse,
    SDKControlRequest,
    SDKControlRewindFilesRequest,
    SDKControlSeedReadStateRequest,
    SDKControlSetMaxThinkingTokensRequest,
    SDKControlStopTaskRequest,
)
from py_claw.cli.runtime import RuntimeState
from py_claw.cli.structured_io import StructuredIOError
from py_claw.settings.loader import SettingsLoadResult, get_settings_with_sources
from py_claw.settings.validation import validate_settings_data

_ALLOWED_PERMISSION_MODES = {
    "default",
    "acceptEdits",
    "bypassPermissions",
    "plan",
    "dontAsk",
}
_ALLOWED_EFFORT_LEVELS = {"low", "medium", "high", "max"}
_AVAILABLE_MODELS: tuple[dict[str, Any], ...] = (
    {
        "value": "claude-opus-4-6",
        "displayName": "Claude Opus 4.6",
        "description": "Most capable Claude model for complex coding and agent workflows.",
        "supportsEffort": True,
        "supportedEffortLevels": ["low", "medium", "high", "max"],
        "supportsAdaptiveThinking": True,
        "supportsFastMode": True,
        "supportsAutoMode": True,
    },
    {
        "value": "claude-sonnet-4-6",
        "displayName": "Claude Sonnet 4.6",
        "description": "Balanced Claude model for everyday development tasks.",
        "supportsEffort": True,
        "supportedEffortLevels": ["low", "medium", "high", "max"],
        "supportsAdaptiveThinking": True,
        "supportsFastMode": True,
        "supportsAutoMode": True,
    },
    {
        "value": "claude-haiku-4-5-20251001",
        "displayName": "Claude Haiku 4.5",
        "description": "Fast Claude model for lightweight coding and utility tasks.",
        "supportsEffort": True,
        "supportedEffortLevels": ["low", "medium"],
        "supportsAdaptiveThinking": True,
        "supportsFastMode": True,
        "supportsAutoMode": True,
    },
)


class ControlRuntime:
    def __init__(self, state: RuntimeState | None = None) -> None:
        self.state = state or RuntimeState()

    def handle_request(self, request: SDKControlRequest) -> dict[str, Any] | None:
        match request.subtype:
            case "initialize":
                self.state.apply_initialize_request(request)
                return self._build_initialize_response().model_dump(by_alias=True, exclude_none=True)
            case "interrupt":
                if self.state.query_runtime is not None:
                    self.state.query_runtime.interrupt()
                else:
                    self.state.interrupt_event.set()
                return {}
            case "set_permission_mode":
                self.state.permission_mode = request.mode
                return {}
            case "set_model":
                self.state.model = request.model
                return {}
            case "set_max_thinking_tokens":
                return self._handle_set_max_thinking_tokens(request)
            case "apply_flag_settings":
                self._apply_flag_settings(request.settings)
                return {}
            case "get_settings":
                return self._get_settings_response()
            case "get_context_usage":
                return self._get_context_usage_response()
            case "rewind_files":
                return self._handle_rewind_files(request)
            case "cancel_async_message":
                return self._handle_cancel_async_message(request)
            case "seed_read_state":
                return self._handle_seed_read_state(request)
            case "can_use_tool":
                return self._handle_can_use_tool(request)
            case "mcp_status":
                return {"mcpServers": self._build_mcp_statuses()}
            case "mcp_set_servers":
                return self._set_mcp_servers(request.servers)
            case "mcp_reconnect":
                return self._handle_mcp_reconnect(request)
            case "mcp_toggle":
                return self._handle_mcp_toggle(request)
            case "mcp_message":
                return self._handle_mcp_message(request)
            case "reload_plugins":
                return self._handle_reload_plugins()
            case "elicitation":
                return self._handle_elicitation(request)
            case "stop_task":
                return self._handle_stop_task(request)
            case _:
                raise StructuredIOError(f"Unsupported control request subtype: {request.subtype}")

    def _get_context_usage_response(self) -> dict[str, Any]:
        settings = self._load_settings()
        model = self.state.model or settings.effective.get("model") or "default"
        raw_max_tokens = self._context_limit_for_model(str(model))
        system_prompt_sections = self._build_system_prompt_sections()
        mcp_statuses = self.state.mcp_runtime.build_statuses(settings)
        response = SDKControlGetContextUsageResponse(
            categories=[],
            totalTokens=0,
            maxTokens=raw_max_tokens,
            rawMaxTokens=raw_max_tokens,
            percentage=0.0,
            gridRows=[],
            model=str(model),
            memoryFiles=[],
            mcpTools=self._build_mcp_tool_usage(mcp_statuses),
            deferredBuiltinTools=self._build_builtin_tool_usage(),
            agents=self.state.build_agent_usage(settings.effective.get("agents")),
            slashCommands=self.state.build_slash_command_usage(settings.effective.get("skills")),
            skills=self.state.build_skill_usage(settings.effective.get("skills")),
            systemPromptSections=system_prompt_sections or None,
            autoCompactThreshold=settings.effective.get("autoCompactThreshold")
            if isinstance(settings.effective.get("autoCompactThreshold"), int)
            else None,
            isAutoCompactEnabled=bool(settings.effective.get("autoCompactEnabled", False)),
        )
        return response.model_dump(by_alias=True, exclude_none=True)

    def _build_builtin_tool_usage(self) -> list[BuiltinToolUsage]:
        tool_names = self.state.tool_runtime.available_tool_names()
        return [BuiltinToolUsage(name=name, tokens=0, isLoaded=True) for name in tool_names]

    def _build_mcp_tool_usage(self, statuses: list[Any]) -> list[dict[str, Any]]:
        usage: list[dict[str, Any]] = []
        for status in statuses:
            server_name = getattr(status, "name", None)
            tools = getattr(status, "tools", None) or []
            is_loaded = getattr(status, "status", None) not in {"disabled", "failed"}
            if not isinstance(server_name, str) or not server_name:
                continue
            for tool in tools:
                tool_name = getattr(tool, "name", None)
                if not isinstance(tool_name, str) or not tool_name:
                    continue
                usage.append(
                    {
                        "name": tool_name,
                        "serverName": server_name,
                        "tokens": 0,
                        "isLoaded": is_loaded,
                    }
                )
        return usage

    def _build_system_prompt_sections(self) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        if self.state.system_prompt:
            sections.append({"name": "systemPrompt", "tokens": 0})
        if self.state.append_system_prompt:
            sections.append({"name": "appendSystemPrompt", "tokens": 0})
        if self.state.json_schema is not None:
            sections.append({"name": "jsonSchema", "tokens": 0})
        return sections

    def _context_limit_for_model(self, model: str) -> int:
        normalized = model.lower()
        if "haiku" in normalized:
            return 200_000
        if "sonnet" in normalized or "opus" in normalized:
            return 200_000
        return 0

    def _build_initialize_response(self) -> SDKControlInitializeResponse:
        settings = self._load_settings()
        command_registry = self.state.build_command_registry(settings.effective.get("skills"))
        return SDKControlInitializeResponse(
            commands=command_registry.slash_commands(),
            agents=self.state.build_agent_infos(settings.effective.get("agents")),
            output_style="text",
            available_output_styles=["text", "json", "stream-json"],
            models=self._build_model_catalog(),
            account=self._build_account_info(settings),
            mcpServers=self._build_mcp_statuses(),
            pid=os.getpid(),
            fast_mode_state="off",
        )

    def _build_model_catalog(self) -> list[ModelInfo]:
        return [ModelInfo.model_validate(model) for model in _AVAILABLE_MODELS]

    def _build_account_info(self, settings: SettingsLoadResult) -> AccountInfo:
        return AccountInfo(
            apiKeySource=self._detect_api_key_source(settings),
            apiProvider=self._detect_api_provider(settings),
        )

    def _detect_api_key_source(self, settings: SettingsLoadResult) -> str | None:
        effective = settings.effective
        if isinstance(effective.get("apiKeySource"), str) and effective.get("apiKeySource"):
            return str(effective["apiKeySource"])
        if isinstance(effective.get("api_key_source"), str) and effective.get("api_key_source"):
            return str(effective["api_key_source"])
        if isinstance(effective.get("apiKey"), str) and effective.get("apiKey"):
            return "user"
        if isinstance(os.environ.get("ANTHROPIC_API_KEY"), str) and os.environ.get("ANTHROPIC_API_KEY"):
            return "user"
        if isinstance(os.environ.get("AWS_REGION"), str) and os.environ.get("AWS_REGION"):
            return "user"
        if isinstance(os.environ.get("VERTEX_PROJECT"), str) and os.environ.get("VERTEX_PROJECT"):
            return "user"
        if isinstance(os.environ.get("AZURE_OPENAI_API_KEY"), str) and os.environ.get("AZURE_OPENAI_API_KEY"):
            return "user"
        return None

    def _detect_api_provider(self, settings: SettingsLoadResult) -> str | None:
        effective = settings.effective
        configured = effective.get("apiProvider")
        if configured in {"firstParty", "bedrock", "vertex", "foundry"}:
            return str(configured)
        if isinstance(os.environ.get("AZURE_OPENAI_API_KEY"), str) and os.environ.get("AZURE_OPENAI_API_KEY"):
            return "foundry"
        if isinstance(os.environ.get("VERTEX_PROJECT"), str) and os.environ.get("VERTEX_PROJECT"):
            return "vertex"
        if isinstance(os.environ.get("AWS_REGION"), str) and os.environ.get("AWS_REGION"):
            return "bedrock"
        if isinstance(os.environ.get("ANTHROPIC_API_KEY"), str) and os.environ.get("ANTHROPIC_API_KEY"):
            return "firstParty"
        return None

    def _apply_flag_settings(self, incoming: dict[str, Any]) -> None:
        merged = {**self.state.flag_settings, **incoming}
        for key in list(merged):
            if merged[key] is None:
                del merged[key]
        normalized, issues = validate_settings_data(merged, "flagSettings")
        validation_errors = [issue.message for issue in issues if issue.path == "" or not issue.message.endswith("was skipped")]
        if normalized is None:
            detail = validation_errors[0] if validation_errors else "Invalid flag settings"
            raise StructuredIOError(detail)
        self.state.flag_settings = normalized
        if "permissions" in normalized:
            default_mode = (normalized.get("permissions") or {}).get("defaultMode")
            if default_mode in _ALLOWED_PERMISSION_MODES:
                self.state.permission_mode = default_mode
        if "model" in normalized:
            model = normalized.get("model")
            self.state.model = str(model) if model is not None else None

    def _get_settings_response(self) -> dict[str, Any]:
        settings = self._load_settings()
        applied_model = self.state.model or settings.effective.get("model") or "default"
        effort = settings.effective.get("effort")
        return {
            "effective": settings.effective,
            "sources": settings.sources,
            "applied": {
                "model": str(applied_model),
                "effort": effort if effort in _ALLOWED_EFFORT_LEVELS else None,
            },
        }

    def _handle_can_use_tool(self, request: SDKControlPermissionRequest) -> dict[str, Any]:
        settings = self._load_settings()
        engine = PermissionEngine.from_settings(settings, mode=self.state.permission_mode)
        current_input = request.input
        permission_target = self.state.tool_runtime.permission_target_for(request.tool_name, current_input)
        hook_result = self.state.hook_runtime.run_permission_request(
            settings=settings,
            cwd=self.state.cwd,
            tool_name=request.tool_name,
            tool_input=current_input,
            content=permission_target.content,
            permission_mode=self.state.permission_mode,
        )
        if hook_result.permission_decision is not None:
            decision = hook_result.permission_decision
            if decision.behavior == "allow":
                updated_input = decision.updated_input or current_input
                result = PermissionResultAllow(
                    behavior="allow",
                    updatedInput=updated_input,
                    updatedPermissions=decision.updated_permissions,
                    toolUseID=request.tool_use_id,
                )
                return result.model_dump(by_alias=True, exclude_none=True)
            message = decision.message or request.description or self._build_permission_message(request.tool_name, "hook")
            result = PermissionResultDeny(
                behavior="deny",
                message=message,
                interrupt=decision.interrupt,
                toolUseID=request.tool_use_id,
            )
            return result.model_dump(by_alias=True, exclude_none=True)

        evaluation = engine.evaluate(permission_target.tool_name, permission_target.content)

        if evaluation.behavior == "allow":
            result = PermissionResultAllow(behavior="allow", updatedInput=current_input)
            return result.model_dump(by_alias=True, exclude_none=True)

        message = request.description or self._build_permission_message(request.tool_name, evaluation.reason)
        self.state.hook_runtime.run_permission_denied(
            settings=settings,
            cwd=self.state.cwd,
            tool_name=request.tool_name,
            tool_input=current_input,
            tool_use_id=request.tool_use_id,
            content=permission_target.content,
            reason=message,
            permission_mode=self.state.permission_mode,
        )
        result = PermissionResultDeny(
            behavior="deny",
            message=message,
            toolUseID=request.tool_use_id,
        )
        return result.model_dump(by_alias=True, exclude_none=True)

    def _load_settings(self) -> SettingsLoadResult:
        return get_settings_with_sources(
            flag_settings=self.state.flag_settings,
            policy_settings=self.state.policy_settings,
            cwd=self.state.cwd,
            home_dir=self.state.home_dir,
        )

    def _build_permission_message(self, tool_name: str, reason: str | None) -> str:
        if reason == "mode" and self.state.permission_mode == "dontAsk":
            return f"Current permission mode ({self.state.permission_mode}) denies {tool_name}"
        return f"{tool_name} requires permission"

    def _build_mcp_statuses(self) -> list[dict[str, Any]]:
        settings = self._load_settings()
        return [status.model_dump(by_alias=True, exclude_none=True) for status in self.state.mcp_runtime.build_statuses(settings)]

    def _set_mcp_servers(self, servers: dict[str, Any]) -> dict[str, Any]:
        return self.state.mcp_runtime.set_servers(servers)

    def _handle_mcp_reconnect(self, request: SDKControlMcpReconnectRequest) -> dict[str, Any]:
        settings = self._load_settings()
        try:
            self.state.mcp_runtime.reconnect_server(request.serverName, settings)
        except (KeyError, ValueError) as exc:
            raise StructuredIOError(str(exc)) from exc
        return {}

    def _handle_mcp_toggle(self, request: SDKControlMcpToggleRequest) -> dict[str, Any]:
        settings = self._load_settings()
        try:
            self.state.mcp_runtime.set_server_enabled(request.serverName, request.enabled, settings)
        except KeyError as exc:
            raise StructuredIOError(str(exc)) from exc
        return {}

    def _handle_mcp_message(self, request: SDKControlMcpMessageRequest) -> dict[str, Any]:
        settings = self._load_settings()
        try:
            response = self.state.mcp_runtime.send_message(request.server_name, request.message, settings)
        except (KeyError, ValueError, NotImplementedError, RuntimeError) as exc:
            raise StructuredIOError(str(exc)) from exc
        if isinstance(response, dict):
            return response
        return {"response": response}

    def _handle_reload_plugins(self) -> dict[str, Any]:
        settings = self._load_settings()
        command_registry = self.state.build_command_registry(settings.effective.get("skills"))
        response = SDKControlReloadPluginsResponse(
            commands=command_registry.slash_commands(),
            agents=self.state.build_agent_infos(settings.effective.get("agents")),
            plugins=[],
            mcpServers=self._build_mcp_statuses(),
            error_count=0,
        )
        return response.model_dump(by_alias=True, exclude_none=True)

    def _handle_elicitation(self, request: SDKControlElicitationRequest) -> dict[str, Any]:
        settings = self._load_settings()
        hook_result = self.state.hook_runtime.run_elicitation(
            settings=settings,
            cwd=self.state.cwd,
            mcp_server_name=request.mcp_server_name,
            message=request.message,
            mode=request.mode,
            url=request.url,
            elicitation_id=request.elicitation_id,
            requested_schema=request.requested_schema,
            permission_mode=self.state.permission_mode,
        )
        if hook_result.action is not None:
            action = hook_result.action
            content = hook_result.content
        else:
            action = "cancel"
            content = None
        result_hook = self.state.hook_runtime.run_elicitation_result(
            settings=settings,
            cwd=self.state.cwd,
            mcp_server_name=request.mcp_server_name,
            elicitation_id=request.elicitation_id,
            mode=request.mode,
            action=action,
            content=content,
            permission_mode=self.state.permission_mode,
        )
        if result_hook.action is not None:
            action = result_hook.action
        if result_hook.content is not None:
            content = result_hook.content
        return {"action": action, "content": content}

    def _handle_set_max_thinking_tokens(self, request: SDKControlSetMaxThinkingTokensRequest) -> dict[str, Any]:
        self.state.max_thinking_tokens = request.max_thinking_tokens
        return {}

    def _handle_rewind_files(self, request: SDKControlRewindFilesRequest) -> dict[str, Any]:
        result = self.state.tool_runtime.rewind_mutations(dry_run=bool(request.dry_run))
        if result.get("canRewind") or request.dry_run:
            return result
        raise StructuredIOError(str(result.get("error") or "Unexpected error"))

    def _handle_cancel_async_message(self, request: SDKControlCancelAsyncMessageRequest) -> dict[str, Any]:
        if self.state.query_runtime is None:
            return {"cancelled": False}
        return {"cancelled": self.state.query_runtime.cancel_async_message(request.message_uuid)}

    def _handle_seed_read_state(self, request: SDKControlSeedReadStateRequest) -> dict[str, Any]:
        self.state.tool_runtime.seed_read_state(path=request.path, mtime=request.mtime, cwd=self.state.cwd)
        return {}

    def _handle_stop_task(self, request: SDKControlStopTaskRequest) -> dict[str, Any]:
        try:
            self.state.task_runtime.stop(request.task_id)
        except (KeyError, ValueError) as exc:
            raise StructuredIOError(str(exc)) from exc
        return {}
