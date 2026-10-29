from __future__ import annotations

import pytest

from phantom_shell.storage import History


@pytest.fixture
def history(tmp_path):
    instance = History(tmp_path / "history.sqlite3")
    yield instance
    instance.close()
