from __future__ import annotations

import base64
import json
from pathlib import Path

from py_claw.cli.control import ControlRuntime
from py_claw.cli.runtime import RuntimeState
from py_claw.hooks.runtime import HookRuntime
from py_claw.schemas.control import SDKControlPermissionRequest
from py_claw.settings.loader import SettingsLoadResult
from py_claw.tools import ToolRuntime


def _hook_settings(event: str, command: str, *, matcher: str | None = None) -> SettingsLoadResult:
    hook_matcher: dict[str, object] = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        hook_matcher["matcher"] = matcher
    hooks = {event: [hook_matcher]}
    return SettingsLoadResult(
        effective={"hooks": hooks},
        sources=[{"source": "flagSettings", "settings": {"hooks": hooks}}],
    )


def _python_print_json(payload: dict[str, object]) -> str:
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return (
        "python - <<'PY'\n"
        "import base64\n"
        f"print(base64.b64decode({encoded!r}).decode('utf-8'))\n"
        "PY"
    )


def _python_write_text(path: Path, text: str) -> str:
    encoded_path = base64.b64encode(str(path).encode("utf-8")).decode("ascii")
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return (
        "python - <<'PY'\n"
        "import base64\n"
        "from pathlib import Path\n"
        f"path = Path(base64.b64decode({encoded_path!r}).decode('utf-8'))\n"
        f"text = base64.b64decode({encoded_text!r}).decode('utf-8')\n"
        "path.write_text(text, encoding='utf-8')\n"
        "PY"
    )


def test_permission_request_hook_can_allow_denied_tool() -> None:
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            }
        }
    )
    runtime = ControlRuntime(
        RuntimeState(
            permission_mode="dontAsk",
            flag_settings={
                "hooks": {
                    "PermissionRequest": [
                        {
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ]
                }
            },
        )
    )

    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Read",
                "input": {"file_path": "README.md"},
                "tool_use_id": "tool-allow",
            }
        )
    )

    assert response == {"behavior": "allow", "updatedInput": {"file_path": "README.md"}, "toolUseID": "tool-allow"}


def test_permission_denied_hook_runs_command(tmp_path) -> None:
    log_path = tmp_path / "permission-denied.txt"
    runtime = ControlRuntime(
        RuntimeState(
            permission_mode="dontAsk",
            flag_settings={
                "hooks": {
                    "PermissionDenied": [
                        {
                            "hooks": [{"type": "command", "command": _python_write_text(log_path, "denied")}],
                        }
                    ]
                }
            },
        )
    )

    response = runtime.handle_request(
        SDKControlPermissionRequest.model_validate(
            {
                "subtype": "can_use_tool",
                "tool_name": "Read",
                "input": {"file_path": "README.md"},
                "tool_use_id": "tool-denied",
            }
        )
    )

    assert response["behavior"] == "deny"
    assert log_path.read_text(encoding="utf-8") == "denied"


def test_pre_tool_use_hook_can_update_input(tmp_path) -> None:
    target = tmp_path / "actual.txt"
    target.write_text("content\n", encoding="utf-8")
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": {"file_path": str(target)},
            }
        }
    )
    settings = _hook_settings("PreToolUse", command)

    result = ToolRuntime().execute(
        "Read",
        {"file_path": str(tmp_path / "missing.txt")},
        cwd=str(tmp_path),
        hook_runtime=HookRuntime(),
        hook_settings=settings,
        tool_use_id="tool-pre",
    )

    assert result.arguments["file_path"] == str(target)
    assert result.output["file"]["filePath"] == str(target)


def test_post_tool_use_failure_hook_runs_after_tool_error(tmp_path) -> None:
    log_path = tmp_path / "hook-failure.txt"
    settings = _hook_settings("PostToolUseFailure", _python_write_text(log_path, "failed"), matcher="Read")

    try:
        ToolRuntime().execute(
            "Read",
            {"file_path": str(tmp_path / "missing.txt")},
            cwd=str(tmp_path),
            hook_runtime=HookRuntime(),
            hook_settings=settings,
            tool_use_id="tool-failure",
        )
    except Exception:
        pass
    else:
        raise AssertionError("expected tool execution to fail")

    assert log_path.read_text(encoding="utf-8") == "failed"


