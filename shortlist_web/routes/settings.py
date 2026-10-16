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
    editing_config: bool = False,
) -> HTMLResponse:
    """Render settings.html through page_context.

    When `error` is set, re-render the submitted `text` instead of what's on
    disk, so nothing the person typed is lost. `editing_config` says which
    editor `text`/`error` belong to (True for config, False for prefs) — the
    caller always knows which form it's handling, so it's passed explicitly
    rather than guessed from the request. It's irrelevant when `text` is
    None (the GET view, or a successful save), since both editors then just
    load fresh from disk.
    """
    if text is not None and editing_config:
        config_text, prefs_text = text, _read(profile.prefs_path)
    elif text is not None:
        config_text, prefs_text = _read(paths.config_path(), DEFAULT_CONFIG_YAML), text
    else:
        config_text = _read(paths.config_path(), DEFAULT_CONFIG_YAML)
        prefs_text = _read(profile.prefs_path)
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
    *,
    editing_config: bool,
) -> HTMLResponse:
    """Validate `text`, then write it verbatim so comments and ordering survive."""
    try:
        parse(text)
    except Exception as exc:  # noqa: BLE001 — yaml and pydantic raise unrelated types
        return _render_settings(
            request, profile, error=str(exc), text=text, code=400, editing_config=editing_config
        )
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
        editing_config=False,
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
        editing_config=True,
    )
