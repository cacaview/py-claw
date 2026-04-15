from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget


class ToolSearchToolInput(PyClawBaseModel):
    query: str = Field(
        description='Query to find tools. Use "select:<tool_name>" for direct selection, or keywords to search.'
    )
    max_results: int = Field(default=5, ge=1, le=25, description="Maximum number of results to return")


@dataclass(frozen=True, slots=True)
class _ToolSearchCandidate:
    name: str
    score: int
    schema: dict[str, Any]


class ToolSearchTool:
    """Search the registered tool pool and return tool schemas."""

    definition = ToolDefinition(name="ToolSearch", input_model=ToolSearchToolInput)

    def __init__(self, registry: Any | None = None) -> None:
        self._registry = registry

    def bind_registry(self, registry: Any) -> None:
        self._registry = registry

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("query")
        content = value.strip() if isinstance(value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content or None)

    def execute(self, arguments: ToolSearchToolInput, *, cwd: str) -> dict[str, object]:
        del cwd
        registry = self._require_registry()
        tools = list(registry.values())
        query = arguments.query.strip()
        if not query:
            raise ToolError("ToolSearch query cannot be empty")

        selected = self._search_tools(query=query, tools=tools, max_results=arguments.max_results)
        return {
            "matches": [candidate.name for candidate in selected],
            "query": query,
            "totalDeferredTools": len(tools),
            "functions": [candidate.schema for candidate in selected],
        }

    def _require_registry(self) -> Any:
        if self._registry is None:
            raise ToolError("ToolSearch requires a tool registry")
        return self._registry

    def _search_tools(self, *, query: str, tools: list[Any], max_results: int) -> list[_ToolSearchCandidate]:
        query_lower = query.lower().strip()

        exact_selection = self._select_explicit_tools(query_lower=query_lower, tools=tools, max_results=max_results)
        if exact_selection is not None:
            return exact_selection

        bare_exact = self._find_exact_tool_match(query_lower=query_lower, tools=tools)
        if bare_exact is not None:
            return [bare_exact]

        required_terms, optional_terms = self._split_terms(query_lower)
        scoring_terms = required_terms + optional_terms if required_terms else [term for term in query_lower.split() if term]
        term_patterns = {term: re.compile(rf"\b{re.escape(term)}\b") for term in scoring_terms}

        candidates: list[_ToolSearchCandidate] = []
        for tool in tools:
            tool_name = tool.definition.name
            name_parts, full_name = self._parse_tool_name(tool_name)
            schema = self._tool_schema(tool)
            searchable_text = self._tool_search_text(tool, schema)
            if required_terms and not self._matches_required_terms(required_terms, term_patterns, name_parts, searchable_text):
                continue

            score = 0
            for term in scoring_terms:
                pattern = term_patterns[term]
                if term in name_parts:
                    score += 10
                elif any(term in part for part in name_parts):
                    score += 5
                elif full_name and term in full_name:
                    score += 3
                if pattern.search(searchable_text):
                    score += 2
            if score > 0:
                candidates.append(_ToolSearchCandidate(name=tool_name, score=score, schema=schema))

        candidates.sort(key=lambda candidate: (-candidate.score, candidate.name.lower()))
        return candidates[:max_results]

    def _select_explicit_tools(
        self,
        *,
        query_lower: str,
        tools: list[Any],
        max_results: int,
    ) -> list[_ToolSearchCandidate] | None:
        if not query_lower.startswith("select:"):
            return None
        raw = query_lower.removeprefix("select:").strip()
        if not raw:
            return []
        names = [part.strip() for part in re.split(r"[\s,]+", raw) if part.strip()]
        if not names:
            return []
        selected: list[_ToolSearchCandidate] = []
        seen: set[str] = set()
        for name in names:
            for tool in tools:
                tool_name = tool.definition.name
                if tool_name.lower() != name or tool_name.lower() in seen:
                    continue
                seen.add(tool_name.lower())
                selected.append(
                    _ToolSearchCandidate(name=tool_name, score=100, schema=self._tool_schema(tool))
                )
                break
        return selected[:max_results]

    def _find_exact_tool_match(self, *, query_lower: str, tools: list[Any]) -> _ToolSearchCandidate | None:
        for tool in tools:
            if tool.definition.name.lower() == query_lower:
                return _ToolSearchCandidate(name=tool.definition.name, score=100, schema=self._tool_schema(tool))
        return None

    def _split_terms(self, query_lower: str) -> tuple[list[str], list[str]]:
        required_terms: list[str] = []
        optional_terms: list[str] = []
        for term in query_lower.split():
            if term.startswith("+") and len(term) > 1:
                required_terms.append(term[1:])
            elif term:
                optional_terms.append(term)
        return required_terms, optional_terms

    def _matches_required_terms(
        self,
        required_terms: list[str],
        term_patterns: dict[str, re.Pattern[str]],
        name_parts: list[str],
        searchable_text: str,
    ) -> bool:
        for term in required_terms:
            pattern = term_patterns[term]
            if term in name_parts:
                continue
            if any(term in part for part in name_parts):
                continue
            if pattern.search(searchable_text):
                continue
            return False
        return True

    def _parse_tool_name(self, name: str) -> tuple[list[str], str]:
        if name.startswith("mcp__"):
            without_prefix = name.removeprefix("mcp__").lower()
            parts = [part for part in re.split(r"__+|_", without_prefix) if part]
            return parts, without_prefix.replace("__", " ").replace("_", " ")

        parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ").lower().split()
        return parts, " ".join(parts)

    def _tool_schema(self, tool: Any) -> dict[str, Any]:
        input_model = tool.definition.input_model
        schema = input_model.model_json_schema()
        description = self._tool_description(tool)
        return {
            "name": tool.definition.name,
            "description": description,
            "parameters": schema,
        }

    def _tool_description(self, tool: Any) -> str:
        docstring = (tool.__class__.__doc__ or "").strip()
        if docstring:
            return docstring
        return tool.definition.name

    def _tool_search_text(self, tool: Any, schema: dict[str, Any]) -> str:
        pieces = [
            tool.definition.name,
            tool.__class__.__name__,
            self._tool_description(tool),
            json.dumps(schema, sort_keys=True, ensure_ascii=False),
        ]
        return " ".join(piece for piece in pieces if piece).lower()
