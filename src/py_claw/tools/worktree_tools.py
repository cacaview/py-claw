from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import model_validator

from py_claw.schemas.common import PyClawBaseModel
from py_claw.settings.loader import get_settings_with_sources
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


_WORKTREE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")


class EnterWorktreeToolInput(PyClawBaseModel):
    name: str | None = None

    @model_validator(mode="after")
    def validate_name(self) -> "EnterWorktreeToolInput":
        if self.name is not None:
            _validate_worktree_name(self.name)
        return self


class ExitWorktreeToolInput(PyClawBaseModel):
    action: Literal["keep", "remove"]
    discard_changes: bool = False


class EnterWorktreeTool:
    definition = ToolDefinition(name="EnterWorktree", input_model=EnterWorktreeToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        name = payload.get("name")
        return ToolPermissionTarget(tool_name=self.definition.name, content=name if isinstance(name, str) else None)

    def execute(self, arguments: EnterWorktreeToolInput, *, cwd: str) -> dict[str, object]:
        state = self._require_state()
        if state.active_worktree_session is not None:
            raise ToolError("Already in a worktree session")

        settings = _load_settings(state)
        original_cwd = state.cwd
        slug = arguments.name or _generate_worktree_name()
        repo_root = _git_repo_root(original_cwd)

        worktree_path: str
        worktree_branch: str | None = None
        original_head_commit: str | None = None
        backend: Literal["git", "hook"]

        if repo_root is not None:
            root_path = Path(repo_root)
            worktree_dir = (root_path / ".claude" / "worktrees" / slug).resolve()
            worktree_dir.parent.mkdir(parents=True, exist_ok=True)
            worktree_branch = f"worktree/{slug.replace('/', '-')}"
            original_head_commit = _git_head_commit(repo_root)
            completed = subprocess.run(
                ["git", "-C", repo_root, "worktree", "add", "-b", worktree_branch, str(worktree_dir), "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip() or "git worktree add failed"
                raise ToolError(detail)
            worktree_path = str(worktree_dir)
            backend = "git"
        else:
            hook_result = state.hook_runtime.run_worktree_create(
                settings=settings,
                cwd=original_cwd,
                name=slug,
                permission_mode=state.permission_mode,
            )
            if not hook_result.continue_:
                raise ToolError(hook_result.stop_reason or "WorktreeCreate hook blocked worktree creation")
            payload = hook_result.content if isinstance(hook_result.content, dict) else None
            candidate = payload.get("worktreePath") if isinstance(payload, dict) else None
            if not isinstance(candidate, str) or not candidate.strip():
                raise ToolError("WorktreeCreate hook did not provide a worktreePath")
            worktree_path = str((Path(original_cwd) / candidate).resolve() if not Path(candidate).is_absolute() else Path(candidate).resolve())
            if not Path(worktree_path).exists() or not Path(worktree_path).is_dir():
                raise ToolError(f"Worktree path does not exist: {worktree_path}")
            backend = "hook"
            repo_root = None

        os.chdir(worktree_path)
        state.cwd = worktree_path
        state.active_worktree_session = state.active_worktree_session.__class__(
            original_cwd=original_cwd,
            worktree_path=worktree_path,
            worktree_branch=worktree_branch,
            repo_root=repo_root,
            original_head_commit=original_head_commit,
            backend=backend,
        ) if state.active_worktree_session is not None else _build_session(
            original_cwd=original_cwd,
            worktree_path=worktree_path,
            worktree_branch=worktree_branch,
            repo_root=repo_root,
            original_head_commit=original_head_commit,
            backend=backend,
        )
        state.hook_runtime.run_cwd_changed(
            settings=settings,
            cwd=state.cwd,
            old_cwd=original_cwd,
            new_cwd=worktree_path,
            permission_mode=state.permission_mode,
        )

        branch_info = f" on branch {worktree_branch}" if worktree_branch else ""
        return {
            "worktreePath": worktree_path,
            "worktreeBranch": worktree_branch,
            "message": (
                f"Created worktree at {worktree_path}{branch_info}. "
                "The session is now working in the worktree. Use ExitWorktree to leave mid-session."
            ),
        }

    def _require_state(self) -> RuntimeState:
        if self._state is None:
            raise ToolError("EnterWorktree requires runtime state")
        return self._state


class ExitWorktreeTool:
    definition = ToolDefinition(name="ExitWorktree", input_model=ExitWorktreeToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        action = payload.get("action")
        return ToolPermissionTarget(tool_name=self.definition.name, content=action if isinstance(action, str) else None)

    def execute(self, arguments: ExitWorktreeToolInput, *, cwd: str) -> dict[str, object]:
        state = self._require_state()
        session = state.active_worktree_session
        if session is None:
            return {
                "message": (
                    "No-op: there is no active EnterWorktree session to exit. "
                    "This tool only operates on worktrees created by EnterWorktree in the current session."
                )
            }

        settings = _load_settings(state)
        if arguments.action == "remove":
            summary = _count_worktree_changes(session.worktree_path, session.original_head_commit)
            if not arguments.discard_changes:
                if summary is None:
                    raise ToolError(
                        f"Could not verify worktree state at {session.worktree_path}. "
                        'Re-invoke with discard_changes: true to proceed — or use action: "keep".'
                    )
                changed_files, commits = summary
                if changed_files > 0 or commits > 0:
                    parts: list[str] = []
                    if changed_files > 0:
                        parts.append(f"{changed_files} uncommitted {'file' if changed_files == 1 else 'files'}")
                    if commits > 0:
                        parts.append(f"{commits} {'commit' if commits == 1 else 'commits'}")
                    raise ToolError(
                        f"Worktree has {' and '.join(parts)}. "
                        'Confirm with the user, then re-invoke with discard_changes: true — or use action: "keep".'
                    )
            else:
                summary = summary or (0, 0)
        else:
            summary = _count_worktree_changes(session.worktree_path, session.original_head_commit) or (0, 0)

        old_cwd = session.worktree_path
        state.cwd = session.original_cwd
        os.chdir(session.original_cwd)

        try:
            if arguments.action == "remove":
                if session.backend == "git":
                    _remove_git_worktree(session, force=arguments.discard_changes)
                else:
                    hook_result = state.hook_runtime.run_worktree_remove(
                        settings=settings,
                        cwd=state.cwd,
                        worktree_path=session.worktree_path,
                        permission_mode=state.permission_mode,
                    )
                    if not hook_result.continue_:
                        raise ToolError(hook_result.stop_reason or "WorktreeRemove hook blocked worktree removal")
            state.active_worktree_session = None
        except Exception:
            state.cwd = old_cwd
            os.chdir(old_cwd)
            raise

        state.hook_runtime.run_cwd_changed(
            settings=settings,
            cwd=state.cwd,
            old_cwd=old_cwd,
            new_cwd=session.original_cwd,
            permission_mode=state.permission_mode,
        )

        changed_files, commits = summary
        if arguments.action == "keep":
            return {
                "action": "keep",
                "originalCwd": session.original_cwd,
                "worktreePath": session.worktree_path,
                "worktreeBranch": session.worktree_branch,
                "message": (
                    f"Exited worktree. Your work is preserved at {session.worktree_path}"
                    f"{f' on branch {session.worktree_branch}' if session.worktree_branch else ''}. "
                    f"Session is now back in {session.original_cwd}."
                ),
            }

        discard_note = ""
        if commits > 0 or changed_files > 0:
            parts: list[str] = []
            if commits > 0:
                parts.append(f"{commits} {'commit' if commits == 1 else 'commits'}")
            if changed_files > 0:
                parts.append(f"{changed_files} uncommitted {'file' if changed_files == 1 else 'files'}")
            discard_note = f" Discarded {' and '.join(parts)}."
        return {
            "action": "remove",
            "originalCwd": session.original_cwd,
            "worktreePath": session.worktree_path,
            "worktreeBranch": session.worktree_branch,
            "discardedFiles": changed_files,
            "discardedCommits": commits,
            "message": f"Exited and removed worktree at {session.worktree_path}.{discard_note} Session is now back in {session.original_cwd}.",
        }

    def _require_state(self) -> RuntimeState:
        if self._state is None:
            raise ToolError("ExitWorktree requires runtime state")
        return self._state


def _validate_worktree_name(name: str) -> None:
    if not name or len(name) > 64 or not _WORKTREE_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "name must contain only letters, digits, dots, underscores, dashes, and optional '/' separators, max 64 chars"
        )



def _generate_worktree_name() -> str:
    return f"wf-{uuid4().hex[:8]}"



def _load_settings(state: RuntimeState):
    return get_settings_with_sources(
        flag_settings=state.flag_settings,
        policy_settings=state.policy_settings,
        cwd=state.cwd,
        home_dir=state.home_dir,
    )



def _git_repo_root(cwd: str) -> str | None:
    completed = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    root = completed.stdout.strip()
    return str(Path(root).resolve()) if root else None



def _git_head_commit(cwd: str) -> str | None:
    completed = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit or None



def _count_worktree_changes(worktree_path: str, original_head_commit: str | None) -> tuple[int, int] | None:
    if _git_repo_root(worktree_path) is None:
        return None
    status = subprocess.run(
        ["git", "-C", worktree_path, "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        return None
    changed_files = sum(1 for line in status.stdout.splitlines() if line.strip())
    if not original_head_commit:
        return None
    rev_list = subprocess.run(
        ["git", "-C", worktree_path, "rev-list", "--count", f"{original_head_commit}..HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if rev_list.returncode != 0:
        return None
    try:
        commits = int(rev_list.stdout.strip() or "0")
    except ValueError:
        commits = 0
    return changed_files, commits



def _remove_git_worktree(session: object, *, force: bool) -> None:
    repo_root = getattr(session, "repo_root", None)
    worktree_path = getattr(session, "worktree_path")
    worktree_branch = getattr(session, "worktree_branch", None)
    if not isinstance(repo_root, str) or not repo_root:
        raise ToolError("Git worktree session is missing repo root")
    command = ["git", "-C", repo_root, "worktree", "remove"]
    if force:
        command.append("--force")
    command.append(worktree_path)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git worktree remove failed"
        raise ToolError(detail)
    if isinstance(worktree_branch, str) and worktree_branch:
        subprocess.run(
            ["git", "-C", repo_root, "branch", "-D", worktree_branch],
            capture_output=True,
            text=True,
            check=False,
        )
    if Path(worktree_path).exists():
        shutil.rmtree(worktree_path, ignore_errors=True)



def _build_session(
    *,
    original_cwd: str,
    worktree_path: str,
    worktree_branch: str | None,
    repo_root: str | None,
    original_head_commit: str | None,
    backend: Literal["git", "hook"],
):
    from py_claw.cli.runtime import ActiveWorktreeSession

    return ActiveWorktreeSession(
        original_cwd=original_cwd,
        worktree_path=worktree_path,
        worktree_branch=worktree_branch,
        repo_root=repo_root,
        original_head_commit=original_head_commit,
        backend=backend,
    )
