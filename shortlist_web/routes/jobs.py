"""Job listing, detail, and status tracking routes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from starlette.responses import Response

from shortlist import paths
from shortlist.store import db as store_db
from shortlist.store.db import transition_status, update_application
from shortlist.tracker.state import InvalidStatusTransitionError, allowed_next
from shortlist_tui.data import JobRow, list_job_rows

router = APIRouter()


def _get_env(request: Request) -> Environment:
    templates_dir: Path = request.app.state.templates_dir
    return Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)


def _load_tailor_dir(db_path: Path, job_id: int) -> Path | None:
    """Return the tailor output directory for a job, or None if not recorded."""
    with store_db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT output_dir FROM tailor_outputs WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return Path(row[0])


_SORT_KEYS: dict[str, Callable[[JobRow], Any]] = {
    "score": lambda r: (r.score is None, r.score or 0),
    "company": lambda r: r.company.lower(),
    "title": lambda r: r.title.lower(),
    "location": lambda r: (r.location or "").lower(),
    "comp": lambda r: r.comp_max or r.comp_min or 0,
    "status": lambda r: r.status,
    "posted": lambda r: (r.posted_at is None, r.posted_at or datetime.min.replace(tzinfo=UTC)),
}


def _sort_rows(rows: list[JobRow], sort: str, direction: str) -> list[JobRow]:
    key_fn = _SORT_KEYS.get(sort, _SORT_KEYS["score"])
    reverse = direction == "desc"
    return sorted(rows, key=key_fn, reverse=reverse)


_MAX_AGE_CHOICES = (7, 30, 90, 365, 0)  # 0 = "all"


@router.get("/", response_class=HTMLResponse)
def job_list(
    request: Request,
    q: str | None = None,
    min_score: int = 0,
    max_age_days: int = 365,
    sort: str = "score",
    dir: str = "desc",  # noqa: A002 — matches HTMX query name
) -> HTMLResponse:
    if sort not in _SORT_KEYS:
        sort = "score"
    if dir not in ("asc", "desc"):
        dir = "desc"
    if max_age_days not in _MAX_AGE_CHOICES:
        max_age_days = 365
    rows = list_job_rows(
        paths.db_path(),
        min_score=min_score if min_score else None,
        max_age_days=max_age_days if max_age_days else None,
    )
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r.company.lower() or ql in r.title.lower()]
    rows = _sort_rows(rows, sort, dir)
    ctx = {
        "request": request,
        "rows": rows,
        "q": q or "",
        "min_score": min_score,
        "max_age_days": max_age_days,
        "max_age_choices": _MAX_AGE_CHOICES,
        "sort": sort,
        "dir": dir,
    }
    # HTMX swaps target #joblist-wrap (sort clicks) or #job-tbody (filter inputs).
    # Filter inputs use hx-target="#job-tbody" and request just rows; sort
    # links target the wrap and request the full table.
    htmx_target = request.headers.get("HX-Target", "")
    if htmx_target == "job-tbody":
        template = "_joblist_rows.html"
    elif request.headers.get("HX-Request"):
        template = "_joblist_table.html"
    else:
        template = "job_list.html"
    html = _get_env(request).get_template(template).render(**ctx)
    return HTMLResponse(html)


@router.get("/job/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: int) -> HTMLResponse:
    jobs = [j for j in store_db.list_jobs(paths.db_path()) if j.id == job_id]
    if not jobs:
        raise HTTPException(404, "job not found")
    job = jobs[0]
    out_dir = _load_tailor_dir(paths.db_path(), job_id)
    materials: dict[str, str | None] = {}
    if out_dir and out_dir.exists():
        for stem in ("resume", "cover", "notes"):
            f = out_dir / f"{stem}.md"
            materials[stem] = f.read_text() if f.exists() else None
    html = (
        _get_env(request)
        .get_template("job_detail.html")
        .render(
            request=request,
            job=job,
            materials=materials,
            allowed_next=sorted(allowed_next(job.status)),
        )
    )
    return HTMLResponse(html)


@router.post("/track/{job_id}", response_class=HTMLResponse, response_model=None)
def track_status(request: Request, job_id: int, status: str = Form(...)) -> Response:
    try:
        transition_status(paths.db_path(), job_id, status)  # type: ignore[arg-type]
        if status == "applied":
            update_application(
                paths.db_path(),
                job_id,
                applied_at=datetime.now(UTC),
                applied_via="web",
            )
    except InvalidStatusTransitionError as e:
        return HTMLResponse(f'<div class="error">{e}</div>', status_code=400)
    return RedirectResponse(f"/job/{job_id}", status_code=303)
