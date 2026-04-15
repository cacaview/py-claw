from __future__ import annotations

from io import StringIO

import pytest

from py_claw.cli.main import main


def test_cli_tui_flag_uses_tui_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("py_claw.cli.main.run_textual_ui", lambda *args, **kwargs: 0)
    assert main(["--tui"], stdin=StringIO(), stdout=StringIO()) == 0
