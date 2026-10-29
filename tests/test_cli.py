from __future__ import annotations

import sys

from phantom_shell.cli import main
from phantom_shell.storage import History


def test_demo_fixture_is_labeled_and_never_persisted(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "history.sqlite3"
    monkeypatch.setenv("PHANTOM_DATABASE", str(db_path))
    monkeypatch.setenv("PHANTOM_LOG_LEVEL", "ERROR")
    monkeypatch.setattr(sys, "argv", ["phantom", "--plain", "demo-fixture"])
    main()
    output = capsys.readouterr().out
    assert "TEST SCENARIO" in output
    assert "no live finding is created or saved" in output
    history = History(db_path)
    try:
        assert history.events() == []
    finally:
        history.close()
