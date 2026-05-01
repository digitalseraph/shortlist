"""Read-only TUI data adapters over shortlist.store.

The TUI only consumes these. Writes go through shortlist_tui.workers
(which call the underlying lib) — never directly via SQL from screens.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shortlist.models import JobStatus
from shortlist.store import db as store_db


def _format_comp(comp_min: int | None, comp_max: int | None) -> str:
    """Render salary/hourly range. Amounts under 1000 treated as hourly."""

    def one(n: int) -> str:
        if n < 1000:
            return f"${n}/hr"
        if n % 1000 == 0:
            return f"${n // 1000}k"
        return f"${n / 1000:.1f}k"

    if comp_min is None and comp_max is None:
        return "—"
    if comp_min is not None and comp_max is not None and comp_min != comp_max:
        left = one(comp_min).replace("/hr", "")
        right = one(comp_max).lstrip("$").replace("/hr", "")
        suffix = "/hr" if comp_max < 1000 else ""
        return f"{left}–{right}{suffix}"
    val = comp_max if comp_max is not None else comp_min
    return one(val) if val is not None else "—"


def _format_posted(posted_at: datetime | None) -> str:
    """Render relative posted age: today / Nd / Nw / Nmo / Ny."""
    if posted_at is None:
        return "—"
    delta = datetime.now(UTC) - posted_at
    days = delta.days
    if days < 1:
        return "today"
    if days < 7:
        return f"{days}d"
    if days < 30:
        return f"{days // 7}w"
    if days < 365:
        return f"{days // 30}mo"
    return f"{days // 365}y"


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
    comp_min: int | None = None
    comp_max: int | None = None
    posted_at: datetime | None = None

    @property
    def score_display(self) -> str:
        return "—" if self.score is None else str(self.score)

    @property
    def status_display(self) -> str:
        return self.status

    @property
    def comp_display(self) -> str:
        return _format_comp(self.comp_min, self.comp_max)

    @property
    def posted_display(self) -> str:
        return _format_posted(self.posted_at)


def list_job_rows(
    db_path: Path,
    *,
    status: JobStatus | None = None,
    min_score: int | None = None,
    max_age_days: int | None = None,
    limit: int | None = None,
) -> list[JobRow]:
    jobs = store_db.list_jobs(
        db_path,
        status=status,
        min_score=min_score,
        max_age_days=max_age_days,
        limit=limit,
    )
    return [
        JobRow(
            id=j.id,
            score=j.score,
            company=j.company,
            title=j.title,
            location=j.location or "",
            status=j.status,
            url=str(j.url),
            comp_min=j.comp_min,
            comp_max=j.comp_max,
            posted_at=j.posted_at,
        )
        for j in jobs
    ]
