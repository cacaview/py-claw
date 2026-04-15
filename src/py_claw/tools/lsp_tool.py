"""
LSP (Language Server Protocol) tool.

Exposes LSP server capabilities (definition, hover, references, diagnostics)
to the model through the tool interface.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from py_claw.services.lsp import LSPServerManager
from py_claw.services.lsp.config import load_lsp_configs_from_settings
from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget


class LSPToolInput(PyClawBaseModel):
    """Input schema for the LSP tool."""

    operation: str = Field(
        description="The LSP operation to perform: goToDefinition, findReferences, hover, documentSymbol, workspaceSymbol, goToImplementation, incomingCalls, outgoingCalls"
    )
    file_path: str = Field(description="The absolute or relative path to the file")
    line: int = Field(description="Line number (1-based)", ge=1)
    character: int = Field(description="Character offset on the line (0-based)", ge=0)


class LSPToolResult(BaseModel):
    """Result of an LSP operation."""

    operation: str
    file_path: str
    success: bool
    result: Any = None
    error: str | None = None


class LSPTool:
    """Tool for LSP operations.

    Provides access to language server features like:
    - goToDefinition: Jump to symbol definition
    - findReferences: Find all references to a symbol
    - hover: Get hover information
    - documentSymbol: List symbols in a document
    - workspaceSymbol: Search symbols across the workspace
    - goToImplementation: Jump to implementation
    - incomingCalls/outgoingCalls: Call hierarchy
    """

    definition = ToolDefinition(name="LSP", input_model=LSPToolInput)

    # Class-level LSP manager shared across all tool instances
    _manager: LSPServerManager | None = None
    _initialized: bool = False

    @classmethod
    def get_manager(cls) -> LSPServerManager:
        """Get or create the shared LSP server manager."""
        if cls._manager is None:
            cls._manager = LSPServerManager()
        return cls._manager

    @classmethod
    def initialize_from_settings(cls, settings: dict[str, Any]) -> None:
        """Initialize LSP servers from settings configuration."""
        if cls._initialized:
            return

        manager = cls.get_manager()
        configs = load_lsp_configs_from_settings(settings)
        if configs:
            manager.register_servers(configs)
            cls._initialized = True

    @classmethod
    def register_builtin_servers(cls) -> None:
        """Register built-in LSP server configurations without requiring settings."""
        from py_claw.services.lsp.config import BUILTIN_LSP_CONFIGS

        manager = cls.get_manager()
        manager.register_servers(BUILTIN_LSP_CONFIGS)
        cls._initialized = True

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        file_path = payload.get("file_path")
        operation = payload.get("operation")
        parts = []
        if isinstance(operation, str) and operation.strip():
            parts.append(f"operation:{operation}")
        if isinstance(file_path, str) and file_path.strip():
            parts.append(f"file:{file_path.strip()}")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=" | ".join(parts) if parts else None,
        )

    def execute(self, arguments: LSPToolInput, *, cwd: str) -> dict[str, object]:
        """Execute an LSP operation."""
        manager = self.get_manager()

        # Resolve file path
        file_path = self._resolve_path(arguments.file_path, cwd)

        # Get or start the appropriate server
        server = manager.get_server_for_file(file_path)
        if server is None:
            return LSPToolResult(
                operation=arguments.operation,
                file_path=file_path,
                success=False,
                error=f"No LSP server configured for file type: {Path(file_path).suffix}",
            ).model_dump()

        if server.status != "running":
            return LSPToolResult(
                operation=arguments.operation,
                file_path=file_path,
                success=False,
                error=f"LSP server not running (status: {server.status}). File type may not be supported.",
            ).model_dump()

        # Execute the operation
        try:
            result = self._execute_operation(manager, arguments, file_path)
            return LSPToolResult(
                operation=arguments.operation,
                file_path=file_path,
                success=True,
                result=result,
            ).model_dump()
        except Exception as e:
            return LSPToolResult(
                operation=arguments.operation,
                file_path=file_path,
                success=False,
                error=str(e),
            ).model_dump()

    def _resolve_path(self, file_path: str, cwd: str) -> str:
        """Resolve a file path to absolute."""
        p = Path(file_path)
        if p.is_absolute():
            return str(p)
        return str((Path(cwd) / p).resolve())

    def _execute_operation(
        self,
        manager: LSPServerManager,
        arguments: LSPToolInput,
        file_path: str,
    ) -> Any:
        """Execute a specific LSP operation."""
        uri = manager._path_to_uri(file_path)
        position = {"line": arguments.line - 1, "character": arguments.character}

        match arguments.operation:
            case "goToDefinition":
                result = manager.send_request(
                    file_path,
                    "textDocument/definition",
                    {"textDocument": {"uri": uri}, "position": position},
                )
                return self._format_location(result)

            case "findReferences":
                result = manager.send_request(
                    file_path,
                    "textDocument/references",
                    {
                        "textDocument": {"uri": uri},
                        "position": position,
                        "context": {"includeDeclaration": True},
                    },
                )
                return self._format_locations(result)

            case "hover":
                result = manager.send_request(
                    file_path,
                    "textDocument/hover",
                    {"textDocument": {"uri": uri}, "position": position},
                )
                return self._format_hover(result)

            case "documentSymbol":
                result = manager.send_request(
                    file_path,
                    "textDocument/documentSymbol",
                    {"textDocument": {"uri": uri}},
                )
                return self._format_symbols(result)

            case "workspaceSymbol":
                query = arguments.file_path  # Reuse field for query
                result = manager.send_request(
                    file_path,
                    "workspace/symbol",
                    {"query": query},
                )
                return self._format_symbols(result)

            case "goToImplementation":
                result = manager.send_request(
                    file_path,
                    "textDocument/implementation",
                    {"textDocument": {"uri": uri}, "position": position},
                )
                return self._format_location(result)

            case "incomingCalls":
                result = manager.send_request(
                    file_path,
                    "callHierarchy/incomingCalls",
                    {"item": {"uri": uri, "position": position}},
                )
                return self._format_calls(result)

            case "outgoingCalls":
                result = manager.send_request(
                    file_path,
                    "callHierarchy/outgoingCalls",
                    {"item": {"uri": uri, "position": position}},
                )
                return self._format_calls(result)

            case _:
                available = [
                    "goToDefinition",
                    "findReferences",
                    "hover",
                    "documentSymbol",
                    "workspaceSymbol",
                    "goToImplementation",
                    "incomingCalls",
                    "outgoingCalls",
                ]
                raise ToolError(
                    f"Unknown LSP operation: {arguments.operation}. "
                    f"Available: {', '.join(available)}"
                )

    def _format_location(self, result: Any) -> str:
        """Format a single location result."""
        if not result:
            return "No definition found."
        if isinstance(result, list):
            if not result:
                return "No definition found."
            result = result[0]
        loc = result.get("location", result)
        uri = loc.get("uri", "")
        rng = loc.get("range", {})
        start = rng.get("start", {})
        path = Path(uri.replace("file://", "")).as_posix() if uri.startswith("file://") else uri
        return f"{path}:{start.get('line', 0) + 1}:{start.get('character', 0)}"

    def _format_locations(self, result: Any) -> str:
        """Format multiple locations."""
        if not result:
            return "No references found."
        locations = result if isinstance(result, list) else [result]
        lines = []
        for loc in locations[:20]:  # Limit to 20 results
            loc_data = loc.get("location", loc)
            uri = loc_data.get("uri", "")
            rng = loc_data.get("range", {})
            start = rng.get("start", {})
            path = Path(uri.replace("file://", "")).as_posix() if uri.startswith("file://") else uri
            lines.append(f"  {path}:{start.get('line', 0) + 1}:{start.get('character', 0)}")
        if len(locations) > 20:
            lines.append(f"  ... and {len(locations) - 20} more")
        return "\n".join(lines) if lines else "No references found."

    def _format_hover(self, result: Any) -> str:
        """Format a hover result."""
        if not result:
            return "No hover information available."
        contents = result.get("contents", {})
        if isinstance(contents, str):
            return contents
        if isinstance(contents, dict):
            value = contents.get("value", str(contents))
        else:
            value = str(contents)
        return value

    def _format_symbols(self, result: Any) -> str:
        """Format document/workspace symbols."""
        if not result:
            return "No symbols found."
        symbols = result if isinstance(result, list) else [result]
        lines = []
        for sym in symbols[:50]:  # Limit to 50
            name = sym.get("name", "?")
            kind = sym.get("kind", 0)
            kind_name = self._symbol_kind_name(kind)
            loc = sym.get("location", sym)
            rng = loc.get("range", loc) if isinstance(loc, dict) else {}
            start = rng.get("start", {}) if isinstance(rng, dict) else {}
            line = start.get("line", 0) + 1 if isinstance(start, dict) else 1
            container = sym.get("containerName", "")
            line_str = f"{name} ({kind_name})" + (f" — {container}" if container else "")
            lines.append(f"  {line}: {line_str}")
        if len(symbols) > 50:
            lines.append(f"  ... and {len(symbols) - 50} more")
        return "\n".join(lines) if lines else "No symbols found."

    def _format_calls(self, result: Any) -> str:
        """Format call hierarchy results."""
        if not result:
            return "No calls found."
        calls = result if isinstance(result, list) else [result]
        lines = []
        for call in calls[:20]:
            from_loc = call.get("from", {})
            from_name = from_loc.get("name", "?")
            from_kind = self._symbol_kind_name(from_loc.get("kind", 0))
            lines.append(f"  {from_name} ({from_kind})")
        if len(calls) > 20:
            lines.append(f"  ... and {len(calls) - 20} more")
        return "\n".join(lines) if lines else "No calls found."

    @staticmethod
    def _symbol_kind_name(kind: int) -> str:
        """Map LSP SymbolKind to human-readable name."""
        KIND_NAMES = {
            1: "File",
            2: "Module",
            3: "Namespace",
            4: "Package",
            5: "Class",
            6: "Method",
            7: "Property",
            8: "Field",
            9: "Constructor",
            10: "Enum",
            11: "Interface",
            12: "Function",
            13: "Variable",
            14: "Constant",
            15: "String",
            16: "Number",
            17: "Boolean",
            18: "Array",
            19: "Object",
            20: "Key",
            21: "Null",
            22: "EnumMember",
            23: "Struct",
            24: "Event",
            25: "Operator",
            26: "TypeParameter",
        }
        return KIND_NAMES.get(kind, f"Kind({kind})")
