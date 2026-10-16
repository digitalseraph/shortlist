"""Background-task action endpoints: fetch, rank, tailor, status."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse

from shortlist import paths
from shortlist.config import Config, load_config, load_prefs
from shortlist.profiles import Profile
from shortlist.store import db as store_db
from shortlist_tui.workers import fetch_all, rank_all, rerank_selected, tailor_one
from shortlist_web.routes._shared import get_env, profile_dep, toast

router = APIRouter()

_LOG_MAX = 200


def _append_log(app: Any, slug: str, entry: str) -> None:
    """Append a task-log line tagged with the profile that caused it."""
    from datetime import datetime as _dt

    log: list[tuple[str, str, str]] = app.state.task_log
    stamp = _dt.now().strftime("%H:%M:%S")
    log.append((slug, stamp, entry))
    if len(log) > _LOG_MAX:
        app.state.task_log = log[-_LOG_MAX:]


# ---------------------------------------------------------------------------
# Background task wrappers — catch all exceptions, log result string
#
# Every wrapper below takes its profile's `slug`/`db_path`/etc. as plain
# arguments captured by the request handler at enqueue time. None of them may
# re-resolve a profile (e.g. via `profiles.resolve()`) once running: the
# active profile can change between enqueue and execution, and a background
# task must always finish against the person it started for.
# ---------------------------------------------------------------------------


def _progress(app: Any, slug: str) -> Any:
    """Build a progress callback that tags each message with the profile."""
    return lambda msg: _append_log(app, slug, msg)


def _run_fetch(app: Any, slug: str, db_path: Path, prefs: Any) -> None:
    try:
        result = fetch_all(db_path, prefs, progress=_progress(app, slug))
        _append_log(app, slug, f"fetch done: {result}")
    except Exception as exc:  # noqa: BLE001
        _append_log(app, slug, f"fetch error: {exc}")


def _run_rank(
    app: Any, slug: str, db_path: Path, cfg: Any, prefs: Any, resume: Path, client: Any
) -> None:
    try:
        result = rank_all(
            db_path,
            cfg=cfg,
            prefs=prefs,
            resume_path=resume,
            anthropic_client=client,
            progress=_progress(app, slug),
        )
        _append_log(app, slug, f"rank done: {result}")
    except Exception as exc:  # noqa: BLE001
        _append_log(app, slug, f"rank error: {exc}")


def _run_rerank_selected(
    app: Any,
    slug: str,
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
            progress=_progress(app, slug),
        )
        _append_log(app, slug, f"rerank done: {result}")
    except Exception as exc:  # noqa: BLE001
        _append_log(app, slug, f"rerank error: {exc}")


def _run_tailor(
    app: Any,
    slug: str,
    db_path: Path,
    job_id: int,
    cfg: Any,
    prefs: Any,
    resume: Path,
    output_root: Path,
    client: Any,
) -> None:
    try:
        result = tailor_one(
            db_path,
            job_id,
            cfg=cfg,
            prefs=prefs,
            resume_path=resume,
            output_root=output_root,
            anthropic_client=client,
        )
        _append_log(app, slug, f"tailor {job_id}: {result}")
    except Exception as exc:  # noqa: BLE001
        _append_log(app, slug, f"tailor {job_id} error: {exc}")


def _config_or_toast(request: Request) -> Config | HTMLResponse:
    """Load the shared config.yaml, or a 400 toast naming how to create it.

    A fresh install created entirely through the web UI has no config.yaml
    yet; `load_config` would raise FileNotFoundError and surface as a bare
    500. The CLI guards this same gap with "run `shortlist config init`
    first" (cli.py) — this is the web equivalent.
    """
    cfg_path = paths.config_path()
    if not cfg_path.exists():
        return toast(
            request,
            f"{cfg_path} not found — create it from Settings, or run `shortlist config init`",
            "error",
            code=400,
        )
    return load_config(cfg_path)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/fetch", response_class=HTMLResponse)
def fetch(
    background: BackgroundTasks,
    request: Request,
    profile: Profile = Depends(profile_dep),
) -> HTMLResponse:
    prefs = load_prefs(profile.prefs_path)
    background.add_task(_run_fetch, request.app, profile.slug, profile.db_path, prefs)
    return toast(request, "fetch started", "info")


@router.post("/rank", response_class=HTMLResponse)
def rank(
    background: BackgroundTasks,
    request: Request,
    mode: str = "no-llm",
    profile: Profile = Depends(profile_dep),
) -> HTMLResponse:
    """Run the ranking pipeline. mode='llm' uses Claude; 'no-llm' is cosine-only."""
    if mode not in ("llm", "no-llm"):
        return toast(request, f"invalid mode: {mode}", "error", code=400)
    cfg = _config_or_toast(request)
    if isinstance(cfg, HTMLResponse):
        return cfg
    prefs = load_prefs(profile.prefs_path)
    resume = profile.resume_path
    if not resume.exists():
        return toast(request, f"resume not found at {resume}", "error", code=400)
    client = None
    if mode == "llm":
        key = os.environ.get(cfg.anthropic.key_env_var, "")
        if not key:
            return toast(request, f"{cfg.anthropic.key_env_var} not set", "error", code=400)
        from anthropic import Anthropic

        client = Anthropic(api_key=key)
    background.add_task(
        _run_rank, request.app, profile.slug, profile.db_path, cfg, prefs, resume, client
    )
    label = "rank started (LLM)" if client else "rank started (cosine only)"
    return toast(request, label, "info")


@router.post("/rank/selected", response_class=HTMLResponse)
def rank_selected(
    background: BackgroundTasks,
    request: Request,
    job_ids: list[int] = Form(default=[]),
    profile: Profile = Depends(profile_dep),
) -> HTMLResponse:
    """LLM-rerank the user's checkbox selection from the job list."""
    if not job_ids:
        return toast(request, "no jobs selected", "error", code=400)
    cfg = _config_or_toast(request)
    if isinstance(cfg, HTMLResponse):
        return cfg
    prefs = load_prefs(profile.prefs_path)
    resume = profile.resume_path
    if not resume.exists():
        return toast(request, f"resume not found at {resume}", "error", code=400)
    key = os.environ.get(cfg.anthropic.key_env_var, "")
    if not key:
        return toast(request, f"{cfg.anthropic.key_env_var} not set", "error", code=400)
    from anthropic import Anthropic

    background.add_task(
        _run_rerank_selected,
        request.app,
        profile.slug,
        profile.db_path,
        list(job_ids),
        cfg,
        prefs,
        resume,
        Anthropic(api_key=key),
    )
    return toast(request, f"reranking {len(job_ids)} job(s)…", "info")


