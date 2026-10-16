from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.widgets import Static

from shortlist.models import RawJob
from shortlist.profiles import Profile
from shortlist.store.db import migrate, transition_status, upsert_job
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
async def test_applications_board_groups_by_status(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    job = upsert_job(
        db,
        RawJob(
            source="greenhouse",
            external_id="acme:1",
            company="Acme",
            title="Senior Backend Engineer",
            url="https://example.com/1",
            posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
            location="Remote - US",
            remote=True,
        ),
    )
    transition_status(db, job.id, "tailored")

    async with ShortlistApp(profile=_profile(db)).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        # Inspect the tailored column directly.
        screen = pilot.app.screen
        header = str(screen.query_one("#col-tailored-header", Static).render())
        body = str(screen.query_one("#col-tailored-body", Static).render())
        assert "tailored" in header
        assert "(1)" in header
        assert "Acme" in body
