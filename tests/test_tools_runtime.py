from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib import parse

import pytest

from py_claw.cli.runtime import RuntimeState
from py_claw.permissions.engine import PermissionEngine
from py_claw.query import BackendTurnResult, PreparedTurn, QueryRuntime, QueryTurnContext
from py_claw.settings.loader import SettingsLoadResult
from py_claw.tools import ToolError, ToolPermissionError, ToolRuntime, build_default_tool_registry


def _write_skill(skill_root: Path, name: str, content: str) -> Path:
    skill_dir = skill_root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


def _settings_with_permissions(*, allow: list[str] | None = None, deny: list[str] | None = None) -> SettingsLoadResult:
    permissions: dict[str, list[str]] = {}
    if allow:
        permissions["allow"] = allow
    if deny:
        permissions["deny"] = deny
    return SettingsLoadResult(
        effective={"permissions": permissions},
        sources=[{"source": "flagSettings", "settings": {"permissions": permissions}}],
    )


def _python_print_json(payload: dict[str, object]) -> str:
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return (
        "python - <<'PY'\n"
        "import base64\n"
        f"print(base64.b64decode({encoded!r}).decode('utf-8'))\n"
        "PY"
    )


@contextmanager
def _serve_http(handler_type: type[BaseHTTPRequestHandler]):
    server = HTTPServer(("127.0.0.1", 0), handler_type)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_default_tool_registry_registers_executable_builtin_tools() -> None:
    registry = build_default_tool_registry()

    for tool_name in (
        "Read",
        "Edit",
        "Write",
        "NotebookEdit",
        "Glob",
        "Grep",
        "Bash",
        "AskUserQuestion",
        "EnterPlanMode",
        "ExitPlanMode",
        "EnterWorktree",
        "ExitWorktree",
        "ListMcpResources",
        "ReadMcpResource",
        "Agent",
        "SendMessage",
        "SendUserMessage",
        "SendUserFile",
        "Brief",
        "WebFetch",
        "WebSearch",
        "Skill",
        "Sleep",
        "Snip",
        "TodoWrite",
        "TaskCreate",
        "TaskGet",
        "TaskList",
        "TaskUpdate",
        "TaskOutput",
        "TaskStop",
    ):
        tool = registry.get(tool_name)
        assert tool is not None
        assert tool.definition.name == tool_name
        assert callable(tool.execute)


def test_tool_runtime_execute_todowrite_updates_runtime_state(tmp_path) -> None:
    state = RuntimeState(cwd=str(tmp_path))
    result = state.tool_runtime.execute(
        "TodoWrite",
        {
            "todos": [
                {"content": "Run tests", "status": "in_progress", "activeForm": "Running tests"},
                {"content": "Ship", "status": "pending", "activeForm": "Shipping"},
            ]
        },
        cwd=str(tmp_path),
    )

    assert result.tool_name == "TodoWrite"
    assert result.output["oldTodos"] == []
    assert result.output["newTodos"] == [
        {"content": "Run tests", "status": "in_progress", "activeForm": "Running tests"},
        {"content": "Ship", "status": "pending", "activeForm": "Shipping"},
    ]
    assert state.todos == result.output["newTodos"]


def test_tool_runtime_execute_toolsearch_finds_tool_schemas() -> None:
    runtime = ToolRuntime()

    result = runtime.execute(
        "ToolSearch",
        {"query": "select:Read,Edit"},
        cwd=".",
    )

    assert result.tool_name == "ToolSearch"
    assert result.output["matches"] == ["Read", "Edit"]
    assert result.output["query"] == "select:Read,Edit"
    assert result.output["functions"][0]["name"] == "Read"
    assert result.output["functions"][1]["name"] == "Edit"


def test_tool_runtime_execute_send_user_file_returns_files(tmp_path) -> None:
    file_a = tmp_path / "a.txt"
    file_a.write_text("alpha", encoding="utf-8")
    file_b = tmp_path / "b.png"
    file_b.write_bytes(b"png")

    result = ToolRuntime().execute(
        "SendUserFile",
        {
            "files": [str(file_a), str(file_b)],
            "message": "see attached",
        },
        cwd=str(tmp_path),
    )

    assert result.tool_name == "SendUserFile"
    assert result.output["message"] == "see attached"
    assert len(result.output["files"]) == 2
    assert result.output["files"][1]["isImage"] is True


def test_tool_runtime_execute_cron_tools_share_session_state(tmp_path) -> None:
    state = RuntimeState(cwd=str(tmp_path))

    created = state.tool_runtime.execute(
        "CronCreate",
        {"cron": "*/5 * * * *", "prompt": "check in", "recurring": True, "durable": False},
        cwd=str(tmp_path),
    )
    listed = state.tool_runtime.execute("CronList", {}, cwd=str(tmp_path))

    assert created.tool_name == "CronCreate"
    assert created.output["recurring"] is True
    assert "durable" not in created.output
    assert listed.output["jobs"][0]["id"] == created.output["id"]
    assert listed.output["jobs"][0]["cron"] == "*/5 * * * *"
    assert listed.output["jobs"][0]["prompt"] == "check in"

    deleted = state.tool_runtime.execute("CronDelete", {"id": created.output["id"]}, cwd=str(tmp_path))
    assert deleted.output == {"id": created.output["id"]}
    assert state.tool_runtime.execute("CronList", {}, cwd=str(tmp_path)).output["jobs"] == []


def test_tool_runtime_execute_read_pdf_pages(tmp_path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in ("First page", "Second page", "Third page"):
        writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    result = ToolRuntime().execute(
        "Read",
        {"file_path": str(pdf_path), "pages": "1-2"},
        cwd=str(tmp_path),
    )

    assert result.tool_name == "Read"
    assert result.output["file"]["filePath"] == str(pdf_path)
    assert result.output["file"]["content"] == "\n"
    assert result.output["file"]["numLines"] is None
    assert result.output["file"]["startLine"] is None
    assert result.output["file"]["totalLines"] is None


def test_tool_runtime_execute_write_and_edit_record_mutations(tmp_path) -> None:
    target = tmp_path / "note.txt"
    runtime = ToolRuntime()

    write_result = runtime.execute(
        "Write",
        {"file_path": str(target), "content": "hello\nworld\n"},
        cwd=str(tmp_path),
    )
    edit_result = runtime.execute(
        "Edit",
        {"file_path": str(target), "old_string": "world", "new_string": "claude"},
        cwd=str(tmp_path),
    )

    assert write_result.output["type"] == "create"
    assert write_result.output["originalFile"] is None
    assert edit_result.output["replacements"] == 1
    assert target.read_text(encoding="utf-8") == "hello\nclaude\n"



def _write_notebook(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"language_info": {"name": "python"}},
                "cells": [
                    {
                        "cell_type": "markdown",
                        "id": "intro",
                        "metadata": {},
                        "source": ["# Title\n"],
                    },
                    {
                        "cell_type": "code",
                        "id": "code-1",
                        "metadata": {},
                        "execution_count": 7,
                        "outputs": [{"output_type": "stream", "text": "old\n"}],
                        "source": ["print('old')\n"],
                    },
                ],
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )



def test_tool_runtime_execute_notebook_edit_replace_resets_code_outputs(tmp_path) -> None:
    notebook = tmp_path / "demo.ipynb"
    _write_notebook(notebook)

    result = ToolRuntime().execute(
        "NotebookEdit",
        {
            "notebook_path": str(notebook),
            "cell_id": "code-1",
            "new_source": "print('new')\n",
            "edit_mode": "replace",
        },
        cwd=str(tmp_path),
    )

    payload = json.loads(notebook.read_text(encoding="utf-8"))
    updated_cell = payload["cells"][1]
    assert result.permission_target.content == str(notebook)
    assert result.output["cell_id"] == "code-1"
    assert result.output["cell_type"] == "code"
    assert result.output["language"] == "python"
    assert updated_cell["source"] == ["print('new')\n"]
    assert updated_cell["execution_count"] is None
    assert updated_cell["outputs"] == []



