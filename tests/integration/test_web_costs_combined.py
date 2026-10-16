"""The cost page shows this profile plus a combined total across everyone."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist_web.app import create_app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def _add_cost(db: Path, usd: float) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO scoring_runs (started_at, model, job_count, cost_usd) "
            "VALUES ('2026-10-13T00:00:00+00:00', 'claude-haiku-4-5', 1, ?)",
            (usd,),
        )


def test_combined_total_sums_every_profile(client: TestClient) -> None:
    david = profiles.create("david", "David")
    alex = profiles.create("alex", "Alex")
    _add_cost(david.db_path, 1.25)
    _add_cost(alex.db_path, 2.50)
    r = client.get("/p/david/costs")
    assert r.status_code == 200
    assert "3.75" in r.text
    assert "Alex" in r.text


def test_costs_page_works_with_one_profile(client: TestClient) -> None:
    david = profiles.create("david", "David")
    _add_cost(david.db_path, 0.40)
    r = client.get("/p/david/costs")
    assert "0.40" in r.text
