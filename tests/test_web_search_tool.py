"""Tests for the WebSearch tool (real backend wiring, input validation, output shape)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from py_claw.tasks import TaskRuntime
from py_claw.tools.registry import build_default_tool_registry
from py_claw.tools.web_search_tool import WebSearchTool, WebSearchToolInput


class TestWebSearchToolInput:
    def test_defaults(self) -> None:
        inp = WebSearchToolInput(query="python web framework")
        assert inp.engine == "auto"
        assert inp.max_results == 8
        assert inp.allowed_domains is None
        assert inp.blocked_domains is None

    def test_query_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebSearchToolInput(query="a")

    def test_query_normalized(self) -> None:
        assert WebSearchToolInput(query="  test query  ").query == "test query"

    def test_engine_alias_normalized(self) -> None:
        assert WebSearchToolInput(query="test", engine="DDG").engine == "duckduckgo"
        assert WebSearchToolInput(query="test", engine="Microsoft").engine == "bing"

    def test_unknown_engine_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebSearchToolInput(query="test", engine="yandex")

    @pytest.mark.parametrize("value", [0, 21])
    def test_max_results_out_of_range_rejected(self, value: int) -> None:
        with pytest.raises(ValidationError):
            WebSearchToolInput(query="test", max_results=value)

    def test_both_domain_filters_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebSearchToolInput(
                query="test",
                allowed_domains=["example.com"],
                blocked_domains=["bad.com"],
            )


class TestWebSearchTool:
    def test_tool_definition(self) -> None:
        assert WebSearchTool().definition.name == "WebSearch"

    def test_permission_target(self) -> None:
        tool = WebSearchTool()
        target = tool.permission_target(
            {"query": "python", "allowed_domains": ["example.com"]}
        )
        assert target.tool_name == "WebSearch"
        assert target.content == "query:python | allow:example.com"

    def test_execute_returns_structured_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_execute_search(query, *, engine, max_results, fetch=None):
            assert query == "python web framework"
            assert engine == "auto"
            assert max_results == 3
            return {
                "query": query,
                "engine": "bing",
                "engines": ["bing", "duckduckgo", "baidu"],
                "totalResults": 2,
                "results": [
                    {"title": "One", "url": "https://example.com/1", "description": "d1", "source": "example.com", "engine": "bing"},
                    {"title": "Two", "url": "https://example.com/2", "description": "", "source": "", "engine": "bing"},
                ],
                "failures": [],
            }

        import py_claw.tools.web_search_backends as backends

        monkeypatch.setattr(backends, "execute_search", fake_execute_search)
        tool = WebSearchTool()
        output = tool.execute(WebSearchToolInput(query="python web framework", max_results=3), cwd="/tmp")
        assert output["engine"] == "bing"
        assert output["totalResults"] == 2
        assert output["results"][0] == {
            "title": "One",
            "url": "https://example.com/1",
            "description": "d1",
            "source": "example.com",
            "engine": "bing",
        }
        assert "error" not in output
        assert "hint" not in output
        assert isinstance(output["durationSeconds"], float)

    def test_execute_all_engines_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import py_claw.tools.web_search_backends as backends

        def fake_execute_search(query, *, engine, max_results, fetch=None):
            return {
                "query": query,
                "engine": "",
                "engines": ["bing", "duckduckgo", "baidu"],
                "totalResults": 0,
                "results": [],
                "failures": [
                    {"engine": "bing", "error": "blocked"},
                    {"engine": "duckduckgo", "error": "offline"},
                    {"engine": "baidu", "error": "blocked"},
                ],
            }

        monkeypatch.setattr(backends, "execute_search", fake_execute_search)
        tool = WebSearchTool()
        output = tool.execute(WebSearchToolInput(query="python"), cwd="/tmp")
        assert output["totalResults"] == 0
        assert output["results"] == []
        assert "No web search results" in output["error"]
        assert "bing: blocked" in output["details"]
        assert "hint" in output

    def test_execute_applies_domain_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import py_claw.tools.web_search_backends as backends

        def fake_execute_search(query, *, engine, max_results, fetch=None):
            return {
                "query": query,
                "engine": "bing",
                "engines": ["bing"],
                "totalResults": 2,
                "results": [
                    {"title": "A", "url": "https://docs.python.org/guide", "description": "", "source": "", "engine": "bing"},
                    {"title": "B", "url": "https://other.com/page", "description": "", "source": "", "engine": "bing"},
                ],
                "failures": [],
            }

        monkeypatch.setattr(backends, "execute_search", fake_execute_search)
        tool = WebSearchTool()
        output = tool.execute(
            WebSearchToolInput(query="python", allowed_domains=["python.org"]),
            cwd="/tmp",
        )
        assert output["totalResults"] == 1
        assert output["results"][0]["url"] == "https://docs.python.org/guide"

    def test_registry_includes_web_search(self) -> None:
        registry = build_default_tool_registry(TaskRuntime())
        tool = registry.get("WebSearch")
        assert tool is not None
        assert tool.definition.name == "WebSearch"


class TestWebSearchToolRuntime:
    def test_executes_through_tool_runtime(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The tool must run inside ToolRuntime with backend results, no network."""
        import py_claw.tools.web_search_backends as backends
        from py_claw.tools.runtime import ToolRuntime

        def fake_execute_search(query, *, engine, max_results, fetch=None):
            return {
                "query": query,
                "engine": "bing",
                "engines": ["bing"],
                "totalResults": 1,
                "results": [
                    {"title": "One", "url": "https://example.com/1", "description": "d", "source": "example.com", "engine": "bing"},
                ],
                "failures": [],
            }

        monkeypatch.setattr(backends, "execute_search", fake_execute_search)
        runtime = ToolRuntime()
        result = runtime.execute(
            "WebSearch",
            {"query": "python web framework", "max_results": 2},
            cwd="/tmp",
        )
        assert result.tool_name == "WebSearch"
        assert result.output["totalResults"] == 1
        assert result.output["results"][0]["url"] == "https://example.com/1"

    def test_runtime_rejects_unknown_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import py_claw.tools.web_search_backends as backends
        from py_claw.tools.runtime import ToolRuntime
        from py_claw.tools.base import ToolError

        monkeypatch.setattr(
            backends,
            "execute_search",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not reach network")),
        )
        runtime = ToolRuntime()
        with pytest.raises(ToolError, match="Invalid input"):
            runtime.execute("WebSearch", {"query": "x y", "engine": "yandex"}, cwd="/tmp")
