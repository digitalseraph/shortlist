"""Applications kanban route."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from shortlist import paths
from shortlist_tui.data import list_job_rows

router = APIRouter()

_COLUMNS = ("tailored", "applied", "screen", "interview", "offer", "rejected")


def _get_env(request: Request) -> Environment:
    templates_dir: Path = request.app.state.templates_dir
    return Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)


@router.get("/applications", response_class=HTMLResponse)
def applications(request: Request) -> HTMLResponse:
    by_status = {s: list_job_rows(paths.db_path(), status=s) for s in _COLUMNS}  # type: ignore[arg-type]
    html = (
        _get_env(request)
        .get_template("applications.html")
        .render(request=request, columns=_COLUMNS, by_status=by_status)
    )
    return HTMLResponse(html)
