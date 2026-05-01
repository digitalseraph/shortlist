"""Settings read-only view — mirrors TUI SettingsScreen."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from shortlist import paths
from shortlist.config import load_config, load_prefs

router = APIRouter()


def _get_env(request: Request) -> Environment:
    templates_dir: Path = request.app.state.templates_dir
    return Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)


@router.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request) -> HTMLResponse:
    config_summary: str | None = None
    prefs_summary: str | None = None
    config_error: str | None = None
    prefs_error: str | None = None

    try:
        cfg = load_config(paths.config_path())
        enabled = [k for k, v in cfg.sources.items() if v.enabled]
        config_summary = (
            f"budget daily ${cfg.budget.daily_usd:.2f} / monthly ${cfg.budget.monthly_usd:.2f} | "
            f"rerank: {cfg.ranker.rerank_model} | tailor: {cfg.tailor.model} | "
            f"sources: {', '.join(enabled) or 'none'}"
        )
    except FileNotFoundError:
        config_error = "config.yaml missing — run `shortlist config init`"

    try:
        prefs = load_prefs(paths.prefs_path())
        prefs_summary = (
            f"titles: {', '.join(prefs.titles)} | "
            f"locations: {', '.join(prefs.locations)} | "
            f"comp floor: ${prefs.comp_floor_usd:,} | "
            f"greenhouse: {len(prefs.greenhouse_companies)} | "
            f"lever: {len(prefs.lever_companies)} | "
            f"ashby: {len(prefs.ashby_companies)}"
        )
    except FileNotFoundError:
        prefs_error = "prefs.yaml missing — run `shortlist config init`"

    html = (
        _get_env(request)
        .get_template("settings.html")
        .render(
            request=request,
            config_path=str(paths.config_path()),
            prefs_path=str(paths.prefs_path()),
            config_summary=config_summary,
            config_error=config_error,
            prefs_summary=prefs_summary,
            prefs_error=prefs_error,
            data_dir=str(paths.data_dir()),
            db_path=str(paths.db_path()),
        )
    )
    return HTMLResponse(html)
