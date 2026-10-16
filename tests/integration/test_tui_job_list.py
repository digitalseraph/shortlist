from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.models import RawJob
from shortlist.profiles import Profile
from shortlist.store.db import migrate, update_score, upsert_job
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
async def test_joblist_renders_seeded_jobs(tmp_path: Path) -> None:
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
    update_score(db, job.id, score=87, reason="x", model="m")

    async with ShortlistApp(profile=_profile(db)).run_test() as pilot:
        await pilot.pause()
        from textual.widgets import DataTable

        table = pilot.app.screen.query_one(DataTable)
        assert table.row_count == 1
        # get_row returns a list of cell renderables; str() each to compare
        cells = [str(c) for c in table.get_row_at(0)]
        row_text = " ".join(cells)
        assert "Acme" in row_text
        assert "87" in row_text


@pytest.mark.asyncio
async def test_joblist_quits_on_q(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    migrate(db)
    async with ShortlistApp(profile=_profile(db)).run_test() as pilot:
        await pilot.press("q")
        assert pilot.app.is_running is False or pilot.app.return_value is None


@pytest.mark.asyncio
async def test_enter_opens_job_detail(tmp_path: Path) -> None:
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
            description_md="Distributed Python systems.",
        ),
    )
    update_score(db, job.id, score=80, reason="x", model="m")

    from textual.widgets import Static

    async with ShortlistApp(profile=_profile(db)).run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Verify JobDetail screen pushed by querying its #title widget.
        widget = pilot.app.screen.query_one("#title", Static)
        title = str(widget.render())
        assert "Senior Backend Engineer" in title
        assert "Acme" in title


@pytest.mark.asyncio
async def test_search_filters_table(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    upsert_job(
        db,
        RawJob(
            source="greenhouse",
            external_id="a",
            company="Acme",
            title="Senior Backend Engineer",
            url="https://example.com/a",
            posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
            location="Remote",
            remote=True,
        ),
    )
    upsert_job(
        db,
        RawJob(
            source="greenhouse",
            external_id="b",
            company="Globex",
            title="Frontend Engineer",
            url="https://example.com/b",
            posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
            location="Remote",
            remote=True,
        ),
    )

    from textual.widgets import DataTable

    async with ShortlistApp(profile=_profile(db)).run_test() as pilot:
        await pilot.pause()
        await pilot.press("slash")
        await pilot.pause()
        for ch in "globex":
            await pilot.press(ch)
        await pilot.pause()
        # Inspect the DataTable rows directly (Textual 8 quirk).
        table = pilot.app.screen.query_one(DataTable)
        assert table.row_count == 1
        # Cell at row 0, column 1 (Company)
        company_cell = table.get_cell_at((0, 1))
        assert "Globex" in str(company_cell)
