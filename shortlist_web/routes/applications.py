"""Applications kanban route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from shortlist.profiles import Profile
from shortlist.tracker.state import InvalidStatusTransitionError, allowed_next
from shortlist_tui.data import list_job_rows
from shortlist_web.routes._shared import apply_status, get_env, page_context, profile_dep, toast

router = APIRouter()

_COLUMNS = ("tailored", "applied", "screen", "interview", "offer", "rejected")


def _allowed_graph() -> dict[str, list[str]]:
    """Status → allowed next statuses, JSON-serializable for the kanban client."""
    sources = (*_COLUMNS, "new")
    return {s: sorted(allowed_next(s)) for s in sources}  # type: ignore[arg-type]


@router.get("/applications", response_class=HTMLResponse)
def applications(request: Request, profile: Profile = Depends(profile_dep)) -> HTMLResponse:
    by_status = {s: list_job_rows(profile.db_path, status=s) for s in _COLUMNS}  # type: ignore[arg-type]
    html = (
        get_env(request)
        .get_template("applications.html")
        .render(
            **page_context(
                request,
                profile,
                columns=_COLUMNS,
                by_status=by_status,
                allowed=_allowed_graph(),
            )
        )
    )
    return HTMLResponse(html)


@router.post(
    "/applications/move/{job_id}",
    response_class=HTMLResponse,
    response_model=None,
)
def move_application(
    request: Request,
    job_id: int,
    status: str = Form(...),
    profile: Profile = Depends(profile_dep),
) -> HTMLResponse:
    """Drag-and-drop move: validate transition + persist. Returns toast HTML.

    A job id that is not in this profile's database is just as much "not
    found" as one that never existed, so it 404s rather than 500ing —
    ``transition_status`` raises a plain ValueError for a missing row, and
    InvalidStatusTransitionError (a ValueError subclass) for a disallowed
    one, so the more specific case is caught first.
    """
    try:
        apply_status(profile.db_path, job_id, status)
    except InvalidStatusTransitionError as e:
        return toast(request, str(e), "error", code=400)
    except ValueError as e:
        return toast(request, str(e), "error", code=404)
    return toast(request, f"moved to {status}", "info")
