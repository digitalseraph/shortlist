"""Helpers shared across the web route modules."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from shortlist.store.db import transition_status, update_application


def get_env(request: Request) -> Environment:
    templates_dir: Path = request.app.state.templates_dir
    return Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)


def toast(request: Request, message: str, severity: str, *, code: int = 200) -> HTMLResponse:
    """Render the `#toast` partial. Autoescaping keeps user-supplied text inert."""
    html = get_env(request).get_template("_toast.html").render(message=message, severity=severity)
    return HTMLResponse(html, status_code=code)


def apply_status(db_path: Path, job_id: int, status: str) -> None:
    """Persist a status transition, stamping application metadata on ``applied``.

    Raises InvalidStatusTransitionError when the move is not allowed.
    """
    transition_status(db_path, job_id, status)  # type: ignore[arg-type]
    if status == "applied":
        update_application(
            db_path,
            job_id,
            applied_at=datetime.now(UTC),
            applied_via="web",
        )
