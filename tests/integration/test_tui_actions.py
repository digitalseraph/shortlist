from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shortlist.store.db import migrate
from shortlist_tui.app import ShortlistApp


@pytest.mark.asyncio
async def test_f_triggers_fetch(tmp_path: Path, monkeypatch):
    db = tmp_path / "db.sqlite"
    migrate(db)
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(cfg_dir))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))

    called: list[bool] = []

    def fake_fetch_all(*_a, **_k):
        called.append(True)
        return "fetched 0 jobs"

    import shortlist_tui.app as app_mod

    monkeypatch.setattr(app_mod, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(app_mod, "load_prefs", lambda *_a, **_k: MagicMock())

    async with ShortlistApp(db_path=db).run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.app.workers.wait_for_complete()
    assert called == [True]
