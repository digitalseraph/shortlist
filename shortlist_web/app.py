"""FastAPI application factory for the Shortlist web layer."""

from __future__ import annotations

import importlib.resources as _ir
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from shortlist_web.routes import actions, applications, costs, jobs, settings


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

    app.include_router(jobs.router)
    app.include_router(applications.router)
    app.include_router(costs.router)
    app.include_router(settings.router)
    app.include_router(actions.router)

    return app
