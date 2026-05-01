"""Background-task action endpoints: fetch, rank, tailor, status."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from shortlist import paths
from shortlist.config import load_config, load_prefs
from shortlist_tui.workers import fetch_all, rank_all, rerank_selected, tailor_one

router = APIRouter()

_LOG_MAX = 200


def _get_env(request: Request) -> Environment:
    templates_dir: Path = request.app.state.templates_dir
    return Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)


def _append_log(app: Any, entry: str) -> None:
    from datetime import datetime as _dt

    log: list[str] = app.state.task_log
    stamp = _dt.now().strftime("%H:%M:%S")
    log.append(f"[{stamp}] {entry}")
    if len(log) > _LOG_MAX:
        app.state.task_log = log[-_LOG_MAX:]


def _toast(request: Request, message: str, severity: str, *, code: int = 200) -> HTMLResponse:
    html = _get_env(request).get_template("_toast.html").render(message=message, severity=severity)
    return HTMLResponse(html, status_code=code)


# ---------------------------------------------------------------------------
# Background task wrappers — catch all exceptions, log result string
# ---------------------------------------------------------------------------


def _progress(app: Any) -> Any:
    """Build a progress callback that appends each message to the task log."""
    return lambda msg: _append_log(app, msg)


def _run_fetch(app: Any, db_path: Path, prefs: Any) -> None:
    try:
        result = fetch_all(db_path, prefs, progress=_progress(app))
        _append_log(app, f"fetch done: {result}")
    except Exception as exc:  # noqa: BLE001
        _append_log(app, f"fetch error: {exc}")


def _run_rank(app: Any, db_path: Path, cfg: Any, prefs: Any, resume: Path, client: Any) -> None:
    try:
        result = rank_all(
            db_path,
            cfg=cfg,
            prefs=prefs,
            resume_path=resume,
            anthropic_client=client,
            progress=_progress(app),
        )
        _append_log(app, f"rank done: {result}")
    except Exception as exc:  # noqa: BLE001
        _append_log(app, f"rank error: {exc}")


def _run_rerank_selected(
    app: Any,
    db_path: Path,
    job_ids: list[int],
    cfg: Any,
    prefs: Any,
    resume: Path,
    client: Any,
) -> None:
    try:
        result = rerank_selected(
            db_path,
            job_ids,
            cfg=cfg,
            prefs=prefs,
            resume_path=resume,
            anthropic_client=client,
            progress=_progress(app),
        )
        _append_log(app, f"rerank done: {result}")
    except Exception as exc:  # noqa: BLE001
        _append_log(app, f"rerank error: {exc}")


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
def rank(
    background: BackgroundTasks, request: Request, mode: str = "no-llm"
) -> HTMLResponse:
    """Run the ranking pipeline. mode='llm' uses Claude; 'no-llm' is cosine-only."""
    if mode not in ("llm", "no-llm"):
        return _toast(request, f"invalid mode: {mode}", "error", code=400)
    cfg = load_config(paths.config_path())
    prefs = load_prefs(paths.prefs_path())
    resume = cfg.paths.resume.expanduser()
    if not resume.exists():
        return _toast(request, f"resume not found at {resume}", "error", code=400)
    client = None
    if mode == "llm":
        key = os.environ.get(cfg.anthropic.key_env_var, "")
        if not key:
            return _toast(
                request, f"{cfg.anthropic.key_env_var} not set", "error", code=400
            )
        from anthropic import Anthropic

        client = Anthropic(api_key=key)
    background.add_task(_run_rank, request.app, paths.db_path(), cfg, prefs, resume, client)
    label = "rank started (LLM)" if client else "rank started (cosine only)"
    return _toast(request, label, "info")


@router.post("/rank/selected", response_class=HTMLResponse)
def rank_selected(
    background: BackgroundTasks,
    request: Request,
    job_ids: list[int] = Form(default=[]),
) -> HTMLResponse:
    """LLM-rerank the user's checkbox selection from the job list."""
    if not job_ids:
        return _toast(request, "no jobs selected", "error", code=400)
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
        _run_rerank_selected,
        request.app,
        paths.db_path(),
        list(job_ids),
        cfg,
        prefs,
        resume,
        Anthropic(api_key=key),
    )
    return _toast(request, f"reranking {len(job_ids)} job(s)…", "info")


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
        _get_env(request).get_template("_status.html").render(request=request, log=log[-25:][::-1])
    )
    return HTMLResponse(html)