def test_elicitation_hook_returns_action_and_content(tmp_path) -> None:
    settings = _hook_settings(
        "Elicitation",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "Elicitation",
                    "action": "accept",
                    "content": {"answer": "yes"},
                }
            }
        ),
    )

    result = HookRuntime().run_elicitation(
        settings=settings,
        cwd=str(tmp_path),
        mcp_server_name="local",
        message="Need approval",
        mode="form",
        elicitation_id="elic-1",
        requested_schema={"type": "object"},
    )

    assert result.action == "accept"
    assert result.content == {"answer": "yes"}


def test_elicitation_result_hook_can_override_action_and_content(tmp_path) -> None:
    settings = _hook_settings(
        "ElicitationResult",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "ElicitationResult",
                    "action": "decline",
                    "content": {"reason": "changed"},
                }
            }
        ),
    )

    result = HookRuntime().run_elicitation_result(
        settings=settings,
        cwd=str(tmp_path),
        mcp_server_name="local",
        elicitation_id="elic-1",
        mode="form",
        action="accept",
        content={"answer": "yes"},
    )

    assert result.action == "decline"
    assert result.content == {"reason": "changed"}



def test_worktree_create_hook_returns_worktree_path(tmp_path) -> None:
    target = tmp_path / "worktree"
    target.mkdir()
    settings = _hook_settings(
        "WorktreeCreate",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "WorktreeCreate",
                    "worktreePath": str(target),
                }
            }
        ),
    )

    result = HookRuntime().run_worktree_create(
        settings=settings,
        cwd=str(tmp_path),
        name="feature/test",
    )

    assert result.continue_ is True
    assert result.content == {"worktreePath": str(target)}



def test_worktree_remove_hook_runs_command(tmp_path) -> None:
    log_path = tmp_path / "worktree-remove.txt"
    settings = _hook_settings("WorktreeRemove", _python_write_text(log_path, "removed"))

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=str(tmp_path / "worktree"),
    )

    assert result.continue_ is True
    assert log_path.read_text(encoding="utf-8") == "removed"



def test_cwd_changed_hook_returns_watch_paths(tmp_path) -> None:
    watch_a = str(tmp_path / "a")
    watch_b = str(tmp_path / "b")
    settings = _hook_settings(
        "CwdChanged",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "CwdChanged",
                    "watchPaths": [watch_a, watch_b],
                }
            }
        ),
    )

    result = HookRuntime().run_cwd_changed(
        settings=settings,
        cwd=str(tmp_path),
        old_cwd=str(tmp_path / "old"),
        new_cwd=str(tmp_path / "new"),
    )

    assert result.continue_ is True
    assert result.content == {"watchPaths": [watch_a, watch_b]}



def test_cwd_changed_hook_can_block(tmp_path) -> None:
    settings = _hook_settings(
        "CwdChanged",
        _python_print_json({"decision": "block", "reason": "no switch"}),
    )

    result = HookRuntime().run_cwd_changed(
        settings=settings,
        cwd=str(tmp_path),
        old_cwd=str(tmp_path / "old"),
        new_cwd=str(tmp_path / "new"),
    )

    assert result.continue_ is False
    assert result.stop_reason == "no switch"
    assert result.content is None



def test_worktree_create_hook_can_block(tmp_path) -> None:
    settings = _hook_settings(
        "WorktreeCreate",
        _python_print_json({"decision": "block", "reason": "blocked"}),
    )

    result = HookRuntime().run_worktree_create(
        settings=settings,
        cwd=str(tmp_path),
        name="blocked",
    )

    assert result.continue_ is False
    assert result.stop_reason == "blocked"
    assert result.content is None



