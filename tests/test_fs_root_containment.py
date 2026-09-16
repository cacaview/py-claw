"""PYCLAW_FS_ROOT containment (ADR-0019, layer 3).

When the ``PYCLAW_FS_ROOT`` environment variable is set, every local FS tool is
confined to that directory: an absolute path outside it, a ``..`` traversal, or
a symlink pointing out of it is refused (fail closed). Glob/Grep results are
additionally filtered so a pattern or a symlinked file cannot leak a path that
resolves outside the root. When the variable is unset the guard is a no-op and
behaviour is unchanged (the default for any deployment that does not opt in).
"""
from __future__ import annotations

import pytest

from py_claw.tools.base import ToolError
from py_claw.tools.local_fs import (
    EditTool,
    EditToolInput,
    GlobTool,
    GlobToolInput,
    GrepTool,
    GrepToolInput,
    NotebookEditTool,
    NotebookEditToolInput,
    ReadTool,
    ReadToolInput,
    WriteTool,
    WriteToolInput,
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """An outside tree and an inside (root) tree, with the root armed."""
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "secret.txt"
    outside_file.write_text("top-secret\n", encoding="utf-8")

    root = tmp_path / "root"
    root.mkdir()
    inside_file = root / "notes.md"
    inside_file.write_text("hello resident\n", encoding="utf-8")

    monkeypatch.setenv("PYCLAW_FS_ROOT", str(root))
    return {"outside": outside, "outside_file": outside_file,
            "root": root, "inside_file": inside_file}


def test_unset_env_is_noop(tmp_path, monkeypatch):
    """Without PYCLAW_FS_ROOT the guard never fires (default behaviour)."""
    monkeypatch.delenv("PYCLAW_FS_ROOT", raising=False)
    f = tmp_path / "free.txt"
    f.write_text("ok", encoding="utf-8")
    out = ReadTool().execute(ReadToolInput(file_path=str(f)), cwd=str(tmp_path))
    assert out["type"] == "text"
    # A write to an arbitrary absolute path is still allowed with no root set.
    target = tmp_path / "written.txt"
    WriteTool().execute(WriteToolInput(file_path=str(target), content="x"),
                        cwd=str(tmp_path))
    assert target.exists()


def test_read_inside_root_allowed(sandbox):
    out = ReadTool().execute(
        ReadToolInput(file_path=str(sandbox["inside_file"])),
        cwd=str(sandbox["root"]),
    )
    assert out["type"] == "text"


def test_read_outside_root_denied(sandbox):
    with pytest.raises(ToolError, match="PYCLAW_FS_ROOT"):
        ReadTool().execute(
            ReadToolInput(file_path=str(sandbox["outside_file"])),
            cwd=str(sandbox["root"]),
        )


def test_read_dotdot_traversal_denied(sandbox):
    """A path that spells itself inside the root but resolves outside."""
    (sandbox["root"] / "sub").mkdir()
    sneaky = sandbox["root"] / "sub" / ".." / ".." / "outside" / "secret.txt"
    with pytest.raises(ToolError, match="PYCLAW_FS_ROOT"):
        ReadTool().execute(ReadToolInput(file_path=str(sneaky)),
                           cwd=str(sandbox["root"]))


def test_read_escaping_symlink_denied(sandbox):
    link = sandbox["root"] / "evil_link"
    link.symlink_to(sandbox["outside_file"])
    with pytest.raises(ToolError, match="PYCLAW_FS_ROOT"):
        ReadTool().execute(ReadToolInput(file_path=str(link)),
                           cwd=str(sandbox["root"]))


def test_write_outside_root_denied(sandbox):
    target = sandbox["outside"] / "created.txt"
    with pytest.raises(ToolError, match="PYCLAW_FS_ROOT"):
        WriteTool().execute(WriteToolInput(file_path=str(target), content="x"),
                            cwd=str(sandbox["root"]))
    assert not target.exists()  # nothing was created


def test_write_inside_root_allowed(sandbox):
    target = sandbox["root"] / "new.txt"
    WriteTool().execute(WriteToolInput(file_path=str(target), content="x"),
                        cwd=str(sandbox["root"]))
    assert target.exists()


def test_edit_outside_root_denied(sandbox):
    with pytest.raises(ToolError, match="PYCLAW_FS_ROOT"):
        EditTool().execute(
            EditToolInput(file_path=str(sandbox["outside_file"]),
                          old_string="top-secret", new_string="x"),
            cwd=str(sandbox["root"]),
        )


def test_glob_outside_root_denied(sandbox):
    with pytest.raises(ToolError, match="PYCLAW_FS_ROOT"):
        GlobTool().execute(GlobToolInput(pattern="*", path=str(sandbox["outside"])),
                           cwd=str(sandbox["root"]))


def test_glob_dotdot_pattern_filtered(sandbox):
    """A glob pattern reaching outside via ``..`` yields no outside files."""
    out = GlobTool().execute(
        GlobToolInput(pattern="../*/secret.txt", path=str(sandbox["root"])),
        cwd=str(sandbox["root"]),
    )
    assert out["filenames"] == []


def test_grep_outside_root_denied(sandbox):
    with pytest.raises(ToolError, match="PYCLAW_FS_ROOT"):
        GrepTool().execute(GrepToolInput(pattern="top-secret",
                                         path=str(sandbox["outside"])),
                           cwd=str(sandbox["root"]))


def test_grep_symlinked_file_filtered(sandbox):
    """A symlinked file inside the root pointing outside is not searched."""
    link = sandbox["root"] / "sneaky_link"
    link.symlink_to(sandbox["outside_file"])
    out = GrepTool().execute(GrepToolInput(pattern="top-secret",
                                           path=str(sandbox["root"])),
                             cwd=str(sandbox["root"]))
    assert out["numFiles"] == 0
    assert out["filenames"] == []


def test_notebook_edit_outside_denied(sandbox):
    with pytest.raises(ToolError, match="PYCLAW_FS_ROOT"):
        NotebookEditTool().execute(
            NotebookEditToolInput(notebook_path=str(sandbox["outside"] / "nb.ipynb")),
            cwd=str(sandbox["root"]),
        )
