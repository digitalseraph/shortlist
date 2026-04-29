from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.models import RawJob
from shortlist.store.db import (
    add_contact,
    get_application,
    list_contacts,
    log_event,
    migrate,
    remove_contact,
    transition_status,
    update_application,
    upsert_job,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "shortlist.sqlite"


def _raw(eid: str = "gh_1") -> RawJob:
    return RawJob(
        source="greenhouse",
        external_id=eid,
        company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/" + eid,
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote - US",
        remote=True,
    )


def test_transition_status_updates_jobs_row(db_path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    transition_status(db_path, job.id, "tailored")
    from shortlist.store.db import list_jobs

    refreshed = next(j for j in list_jobs(db_path) if j.id == job.id)
    assert refreshed.status == "tailored"
    assert refreshed.status_changed_at is not None


def test_transition_status_rejects_invalid(db_path):
    from shortlist.tracker.state import InvalidStatusTransitionError

    migrate(db_path)
    job = upsert_job(db_path, _raw())
    with pytest.raises(InvalidStatusTransitionError):
        transition_status(db_path, job.id, "interview")


def test_update_application_creates_then_updates(db_path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    update_application(
        db_path,
        job.id,
        applied_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
        applied_via="company website",
    )
    update_application(db_path, job.id, salary_offered=210000)
    a = get_application(db_path, job.id)
    assert a is not None
    assert a.applied_via == "company website"
    assert a.salary_offered == 210000


def test_contact_add_list_remove(db_path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    update_application(db_path, job.id, applied_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC))
    cid = add_contact(db_path, job.id, name="Jane Doe", email="jane@acme.com", role="recruiter")
    rows = list_contacts(db_path, job.id)
    assert len(rows) == 1
    assert rows[0].name == "Jane Doe"
    assert rows[0].email == "jane@acme.com"
    remove_contact(db_path, cid)
    assert list_contacts(db_path, job.id) == []


def test_log_event_records_transition(db_path):
    import sqlite3

    migrate(db_path)
    job = upsert_job(db_path, _raw())
    log_event(
        db_path,
        job_id=job.id,
        type="status.transition",
        payload={"from": "new", "to": "tailored"},
    )
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT type, payload_json FROM events WHERE job_id = ?", (job.id,)
        ).fetchall()
    assert rows[0][0] == "status.transition"
    assert "tailored" in rows[0][1]
