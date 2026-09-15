from __future__ import annotations

import time

from pydantic import field_validator, model_validator

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools import web_search_backends as backends
from py_claw.tools.base import ToolDefinition, ToolPermissionTarget


class WebSearchToolInput(PyClawBaseModel):
    query: str
    engine: str = "auto"
    max_results: int = 8
    allowed_domains: list[str] | None = None
    blocked_domains: list[str] | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("query must be at least 2 characters")
        return normalized

    @field_validator("engine")
    @classmethod
    def validate_engine(cls, value: str) -> str:
        normalized = backends.normalize_engine_name(value)
        if normalized != "auto" and normalized not in backends.SUPPORTED_ENGINES:
            supported = ", ".join(["auto", *backends.SUPPORTED_ENGINES])
            raise ValueError(f"engine must be one of: {supported}")
        return normalized

    @field_validator("max_results")
    @classmethod
    def validate_max_results(cls, value: int) -> int:
        if not 1 <= value <= 20:
            raise ValueError("max_results must be between 1 and 20")
        return value

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
    """Search the web through key-free engines (Bing / DuckDuckGo / Baidu).

    Mirrors the open-webSearch MCP server design: no API keys, engine
    fallback in ``auto`` mode, structured results the model can follow up
    with WebFetch.
    """

    definition = ToolDefinition(
        name="WebSearch",
        input_model=WebSearchToolInput,
    )

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
        result = backends.execute_search(
            arguments.query,
            engine=arguments.engine,
            max_results=arguments.max_results,
        )
        results = backends.filter_results(
            [backends.SearchResult(**item) for item in result["results"]],
            allowed_domains=arguments.allowed_domains,
            blocked_domains=arguments.blocked_domains,
        )
        duration_seconds = time.perf_counter() - start
        output: dict[str, object] = {
            "query": result["query"],
            "engine": result["engine"],
            "engines": result["engines"],
            "totalResults": len(results),
            "results": [item.to_dict() for item in results],
            "failures": result["failures"],
            "durationSeconds": round(duration_seconds, 3),
        }
        if not results:
            failures = result["failures"]
            if failures:
                detail = "; ".join(f"{f['engine']}: {f['error']}" for f in failures)
                output["error"] = "No web search results were obtained."
                output["details"] = detail
            else:
                output["error"] = "No web search results were found for this query."
            output["hint"] = (
                "Try a different query, a different engine (engine parameter), "
                "or fetch a known URL directly with WebFetch."
            )
        return output
