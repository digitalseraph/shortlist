"""Helpers shared across the web route modules."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from shortlist import profiles, state
from shortlist.profiles import Profile
from shortlist.store.db import transition_status, update_application


def get_env(request: Request) -> Environment:
    templates_dir: Path = request.app.state.templates_dir
    return Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)


def toast(request: Request, message: str, severity: str, *, code: int = 200) -> HTMLResponse:
    """Render the `#toast` partial. Autoescaping keeps user-supplied text inert."""
    html = get_env(request).get_template("_toast.html").render(message=message, severity=severity)
    return HTMLResponse(html, status_code=code)


def profile_dep(slug: str) -> Profile:
    """Resolve the `{slug}` path parameter, 404ing rather than falling back.

    A stale or mistyped link must never act on a different person's data. A
    malformed slug (``load`` -> ``profile_dirs`` -> ``validate_slug``, which
    raises ``InvalidSlugError`` before any not-found check runs) is just as
    unknown as a well-formed absent one, so every ``ProfileError`` — not only
    ``ProfileNotFoundError`` — 404s here instead of propagating as a 500.

    Also records `slug` as the last-*used* profile — every page view resolves
    through here, which is the whole point: "most recently used", not "most
    recently created". Read before write so a normal page view does not
    rewrite state.yaml on every request, only on an actual switch.
    """
    try:
        prof = profiles.load(slug)
    except profiles.ProfileError as exc:
        raise HTTPException(status_code=404, detail=f"no profile {slug!r}") from exc
    if state.get_last_profile() != prof.slug:
        state.set_last_profile(prof.slug)
    return prof


def switch_suffix(request: Request, profile: Profile) -> str:
    """The part of the current path after `/p/<slug>`, for the profile switcher.

    Switching rewrites the slug in the current path rather than always
    landing on the job list, so you stay on the same page for a different
    person. Falls back to "/" (that profile's job list) when the current
    path cannot be mapped cleanly - e.g. it does not start with this
    profile's own prefix.
    """
    prefix = f"/p/{profile.slug}"
    path = request.url.path
    if path == prefix:
        return "/"
    if path.startswith(prefix + "/"):
        return path[len(prefix) :]
    return "/"


def page_context(request: Request, profile: Profile, **extra: object) -> dict[str, object]:
    """Common template variables for any profile-scoped page.

    Calls `list_profiles()` fresh on every render rather than caching it -
    each call re-walks (and, via `load()`, repairs) every profile on disk.
    Deliberate, per the design spec's "repair, don't hide": a profile fixed
    up by hand between requests should show up fixed on the very next page
    view, not after a server restart.
    """
    return {
        "request": request,
        "active": profile,
        "all_profiles": profiles.list_profiles(),
        "switch_suffix": switch_suffix(request, profile),
        **extra,
    }


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
