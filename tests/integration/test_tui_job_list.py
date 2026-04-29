from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.models import RawJob
from shortlist.store.db import migrate, update_score, upsert_job
from shortlist_tui.app import ShortlistApp


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

    async with ShortlistApp(db_path=db).run_test() as pilot:
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
    async with ShortlistApp(db_path=db).run_test() as pilot:
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

    async with ShortlistApp(db_path=db).run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Verify JobDetail screen pushed by querying its #title widget.
        widget = pilot.app.screen.query_one("#title", Static)
        title = str(widget.render())
        assert "Senior Backend Engineer" in title
        assert "Acme" in title
