from pathlib import Path

import pytest

from shortlist.store.db import (
    connect,
    current_version,
    migrate,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "shortlist.sqlite"


def test_migrate_from_zero_to_latest(db_path: Path):
    migrate(db_path)
    assert current_version(db_path) == 1


def test_migrate_is_idempotent(db_path: Path):
    migrate(db_path)
    migrate(db_path)
    migrate(db_path)
    assert current_version(db_path) == 1


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
