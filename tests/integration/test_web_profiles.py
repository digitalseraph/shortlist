"""Profile scoping in the web layer: isolation, 404s and redirects."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist.models import RawJob
from shortlist.store.db import list_jobs, transition_status, upsert_job
from shortlist_web.app import create_app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("SHORTLIST_PROFILE", raising=False)
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def _seed(db: Path, eid: str, company: str) -> int:
    job = upsert_job(
        db,
        RawJob(
            source="greenhouse",
            external_id=eid,
            company=company,
            title="Senior Backend Engineer",
            url=f"https://example.com/{eid}",
            posted_at=datetime.now(UTC),
        ),
    )
    return job.id


def test_unknown_slug_is_404_not_a_fallback(client: TestClient) -> None:
    profiles.create("david", "David")
    assert client.get("/p/nobody/applications").status_code == 404


def test_bare_path_redirects_to_the_active_profile(client: TestClient) -> None:
    profiles.create("david", "David")
    r = client.get("/applications", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/p/david/applications"


def test_profiles_are_isolated(client: TestClient) -> None:
    """The load-bearing test: one person's data never appears on another's board."""
    david = profiles.create("david", "David")
    alex = profiles.create("alex", "Alex")
    jid = _seed(david.db_path, "gh_1", "Datadog")
    transition_status(david.db_path, jid, "tailored")

    mine = client.get("/p/david/applications")
    theirs = client.get("/p/alex/applications")

    assert "Datadog" in mine.text
    assert "Datadog" not in theirs.text
    assert list_jobs(alex.db_path) == []


def test_move_acts_on_the_profile_in_the_url(client: TestClient) -> None:
    david = profiles.create("david", "David")
    profiles.create("alex", "Alex")
    jid = _seed(david.db_path, "gh_1", "Datadog")
    transition_status(david.db_path, jid, "tailored")

    # The same job id under the other profile's URL must not touch David's job:
    # alex's database has no such row, so this 404s rather than acting on it.
    r = client.post(f"/p/alex/applications/move/{jid}", data={"status": "applied"})
    assert r.status_code == 404
    assert next(j for j in list_jobs(david.db_path) if j.id == jid).status == "tailored"


def test_invalid_transition_on_an_existing_job_is_400(client: TestClient) -> None:
    """A real job in this profile, but a transition the state machine forbids."""
    david = profiles.create("david", "David")
    jid = _seed(david.db_path, "gh_1", "Datadog")

    # "new" -> "offer" is not an allowed transition.
    r = client.post(f"/p/david/applications/move/{jid}", data={"status": "offer"})
    assert r.status_code == 400
    assert next(j for j in list_jobs(david.db_path) if j.id == jid).status == "new"


def test_no_profiles_redirects_to_first_run(client: TestClient) -> None:
    r = client.get("/applications", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/profiles/new"
