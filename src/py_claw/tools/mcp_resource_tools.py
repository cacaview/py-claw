from __future__ import annotations

from typing import TYPE_CHECKING

from py_claw.schemas.common import PyClawBaseModel
from py_claw.settings.loader import get_settings_with_sources
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState
    from py_claw.schemas.common import McpServerStatusModel


class ListMcpResourcesToolInput(PyClawBaseModel):
    server: str | None = None


class ReadMcpResourceToolInput(PyClawBaseModel):
    server: str
    uri: str


class ListMcpResourcesTool:
    definition = ToolDefinition(name="ListMcpResources", input_model=ListMcpResourcesToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        server = payload.get("server")
        return ToolPermissionTarget(tool_name=self.definition.name, content=server if isinstance(server, str) else None)

    def execute(self, arguments: ListMcpResourcesToolInput, *, cwd: str) -> dict[str, object]:
        statuses = self._load_statuses()
        matched = _match_servers(statuses, arguments.server)
        if not matched:
            if arguments.server is not None:
                raise ToolError(_server_not_found_message(arguments.server, statuses))
            return {
                "resources": [],
                "servers": [],
                "message": (
                    "No MCP servers configured. "
                    "Configure MCP servers in your settings to enable resource discovery."
                ),
            }

        state = _require_state(self._state, self.definition.name)
        settings = _load_settings_for_state(state)

        # If no specific server requested, list resources from all matched servers
        if arguments.server is None:
            all_resources = []
            for server_status in matched:
                try:
                    server_resources = state.mcp_runtime.list_resources(server_status.name, settings)
                    all_resources.extend(server_resources)
                except (KeyError, ValueError, NotImplementedError, RuntimeError):
                    # Skip servers that fail to provide resources
                    pass
            return {
                "resources": all_resources,
                "servers": [_status_summary(status) for status in matched],
                "message": f"Discovered {len(all_resources)} resource(s) from {len(matched)} server(s).",
            }

        # Specific server requested
        try:
            resources = state.mcp_runtime.list_resources(arguments.server, settings)
        except (KeyError, ValueError, NotImplementedError, RuntimeError) as exc:
            raise ToolError(str(exc)) from exc
        refreshed = _find_server(state.mcp_runtime.build_statuses(settings), arguments.server)
        return {
            "resources": resources,
            "servers": [_status_summary(refreshed)] if refreshed is not None else [],
            "message": f"Discovered {len(resources)} resource(s) from {arguments.server}.",
        }

    def _load_statuses(self) -> list[McpServerStatusModel]:
        state = _require_state(self._state, self.definition.name)
        settings = _load_settings_for_state(state)
        return state.mcp_runtime.build_statuses(settings)


class ReadMcpResourceTool:
    definition = ToolDefinition(name="ReadMcpResource", input_model=ReadMcpResourceToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        parts: list[str] = []
        server = payload.get("server")
        if isinstance(server, str) and server:
            parts.append(f"server:{server}")
        uri = payload.get("uri")
        if isinstance(uri, str) and uri:
            parts.append(f"uri:{uri}")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=" | ".join(parts) if parts else None,
        )

    def execute(self, arguments: ReadMcpResourceToolInput, *, cwd: str) -> dict[str, object]:
        statuses = self._load_statuses()
        status = _find_server(statuses, arguments.server)
        if status is None:
            raise ToolError(_server_not_found_message(arguments.server, statuses))

        state = _require_state(self._state, self.definition.name)
        settings = _load_settings_for_state(state)
        try:
            contents = state.mcp_runtime.read_resource(arguments.server, arguments.uri, settings)
        except (KeyError, ValueError, NotImplementedError, RuntimeError) as exc:
            raise ToolError(str(exc)) from exc
        refreshed = _find_server(state.mcp_runtime.build_statuses(settings), arguments.server)
        return {
            "server": arguments.server,
            "uri": arguments.uri,
            "contents": contents,
            "message": (
                f"Read {len(contents)} content record(s) from {arguments.server}. "
                f"Server summary: {_format_server_summaries([refreshed or status])}."
            ),
        }

    def _load_statuses(self) -> list[McpServerStatusModel]:
        state = _require_state(self._state, self.definition.name)
        settings = _load_settings_for_state(state)
        return state.mcp_runtime.build_statuses(settings)



def _load_settings_for_state(state: RuntimeState):
    return get_settings_with_sources(
        flag_settings=state.flag_settings,
        policy_settings=state.policy_settings,
        cwd=state.cwd,
        home_dir=state.home_dir,
    )



def _require_state(state: RuntimeState | None, tool_name: str) -> RuntimeState:
    if state is None:
        raise ToolError(f"{tool_name} requires runtime state")
    return state



def _find_server(statuses: list[McpServerStatusModel], server_name: str) -> McpServerStatusModel | None:
    for status in statuses:
        if status.name == server_name:
            return status
    return None



def _match_servers(statuses: list[McpServerStatusModel], server_name: str | None) -> list[McpServerStatusModel]:
    if server_name is None:
        return statuses
    status = _find_server(statuses, server_name)
    return [status] if status is not None else []



def _server_not_found_message(server_name: str, statuses: list[McpServerStatusModel]) -> str:
    available = ", ".join(status.name for status in statuses) or "none"
    return f'Server "{server_name}" not found. Available servers: {available}'



def _status_summary(status: McpServerStatusModel) -> dict[str, str]:
    summary = {"server": status.name, "status": status.status}
    if status.scope is not None:
        summary["scope"] = status.scope
    return summary



def _format_server_summaries(statuses: list[McpServerStatusModel]) -> str:
    return ", ".join(
        f'{status.name} (status={status.status}{f", scope={status.scope}" if status.scope is not None else ""})'
        for status in statuses
    )