def test_worktree_remove_hook_nonzero_exit_does_not_block_by_default(tmp_path) -> None:
    settings = _hook_settings(
        "WorktreeRemove",
        "python - <<'PY'\nimport sys\nsys.exit(7)\nPY",
    )

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=str(tmp_path / "worktree"),
    )

    assert result.continue_ is True
    assert result.stop_reason is None
    assert len(result.executions) == 1
    assert result.executions[0].exit_code == 7



def test_worktree_create_hook_matches_enter_worktree_tool_name(tmp_path) -> None:
    target = tmp_path / "named"
    target.mkdir()
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "WorktreeCreate",
                "worktreePath": str(target),
            }
        }
    )
    settings = _hook_settings("WorktreeCreate", command, matcher="EnterWorktree")

    result = HookRuntime().run_worktree_create(
        settings=settings,
        cwd=str(tmp_path),
        name="named",
    )

    assert result.content == {"worktreePath": str(target)}



def test_cwd_changed_hook_matches_special_tool_name(tmp_path) -> None:
    settings = _hook_settings(
        "CwdChanged",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "CwdChanged",
                    "watchPaths": [str(tmp_path / "watch")],
                }
            }
        ),
        matcher="CwdChanged",
    )

    result = HookRuntime().run_cwd_changed(
        settings=settings,
        cwd=str(tmp_path),
        old_cwd=str(tmp_path / "old"),
        new_cwd=str(tmp_path / "new"),
    )

    assert result.content == {"watchPaths": [str(tmp_path / "watch")]}



def test_worktree_remove_hook_matches_exit_worktree_tool_name(tmp_path) -> None:
    log_path = tmp_path / "remove-match.txt"
    settings = _hook_settings("WorktreeRemove", _python_write_text(log_path, "ok"), matcher="ExitWorktree")

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=str(tmp_path / "worktree"),
    )

    assert result.continue_ is True
    assert log_path.read_text(encoding="utf-8") == "ok"



def test_worktree_remove_hook_unmatched_matcher_is_ignored(tmp_path) -> None:
    log_path = tmp_path / "remove-ignore.txt"
    settings = _hook_settings("WorktreeRemove", _python_write_text(log_path, "nope"), matcher="Read")

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=str(tmp_path / "worktree"),
    )

    assert result.executions == []
    assert not log_path.exists()
    assert result.continue_ is True
    assert result.content is None



def test_cwd_changed_hook_unmatched_matcher_is_ignored(tmp_path) -> None:
    settings = _hook_settings(
        "CwdChanged",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "CwdChanged",
                    "watchPaths": [str(tmp_path / "watch")],
                }
            }
        ),
        matcher="Read",
    )

    result = HookRuntime().run_cwd_changed(
        settings=settings,
        cwd=str(tmp_path),
        old_cwd=str(tmp_path / "old"),
        new_cwd=str(tmp_path / "new"),
    )

    assert result.executions == []
    assert result.content is None
    assert result.continue_ is True



def test_worktree_create_hook_unmatched_matcher_is_ignored(tmp_path) -> None:
    target = tmp_path / "ignored"
    target.mkdir()
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "WorktreeCreate",
                "worktreePath": str(target),
            }
        }
    )
    settings = _hook_settings("WorktreeCreate", command, matcher="Read")

    result = HookRuntime().run_worktree_create(
        settings=settings,
        cwd=str(tmp_path),
        name="ignored",
    )

    assert result.executions == []
    assert result.content is None
    assert result.continue_ is True



def test_worktree_create_hook_captures_execution_record(tmp_path) -> None:
    target = tmp_path / "recorded"
    target.mkdir()
    settings = _hook_settings(
        "WorktreeCreate",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "WorktreeCreate",
                    "worktreePath": str(target),
                }
            }
        ),
    )

    result = HookRuntime().run_worktree_create(
        settings=settings,
        cwd=str(tmp_path),
        name="recorded",
    )

    assert len(result.executions) == 1
    assert result.executions[0].event == "WorktreeCreate"
    assert result.executions[0].structured_output is not None
    assert result.content == {"worktreePath": str(target)}