def test_tool_runtime_execute_notebook_edit_insert_delete_and_rewind(tmp_path) -> None:
    notebook = tmp_path / "demo.ipynb"
    _write_notebook(notebook)
    runtime = ToolRuntime()

    inserted = runtime.execute(
        "NotebookEdit",
        {
            "notebook_path": str(notebook),
            "cell_id": "intro",
            "new_source": "Inserted text\n",
            "cell_type": "markdown",
            "edit_mode": "insert",
        },
        cwd=str(tmp_path),
    )

    after_insert = json.loads(notebook.read_text(encoding="utf-8"))
    assert len(after_insert["cells"]) == 3
    assert after_insert["cells"][1]["cell_type"] == "markdown"
    assert after_insert["cells"][1]["source"] == ["Inserted text\n"]
    inserted_cell_id = inserted.output["cell_id"]

    deleted = runtime.execute(
        "NotebookEdit",
        {
            "notebook_path": str(notebook),
            "cell_id": inserted_cell_id,
            "edit_mode": "delete",
        },
        cwd=str(tmp_path),
    )

    after_delete = json.loads(notebook.read_text(encoding="utf-8"))
    assert len(after_delete["cells"]) == 2
    assert deleted.output["cell_id"] == inserted_cell_id

    dry_run = runtime.rewind_mutations(dry_run=True)
    assert dry_run["canRewind"] is True
    assert dry_run["filesChanged"] == [str(notebook)]

    runtime.rewind_mutations(dry_run=False)
    restored = json.loads(notebook.read_text(encoding="utf-8"))
    assert [cell["id"] for cell in restored["cells"]] == ["intro", "code-1"]



def test_tool_runtime_execute_notebook_edit_validates_inputs(tmp_path) -> None:
    notebook = tmp_path / "demo.ipynb"
    _write_notebook(notebook)
    runtime = ToolRuntime()

    with pytest.raises(ToolError, match="cell_type is required when using edit_mode=insert"):
        runtime.execute(
            "NotebookEdit",
            {
                "notebook_path": str(notebook),
                "cell_id": "intro",
                "new_source": "Inserted text\n",
                "edit_mode": "insert",
            },
            cwd=str(tmp_path),
        )

    with pytest.raises(ToolError, match='Cell with ID "missing" not found in notebook'):
        runtime.execute(
            "NotebookEdit",
            {
                "notebook_path": str(notebook),
                "cell_id": "missing",
                "new_source": "print('new')\n",
                "edit_mode": "replace",
            },
            cwd=str(tmp_path),
        )

    with pytest.raises(ToolError, match="notebook_path must point to a .ipynb file"):
        runtime.execute(
            "NotebookEdit",
            {
                "notebook_path": str(tmp_path / "demo.txt"),
                "cell_id": "intro",
                "new_source": "nope\n",
                "edit_mode": "replace",
            },
            cwd=str(tmp_path),
        )



def test_tool_runtime_seed_read_state_normalizes_utf8_bom_and_newlines(tmp_path) -> None:
    target = tmp_path / "seed.txt"
    target.write_text("\ufeffalpha\r\nbeta\r\n", encoding="utf-8")
    runtime = ToolRuntime()

    runtime.seed_read_state(path=str(target), mtime=target.stat().st_mtime, cwd=str(tmp_path))

    assert runtime.seeded_read_state[str(target.resolve())] == {
        "content": "alpha\nbeta\n",
        "timestamp": target.stat().st_mtime,
        "offset": None,
        "limit": None,
    }



def test_tool_runtime_rewind_mutations_dry_run_and_apply(tmp_path) -> None:
    target = tmp_path / "note.txt"
    runtime = ToolRuntime()
    runtime.execute(
        "Write",
        {"file_path": str(target), "content": "hello\nworld\n"},
        cwd=str(tmp_path),
    )
    runtime.execute(
        "Edit",
        {"file_path": str(target), "old_string": "world", "new_string": "claude"},
        cwd=str(tmp_path),
    )

    dry_run = runtime.rewind_mutations(dry_run=True)

    assert dry_run == {
        "canRewind": True,
        "filesChanged": [str(target)],
        "insertions": 2,
        "deletions": 0,
    }
    assert target.read_text(encoding="utf-8") == "hello\nclaude\n"

    applied = runtime.rewind_mutations(dry_run=False)

    assert applied == dry_run
    assert not target.exists()
    assert runtime.file_mutation_history == []


