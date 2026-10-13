"""Profile creation, switching and deletion. These routes are not profile-scoped."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from shortlist import profiles, state
from shortlist_web.routes._shared import get_env, toast

router = APIRouter()


@router.get("/profiles/new", response_class=HTMLResponse)
def new_profile_form(request: Request) -> HTMLResponse:
    html = get_env(request).get_template("profiles_new.html").render(request=request)
    return HTMLResponse(html)


@router.get("/profiles", response_class=HTMLResponse)
def list_profiles_view(request: Request) -> HTMLResponse:
    html = (
        get_env(request)
        .get_template("profiles_list.html")
        .render(request=request, profiles=profiles.list_profiles())
    )
    return HTMLResponse(html)


@router.post("/profiles", response_class=HTMLResponse, response_model=None)
def create_profile(
    request: Request, slug: str = Form(...), display_name: str = Form(...)
) -> Response:
    try:
        prof = profiles.create(slug, display_name)
    except profiles.ProfileError as exc:
        return toast(request, str(exc), "error", code=400)
    state.set_last_profile(prof.slug)
    return RedirectResponse(f"/p/{prof.slug}/", status_code=303)


@router.post("/profiles/{slug}/delete", response_class=HTMLResponse, response_model=None)
def delete_profile(request: Request, slug: str, confirm: str = Form(...)) -> Response:
    """Delete a profile. The typed display name is the confirmation."""
    try:
        prof = profiles.load(slug)
    except profiles.ProfileNotFoundError as exc:
        return toast(request, str(exc), "error", code=404)
    if confirm.strip() != prof.display_name:
        return toast(request, "type the display name exactly to confirm", "error", code=400)
    profiles.delete(slug)
    return RedirectResponse("/profiles", status_code=303)
