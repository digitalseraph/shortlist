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
from pathlib import Path

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
