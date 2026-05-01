"""Integration tests for the shortlist_web FastAPI layer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist.models import RawJob
from shortlist.store.db import migrate, transition_status, update_score, upsert_job
from shortlist_web.app import create_app


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
def client(env: tuple[Path, Path]) -> TestClient:
    _cfg, data = env
    db = data / "db.sqlite"
    migrate(db)
    return TestClient(create_app())


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


def test_root_renders_empty(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Shortlist" in r.text


def test_root_lists_jobs(client: TestClient, env: tuple[Path, Path]) -> None:
    _cfg, data = env
    _seed(data / "db.sqlite", score=87)
    r = client.get("/")
    assert "Acme" in r.text
    assert "Senior Backend Engineer" in r.text
    assert "87" in r.text


def test_search_filter(client: TestClient, env: tuple[Path, Path]) -> None:
    _cfg, data = env
    _seed(data / "db.sqlite", "a", "Senior Backend Engineer")
    _seed(data / "db.sqlite", "b", "Frontend Engineer")
    r = client.get("/?q=frontend")
    assert "Frontend" in r.text
    assert "Backend" not in r.text


def test_job_detail(client: TestClient, env: tuple[Path, Path]) -> None:
    _cfg, data = env
    jid = _seed(data / "db.sqlite", score=80)
    r = client.get(f"/job/{jid}")
    assert r.status_code == 200
    assert "Senior Backend Engineer" in r.text


def test_job_detail_404(client: TestClient) -> None:
    assert client.get("/job/9999").status_code == 404


def test_applications_groups_by_status(client: TestClient, env: tuple[Path, Path]) -> None:
    _cfg, data = env
    jid = _seed(data / "db.sqlite")
    transition_status(data / "db.sqlite", jid, "tailored")
    r = client.get("/applications")
    assert "tailored" in r.text.lower()
    assert "Acme" in r.text


def test_settings_renders_when_config_missing(client: TestClient) -> None:
    r = client.get("/settings")
    assert r.status_code == 200
    assert "config" in r.text.lower()


def test_track_invalid_transition(client: TestClient, env: tuple[Path, Path]) -> None:
    _cfg, data = env
    jid = _seed(data / "db.sqlite")
    # new → interview is not a valid transition
    r = client.post(f"/track/{jid}", data={"status": "interview"})
    assert r.status_code == 400


def test_track_valid_transition(client: TestClient, env: tuple[Path, Path]) -> None:
    _cfg, data = env
    jid = _seed(data / "db.sqlite")
    r = client.post(f"/track/{jid}", data={"status": "tailored"}, follow_redirects=False)
    assert r.status_code == 303
