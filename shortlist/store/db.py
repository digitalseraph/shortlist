"""SQLite connection + migration runner for Shortlist.

Migrations live in `_migrations/NNN_*.sql`, applied in lexical order.
A `_schema_version` table records the highest applied migration number.
Every `migrate()` is idempotent.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from shortlist.models import Job, JobStatus, RawJob

_MIGRATIONS_DIR = Path(__file__).parent / "_migrations"
_VERSION_RE = re.compile(r"^(\d{3})_.*\.sql$")


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with WAL mode + FK enforcement."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER NOT NULL PRIMARY KEY)"
    )


def current_version(path: Path) -> int:
    with connect(path) as conn:
        _ensure_version_table(conn)
        row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM _schema_version").fetchone()
    return int(row[0])


def _discover_migrations() -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for p in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        m = _VERSION_RE.match(p.name)
        if not m:
            continue
        out.append((int(m.group(1)), p))
    return out


def migrate(path: Path) -> None:
    """Apply all pending migrations. Idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    applied = current_version(path)
    with connect(path) as conn:
        _ensure_version_table(conn)
        for version, mig_path in _discover_migrations():
            if version <= applied:
                continue
            conn.executescript(mig_path.read_text())
            conn.execute("INSERT INTO _schema_version (version) VALUES (?)", (version,))


# ---------------------------------------------------------------------------
# Job helpers
# ---------------------------------------------------------------------------


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_job(row: sqlite3.Row) -> Job:
    def _dt(val: str | None) -> datetime | None:
        if val is None:
            return None
        return datetime.fromisoformat(val.replace("Z", "+00:00"))

    return Job(
        id=row["id"],
        source=row["source"],
        external_id=row["external_id"],
        company=row["company"],
        title=row["title"],
        url=row["url"],
        posted_at=datetime.fromisoformat(row["posted_at"].replace("Z", "+00:00")),
        discovered_at=datetime.fromisoformat(row["discovered_at"].replace("Z", "+00:00")),
        location=row["location"],
        remote=bool(row["remote"]),
        comp_min=row["comp_min"],
        comp_max=row["comp_max"],
        description_md=row["description_md"],
        score=row["score"],
        score_reason=row["score_reason"],
        status=row["status"],
        status_changed_at=_dt(row["status_changed_at"]),
        scored_with_prefs_at=_dt(row["scored_with_prefs_at"]),
        scored_with_model=row["scored_with_model"],
    )


def upsert_job(path: Path, raw: RawJob, *, now: datetime | None = None) -> Job:
    """Insert or update a job by (source, external_id). Returns the persisted Job."""
    discovered = now or datetime.now(UTC)
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO jobs (source, external_id, company, title, url, posted_at,
                              discovered_at, location, remote, comp_min, comp_max,
                              description_md)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source, external_id) DO UPDATE SET
                company        = excluded.company,
                title          = excluded.title,
                url            = excluded.url,
                posted_at      = excluded.posted_at,
                location       = excluded.location,
                remote         = excluded.remote,
                comp_min       = excluded.comp_min,
                comp_max       = excluded.comp_max,
                description_md = excluded.description_md
            """,
            (
                raw.source,
                raw.external_id,
                raw.company,
                raw.title,
                str(raw.url),
                _utc_iso(raw.posted_at),
                _utc_iso(discovered),
                raw.location,
                int(raw.remote),
                raw.comp_min,
                raw.comp_max,
                raw.description_md,
            ),
        )
        row = conn.execute(
            "SELECT * FROM jobs WHERE source = ? AND external_id = ?",
            (raw.source, raw.external_id),
        ).fetchone()
    return _row_to_job(row)


def list_jobs(
    path: Path,
    *,
    status: JobStatus | None = None,
    min_score: int | None = None,
    limit: int | None = None,
) -> list[Job]:
    """Read jobs ordered by score DESC NULLS LAST, then discovered_at DESC."""
    sql = "SELECT * FROM jobs"
    clauses: list[str] = []
    params: list[object] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if min_score is not None:
        clauses.append("score >= ?")
        params.append(min_score)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY (score IS NULL), score DESC, discovered_at DESC"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_job(r) for r in rows]


# ---------------------------------------------------------------------------
# Source helpers
# ---------------------------------------------------------------------------


def mark_source_fetched(path: Path, name: str, when: datetime) -> None:
    """Record the last successful fetch time for a source."""
    with connect(path) as conn:
        conn.execute(
            """
            INSERT INTO sources (name, last_fetched_at) VALUES (?, ?)
            ON CONFLICT (name) DO UPDATE SET last_fetched_at = excluded.last_fetched_at,
                                             last_error = NULL
            """,
            (name, _utc_iso(when)),
        )


def source_last_fetched(path: Path, name: str) -> datetime | None:
    """Return the last fetch time for a source, or None if never fetched."""
    with connect(path) as conn:
        row = conn.execute("SELECT last_fetched_at FROM sources WHERE name = ?", (name,)).fetchone()
    if row is None or row[0] is None:
        return None
    return datetime.fromisoformat(row[0].replace("Z", "+00:00"))