def test_cwd_changed_hook_captures_execution_record(tmp_path) -> None:
    settings = _hook_settings(
        "CwdChanged",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "CwdChanged",
                    "watchPaths": [str(tmp_path / "watch")],
                }
            }
        ),
    )

    result = HookRuntime().run_cwd_changed(
        settings=settings,
        cwd=str(tmp_path),
        old_cwd=str(tmp_path / "old"),
        new_cwd=str(tmp_path / "new"),
    )

    assert len(result.executions) == 1
    assert result.executions[0].event == "CwdChanged"
    assert result.executions[0].structured_output is not None
    assert result.content == {"watchPaths": [str(tmp_path / "watch")]}



def test_worktree_remove_hook_captures_execution_record(tmp_path) -> None:
    log_path = tmp_path / "record-remove.txt"
    settings = _hook_settings("WorktreeRemove", _python_write_text(log_path, "removed"))

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=str(tmp_path / "worktree"),
    )

    assert len(result.executions) == 1
    assert result.executions[0].event == "WorktreeRemove"
    assert result.executions[0].command
    assert log_path.read_text(encoding="utf-8") == "removed"



def test_worktree_remove_hook_preserves_execution_record_on_failure(tmp_path) -> None:
    settings = _hook_settings(
        "WorktreeRemove",
        "python - <<'PY'\nimport sys\nprint('fail')\nsys.exit(2)\nPY",
    )

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=str(tmp_path / "worktree"),
    )

    assert len(result.executions) == 1
    assert result.executions[0].event == "WorktreeRemove"
    assert result.executions[0].exit_code == 2
    assert result.executions[0].stdout.strip() == "fail"
    assert result.continue_ is True



def test_cwd_changed_hook_preserves_block_reason_from_structured_output(tmp_path) -> None:
    settings = _hook_settings(
        "CwdChanged",
        _python_print_json({"continue": False, "stopReason": "stay put"}),
    )

    result = HookRuntime().run_cwd_changed(
        settings=settings,
        cwd=str(tmp_path),
        old_cwd=str(tmp_path / "old"),
        new_cwd=str(tmp_path / "new"),
    )

    assert result.continue_ is False
    assert result.stop_reason == "stay put"



def test_worktree_create_hook_preserves_block_reason_from_structured_output(tmp_path) -> None:
    settings = _hook_settings(
        "WorktreeCreate",
        _python_print_json({"continue": False, "stopReason": "stay"}),
    )

    result = HookRuntime().run_worktree_create(
        settings=settings,
        cwd=str(tmp_path),
        name="stay",
    )

    assert result.continue_ is False
    assert result.stop_reason == "stay"



def test_worktree_remove_hook_ignores_structured_output_block(tmp_path) -> None:
    settings = _hook_settings(
        "WorktreeRemove",
        _python_print_json({"decision": "block", "reason": "ignored"}),
    )

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=str(tmp_path / "worktree"),
    )

    assert result.continue_ is True
    assert result.stop_reason is None
    assert len(result.executions) == 1
    assert result.executions[0].structured_output is not None



def test_worktree_remove_hook_can_match_on_path_content(tmp_path) -> None:
    log_path = tmp_path / "path-match.txt"
    worktree_path = str(tmp_path / "named-worktree")
    settings = _hook_settings("WorktreeRemove", _python_write_text(log_path, "matched"), matcher=f"ExitWorktree({worktree_path})")

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=worktree_path,
    )

    assert result.continue_ is True
    assert log_path.read_text(encoding="utf-8") == "matched"



def test_cwd_changed_hook_can_match_on_new_cwd_content(tmp_path) -> None:
    new_cwd = str(tmp_path / "target")
    settings = _hook_settings(
        "CwdChanged",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "CwdChanged",
                    "watchPaths": [str(tmp_path / "watch")],
                }
            }
        ),
        matcher=f"CwdChanged({new_cwd})",
    )

    result = HookRuntime().run_cwd_changed(
        settings=settings,
        cwd=str(tmp_path),
        old_cwd=str(tmp_path / "old"),
        new_cwd=new_cwd,
    )

    assert result.content == {"watchPaths": [str(tmp_path / "watch")]}



