"""Read-only TUI data adapters over shortlist.store.

The TUI only consumes these. Writes go through shortlist_tui.workers
(which call the underlying lib) — never directly via SQL from screens.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shortlist.models import JobStatus
from shortlist.store import db as store_db


@dataclass(frozen=True)
class JobRow:
    """View-friendly job for table display."""

    id: int
    score: int | None
    company: str
    title: str
    location: str
    status: JobStatus
    url: str

    @property
    def score_display(self) -> str:
        return "—" if self.score is None else str(self.score)

    @property
    def status_display(self) -> str:
        return self.status


def list_job_rows(
    db_path: Path,
    *,
    status: JobStatus | None = None,
    min_score: int | None = None,
    limit: int | None = None,
) -> list[JobRow]:
    jobs = store_db.list_jobs(db_path, status=status, min_score=min_score, limit=limit)
    return [
        JobRow(
            id=j.id,
            score=j.score,
            company=j.company,
            title=j.title,
            location=j.location or "",
            status=j.status,
            url=str(j.url),
        )
        for j in jobs
    ]