def test_tool_runtime_execute_glob_and_grep_find_matching_files(tmp_path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    alpha = src_dir / "alpha.py"
    beta = src_dir / "beta.py"
    alpha.write_text("print('alpha')\nneedle\n", encoding="utf-8")
    beta.write_text("print('beta')\n", encoding="utf-8")

    runtime = ToolRuntime()
    glob_result = runtime.execute("Glob", {"pattern": "src/**/*.py"}, cwd=str(tmp_path))
    grep_result = runtime.execute(
        "Grep",
        {"pattern": "needle", "path": str(src_dir), "glob": "*.py"},
        cwd=str(tmp_path),
    )

    assert glob_result.output["numFiles"] == 2
    assert {Path(path).name for path in glob_result.output["filenames"]} == {"alpha.py", "beta.py"}
    assert grep_result.output["mode"] == "files_with_matches"
    assert grep_result.output["filenames"] == [str(alpha)]
    assert grep_result.output["numFiles"] == 1


def test_tool_runtime_execute_grep_type_filter(tmp_path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    py_file = src_dir / "script.py"
    js_file = src_dir / "script.js"
    ts_file = src_dir / "script.ts"
    py_file.write_text("def hello(): pass\n", encoding="utf-8")
    js_file.write_text("function hello() {}\n", encoding="utf-8")
    ts_file.write_text("function hello(): void {}\n", encoding="utf-8")

    runtime = ToolRuntime()

    # type=py should only match .py files
    result_py = runtime.execute(
        "Grep",
        {"pattern": "hello", "path": str(src_dir), "type": "py"},
        cwd=str(tmp_path),
    )
    assert result_py.output["numFiles"] == 1
    assert "script.py" in result_py.output["filenames"][0]

    # type=js should only match .js files
    result_js = runtime.execute(
        "Grep",
        {"pattern": "hello", "path": str(src_dir), "type": "js"},
        cwd=str(tmp_path),
    )
    assert result_js.output["numFiles"] == 1
    assert "script.js" in result_js.output["filenames"][0]

    # type=ts should only match .ts files
    result_ts = runtime.execute(
        "Grep",
        {"pattern": "hello", "path": str(src_dir), "type": "ts"},
        cwd=str(tmp_path),
    )
    assert result_ts.output["numFiles"] == 1
    assert "script.ts" in result_ts.output["filenames"][0]

    # no type filter should match all three
    result_all = runtime.execute(
        "Grep",
        {"pattern": "hello", "path": str(src_dir)},
        cwd=str(tmp_path),
    )
    assert result_all.output["numFiles"] == 3

    # unknown type should return no files
    result_unknown = runtime.execute(
        "Grep",
        {"pattern": "hello", "path": str(src_dir), "type": "nonexistent_type_xyz"},
        cwd=str(tmp_path),
    )
    assert result_unknown.output["numFiles"] == 0


def test_tool_runtime_execute_grep_type_and_glob_combined(tmp_path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.py").write_text("needle\n", encoding="utf-8")
    (src_dir / "b.py").write_text("needle\n", encoding="utf-8")
    (src_dir / "c.txt").write_text("needle\n", encoding="utf-8")

    runtime = ToolRuntime()
    # type=py + glob=*.py should still only match .py files
    result = runtime.execute(
        "Grep",
        {"pattern": "needle", "path": str(src_dir), "type": "py", "glob": "*.py"},
        cwd=str(tmp_path),
    )
    assert result.output["numFiles"] == 2
    for f in result.output["filenames"]:
        assert f.endswith(".py")


def test_tool_runtime_execute_bash_returns_output(tmp_path) -> None:
    result = ToolRuntime().execute("Bash", {"command": "printf 'hello'"}, cwd=str(tmp_path))

    assert result.output["command"] == "printf 'hello'"
    assert result.output["stdout"] == "hello"
    assert result.output["stderr"] == ""
    assert result.output["exitCode"] == 0


class _WebFetchHTMLHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/html":
            body = (
                "<html><body><main><h1>Title</h1><p>Hello <b>world</b>.</p>"
                "<script>ignored()</script></main></body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return


class _WebFetchCrossHostRedirectHandler(BaseHTTPRequestHandler):
    redirect_base: str = ""

    def do_GET(self) -> None:
        if self.path == "/redirect":
            location = parse.urljoin(self.redirect_base, "/target")
            self.send_response(302)
            self.send_header("Location", location)
            self.end_headers()
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return


class _WebFetchTargetHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/target":
            body = b"redirect target"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return



def test_tool_runtime_execute_web_fetch_returns_rendered_content(tmp_path) -> None:
    with _serve_http(_WebFetchHTMLHandler) as base_url:
        result = ToolRuntime().execute(
            "WebFetch",
            {"url": f"{base_url}/html", "prompt": "Summarize this page"},
            cwd=str(tmp_path),
        )

    assert result.tool_name == "WebFetch"
    assert result.permission_target.content == "domain:127.0.0.1"
    assert result.output["code"] == 200
    assert result.output["codeText"] == "OK"
    assert result.output["url"].endswith("/html")
    assert "Prompt:\nSummarize this page" in result.output["result"]
    assert "Fetched URL:" in result.output["result"]
    assert "Title" in result.output["result"]
    assert "Hello world." in result.output["result"]
    assert "ignored()" not in result.output["result"]



def test_tool_runtime_execute_web_fetch_surfaces_cross_host_redirect(tmp_path) -> None:
    with _serve_http(_WebFetchTargetHandler) as redirect_base:
        redirect_alias = redirect_base.replace("127.0.0.1", "localhost")
        handler_type = type(
            "BoundWebFetchCrossHostRedirectHandler",
            (_WebFetchCrossHostRedirectHandler,),
            {"redirect_base": redirect_alias},
        )
        with _serve_http(handler_type) as source_base:
            result = ToolRuntime().execute(
                "WebFetch",
                {"url": f"{source_base}/redirect", "prompt": "Follow redirect"},
                cwd=str(tmp_path),
            )

    assert result.output["code"] == 302
    assert result.output["codeText"] == "Found"
    assert result.output["url"].endswith("/redirect")
    assert "REDIRECT DETECTED" in result.output["result"]
    assert f"Original URL: {source_base}/redirect" in result.output["result"]
    assert f"Redirect URL: {redirect_alias}/target" in result.output["result"]



def test_tool_runtime_execute_web_fetch_respects_permission_engine(tmp_path) -> None:
    with _serve_http(_WebFetchHTMLHandler) as base_url:
        engine = PermissionEngine.from_settings(
            _settings_with_permissions(allow=["WebFetch(domain:127.0.0.1)"]),
            mode="default",
        )

        result = ToolRuntime().execute(
            "WebFetch",
            {"url": f"{base_url}/html", "prompt": "Summarize this page"},
            cwd=str(tmp_path),
            permission_engine=engine,
        )

    assert result.output["code"] == 200



def test_tool_runtime_execute_web_fetch_raises_permission_error_when_denied(tmp_path) -> None:
    engine = PermissionEngine.from_settings(
        _settings_with_permissions(deny=["WebFetch(domain:127.0.0.1)"]),
        mode="default",
    )

    with pytest.raises(ToolPermissionError) as exc_info:
        ToolRuntime().execute(
            "WebFetch",
            {"url": "http://127.0.0.1:9999/html", "prompt": "Blocked"},
            cwd=str(tmp_path),
            permission_engine=engine,
        )

    assert exc_info.value.behavior == "deny"
    assert str(exc_info.value) == "WebFetch requires permission"



def test_tool_runtime_execute_web_search_returns_honest_degraded_result(tmp_path) -> None:
    result = ToolRuntime().execute(
        "WebSearch",
        {"query": "Claude Code", "allowed_domains": ["docs.anthropic.com"]},
        cwd=str(tmp_path),
    )

    assert result.tool_name == "WebSearch"
    assert result.permission_target.content == "query:Claude Code | allow:docs.anthropic.com"
    assert result.output["query"] == "Claude Code"
    assert isinstance(result.output["durationSeconds"], float)
    assert result.output["results"] == [
        "WebSearch is not yet connected to a live search backend in py-claw.\n\nQuery: \"Claude Code\"\nAllowed domains: docs.anthropic.com\n\nTo enable web search, configure a search backend in settings or connect to a search provider.\nThe query was not executed against any live search service."
    ]



def test_tool_runtime_execute_web_search_rejects_conflicting_domain_filters(tmp_path) -> None:
    with pytest.raises(ToolError, match="cannot specify both allowed_domains and blocked_domains"):
        ToolRuntime().execute(
            "WebSearch",
            {
                "query": "Claude Code",
                "allowed_domains": ["docs.anthropic.com"],
                "blocked_domains": ["example.com"],
            },
            cwd=str(tmp_path),
        )



def test_tool_runtime_execute_web_search_normalizes_blocked_domains(tmp_path) -> None:
    result = ToolRuntime().execute(
        "WebSearch",
        {"query": "Claude Code", "blocked_domains": [" example.com ", "", "docs.anthropic.com "]},
        cwd=str(tmp_path),
    )

    assert result.permission_target.content == "query:Claude Code | block:example.com,docs.anthropic.com"
    assert result.output["results"] == [
        "WebSearch is not yet connected to a live search backend in py-claw.\n\nQuery: \"Claude Code\"\nBlocked domains: example.com, docs.anthropic.com\n\nTo enable web search, configure a search backend in settings or connect to a search provider.\nThe query was not executed against any live search service."
    ]



def test_tool_runtime_execute_web_search_rejects_short_query(tmp_path) -> None:
    with pytest.raises(ToolError, match="query must be at least 2 characters"):
        ToolRuntime().execute(
            "WebSearch",
            {"query": " x "},
            cwd=str(tmp_path),
        )



def test_tool_runtime_execute_web_search_respects_permission_engine(tmp_path) -> None:
    engine = PermissionEngine.from_settings(
        _settings_with_permissions(allow=["WebSearch(query:Claude Code | allow:docs.anthropic.com)"]),
        mode="default",
    )

    result = ToolRuntime().execute(
        "WebSearch",
        {"query": "Claude Code", "allowed_domains": ["docs.anthropic.com"]},
        cwd=str(tmp_path),
        permission_engine=engine,
    )

    assert result.output["query"] == "Claude Code"



def test_tool_runtime_execute_web_search_raises_permission_error_when_denied(tmp_path) -> None:
    engine = PermissionEngine.from_settings(
        _settings_with_permissions(deny=["WebSearch(query:Claude Code)"]),
        mode="default",
    )

    with pytest.raises(ToolPermissionError) as exc_info:
        ToolRuntime().execute(
            "WebSearch",
            {"query": "Claude Code"},
            cwd=str(tmp_path),
            permission_engine=engine,
        )

    assert exc_info.value.behavior == "deny"
    assert str(exc_info.value) == "WebSearch requires permission"



def test_tool_runtime_execute_list_mcp_resources_returns_honest_degraded_result(tmp_path) -> None:
    state = RuntimeState(
        cwd=str(tmp_path),
        flag_settings={
            "mcp": {
                "local": {"command": "python", "args": ["-m", "server"]},
                "remote": {"type": "http", "url": "https://example.com/mcp"},
            }
        },
    )

    result = state.tool_runtime.execute("ListMcpResources", {}, cwd=str(tmp_path))

    assert result.tool_name == "ListMcpResources"
    assert result.permission_target.content is None
    assert result.output == {
        "resources": [],
        "servers": [
            {"server": "local", "status": "pending", "scope": "local"},
            {"server": "remote", "status": "pending", "scope": "local"},
        ],
        "message": "Discovered 0 resource(s) from 2 server(s).",
    }



def test_tool_runtime_execute_list_mcp_resources_filters_server_and_uses_permission_engine(tmp_path) -> None:
    script = tmp_path / "stdio_mcp.py"
    script.write_text(
        "import json, sys\n"
        "message = json.loads(sys.stdin.read())\n"
        "print(json.dumps({\"jsonrpc\": \"2.0\", \"result\": {\"resources\": []}}))\n",
        encoding="utf-8",
    )
    state = RuntimeState(
        cwd=str(tmp_path),
        flag_settings={
            "mcp": {
                "local": {"command": sys.executable, "args": [str(script)]},
                "remote": {"type": "http", "url": "https://example.com/mcp"},
            }
        },
    )
    engine = PermissionEngine.from_settings(
        _settings_with_permissions(allow=["ListMcpResources(local)"]),
        mode="default",
    )

    result = state.tool_runtime.execute("ListMcpResources", {"server": "local"}, cwd=str(tmp_path), permission_engine=engine)

    assert result.tool_name == "ListMcpResources"
    assert result.permission_target.content == "local"
    assert result.output["resources"] == []
    assert result.output["servers"] == [{"server": "local", "status": "connected", "scope": "local"}]
    assert result.output["message"] == "Discovered 0 resource(s) from local."



def test_tool_runtime_execute_list_mcp_resources_rejects_unknown_server(tmp_path) -> None:
    state = RuntimeState(
        cwd=str(tmp_path),
        flag_settings={
            "mcp": {
                "local": {"command": "python", "args": ["-m", "server"]},
            }
        },
    )

    with pytest.raises(ToolError, match='Server "missing" not found. Available servers: local'):
        state.tool_runtime.execute("ListMcpResources", {"server": "missing"}, cwd=str(tmp_path))



def test_tool_runtime_execute_read_mcp_resource_returns_transport_error_for_stdio_server(tmp_path) -> None:
    script = tmp_path / "stdio_mcp.py"
    script.write_text(
        "import json, sys\n"
        "message = json.loads(sys.stdin.read())\n"
        "print(json.dumps({\"jsonrpc\": \"2.0\", \"result\": {\"contents\": [{\"uri\": message[\"params\"][\"uri\"], \"mimeType\": \"text/plain\", \"text\": \"hello\"}]}}))\n",
        encoding="utf-8",
    )
    state = RuntimeState(
        cwd=str(tmp_path),
        flag_settings={
            "mcp": {
                "local": {"command": sys.executable, "args": [str(script)]},
            }
        },
    )

    result = state.tool_runtime.execute(
        "ReadMcpResource",
        {"server": "local", "uri": "file://resource.txt"},
        cwd=str(tmp_path),
    )

    assert result.output == {
        "server": "local",
        "uri": "file://resource.txt",
        "contents": [{"uri": "file://resource.txt", "mimeType": "text/plain", "text": "hello"}],
        "message": "Read 1 content record(s) from local. Server summary: local (status=connected, scope=local).",
    }



def test_tool_runtime_execute_read_mcp_resource_respects_permission_engine(tmp_path) -> None:
    script = tmp_path / "stdio_mcp.py"
    script.write_text(
        "import json, sys\n"
        "message = json.loads(sys.stdin.read())\n"
        "uri = message[\"params\"][\"uri\"]\n"
        "print(json.dumps({\"jsonrpc\": \"2.0\", \"result\": {\"contents\": [{\"uri\": uri, \"mimeType\": \"text/plain\", \"text\": \"hello\"}]}}))\n",
        encoding="utf-8",
    )
    state = RuntimeState(
        cwd=str(tmp_path),
        flag_settings={
            "mcp": {
                "local": {"command": sys.executable, "args": [str(script)]},
            }
        },
    )
    engine = PermissionEngine.from_settings(
        _settings_with_permissions(allow=["ReadMcpResource(server:local | uri:file://resource.txt)"]),
        mode="default",
    )

    result = state.tool_runtime.execute(
        "ReadMcpResource",
        {"server": "local", "uri": "file://resource.txt"},
        cwd=str(tmp_path),
        permission_engine=engine,
    )

    assert result.output["server"] == "local"
    assert result.output["uri"] == "file://resource.txt"
    assert result.output["contents"][0]["text"] == "hello"



def test_tool_runtime_execute_read_mcp_resource_rejects_unknown_server(tmp_path) -> None:
    state = RuntimeState(cwd=str(tmp_path))

    with pytest.raises(ToolError, match='Server "missing" not found. Available servers: none'):
        state.tool_runtime.execute(
            "ReadMcpResource",
            {"server": "missing", "uri": "file://resource.txt"},
            cwd=str(tmp_path),
        )



def test_tool_runtime_execute_agent_returns_honest_sync_result(tmp_path) -> None:
    state = RuntimeState(cwd=str(tmp_path))

    result = state.tool_runtime.execute(
        "Agent",
        {"description": "Research helper", "prompt": "Summarize the current status"},
        cwd=str(tmp_path),
    )

    assert result.tool_name == "Agent"
    assert result.permission_target.content == "Research helper"
    assert result.output["agentType"] == "research-helper"
    assert result.output["status"] == "completed"
    assert "degraded agent session" in result.output["message"]
    assert "Query runtime skeleton is not connected to a model yet." in result.output["result"]
    assert "Received prompt:\nSummarize the current status" in result.output["result"]
    assert result.output["usage"]["backendType"] == "placeholder"
    assert isinstance(result.output["modelUsage"], dict)



class _FixedBackend:
    def __init__(self, assistant_text: str, *, backend_type: str = "custom") -> None:
        self.assistant_text = assistant_text
        self.backend_type = backend_type
        self.calls: list[tuple[PreparedTurn, QueryTurnContext]] = []

    def run_turn(self, prepared: PreparedTurn, context: QueryTurnContext) -> BackendTurnResult:
        self.calls.append((prepared, context))
        return BackendTurnResult(
            assistant_text=self.assistant_text,
            usage={"backendRequests": 1, "backendType": self.backend_type},
            model_usage={},
        )



def test_tool_runtime_execute_agent_uses_state_configured_backend(tmp_path) -> None:
    backend = _FixedBackend("state-backed result")
    state = RuntimeState(cwd=str(tmp_path), query_backend=backend)
    QueryRuntime(state)

    result = state.tool_runtime.execute(
        "Agent",
        {"description": "Research helper", "prompt": "Summarize the current status"},
        cwd=str(tmp_path),
    )

    assert len(backend.calls) == 1
    prepared, context = backend.calls[0]
    assert prepared.query_text == "Summarize the current status"
    assert context.turn_count == 0
    assert result.output["result"] == "state-backed result"
    assert result.output["usage"]["backendType"] == "custom"



def test_tool_runtime_execute_agent_creates_background_session_for_initialized_agent(tmp_path) -> None:
    state = RuntimeState(
        cwd=str(tmp_path),
        initialized_agents={
            "general-purpose": {
                "description": "General helper",
                "prompt": "You are the shared agent prompt.",
                "tools": ["Read", "Grep"],
                "model": "sonnet",
            }
        },
    )

    result = state.tool_runtime.execute(
        "Agent",
        {
            "description": "Search codebase",
            "prompt": "Find the runtime entrypoint",
            "subagent_type": "general-purpose",
            "run_in_background": True,
        },
        cwd=str(tmp_path),
    )

    assert result.permission_target.content == "type:general-purpose | Search codebase"
    assert result.output["agentType"] == "general-purpose"
    assert result.output["status"] == "background_ready"
    assert result.output["task_id"] == "1"
    assert result.output["output_file"].endswith("1.log")
    assert result.output["usage"]["backendType"] == "placeholder"

    task = state.tool_runtime.execute("TaskGet", {"taskId": "1"}, cwd=str(tmp_path))
    assert task.output["task"]["taskType"] == "local_agent"
    assert task.output["task"]["status"] == "completed"
    assert task.output["task"]["agentType"] == "general-purpose"
    assert task.output["task"]["model"] == "sonnet"
    assert task.output["task"]["outputFile"] == result.output["output_file"]

    output = state.tool_runtime.execute(
        "TaskOutput",
        {"task_id": "1", "block": True, "timeout": 1000},
        cwd=str(tmp_path),
    )
    rendered = output.output["task"]["output"]
    assert output.output["task"]["agent_id"] == result.output["agent_id"]
    assert output.output["task"]["agentType"] == "general-purpose"
    assert "agent_name: general-purpose" in rendered
    assert "model: sonnet" in rendered
    assert "allowed_tools: Read, Grep" in rendered
    assert "Find the runtime entrypoint" in rendered



def test_tool_runtime_execute_send_message_appends_agent_exchange(tmp_path) -> None:
    state = RuntimeState(cwd=str(tmp_path))
    started = state.tool_runtime.execute(
        "Agent",
        {"description": "Review helper", "prompt": "Review the registry", "run_in_background": True},
        cwd=str(tmp_path),
    )

    result = state.tool_runtime.execute(
        "SendMessage",
        {
            "to": started.output["agent_id"],
            "summary": "Follow-up",
            "message": {"question": "What should change next?", "priority": 1},
        },
        cwd=str(tmp_path),
    )

    assert result.tool_name == "SendMessage"
    assert result.permission_target.content == f"to:{started.output['agent_id']} | summary:Follow-up"
    assert result.output["sent"] is True
    assert result.output["recipient"] == started.output["agent_id"]
    assert result.output["task_id"] == started.output["task_id"]
    assert result.output["output_file"] == started.output["output_file"]
    assert result.output["summary"] == "Follow-up"
    assert result.output["message"] == '{"priority": 1, "question": "What should change next?"}'
    assert "Received prompt:" in result.output["result"]
    assert result.output["usage"]["backendType"] == "placeholder"

    output = state.tool_runtime.execute(
        "TaskOutput",
        {"task_id": started.output["task_id"], "block": True, "timeout": 1000},
        cwd=str(tmp_path),
    )
    rendered = output.output["task"]["output"]
    assert "[2] user" in rendered
    assert "summary: Follow-up" in rendered
    assert '{"priority": 1, "question": "What should change next?"}' in rendered
    assert rendered.count("[1] user") == 1
    assert rendered.count("[2] assistant") == 1



def test_tool_runtime_execute_skill_returns_rendered_prompt(tmp_path) -> None:
    _write_skill(
        tmp_path / ".claude" / "skills",
        "commit",
        "---\n"
        "description: Commit changes\n"
        "argument-hint: <message>\n"
        "---\n"
        "Use skill dir ${CLAUDE_SKILL_DIR}\n"
        "Args: $ARGUMENTS\n"
        "Session: ${CLAUDE_SESSION_ID}\n",
    )

    result = ToolRuntime().execute("Skill", {"skill": "/commit", "args": "fix bug"}, cwd=str(tmp_path))

    assert result.permission_target.content == "commit"
    assert result.output == {
        "success": True,
        "commandName": "commit",
        "source": "projectSettings",
        "argumentHint": "<message>",
        "prompt": f"Base directory for this skill: {(tmp_path / '.claude' / 'skills' / 'commit').resolve()}\n\nUse skill dir {((tmp_path / '.claude' / 'skills' / 'commit').resolve()).as_posix()}\nArgs: fix bug\nSession: \n",
        "status": "inline",
        "allowedTools": None,
        "model": None,
        "effort": None,
    }



def test_tool_runtime_execute_skill_rejects_unknown_or_disabled_skill(tmp_path) -> None:
    _write_skill(
        tmp_path / ".claude" / "skills",
        "hidden",
        "---\n"
        "description: Hidden skill\n"
        "disable-model-invocation: true\n"
        "---\n"
        "Nope\n",
    )
    runtime = ToolRuntime()

    with pytest.raises(ToolError, match="Unknown skill: missing"):
        runtime.execute("Skill", {"skill": "missing"}, cwd=str(tmp_path))

    with pytest.raises(ToolError, match="Skill is disabled for model invocation: hidden"):
        runtime.execute("Skill", {"skill": "hidden"}, cwd=str(tmp_path))



def test_tool_runtime_execute_ask_user_question_returns_provided_answers_without_runtime(tmp_path) -> None:
    runtime = ToolRuntime()

    result = runtime.execute(
        "AskUserQuestion",
        {
            "questions": [
                {
                    "question": "Which library should we use?",
                    "header": "Library",
                    "options": [
                        {"label": "React", "description": "Use React"},
                        {"label": "Vue", "description": "Use Vue"},
                    ],
                }
            ],
            "answers": {"Which library should we use?": "React"},
        },
        cwd=str(tmp_path),
    )

    assert result.tool_name == "AskUserQuestion"
    assert result.permission_target.content == "Which library should we use?"
    assert result.output == {
        "questions": [
            {
                "question": "Which library should we use?",
                "header": "Library",
                "options": [
                    {"label": "React", "description": "Use React"},
                    {"label": "Vue", "description": "Use Vue"},
                ],
                "multiSelect": False,
            }
        ],
        "answers": {"Which library should we use?": "React"},
    }



def test_tool_runtime_execute_ask_user_question_uses_elicitation_hooks(tmp_path) -> None:
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "Elicitation",
                "action": "accept",
                "content": {
                    "answers": {
                        "Which features do you want?": ["Search", "Export"],
                    },
                    "annotations": {
                        "Which features do you want?": {"notes": "Need both"},
                    },
                },
            }
        }
    )
    state = RuntimeState(
        cwd=str(tmp_path),
        flag_settings={
            "hooks": {
                "Elicitation": [{"hooks": [{"type": "command", "command": command}]}],
            }
        },
    )

    result = state.tool_runtime.execute(
        "AskUserQuestion",
        {
            "questions": [
                {
                    "question": "Which features do you want?",
                    "header": "Features",
                    "options": [
                        {"label": "Search", "description": "Enable search"},
                        {"label": "Export", "description": "Enable export"},
                    ],
                    "multiSelect": True,
                }
            ],
            "metadata": {"source": "remember"},
        },
        cwd=str(tmp_path),
    )

    assert result.output == {
        "questions": [
            {
                "question": "Which features do you want?",
                "header": "Features",
                "options": [
                    {"label": "Search", "description": "Enable search"},
                    {"label": "Export", "description": "Enable export"},
                ],
                "multiSelect": True,
            }
        ],
        "answers": {"Which features do you want?": "Search, Export"},
        "annotations": {"Which features do you want?": {"notes": "Need both"}},
    }



def test_tool_runtime_execute_ask_user_question_rejects_missing_answers(tmp_path) -> None:
    state = RuntimeState(cwd=str(tmp_path))

    with pytest.raises(ToolError, match="User did not answer questions"):
        state.tool_runtime.execute(
            "AskUserQuestion",
            {
                "questions": [
                    {
                        "question": "Which library should we use?",
                        "header": "Library",
                        "options": [
                            {"label": "React", "description": "Use React"},
                            {"label": "Vue", "description": "Use Vue"},
                        ],
                    }
                ]
            },
            cwd=str(tmp_path),
        )



def test_enter_plan_mode_updates_runtime_permission_mode(tmp_path) -> None:
    state = RuntimeState(cwd=str(tmp_path))

    result = state.tool_runtime.execute("EnterPlanMode", {}, cwd=str(tmp_path))

    assert result.tool_name == "EnterPlanMode"
    assert result.output == {
        "message": "Entered plan mode. Focus on exploring the codebase and designing an implementation approach before coding."
    }
    assert state.permission_mode == "plan"



def test_runtime_state_preserves_custom_registry_when_binding_state() -> None:
    registry = build_default_tool_registry()
    runtime = ToolRuntime(registry=registry)

    state = RuntimeState(tool_runtime=runtime)

    assert state.tool_runtime.registry is registry
    assert state.tool_runtime.registry.get("EnterPlanMode") is not None
    assert state.tool_runtime.registry.get("ExitPlanMode") is not None



def test_exit_plan_mode_restores_default_mode_and_returns_allowed_prompts(tmp_path) -> None:
    state = RuntimeState(cwd=str(tmp_path), permission_mode="plan")

    result = state.tool_runtime.execute(
        "ExitPlanMode",
        {"allowedPrompts": [{"tool": "Bash", "prompt": "run tests"}]},
        cwd=str(tmp_path),
    )

    assert result.tool_name == "ExitPlanMode"
    assert result.permission_target.tool_name == "ExitPlanMode"
    assert result.permission_target.content == "1"
    assert result.output == {
        "message": "Exited plan mode. The implementation plan is ready for approval and coding can begin after approval.",
        "allowedPrompts": [{"tool": "Bash", "prompt": "run tests"}],
    }
    assert state.permission_mode == "default"



def test_exit_plan_mode_requires_active_plan_mode(tmp_path) -> None:
    state = RuntimeState(cwd=str(tmp_path), permission_mode="default")

    with pytest.raises(ToolError, match="You are not in plan mode"):
        state.tool_runtime.execute("ExitPlanMode", {}, cwd=str(tmp_path))



def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Test User",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test User",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )



