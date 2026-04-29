"""SQLite connection + migration runner for Shortlist.

Migrations live in `_migrations/NNN_*.sql`, applied in lexical order.
A `_schema_version` table records the highest applied migration number.
Every `migrate()` is idempotent.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import sqlite_vec  # type: ignore[import-untyped]

from shortlist.models import Application, Contact, Job, JobStatus, RawJob
from shortlist.tracker.state import validate_transition

_MIGRATIONS_DIR = Path(__file__).parent / "_migrations"
_VERSION_RE = re.compile(r"^(\d{3})_.*\.sql$")


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with sqlite-vec, WAL mode, and FK enforcement."""
    conn = sqlite3.connect(path)
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
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


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _row_to_job(row: sqlite3.Row) -> Job:
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
        status_changed_at=_parse_dt(row["status_changed_at"]),
        scored_with_prefs_at=_parse_dt(row["scored_with_prefs_at"]),
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


def update_score(
    path: Path,
    job_id: int,
    *,
    score: int,
    reason: str,
    model: str,
    when: datetime | None = None,
) -> None:
    """Update the score fields for a job."""
    when = when or datetime.now(UTC)
    with connect(path) as conn:
        conn.execute(
            """
            UPDATE jobs SET score = ?, score_reason = ?, scored_with_model = ?,
                            scored_with_prefs_at = ?
            WHERE id = ?
            """,
            (score, reason, model, _utc_iso(when), job_id),
        )


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


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------


def upsert_embedding(path: Path, job_id: int, vec: np.ndarray) -> None:
    """Store a 384-dim float32 embedding for a job, replacing any prior value."""
    if vec.dtype != np.float32:
        vec = vec.astype(np.float32)
    if vec.shape != (384,):
        raise ValueError(f"expected (384,) vector, got {vec.shape}")
    with connect(path) as conn:
        conn.execute("DELETE FROM job_embeddings WHERE job_id = ?", (job_id,))
        conn.execute(
            "INSERT INTO job_embeddings (job_id, embedding) VALUES (?, ?)",
            (job_id, vec.tobytes()),
        )


