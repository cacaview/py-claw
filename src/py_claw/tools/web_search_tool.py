from __future__ import annotations

import time

from pydantic import field_validator, model_validator

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolPermissionTarget


class WebSearchToolInput(PyClawBaseModel):
    query: str
    allowed_domains: list[str] | None = None
    blocked_domains: list[str] | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("query must be at least 2 characters")
        return normalized

    @field_validator("allowed_domains", "blocked_domains")
    @classmethod
    def validate_domains(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [item.strip() for item in value if item.strip()]
        return normalized or None

    @model_validator(mode="after")
    def validate_domain_filters(self) -> WebSearchToolInput:
        if self.allowed_domains and self.blocked_domains:
            raise ValueError("cannot specify both allowed_domains and blocked_domains")
        return self


class WebSearchTool:
    definition = ToolDefinition(name="WebSearch", input_model=WebSearchToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        parts: list[str] = []
        query = payload.get("query")
        if isinstance(query, str) and query.strip():
            parts.append(f"query:{query.strip()}")
        allowed_domains = payload.get("allowed_domains")
        if isinstance(allowed_domains, list):
            domains = [item.strip() for item in allowed_domains if isinstance(item, str) and item.strip()]
            if domains:
                parts.append(f"allow:{','.join(domains)}")
        blocked_domains = payload.get("blocked_domains")
        if isinstance(blocked_domains, list):
            domains = [item.strip() for item in blocked_domains if isinstance(item, str) and item.strip()]
            if domains:
                parts.append(f"block:{','.join(domains)}")
        content = " | ".join(parts) if parts else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: WebSearchToolInput, *, cwd: str) -> dict[str, object]:
        start = time.perf_counter()
        lines = [
            "WebSearch is not yet connected to a live search backend in py-claw.",
            "",
            f'Query: "{arguments.query}"',
        ]
        if arguments.allowed_domains:
            lines.append(f"Allowed domains: {', '.join(arguments.allowed_domains)}")
        if arguments.blocked_domains:
            lines.append(f"Blocked domains: {', '.join(arguments.blocked_domains)}")
        lines.extend(
            [
                "",
                "To enable web search, configure a search backend in settings or connect to a search provider.",
                "The query was not executed against any live search service.",
            ]
        )
        duration_seconds = time.perf_counter() - start
        return {
            "query": arguments.query,
            "results": ["\n".join(lines)],
            "durationSeconds": round(duration_seconds, 6),
        }