def _init_git_repo(path: Path) -> None:
    _git(path, "init", "-b", "main")
    (path / "README.md").write_text("root\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")



def test_enter_worktree_creates_git_worktree_and_switches_runtime(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    original_cwd = os.getcwd()
    monkeypatch.chdir(repo)
    state = RuntimeState(cwd=str(repo))

    result = state.tool_runtime.execute("EnterWorktree", {"name": "feature/test"}, cwd=str(repo))
    worktree_path = Path(result.output["worktreePath"])

    try:
        assert result.tool_name == "EnterWorktree"
        assert result.output["worktreeBranch"] == "worktree/feature-test"
        assert worktree_path.is_dir()
        assert state.cwd == str(worktree_path)
        assert os.getcwd() == str(worktree_path)
        assert state.active_worktree_session is not None
        assert state.active_worktree_session.original_cwd == str(repo)
        assert state.active_worktree_session.worktree_path == str(worktree_path)
        assert state.active_worktree_session.worktree_branch == "worktree/feature-test"
        assert state.active_worktree_session.repo_root == str(repo.resolve())
        assert state.active_worktree_session.backend == "git"
    finally:
        monkeypatch.chdir(original_cwd)
        _git(repo, "worktree", "remove", "--force", str(worktree_path))
        _git(repo, "branch", "-D", "worktree/feature-test")



def test_exit_worktree_keep_restores_original_cwd_and_preserves_worktree(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    original_cwd = os.getcwd()
    monkeypatch.chdir(repo)
    state = RuntimeState(cwd=str(repo))
    entered = state.tool_runtime.execute("EnterWorktree", {"name": "keep-me"}, cwd=str(repo))
    worktree_path = Path(entered.output["worktreePath"])

    result = state.tool_runtime.execute("ExitWorktree", {"action": "keep"}, cwd=str(worktree_path))

    assert result.output["action"] == "keep"
    assert result.output["originalCwd"] == str(repo)
    assert result.output["worktreePath"] == str(worktree_path)
    assert state.cwd == str(repo)
    assert os.getcwd() == str(repo)
    assert state.active_worktree_session is None
    assert worktree_path.exists()

    _git(repo, "worktree", "remove", "--force", str(worktree_path))
    _git(repo, "branch", "-D", "worktree/keep-me")
    monkeypatch.chdir(original_cwd)



def test_exit_worktree_remove_refuses_dirty_git_worktree_without_discard(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    original_cwd = os.getcwd()
    monkeypatch.chdir(repo)
    state = RuntimeState(cwd=str(repo))
    entered = state.tool_runtime.execute("EnterWorktree", {"name": "dirty"}, cwd=str(repo))
    worktree_path = Path(entered.output["worktreePath"])
    (worktree_path / "README.md").write_text("changed\n", encoding="utf-8")

    with pytest.raises(ToolError, match="Worktree has 1 uncommitted file"):
        state.tool_runtime.execute("ExitWorktree", {"action": "remove"}, cwd=str(worktree_path))

    assert state.active_worktree_session is not None
    assert state.cwd == str(worktree_path)
    assert os.getcwd() == str(worktree_path)

    state.tool_runtime.execute("ExitWorktree", {"action": "remove", "discard_changes": True}, cwd=str(worktree_path))
    monkeypatch.chdir(original_cwd)



def test_exit_worktree_remove_discards_dirty_git_worktree_and_clears_session(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    original_cwd = os.getcwd()
    monkeypatch.chdir(repo)
    state = RuntimeState(cwd=str(repo))
    entered = state.tool_runtime.execute("EnterWorktree", {"name": "discard"}, cwd=str(repo))
    worktree_path = Path(entered.output["worktreePath"])
    (worktree_path / "README.md").write_text("changed\n", encoding="utf-8")

    result = state.tool_runtime.execute(
        "ExitWorktree",
        {"action": "remove", "discard_changes": True},
        cwd=str(worktree_path),
    )

    assert result.output["action"] == "remove"
    assert result.output["discardedFiles"] == 1
    assert result.output["discardedCommits"] == 0
    assert state.active_worktree_session is None
    assert state.cwd == str(repo)
    assert os.getcwd() == str(repo)
    assert not worktree_path.exists()

    branch_check = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "worktree/discard"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert branch_check.returncode != 0
    monkeypatch.chdir(original_cwd)



def test_enter_worktree_uses_hook_when_not_in_git_repo(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = tmp_path / "external-worktree"
    target.mkdir()
    original_cwd = os.getcwd()
    monkeypatch.chdir(workspace)
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "WorktreeCreate",
                "worktreePath": str(target),
            }
        }
    )
    state = RuntimeState(
        cwd=str(workspace),
        flag_settings={
            "hooks": {
                "WorktreeCreate": [{"hooks": [{"type": "command", "command": command}]}],
            }
        },
    )

    result = state.tool_runtime.execute("EnterWorktree", {"name": "hooked"}, cwd=str(workspace))

    assert result.output["worktreePath"] == str(target)
    assert result.output["worktreeBranch"] is None
    assert state.active_worktree_session is not None
    assert state.active_worktree_session.backend == "hook"
    assert state.cwd == str(target)
    assert os.getcwd() == str(target)
    monkeypatch.chdir(original_cwd)



def test_tool_runtime_execute_enforces_permission_engine(tmp_path) -> None:
    target = tmp_path / "allowed.txt"
    target.write_text("payload\n", encoding="utf-8")
    engine = PermissionEngine.from_settings(
        _settings_with_permissions(allow=[f"Read({str(target)})"]),
        mode="default",
    )

    result = ToolRuntime().execute(
        "Read",
        {"file_path": str(target)},
        cwd=str(tmp_path),
        permission_engine=engine,
    )

    assert result.output["file"]["filePath"] == str(target)


def test_tool_runtime_execute_raises_permission_error_when_denied(tmp_path) -> None:
    target = tmp_path / "blocked.txt"
    target.write_text("secret\n", encoding="utf-8")
    engine = PermissionEngine.from_settings(
        _settings_with_permissions(deny=[f"Read({str(target)})"]),
        mode="default",
    )

    with pytest.raises(ToolPermissionError) as exc_info:
        ToolRuntime().execute(
            "Read",
            {"file_path": str(target)},
            cwd=str(tmp_path),
            permission_engine=engine,
        )

    assert exc_info.value.behavior == "deny"
    assert str(exc_info.value) == "Read requires permission"


def test_task_tools_create_get_list_and_update_tasks(tmp_path) -> None:
    runtime = ToolRuntime()

    created = runtime.execute(
        "TaskCreate",
        {
            "subject": "Implement runtime",
            "description": "Build the task runtime",
            "activeForm": "Implementing runtime",
        },
        cwd=str(tmp_path),
    )
    task_id = created.output["task"]["id"]

    fetched = runtime.execute("TaskGet", {"taskId": task_id}, cwd=str(tmp_path))
    listed = runtime.execute("TaskList", {}, cwd=str(tmp_path))
    updated = runtime.execute(
        "TaskUpdate",
        {"taskId": task_id, "status": "in_progress", "owner": "claude"},
        cwd=str(tmp_path),
    )

    assert created.output["task"] == {
        "id": "1",
        "subject": "Implement runtime",
        "description": "Build the task runtime",
        "status": "pending",
        "activeForm": "Implementing runtime",
        "owner": None,
        "blocks": [],
        "blockedBy": [],
    }
    assert fetched.output["task"]["id"] == task_id
    assert listed.output["tasks"] == [
        {
            "id": "1",
            "subject": "Implement runtime",
            "status": "pending",
            "owner": None,
            "blockedBy": [],
        }
    ]
    assert updated.output["task"]["status"] == "in_progress"
    assert updated.output["task"]["owner"] == "claude"


def test_task_update_supports_dependencies_and_deletion(tmp_path) -> None:
    runtime = ToolRuntime()
    first = runtime.execute(
        "TaskCreate",
        {"subject": "First", "description": "First task"},
        cwd=str(tmp_path),
    )
    second = runtime.execute(
        "TaskCreate",
        {"subject": "Second", "description": "Second task"},
        cwd=str(tmp_path),
    )

    update = runtime.execute(
        "TaskUpdate",
        {"taskId": second.output["task"]["id"], "addBlockedBy": [first.output["task"]["id"]]},
        cwd=str(tmp_path),
    )
    runtime.execute(
        "TaskUpdate",
        {"taskId": first.output["task"]["id"], "status": "completed"},
        cwd=str(tmp_path),
    )
    after_completion = runtime.execute("TaskGet", {"taskId": second.output["task"]["id"]}, cwd=str(tmp_path))
    deleted = runtime.execute(
        "TaskUpdate",
        {"taskId": first.output["task"]["id"], "status": "deleted"},
        cwd=str(tmp_path),
    )

    assert update.output["task"]["blockedBy"] == ["1"]
    assert after_completion.output["task"]["blockedBy"] == []
    assert deleted.output == {"deleted": True, "taskId": "1"}


def test_task_tools_validate_unknown_ids_and_status(tmp_path) -> None:
    runtime = ToolRuntime()

    with pytest.raises(KeyError):
        runtime.execute("TaskGet", {"taskId": "999"}, cwd=str(tmp_path))

    created = runtime.execute(
        "TaskCreate",
        {"subject": "Only", "description": "Only task"},
        cwd=str(tmp_path),
    )

    with pytest.raises(ValueError):
        runtime.execute(
            "TaskUpdate",
            {"taskId": created.output["task"]["id"], "status": "invalid"},
            cwd=str(tmp_path),
        )

    with pytest.raises(KeyError):
        runtime.execute(
            "TaskUpdate",
            {"taskId": created.output["task"]["id"], "addBlockedBy": ["999"]},
            cwd=str(tmp_path),
        )


def test_background_bash_task_supports_output_retrieval_and_stop(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"import time; print('start', flush=True); time.sleep(30)\""

    started = runtime.execute(
        "Bash",
        {"command": command, "description": "Long task", "run_in_background": True},
        cwd=str(tmp_path),
    )
    task_id = started.output["task_id"]

    assert started.output["status"] == "in_progress"
    assert started.output["description"] == "Long task"
    assert started.output["outputFile"].endswith(f"{task_id}.log")

    saw_start = False
    for _ in range(50):
        output_before_stop = runtime.execute(
            "TaskOutput",
            {"task_id": task_id, "block": False},
            cwd=str(tmp_path),
        )
        assert output_before_stop.output["retrieval_status"] in {"success", "not_ready"}
        if "start" in output_before_stop.output["task"]["output"]:
            saw_start = True
            break
        time.sleep(0.02)

    stopped = runtime.execute("TaskStop", {"task_id": task_id}, cwd=str(tmp_path))

    assert stopped.output["task_id"] == task_id
    assert stopped.output["task_type"] == "local_bash"
    assert stopped.output["command"] == command

    output_after_stop = runtime.execute(
        "TaskOutput",
        {"task_id": task_id, "block": True, "timeout": 1000},
        cwd=str(tmp_path),
    )

    assert output_after_stop.output["retrieval_status"] == "success"
    assert output_after_stop.output["task"]["task_id"] == task_id
    assert output_after_stop.output["task"]["task_type"] == "local_bash"
    assert output_after_stop.output["task"]["status"] == "completed"
    assert output_after_stop.output["task"]["description"] == "Long task"
    assert output_after_stop.output["task"]["command"] == command
    assert output_after_stop.output["task"]["output_file"].endswith(f"{task_id}.log")
    assert output_after_stop.output["task"]["error"] == "Task stopped"
    assert saw_start or output_after_stop.output["task"]["output"] == ""

    output_file = Path(output_after_stop.output["task"]["output_file"])
    assert output_file.read_text(encoding="utf-8") in {
        output_after_stop.output["task"]["output"],
        output_after_stop.output["task"]["output"] + "\n",
    }


def test_task_output_times_out_for_running_task(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"import time; time.sleep(30)\""

    started = runtime.execute(
        "Bash",
        {"command": command, "run_in_background": True},
        cwd=str(tmp_path),
    )
    task_id = started.output["task_id"]

    try:
        timed_out = runtime.execute(
            "TaskOutput",
            {"task_id": task_id, "block": True, "timeout": 1},
            cwd=str(tmp_path),
        )

        assert timed_out.output["retrieval_status"] == "timeout"
        assert timed_out.output["task"]["task_id"] == task_id
        assert timed_out.output["task"]["status"] == "in_progress"
    finally:
        runtime.execute("TaskStop", {"task_id": task_id}, cwd=str(tmp_path))


def test_task_stop_accepts_deprecated_shell_id(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"import time; time.sleep(30)\""

    started = runtime.execute(
        "Bash",
        {"command": command, "run_in_background": True},
        cwd=str(tmp_path),
    )
    task_id = started.output["task_id"]

    stopped = runtime.execute("TaskStop", {"shell_id": task_id}, cwd=str(tmp_path))

    assert stopped.output["task_id"] == task_id
    assert stopped.output["task_type"] == "local_bash"


def test_task_stop_rejects_non_running_task(tmp_path) -> None:
    runtime = ToolRuntime()
    created = runtime.execute(
        "TaskCreate",
        {"subject": "Only", "description": "Only task"},
        cwd=str(tmp_path),
    )

    with pytest.raises(ValueError):
        runtime.execute("TaskStop", {"task_id": created.output["task"]["id"]}, cwd=str(tmp_path))


def test_bash_background_requires_task_runtime() -> None:
    tool = build_default_tool_registry().require("Bash")

    result = tool.execute(
        tool.definition.input_model.model_validate({"command": "printf hi", "run_in_background": True}),
        cwd=",",
    )

    assert result["task_id"] == "1"



def test_bash_background_without_task_runtime_raises_tool_error(tmp_path) -> None:
    from py_claw.tools.base import ToolError
    from py_claw.tools.local_shell import BashTool

    tool = BashTool(task_runtime=None)
    arguments = tool.definition.input_model.model_validate({"command": "printf hi", "run_in_background": True})

    with pytest.raises(ToolError) as exc_info:
        tool.execute(arguments, cwd=str(tmp_path))

    assert "task runtime" in str(exc_info.value)



def test_task_output_and_stop_validate_unknown_ids(tmp_path) -> None:
    runtime = ToolRuntime()

    with pytest.raises(KeyError):
        runtime.execute("TaskOutput", {"task_id": "999", "block": False}, cwd=str(tmp_path))

    with pytest.raises(KeyError):
        runtime.execute("TaskStop", {"task_id": "999"}, cwd=str(tmp_path))

    with pytest.raises(ValueError):
        runtime.execute("TaskStop", {}, cwd=str(tmp_path))



def test_task_output_includes_completed_sync_task_shape(tmp_path) -> None:
    runtime = ToolRuntime()
    created = runtime.execute(
        "TaskCreate",
        {"subject": "Only", "description": "Only task"},
        cwd=str(tmp_path),
    )
    runtime.execute(
        "TaskUpdate",
        {"taskId": created.output["task"]["id"], "status": "completed"},
        cwd=str(tmp_path),
    )

    output = runtime.execute(
        "TaskOutput",
        {"task_id": created.output["task"]["id"], "block": False},
        cwd=str(tmp_path),
    )

    assert output.output["retrieval_status"] == "success"
    assert output.output["task"] == {
        "task_id": "1",
        "task_type": "generic",
        "status": "completed",
        "description": "Only task",
        "output": "",
    }



def test_task_output_and_stop_validate_missing_and_invalid_payloads(tmp_path) -> None:
    runtime = ToolRuntime()

    with pytest.raises(Exception):
        runtime.execute("TaskOutput", {"task_id": "1", "timeout": 600001}, cwd=str(tmp_path))

    with pytest.raises(Exception):
        runtime.execute("TaskStop", {"task_id": 1}, cwd=str(tmp_path))

    with pytest.raises(Exception):
        runtime.execute("TaskStop", {"task_id": None, "shell_id": None}, cwd=str(tmp_path))



def test_task_output_blocks_until_background_task_completes(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"print('done')\""

    started = runtime.execute(
        "Bash",
        {"command": command, "description": "Quick task", "run_in_background": True},
        cwd=str(tmp_path),
    )

    output = runtime.execute(
        "TaskOutput",
        {"task_id": started.output["task_id"], "block": True, "timeout": 5000},
        cwd=str(tmp_path),
    )

    assert output.output["retrieval_status"] == "success"
    assert output.output["task"]["status"] == "completed"
    assert output.output["task"]["exitCode"] == 0
    assert output.output["task"]["output"] == "done"



def test_task_stop_requires_id_parameter(tmp_path) -> None:
    runtime = ToolRuntime()

    with pytest.raises(ValueError):
        runtime.execute("TaskStop", {"task_id": None}, cwd=str(tmp_path))



def test_task_output_non_blocking_reports_not_ready_for_pending_background_task(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"import time; time.sleep(30)\""

    started = runtime.execute(
        "Bash",
        {"command": command, "run_in_background": True},
        cwd=str(tmp_path),
    )
    task_id = started.output["task_id"]

    try:
        output = runtime.execute(
            "TaskOutput",
            {"task_id": task_id, "block": False},
            cwd=str(tmp_path),
        )
        assert output.output["retrieval_status"] in {"success", "not_ready"}
        assert output.output["task"]["task_id"] == task_id
    finally:
        runtime.execute("TaskStop", {"task_id": task_id}, cwd=str(tmp_path))



def test_task_output_returns_exit_code_for_failed_background_task(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"import sys; print('boom'); sys.exit(3)\""

    started = runtime.execute(
        "Bash",
        {"command": command, "run_in_background": True},
        cwd=str(tmp_path),
    )

    output = runtime.execute(
        "TaskOutput",
        {"task_id": started.output["task_id"], "block": True, "timeout": 5000},
        cwd=str(tmp_path),
    )

    assert output.output["retrieval_status"] == "success"
    assert output.output["task"]["status"] == "completed"
    assert output.output["task"]["exitCode"] == 3
    assert output.output["task"]["error"] == "Command exited with code 3"
    assert output.output["task"]["output"] == "boom"



def test_task_stop_message_includes_description_for_non_shell_command(tmp_path) -> None:
    runtime = ToolRuntime()

    created = runtime.execute(
        "TaskCreate",
        {"subject": "Only", "description": "Only task"},
        cwd=str(tmp_path),
    )

    with pytest.raises(ValueError):
        runtime.execute("TaskStop", {"task_id": created.output["task"]["id"]}, cwd=str(tmp_path))



def test_task_output_reads_same_task_runtime_as_bash_background(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"print('shared')\""

    started = runtime.execute(
        "Bash",
        {"command": command, "run_in_background": True},
        cwd=str(tmp_path),
    )

    output = runtime.execute(
        "TaskOutput",
        {"task_id": started.output["task_id"], "block": True, "timeout": 5000},
        cwd=str(tmp_path),
    )

    assert output.output["task"]["task_id"] == started.output["task_id"]
    assert output.output["task"]["output"] == "shared"



def test_task_stop_result_message_shape(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"import time; time.sleep(30)\""

    started = runtime.execute(
        "Bash",
        {"command": command, "run_in_background": True},
        cwd=str(tmp_path),
    )

    stopped = runtime.execute("TaskStop", {"task_id": started.output["task_id"]}, cwd=str(tmp_path))

    assert stopped.output["message"] == f"Successfully stopped task: {started.output['task_id']} ({command})"
    assert stopped.output["command"] == command
    assert stopped.output["task_type"] == "local_bash"



def test_task_output_log_file_path_is_under_workdir(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"print('path')\""

    started = runtime.execute(
        "Bash",
        {"command": command, "run_in_background": True},
        cwd=str(tmp_path),
    )

    output = runtime.execute(
        "TaskOutput",
        {"task_id": started.output["task_id"], "block": True, "timeout": 5000},
        cwd=str(tmp_path),
    )

    assert Path(output.output["task"]["output_file"]).parent == tmp_path / ".py_claw" / "tasks"
    assert output.output["task"]["output"] == "path"



def test_task_output_preserves_empty_output_for_silent_command(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"pass\""

    started = runtime.execute(
        "Bash",
        {"command": command, "run_in_background": True},
        cwd=str(tmp_path),
    )

    output = runtime.execute(
        "TaskOutput",
        {"task_id": started.output["task_id"], "block": True, "timeout": 5000},
        cwd=str(tmp_path),
    )

    assert output.output["task"]["output"] == ""
    assert output.output["task"]["status"] == "completed"



def test_task_stop_sets_completed_status_in_runtime(tmp_path) -> None:
    runtime = ToolRuntime()
    command = f"{shlex.quote(sys.executable)} -c \"import time; time.sleep(30)\""

    started = runtime.execute(
        "Bash",
        {"command": command, "run_in_background": True},
        cwd=str(tmp_path),
    )
    task_id = started.output["task_id"]

    runtime.execute("TaskStop", {"task_id": task_id}, cwd=str(tmp_path))
    fetched = runtime.execute("TaskGet", {"taskId": task_id}, cwd=str(tmp_path))

    assert fetched.output["task"]["status"] == "completed"
    assert fetched.output["task"]["taskType"] == "local_bash"
    assert fetched.output["task"]["error"] == "Task stopped"
    assert fetched.output["task"]["command"] == command
    assert fetched.output["task"]["outputFile"].endswith(f"{task_id}.log")
    assert "exitCode" in fetched.output["task"]



def test_task_output_for_created_but_unfinished_generic_task(tmp_path) -> None:
    runtime = ToolRuntime()
    created = runtime.execute(
        "TaskCreate",
        {"subject": "Only", "description": "Only task"},
        cwd=str(tmp_path),
    )

    output = runtime.execute(
        "TaskOutput",
        {"task_id": created.output["task"]["id"], "block": False},
        cwd=str(tmp_path),
    )

    assert output.output["retrieval_status"] == "not_ready"
    assert output.output["task"]["status"] == "pending"
    assert output.output["task"]["description"] == "Only task"
    assert output.output["task"]["output"] == ""
    assert output.output["task"]["task_type"] == "generic"
    assert "error" not in output.output["task"]
    assert "command" not in output.output["task"]
    assert "output_file" not in output.output["task"]
    assert "exitCode" not in output.output["task"]
    assert output.output["task"]["task_id"] == "1"
    assert created.output["task"]["status"] == "pending"
    assert created.output["task"]["description"] == "Only task"
    assert created.output["task"]["subject"] == "Only"
    assert created.output["task"]["activeForm"] is None
    assert created.output["task"]["owner"] is None
    assert created.output["task"]["blocks"] == []
    assert created.output["task"]["blockedBy"] == []
    assert "taskType" not in created.output["task"]
    assert runtime.execute("TaskList", {}, cwd=str(tmp_path)).output["tasks"][0]["status"] == "pending"
    assert runtime.execute("TaskList", {}, cwd=str(tmp_path)).output["tasks"][0]["subject"] == "Only"
    assert runtime.execute("TaskList", {}, cwd=str(tmp_path)).output["tasks"][0]["blockedBy"] == []
    assert "taskType" not in runtime.execute("TaskList", {}, cwd=str(tmp_path)).output["tasks"][0]
    assert runtime.execute("TaskGet", {"taskId": "1"}, cwd=str(tmp_path)).output["task"]["status"] == "pending"
    assert runtime.execute("TaskGet", {"taskId": "1"}, cwd=str(tmp_path)).output["task"]["description"] == "Only task"
    assert runtime.execute("TaskGet", {"taskId": "1"}, cwd=str(tmp_path)).output["task"]["blocks"] == []
    assert runtime.execute("TaskGet", {"taskId": "1"}, cwd=str(tmp_path)).output["task"]["blockedBy"] == []
    assert "taskType" not in runtime.execute("TaskGet", {"taskId": "1"}, cwd=str(tmp_path)).output["task"]
    assert "error" not in runtime.execute("TaskGet", {"taskId": "1"}, cwd=str(tmp_path)).output["task"]
    assert "command" not in runtime.execute("TaskGet", {"taskId": "1"}, cwd=str(tmp_path)).output["task"]
    assert "outputFile" not in runtime.execute("TaskGet", {"taskId": "1"}, cwd=str(tmp_path)).output["task"]
    assert "exitCode" not in runtime.execute("TaskGet", {"taskId": "1"}, cwd=str(tmp_path)).output["task"]
    assert runtime.execute("TaskOutput", {"task_id": "1", "block": True, "timeout": 1}, cwd=str(tmp_path)).output["retrieval_status"] == "timeout"
    assert runtime.execute("TaskOutput", {"task_id": "1", "block": True, "timeout": 1}, cwd=str(tmp_path)).output["task"]["status"] == "pending"
    assert runtime.execute("TaskOutput", {"task_id": "1", "block": True, "timeout": 1}, cwd=str(tmp_path)).output["task"]["description"] == "Only task"
    assert runtime.execute("TaskOutput", {"task_id": "1", "block": True, "timeout": 1}, cwd=str(tmp_path)).output["task"]["output"] == ""
    assert runtime.execute("TaskOutput", {"task_id": "1", "block": True, "timeout": 1}, cwd=str(tmp_path)).output["task"]["task_type"] == "generic"
    assert "error" not in runtime.execute("TaskOutput", {"task_id": "1", "block": True, "timeout": 1}, cwd=str(tmp_path)).output["task"]
    assert "command" not in runtime.execute("TaskOutput", {"task_id": "1", "block": True, "timeout": 1}, cwd=str(tmp_path)).output["task"]
    assert "output_file" not in runtime.execute("TaskOutput", {"task_id": "1", "block": True, "timeout": 1}, cwd=str(tmp_path)).output["task"]
    assert "exitCode" not in runtime.execute("TaskOutput", {"task_id": "1", "block": True, "timeout": 1}, cwd=str(tmp_path)).output["task"]