def test_worktree_create_hook_can_match_on_name_content(tmp_path) -> None:
    target = tmp_path / "matched-by-name"
    target.mkdir()
    settings = _hook_settings(
        "WorktreeCreate",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "WorktreeCreate",
                    "worktreePath": str(target),
                }
            }
        ),
        matcher="EnterWorktree(feature/test)",
    )

    result = HookRuntime().run_worktree_create(
        settings=settings,
        cwd=str(tmp_path),
        name="feature/test",
    )

    assert result.content == {"worktreePath": str(target)}



def test_worktree_create_hook_non_matching_name_content_is_ignored(tmp_path) -> None:
    target = tmp_path / "ignored-by-name"
    target.mkdir()
    settings = _hook_settings(
        "WorktreeCreate",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "WorktreeCreate",
                    "worktreePath": str(target),
                }
            }
        ),
        matcher="EnterWorktree(other)",
    )

    result = HookRuntime().run_worktree_create(
        settings=settings,
        cwd=str(tmp_path),
        name="feature/test",
    )

    assert result.executions == []
    assert result.content is None
    assert result.continue_ is True



def test_cwd_changed_hook_non_matching_new_cwd_content_is_ignored(tmp_path) -> None:
    settings = _hook_settings(
        "CwdChanged",
        _python_print_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "CwdChanged",
                    "watchPaths": [str(tmp_path / "watch")],
                }
            }
        ),
        matcher=f"CwdChanged({str(tmp_path / 'other')})",
    )

    result = HookRuntime().run_cwd_changed(
        settings=settings,
        cwd=str(tmp_path),
        old_cwd=str(tmp_path / "old"),
        new_cwd=str(tmp_path / "new"),
    )

    assert result.executions == []
    assert result.content is None
    assert result.continue_ is True



def test_worktree_remove_hook_non_matching_path_content_is_ignored(tmp_path) -> None:
    log_path = tmp_path / "path-ignore.txt"
    settings = _hook_settings(
        "WorktreeRemove",
        _python_write_text(log_path, "nope"),
        matcher=f"ExitWorktree({str(tmp_path / 'other')})",
    )

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=str(tmp_path / "worktree"),
    )

    assert result.executions == []
    assert result.content is None
    assert result.continue_ is True
    assert not log_path.exists()



def test_worktree_remove_hook_respects_if_matcher(tmp_path) -> None:
    log_path = tmp_path / "if-match.txt"
    settings = SettingsLoadResult(
        effective={
            "hooks": {
                "WorktreeRemove": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": _python_write_text(log_path, "ok"),
                                "if": "ExitWorktree",
                            }
                        ]
                    }
                ]
            }
        },
        sources=[
            {
                "source": "flagSettings",
                "settings": {
                    "hooks": {
                        "WorktreeRemove": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": _python_write_text(log_path, "ok"),
                                        "if": "ExitWorktree",
                                    }
                                ]
                            }
                        ]
                    }
                },
            }
        ],
    )

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=str(tmp_path / "worktree"),
    )

    assert result.continue_ is True
    assert log_path.read_text(encoding="utf-8") == "ok"



def test_worktree_create_hook_respects_if_matcher(tmp_path) -> None:
    target = tmp_path / "if-create"
    target.mkdir()
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "WorktreeCreate",
                "worktreePath": str(target),
            }
        }
    )
    settings = SettingsLoadResult(
        effective={
            "hooks": {
                "WorktreeCreate": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": command,
                                "if": "EnterWorktree",
                            }
                        ]
                    }
                ]
            }
        },
        sources=[
            {
                "source": "flagSettings",
                "settings": {
                    "hooks": {
                        "WorktreeCreate": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": command,
                                        "if": "EnterWorktree",
                                    }
                                ]
                            }
                        ]
                    }
                },
            }
        ],
    )

    result = HookRuntime().run_worktree_create(
        settings=settings,
        cwd=str(tmp_path),
        name="if-create",
    )

    assert result.content == {"worktreePath": str(target)}