@router.post("/tailor/{job_id}", response_class=HTMLResponse)
def tailor(
    job_id: int,
    background: BackgroundTasks,
    request: Request,
    profile: Profile = Depends(profile_dep),
) -> HTMLResponse:
    cfg = _config_or_toast(request)
    if isinstance(cfg, HTMLResponse):
        return cfg
    prefs = load_prefs(profile.prefs_path)
    resume = profile.resume_path
    if not resume.exists():
        return toast(request, f"resume not found at {resume}", "error", code=400)
    key = os.environ.get(cfg.anthropic.key_env_var, "")
    if not key:
        return toast(request, f"{cfg.anthropic.key_env_var} not set", "error", code=400)
    from anthropic import Anthropic

    background.add_task(
        _run_tailor,
        request.app,
        profile.slug,
        profile.db_path,
        job_id,
        cfg,
        prefs,
        resume,
        profile.output_dir,
        Anthropic(api_key=key),
    )
    return toast(request, f"tailoring job {job_id}…", "info")


@router.post("/jobs/purge-untailored", response_class=HTMLResponse)
def purge_untailored(request: Request, profile: Profile = Depends(profile_dep)) -> HTMLResponse:
    """Delete every job that has no tailor_outputs row. Destructive."""
    n = store_db.purge_untailored(profile.db_path)
    _append_log(request.app, profile.slug, f"purge: deleted {n} untailored job(s)")
    return toast(request, f"deleted {n} untailored job(s)", "info")


@router.get("/status", response_class=HTMLResponse)
def status(request: Request, profile: Profile = Depends(profile_dep)) -> HTMLResponse:
    """HTMX-polled status feed, scoped to this profile."""
    log: list[tuple[str, str, str]] = list(getattr(request.app.state, "task_log", []))
    mine = [f"[{stamp}] {msg}" for slug, stamp, msg in log if slug == profile.slug]
    html = (
        get_env(request).get_template("_status.html").render(request=request, log=mine[-25:][::-1])
    )
    return HTMLResponse(html)