def get_embedding(path: Path, job_id: int) -> np.ndarray | None:
    """Return the stored embedding for a job, or None if not found."""
    with connect(path) as conn:
        row = conn.execute(
            "SELECT embedding FROM job_embeddings WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return np.frombuffer(row[0], dtype=np.float32).copy()


def cosine_top_k(path: Path, query: np.ndarray, *, k: int = 30) -> list[tuple[int, float]]:
    """Return up to k (job_id, distance) ordered by ascending vec0 distance.

    sqlite-vec uses L2 by default; on normalized vectors L2-rank == cosine-rank,
    so callers should normalize vectors at encode time.
    """
    if query.dtype != np.float32:
        query = query.astype(np.float32)
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT job_id, distance
            FROM job_embeddings
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
            """,
            (query.tobytes(), int(k)),
        ).fetchall()
    return [(int(r["job_id"]), float(r["distance"])) for r in rows]


# ---------------------------------------------------------------------------
# Application + tracker helpers
# ---------------------------------------------------------------------------


def transition_status(
    path: Path,
    job_id: int,
    target: JobStatus,
    *,
    when: datetime | None = None,
) -> None:
    """Validate and apply a status transition; record an event."""
    when = when or datetime.now(UTC)
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError(f"job {job_id} not found")
        current: JobStatus = row["status"]
        validate_transition(current, target)
        conn.execute(
            "UPDATE jobs SET status = ?, status_changed_at = ? WHERE id = ?",
            (target, _utc_iso(when), job_id),
        )
        conn.execute(
            "INSERT INTO events (job_id, type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (
                job_id,
                "status.transition",
                json.dumps({"from": current, "to": target}),
                _utc_iso(when),
            ),
        )


def update_application(path: Path, job_id: int, **fields: object) -> None:
    """Upsert the applications row for `job_id`. Only provided fields change."""
    if not fields:
        return
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    sets = ", ".join(f"{k} = excluded.{k}" for k in fields)
    values: list[object] = []
    for v in fields.values():
        if isinstance(v, datetime):
            values.append(_utc_iso(v))
        else:
            values.append(v)
    with connect(path) as conn:
        conn.execute(
            f"INSERT INTO applications (job_id, {cols}) VALUES (?, {placeholders}) "
            f"ON CONFLICT (job_id) DO UPDATE SET {sets}",
            (job_id, *values),
        )


def get_application(path: Path, job_id: int) -> Application | None:
    """Return the application row for `job_id`, or None if not present."""
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return Application(
        job_id=row["job_id"],
        applied_at=_parse_dt(row["applied_at"]),
        applied_via=row["applied_via"],
        follow_up_due=_parse_dt(row["follow_up_due"]),
        salary_offered=row["salary_offered"],
        decision=row["decision"],
        decision_reason=row["decision_reason"],
        lessons=row["lessons"],
    )


def add_contact(
    path: Path,
    application_id: int,
    *,
    name: str,
    email: str | None = None,
    role: str | None = None,
    source: str | None = None,
    when: datetime | None = None,
) -> int:
    """Insert a contact row, returning the new id."""
    when = when or datetime.now(UTC)
    with connect(path) as conn:
        cursor = conn.execute(
            "INSERT INTO contacts (application_id, name, email, role, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (application_id, name, email, role, source, _utc_iso(when)),
        )
        return int(cursor.lastrowid or 0)


def list_contacts(path: Path, application_id: int) -> list[Contact]:
    """Return contacts for an application, oldest first."""
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM contacts WHERE application_id = ? ORDER BY created_at",
            (application_id,),
        ).fetchall()
    return [
        Contact(
            id=r["id"],
            application_id=r["application_id"],
            name=r["name"],
            email=r["email"],
            role=r["role"],
            source=r["source"],
            created_at=_parse_dt(r["created_at"]) or datetime.now(UTC),
        )
        for r in rows
    ]


def remove_contact(path: Path, contact_id: int) -> None:
    """Delete a contact by id."""
    with connect(path) as conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def log_event(
    path: Path,
    *,
    job_id: int | None,
    type: str,  # noqa: A002 - matches column name
    payload: dict[str, object] | None = None,
    cost_usd: float | None = None,
    tokens: int | None = None,
    when: datetime | None = None,
) -> None:
    """Record an event row tied to a job (or global if job_id is None)."""
    when = when or datetime.now(UTC)
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO events (job_id, type, payload_json, cost_usd, tokens, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, type, json.dumps(payload or {}), cost_usd, tokens, _utc_iso(when)),
        )


# ---------------------------------------------------------------------------
# Cooldown helpers
# ---------------------------------------------------------------------------


def mark_source_cooldown(path: Path, name: str, *, until: datetime) -> None:
    """Set the cooldown_until timestamp for a source."""
    with connect(path) as conn:
        conn.execute(
            """
            INSERT INTO sources (name, cooldown_until) VALUES (?, ?)
            ON CONFLICT (name) DO UPDATE SET cooldown_until = excluded.cooldown_until
            """,
            (name, _utc_iso(until)),
        )


def is_source_in_cooldown(path: Path, name: str, *, now: datetime | None = None) -> bool:
    """Return True if the source is currently cooled down."""
    now = now or datetime.now(UTC)
    with connect(path) as conn:
        row = conn.execute("SELECT cooldown_until FROM sources WHERE name = ?", (name,)).fetchone()
    if row is None or row[0] is None:
        return False
    until = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
    return now < until


def clear_source_cooldown(path: Path, name: str) -> None:
    """Reset cooldown_until for a source."""
    with connect(path) as conn:
        conn.execute("UPDATE sources SET cooldown_until = NULL WHERE name = ?", (name,))