def test_cwd_changed_hook_respects_if_matcher(tmp_path) -> None:
    settings = SettingsLoadResult(
        effective={
            "hooks": {
                "CwdChanged": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": _python_print_json(
                                    {
                                        "hookSpecificOutput": {
                                            "hookEventName": "CwdChanged",
                                            "watchPaths": [str(tmp_path / "watch")],
                                        }
                                    }
                                ),
                                "if": "CwdChanged",
                            }
                        ]
                    }
                ]
            }
        },
        sources=[
            {
                "source": "flagSettings",
                "settings": {
                    "hooks": {
                        "CwdChanged": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": _python_print_json(
                                            {
                                                "hookSpecificOutput": {
                                                    "hookEventName": "CwdChanged",
                                                    "watchPaths": [str(tmp_path / "watch")],
                                                }
                                            }
                                        ),
                                        "if": "CwdChanged",
                                    }
                                ]
                            }
                        ]
                    }
                },
            }
        ],
    )

    result = HookRuntime().run_cwd_changed(
        settings=settings,
        cwd=str(tmp_path),
        old_cwd=str(tmp_path / "old"),
        new_cwd=str(tmp_path / "new"),
    )

    assert result.content == {"watchPaths": [str(tmp_path / "watch")]}



def test_worktree_remove_hook_if_non_match_is_ignored(tmp_path) -> None:
    log_path = tmp_path / "if-ignore.txt"
    settings = SettingsLoadResult(
        effective={
            "hooks": {
                "WorktreeRemove": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": _python_write_text(log_path, "nope"),
                                "if": "Read",
                            }
                        ]
                    }
                ]
            }
        },
        sources=[
            {
                "source": "flagSettings",
                "settings": {
                    "hooks": {
                        "WorktreeRemove": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": _python_write_text(log_path, "nope"),
                                        "if": "Read",
                                    }
                                ]
                            }
                        ]
                    }
                },
            }
        ],
    )

    result = HookRuntime().run_worktree_remove(
        settings=settings,
        cwd=str(tmp_path),
        worktree_path=str(tmp_path / "worktree"),
    )

    assert result.executions == []
    assert not log_path.exists()



def test_worktree_create_hook_if_non_match_is_ignored(tmp_path) -> None:
    target = tmp_path / "if-ignore"
    target.mkdir()
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "WorktreeCreate",
                "worktreePath": str(target),
            }
        }
    )
    settings = SettingsLoadResult(
        effective={
            "hooks": {
                "WorktreeCreate": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": command,
                                "if": "Read",
                            }
                        ]
                    }
                ]
            }
        },
        sources=[
            {
                "source": "flagSettings",
                "settings": {
                    "hooks": {
                        "WorktreeCreate": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": command,
                                        "if": "Read",
                                    }
                                ]
                            }
                        ]
                    }
                },
            }
        ],
    )

    result = HookRuntime().run_worktree_create(
        settings=settings,
        cwd=str(tmp_path),
        name="ignored",
    )

    assert result.executions == []
    assert result.content is None



def test_cwd_changed_hook_if_non_match_is_ignored(tmp_path) -> None:
    command = _python_print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "CwdChanged",
                "watchPaths": [str(tmp_path / "watch")],
            }
        }
    )
    settings = SettingsLoadResult(
        effective={
            "hooks": {
                "CwdChanged": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": command,
                                "if": "Read",
                            }
                        ]
                    }
                ]
            }
        },
        sources=[
            {
                "source": "flagSettings",
                "settings": {
                    "hooks": {
                        "CwdChanged": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": command,
                                        "if": "Read",
                                    }
                                ]
                            }
                        ]
                    }
                },
            }
        ],
    )

    result = HookRuntime().run_cwd_changed(
        settings=settings,
        cwd=str(tmp_path),
        old_cwd=str(tmp_path / "old"),
        new_cwd=str(tmp_path / "new"),
    )

    assert result.executions == []
    assert result.content is None
