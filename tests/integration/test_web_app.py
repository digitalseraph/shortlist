"""Integration tests for the shortlist_web FastAPI layer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist.models import RawJob
from shortlist.profiles import Profile
from shortlist.store.db import transition_status, update_score, upsert_job
from shortlist_web.app import create_app

PREFIX = "/p/test"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    cfg = tmp_path / "config"
    cfg.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(cfg))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(data))
    return cfg, data


@pytest.fixture
def client(env: tuple[Path, Path]) -> tuple[TestClient, Profile]:
    prof = profiles.create("test", "Test Person")
    return TestClient(create_app()), prof


def _seed(
    db: Path,
    eid: str = "gh_1",
    title: str = "Senior Backend Engineer",
    score: int | None = None,
) -> int:
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
    if score is not None:
        update_score(db, job.id, score=score, reason="x", model="x")
    return job.id


def test_root_renders_empty(client: tuple[TestClient, Profile]) -> None:
    tc, _prof = client
    r = tc.get(f"{PREFIX}/")
    assert r.status_code == 200
    assert "Shortlist" in r.text


def test_root_lists_jobs(client: tuple[TestClient, Profile]) -> None:
    tc, prof = client
    _seed(prof.db_path, score=87)
    r = tc.get(f"{PREFIX}/")
    assert "Acme" in r.text
    assert "Senior Backend Engineer" in r.text
    assert "87" in r.text


def test_search_filter(client: tuple[TestClient, Profile]) -> None:
    tc, prof = client
    _seed(prof.db_path, "a", "Senior Backend Engineer")
    _seed(prof.db_path, "b", "Frontend Engineer")
    r = tc.get(f"{PREFIX}/?q=frontend")
    assert "Frontend" in r.text
    assert "Backend" not in r.text


def test_job_detail(client: tuple[TestClient, Profile]) -> None:
    tc, prof = client
    jid = _seed(prof.db_path, score=80)
    r = tc.get(f"{PREFIX}/job/{jid}")
    assert r.status_code == 200
    assert "Senior Backend Engineer" in r.text


def test_job_detail_404(client: tuple[TestClient, Profile]) -> None:
    tc, _prof = client
    assert tc.get(f"{PREFIX}/job/9999").status_code == 404


def test_applications_groups_by_status(client: tuple[TestClient, Profile]) -> None:
    tc, prof = client
    jid = _seed(prof.db_path)
    transition_status(prof.db_path, jid, "tailored")
    r = tc.get(f"{PREFIX}/applications")
    assert "tailored" in r.text.lower()
    assert "Acme" in r.text


def test_settings_renders_when_config_missing(client: tuple[TestClient, Profile]) -> None:
    tc, _prof = client
    r = tc.get(f"{PREFIX}/settings")
    assert r.status_code == 200
    assert "config" in r.text.lower()


def test_track_invalid_transition(client: tuple[TestClient, Profile]) -> None:
    tc, prof = client
    jid = _seed(prof.db_path)
    # new → interview is not a valid transition
    r = tc.post(f"{PREFIX}/track/{jid}", data={"status": "interview"})
    assert r.status_code == 400


def test_track_valid_transition(client: tuple[TestClient, Profile]) -> None:
    tc, prof = client
    jid = _seed(prof.db_path)
    r = tc.post(f"{PREFIX}/track/{jid}", data={"status": "tailored"}, follow_redirects=False)
    assert r.status_code == 303


def test_applications_kanban_renders_drag_attributes(client: tuple[TestClient, Profile]) -> None:
    tc, prof = client
    jid = _seed(prof.db_path)
    transition_status(prof.db_path, jid, "tailored")
    r = tc.get(f"{PREFIX}/applications")
    assert r.status_code == 200
    assert 'draggable="true"' in r.text
    assert f'data-job-id="{jid}"' in r.text
    assert 'data-status="tailored"' in r.text
    # State graph must be embedded for client-side validation
    assert 'id="kanban-graph"' in r.text


def test_applications_move_valid_transition(client: tuple[TestClient, Profile]) -> None:
    from shortlist.store.db import get_application, list_jobs

    tc, prof = client
    jid = _seed(prof.db_path)
    transition_status(prof.db_path, jid, "tailored")

    r = tc.post(f"{PREFIX}/applications/move/{jid}", data={"status": "applied"})
    assert r.status_code == 200
    assert 'class="toast info"' in r.text

    job = next(j for j in list_jobs(prof.db_path) if j.id == jid)
    assert job.status == "applied"
    app_row = get_application(prof.db_path, jid)
    assert app_row is not None and app_row.applied_at is not None
    assert app_row.applied_via == "web"


def test_applications_move_invalid_transition(client: tuple[TestClient, Profile]) -> None:
    tc, prof = client
    jid = _seed(prof.db_path)
    transition_status(prof.db_path, jid, "tailored")
    # tailored → interview is not allowed
    r = tc.post(f"{PREFIX}/applications/move/{jid}", data={"status": "interview"})
    assert r.status_code == 400
    assert 'class="toast error"' in r.text


def test_applications_move_escapes_status_in_error(client: tuple[TestClient, Profile]) -> None:
    """The rejected status is echoed in the error toast; it must not render as markup."""
    tc, prof = client
    jid = _seed(prof.db_path)
    r = tc.post(f"{PREFIX}/applications/move/{jid}", data={"status": "<script>x</script>"})
    assert r.status_code == 400
    assert "<script>" not in r.text


def test_bare_path_redirects_to_active_profile(client: tuple[TestClient, Profile]) -> None:
    """A pre-profile bookmark still works: it is sent to the one active profile."""
    tc, prof = client
    r = tc.get("/applications?q=engineer", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == f"/p/{prof.slug}/applications?q=engineer"
