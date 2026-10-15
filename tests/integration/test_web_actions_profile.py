"""Background work is pinned to the profile that enqueued it."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist.store import db as store_db
from shortlist_web.app import create_app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def test_status_feed_only_shows_this_profile(client: TestClient) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    client.app.state.task_log = [
        ("david", "10:00:00", "fetch done: 3 jobs"),
        ("alex", "10:00:01", "fetch done: 7 jobs"),
    ]
    mine = client.get("/p/david/status")
    assert "3 jobs" in mine.text
    assert "7 jobs" not in mine.text


def test_purge_acts_on_the_url_profile(client: TestClient) -> None:
    david = profiles.create("david", "David")
    profiles.create("alex", "Alex")
    r = client.post("/p/alex/jobs/purge-untailored")
    assert r.status_code == 200
    assert client.app.state.task_log[-1][0] == "alex"
    assert david.db_path.exists()


def test_fetch_writes_to_the_url_profile_not_the_env_active_one(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fetch enqueued for `david` must write to david's database even when
    something else (here: $SHORTLIST_PROFILE) claims a different profile is
    'active' by the time the background task actually runs. The handler must
    capture david's db_path/slug at enqueue time and the `_run_fetch` wrapper
    must use exactly that — never re-resolve a profile from ambient state.
    """
    david = profiles.create("david", "David")
    alex = profiles.create("alex", "Alex")

    def fake_fetch_all(db_path: Path, prefs: object, *, progress: object = None) -> str:
        # Prove which db this background run actually touched.
        store_db.mark_source_fetched(db_path, "fake", datetime.now(UTC))
        return "fetched 1"

    monkeypatch.setattr("shortlist_web.routes.actions.fetch_all", fake_fetch_all)
    # Simulate a profile switch that happens before the background task runs:
    # whatever resolve()-based logic would see "alex" as active right now.
    monkeypatch.setenv("SHORTLIST_PROFILE", "alex")

    r = client.post("/p/david/fetch")

    assert r.status_code == 200
    assert store_db.source_last_fetched(david.db_path, "fake") is not None
    assert store_db.source_last_fetched(alex.db_path, "fake") is None
    assert client.app.state.task_log[-1][0] == "david"
