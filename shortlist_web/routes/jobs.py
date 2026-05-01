"""Job listing, detail, and status tracking routes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response
from jinja2 import Environment, FileSystemLoader

from shortlist import paths
from shortlist.store import db as store_db
from shortlist.store.db import transition_status, update_application
from shortlist.tracker.state import InvalidStatusTransitionError, allowed_next
from shortlist_tui.data import list_job_rows

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


@router.get("/", response_class=HTMLResponse)
def job_list(request: Request, q: str | None = None, min_score: int = 0) -> HTMLResponse:
    rows = list_job_rows(paths.db_path(), min_score=min_score if min_score else None)
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r.company.lower() or ql in r.title.lower()]
    html = (
        _get_env(request)
        .get_template("job_list.html")
        .render(request=request, rows=rows, q=q or "", min_score=min_score)
    )
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
