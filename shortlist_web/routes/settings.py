"""Settings: one shared config.yaml editor, plus one prefs.yaml editor per person.

Both forms validate through the existing pydantic models before writing
anything. ``config.yaml`` is what the application boots from, so a broken
file saved here could lock someone out of the very screen they'd use to fix
it — validate-before-write is what keeps that from happening.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from shortlist import paths
from shortlist.config import DEFAULT_CONFIG_YAML, Config, Prefs
from shortlist.profiles import Profile
from shortlist_web.routes._shared import get_env, page_context, profile_dep

router = APIRouter()


def _read(path: Path, default: str = "") -> str:
    return path.read_text() if path.exists() else default


def _render_settings(
    request: Request,
    profile: Profile,
    *,
    note: str = "",
    error: str = "",
    text: str | None = None,
    code: int = 200,
) -> HTMLResponse:
    """Render settings.html through page_context.

    When `error` is set, re-render the submitted `text` instead of what's on
    disk — in whichever editor this request posted to, so nothing the person
    typed is lost. Which editor that is comes from the request path itself
    (config and prefs post to different routes), not an extra parameter. When
    `text` is None (the GET view, or a successful save), both editors load
    fresh from disk.
    """
    editing_config = text is not None and request.url.path.endswith("/settings/config")
    config_text = text if editing_config else _read(paths.config_path(), DEFAULT_CONFIG_YAML)
    prefs_text = text if (text is not None and not editing_config) else _read(profile.prefs_path)
    html = (
        get_env(request)
        .get_template("settings.html")
        .render(
            **page_context(
                request,
                profile,
                config_path=str(paths.config_path()),
                prefs_path=str(profile.prefs_path),
                config_text=config_text,
                prefs_text=prefs_text,
                config_error=error if editing_config else "",
                prefs_error=error if (error and not editing_config) else "",
                note=note,
            )
        )
    )
    return HTMLResponse(html, status_code=code)


@router.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request, profile: Profile = Depends(profile_dep)) -> HTMLResponse:
    return _render_settings(request, profile)


def _save_yaml(
    request: Request,
    profile: Profile,
    path: Path,
    text: str,
    parse: Callable[[str], object],
) -> HTMLResponse:
    """Validate `text`, then write it verbatim so comments and ordering survive."""
    try:
        parse(text)
    except Exception as exc:  # noqa: BLE001 — yaml and pydantic raise unrelated types
        return _render_settings(request, profile, error=str(exc), text=text, code=400)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        backup.write_text(path.read_text())
    path.write_text(text)
    return _render_settings(request, profile, note="Saved.")


@router.post("/settings/prefs", response_class=HTMLResponse)
def save_prefs(
    request: Request,
    profile: Profile = Depends(profile_dep),
    text: str = Form(...),
) -> HTMLResponse:
    return _save_yaml(
        request,
        profile,
        profile.prefs_path,
        text,
        lambda s: Prefs(**(yaml.safe_load(s) or {})),
    )


@router.post("/settings/config", response_class=HTMLResponse)
def save_config(
    request: Request,
    profile: Profile = Depends(profile_dep),
    text: str = Form(...),
) -> HTMLResponse:
    return _save_yaml(
        request,
        profile,
        paths.config_path(),
        text,
        lambda s: Config(**(yaml.safe_load(s) or {})),
    )
