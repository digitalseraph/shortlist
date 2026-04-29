from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.models import Job, RawJob
from shortlist.store.db import (
    connect,
    current_version,
    list_jobs,
    mark_source_fetched,
    migrate,
    source_last_fetched,
    upsert_job,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "shortlist.sqlite"


def test_migrate_from_zero_to_latest(db_path: Path):
    migrate(db_path)
    assert current_version(db_path) == 2


def test_migrate_is_idempotent(db_path: Path):
    migrate(db_path)
    migrate(db_path)
    migrate(db_path)
    assert current_version(db_path) == 2


def test_migrate_creates_jobs_table(db_path: Path):
    migrate(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"jobs", "sources", "events", "_schema_version"} <= names


def test_jobs_unique_constraint(db_path: Path):
    import sqlite3

    migrate(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO jobs (source, external_id, company, title, url, "
            "posted_at, discovered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "greenhouse",
                "gh_1",
                "Acme",
                "Eng",
                "https://x",
                "2026-04-25T09:00:00Z",
                "2026-04-28T12:00:00Z",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO jobs (source, external_id, company, title, url, "
                "posted_at, discovered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "greenhouse",
                    "gh_1",
                    "Acme",
                    "Eng",
                    "https://x",
                    "2026-04-25T09:00:00Z",
                    "2026-04-28T12:00:00Z",
                ),
            )


def _raw(external_id: str = "gh_1", *, title: str = "Senior Backend Engineer") -> RawJob:
    return RawJob(
        source="greenhouse",
        external_id=external_id,
        company="Acme",
        title=title,
        url="https://example.com/jobs/" + external_id,
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote - US",
        remote=True,
    )


def test_upsert_inserts_new_job(db_path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    assert isinstance(job, Job)
    assert job.id > 0
    assert job.title == "Senior Backend Engineer"
    assert job.status == "new"


def test_upsert_updates_existing_job(db_path):
    migrate(db_path)
    a = upsert_job(db_path, _raw(title="Old Title"))
    b = upsert_job(db_path, _raw(title="New Title"))
    assert a.id == b.id
    assert b.title == "New Title"


def test_list_jobs_returns_all(db_path):
    migrate(db_path)
    upsert_job(db_path, _raw("gh_1"))
    upsert_job(db_path, _raw("gh_2"))
    jobs = list_jobs(db_path)
    assert len(jobs) == 2


def test_list_jobs_filters_by_status(db_path):
    migrate(db_path)
    upsert_job(db_path, _raw("gh_1"))
    upsert_job(db_path, _raw("gh_2"))
    jobs = list_jobs(db_path, status="new")
    assert len(jobs) == 2
    jobs = list_jobs(db_path, status="applied")
    assert jobs == []


def test_source_fetched_marker(db_path):
    migrate(db_path)
    assert source_last_fetched(db_path, "greenhouse") is None
    when = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    mark_source_fetched(db_path, "greenhouse", when)
    got = source_last_fetched(db_path, "greenhouse")
    assert got == when


def test_update_score(db_path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    from shortlist.store.db import update_score

    update_score(db_path, job.id, score=42, reason="hard filter pass", model="hard_filter")
    out = list_jobs(db_path)[0]
    assert out.score == 42
    assert out.score_reason == "hard filter pass"
    assert out.scored_with_model == "hard_filter"


def test_migrate_to_v2_creates_embeddings_tables(db_path: Path):
    migrate(db_path)
    assert current_version(db_path) == 2
    with connect(db_path) as conn:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','virtual')"
            )
        }
    assert "job_embeddings" in names
    assert "resume_embeddings" in names
    assert "scoring_runs" in names


def test_sqlite_vec_extension_loads(db_path: Path):
    migrate(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT vec_version()").fetchone()
    assert row is not None
