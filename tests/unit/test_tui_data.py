from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.models import RawJob
from shortlist.store.db import migrate, update_score, upsert_job
from shortlist_tui.data import JobRow, list_job_rows


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "db.sqlite"


def _seed(db: Path, eid: str = "gh_1", title: str = "Senior Backend Engineer") -> int:
    job = upsert_job(
        db,
        RawJob(
            source="greenhouse",
            external_id=eid,
            company="Acme",
            title=title,
            url=f"https://example.com/{eid}",
            posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
            location="Remote - US",
            remote=True,
        ),
    )
    return job.id


def test_list_job_rows_empty(db_path):
    migrate(db_path)
    rows = list_job_rows(db_path)
    assert rows == []


def test_list_job_rows_returns_jobrow(db_path):
    migrate(db_path)
    jid = _seed(db_path)
    update_score(db_path, jid, score=87, reason="great", model="haiku")
    rows = list_job_rows(db_path)
    assert len(rows) == 1
    assert isinstance(rows[0], JobRow)
    assert rows[0].id == jid
    assert rows[0].score == 87
    assert rows[0].score_display == "87"
    assert rows[0].title == "Senior Backend Engineer"
    assert rows[0].company == "Acme"
    assert rows[0].status_display == "new"


def test_list_job_rows_min_score_filter(db_path):
    migrate(db_path)
    jid1 = _seed(db_path, "a", "Senior Backend Engineer")
    jid2 = _seed(db_path, "b", "Junior Engineer")
    update_score(db_path, jid1, score=80, reason="ok", model="haiku")
    update_score(db_path, jid2, score=10, reason="weak", model="haiku")
    rows = list_job_rows(db_path, min_score=50)
    assert len(rows) == 1
    assert rows[0].id == jid1


def test_jobrow_score_display_handles_none(db_path):
    migrate(db_path)
    _seed(db_path)
    rows = list_job_rows(db_path)
    assert rows[0].score is None
    assert rows[0].score_display == "—"
