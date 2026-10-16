"""FastAPI application factory for the Shortlist web layer."""

from __future__ import annotations

import importlib.resources as _ir
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, Response

from shortlist import profiles
from shortlist_web.routes import actions, applications, costs, jobs, resume, settings
from shortlist_web.routes import places as places_router
from shortlist_web.routes import profiles as profiles_router

# Pages that existed before profiles were URL-scoped. A request for one of
# these bare paths is sent to the active profile's version instead of 404ing.
_BARE_PATHS = ("/", "/applications", "/costs", "/settings", "/resume")


def create_app() -> FastAPI:
    """Return a fresh FastAPI instance — call once per process (or test)."""
    app = FastAPI(title="Shortlist", docs_url=None, redoc_url=None)

    # In-memory task log; capped in routes/actions.py
    app.state.task_log = []

    # Resolve bundled template + static directories via importlib.resources
    pkg = _ir.files("shortlist_web")
    templates_dir = Path(str(pkg / "templates"))
    static_dir = Path(str(pkg / "static"))

    # Make resolved paths available to routes
    app.state.templates_dir = templates_dir
    app.state.static_dir = static_dir

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.middleware("http")
    async def _redirect_bare_paths(request: Request, call_next: Any) -> Response:
        """Send unprefixed page requests to the active profile, or to first-run setup."""
        path = request.url.path
        if path not in _BARE_PATHS:
            # call_next is typed Any (its real type lives in starlette.middleware.base
            # and varies across versions); cast narrows it back to our declared return type.
            return cast(Response, await call_next(request))
        try:
            active = profiles.resolve()
        except profiles.AmbiguousProfileError:
            # Several profiles exist and nothing (yet) says which one - let
            # the person pick, rather than sending them to create a new one.
            return RedirectResponse("/profiles", status_code=307)
        except profiles.ProfileError:
            # No profiles exist at all - this is the actual first-run case.
            return RedirectResponse("/profiles/new", status_code=307)
        # "/" itself needs the trailing slash — job_list is registered at
        # "/p/{slug}/", and a bare "/p/{slug}" would just trigger a second,
        # Starlette-issued redirect to add it back.
        suffix = "/" if path == "/" else path
        target = f"/p/{active.slug}{suffix}"
        if request.url.query:
            target = f"{target}?{request.url.query}"
        return RedirectResponse(target, status_code=307)

    # profiles.router is unprefixed: it exists precisely for when there is no
    # active profile.
    app.include_router(profiles_router.router)
    # Place suggestions are the same for everyone, so not profile-scoped either.
    app.include_router(places_router.router)
    for router in (
        jobs.router,
        applications.router,
        costs.router,
        actions.router,
        resume.router,
        settings.router,
    ):
        app.include_router(router, prefix="/p/{slug}")

    return app
