from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Static

from shortlist.profiles import Profile
from shortlist.store.db import migrate
from shortlist_tui.app import ShortlistApp


def _profile(db: Path) -> Profile:
    """Minimal profile pointing at a test database."""
    return Profile(
        slug="test",
        display_name="Test",
        db_path=db,
        prefs_path=db.parent / "prefs.yaml",
        resume_path=db.parent / "resume.md",
        original_resume_path=db.parent / "resume.original",
        output_dir=db.parent / "output",
    )


@pytest.mark.asyncio
async def test_settings_renders_when_config_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    db = tmp_path / "data" / "db.sqlite"
    migrate(db)
    async with ShortlistApp(profile=_profile(db)).run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        cfg_text = str(pilot.app.screen.query_one("#config-summary", Static).render())
        assert "config.yaml missing" in cfg_text or "Config" in cfg_text
