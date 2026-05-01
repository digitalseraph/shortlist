"""Background-task action endpoints: fetch, rank, tailor, status."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from shortlist import paths
from shortlist.config import load_config, load_prefs
from shortlist_tui.workers import fetch_all, rank_all, tailor_one

router = APIRouter()

_LOG_MAX = 50


def _get_env(request: Request) -> Environment:
    templates_dir: Path = request.app.state.templates_dir
    return Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)


def _append_log(app: Any, entry: str) -> None:
    log: list[str] = app.state.task_log
    log.append(entry)
    if len(log) > _LOG_MAX:
        app.state.task_log = log[-_LOG_MAX:]


def _toast(request: Request, message: str, severity: str, *, code: int = 200) -> HTMLResponse:
    html = _get_env(request).get_template("_toast.html").render(message=message, severity=severity)
    return HTMLResponse(html, status_code=code)


# ---------------------------------------------------------------------------
# Background task wrappers — catch all exceptions, log result string
# ---------------------------------------------------------------------------


def _run_fetch(app: Any, db_path: Path, prefs: Any) -> None:
    try:
        result = fetch_all(db_path, prefs)
        _append_log(app, f"fetch: {result}")
    except Exception as exc:  # noqa: BLE001
        _append_log(app, f"fetch error: {exc}")


def _run_rank(app: Any, db_path: Path, cfg: Any, prefs: Any, resume: Path, client: Any) -> None:
    try:
        result = rank_all(
            db_path, cfg=cfg, prefs=prefs, resume_path=resume, anthropic_client=client
        )
        _append_log(app, f"rank: {result}")
    except Exception as exc:  # noqa: BLE001
        _append_log(app, f"rank error: {exc}")


def _run_tailor(
    app: Any, db_path: Path, job_id: int, cfg: Any, prefs: Any, resume: Path, client: Any
) -> None:
    try:
        result = tailor_one(
            db_path, job_id, cfg=cfg, prefs=prefs, resume_path=resume, anthropic_client=client
        )
        _append_log(app, f"tailor {job_id}: {result}")
    except Exception as exc:  # noqa: BLE001
        _append_log(app, f"tailor {job_id} error: {exc}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/fetch", response_class=HTMLResponse)
def fetch(background: BackgroundTasks, request: Request) -> HTMLResponse:
    prefs = load_prefs(paths.prefs_path())
    background.add_task(_run_fetch, request.app, paths.db_path(), prefs)
    return _toast(request, "fetch started", "info")


@router.post("/rank", response_class=HTMLResponse)
def rank(background: BackgroundTasks, request: Request) -> HTMLResponse:
    cfg = load_config(paths.config_path())
    prefs = load_prefs(paths.prefs_path())
    resume = cfg.paths.resume.expanduser()
    if not resume.exists():
        return _toast(request, f"resume not found at {resume}", "error", code=400)
    key = os.environ.get(cfg.anthropic.key_env_var, "")
    client = None
    if key:
        from anthropic import Anthropic

        client = Anthropic(api_key=key)
    background.add_task(_run_rank, request.app, paths.db_path(), cfg, prefs, resume, client)
    return _toast(request, "rank started" + (" (no LLM)" if client is None else ""), "info")


@router.post("/tailor/{job_id}", response_class=HTMLResponse)
def tailor(job_id: int, background: BackgroundTasks, request: Request) -> HTMLResponse:
    cfg = load_config(paths.config_path())
    prefs = load_prefs(paths.prefs_path())
    resume = cfg.paths.resume.expanduser()
    if not resume.exists():
        return _toast(request, f"resume not found at {resume}", "error", code=400)
    key = os.environ.get(cfg.anthropic.key_env_var, "")
    if not key:
        return _toast(request, f"{cfg.anthropic.key_env_var} not set", "error", code=400)
    from anthropic import Anthropic

    background.add_task(
        _run_tailor,
        request.app,
        paths.db_path(),
        job_id,
        cfg,
        prefs,
        resume,
        Anthropic(api_key=key),
    )
    return _toast(request, f"tailoring job {job_id}…", "info")


@router.get("/status", response_class=HTMLResponse)
def status(request: Request) -> HTMLResponse:
    """HTMX-polled status feed."""
    log = list(getattr(request.app.state, "task_log", []))
    html = (
        _get_env(request).get_template("_status.html").render(request=request, log=log[-10:][::-1])
    )
    return HTMLResponse(html)
