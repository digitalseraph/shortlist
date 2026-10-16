"""Settings: forms for the shared config.yaml and each person's prefs.yaml.

The forms are the everyday editors; the raw YAML editors stay under
"Advanced" for anything the forms do not cover. Every save validates through
the pydantic models before writing anything. ``config.yaml`` is what the
application boots from, so a broken file saved here could lock someone out of
the very screen they'd use to fix it — validate-before-write is what keeps
that from happening.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from shortlist import paths
from shortlist.config import DEFAULT_CONFIG_YAML, Config, Prefs, load_prefs
from shortlist.profiles import Profile
from shortlist_web import settings_forms
from shortlist_web.routes._shared import get_env, page_context, profile_dep

router = APIRouter()


def _read(path: Path, default: str = "") -> str:
    return path.read_text() if path.exists() else default


def _write_with_backup(path: Path, text: str) -> None:
    """Copy the current file to `.bak`, then write `text`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.with_name(path.name + ".bak").write_text(path.read_text())
    path.write_text(text)


def _disk_prefs_values(profile: Profile) -> tuple[dict[str, object], str]:
    """Prefs form values from disk, or empty values and a message if the file is invalid."""
    try:
        return settings_forms.prefs_values(load_prefs(profile.prefs_path)), ""
    except Exception as exc:  # noqa: BLE001 — yaml and pydantic raise unrelated types
        return {}, f"prefs.yaml could not be loaded ({exc}); fix it under Advanced."


def _disk_config_values() -> tuple[dict[str, object], str]:
    """Config form values from disk (or the default), or a message if the YAML is broken."""
    path = paths.config_path()
    try:
        current = settings_forms.current_config(path.read_text() if path.exists() else None)
    except yaml.YAMLError as exc:
        return {}, f"config.yaml could not be loaded ({exc}); fix it under Advanced."
    return settings_forms.config_values(current), ""


def _render_settings(
    request: Request,
    profile: Profile,
    *,
    note: str = "",
    error: str = "",
    text: str | None = None,
    code: int = 200,
    editing_config: bool = False,
    prefs_values: dict[str, object] | None = None,
    prefs_errors: dict[str, str] | None = None,
    config_values: dict[str, object] | None = None,
    config_errors: dict[str, str] | None = None,
) -> HTMLResponse:
    """Render settings.html through page_context.

    `text`/`error` belong to the raw YAML editors: when `error` is set, the
    submitted `text` is re-rendered instead of what's on disk, so nothing the
    person typed is lost. `editing_config` says which raw editor they belong
    to (True for config, False for prefs) — the caller always knows which
    form it's handling, so it's passed explicitly rather than guessed.

    `prefs_values`/`config_values` are the forms' field values; None means
    "load from disk", which is what every view but a failed form save wants.
    """
    if text is not None and editing_config:
        config_text, prefs_text = text, _read(profile.prefs_path)
    elif text is not None:
        config_text, prefs_text = _read(paths.config_path(), DEFAULT_CONFIG_YAML), text
    else:
        config_text = _read(paths.config_path(), DEFAULT_CONFIG_YAML)
        prefs_text = _read(profile.prefs_path)

    prefs_errors = dict(prefs_errors or {})
    if prefs_values is None:
        prefs_values, load_error = _disk_prefs_values(profile)
        if load_error:
            prefs_errors.setdefault("_form", load_error)
    config_errors = dict(config_errors or {})
    if config_values is None:
        config_values, load_error = _disk_config_values()
        if load_error:
            config_errors.setdefault("_form", load_error)

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
                prefs_values=prefs_values,
                prefs_errors=prefs_errors,
                config_values=config_values,
                config_errors=config_errors,
                note=note,
            )
        )
    )
    return HTMLResponse(html, status_code=code)


def _saved(profile: Profile) -> RedirectResponse:
    """Post/redirect/get after a save: a refresh then re-reads instead of re-posting,
    and the profile switcher (which keeps the current path) lands on a GET page."""
    return RedirectResponse(f"/p/{profile.slug}/settings?saved=1", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
def settings_view(
    request: Request, profile: Profile = Depends(profile_dep), saved: bool = False
) -> HTMLResponse:
    return _render_settings(request, profile, note="Saved." if saved else "")


@router.post("/settings/prefs/form", response_class=HTMLResponse, response_model=None)
async def save_prefs_form(
    request: Request, profile: Profile = Depends(profile_dep)
) -> HTMLResponse | RedirectResponse:
    data = settings_forms.prefs_data(await request.form())
    try:
        prefs = Prefs.model_validate(data)
    except ValidationError as exc:
        errors = settings_forms.field_errors(exc, settings_forms.PREFS_ERROR_NAMES)
        return _render_settings(request, profile, prefs_values=data, prefs_errors=errors, code=400)
    text = settings_forms.to_yaml(settings_forms.PREFS_HEADER, prefs)
    _write_with_backup(profile.prefs_path, text)
    return _saved(profile)


@router.post("/settings/config/form", response_class=HTMLResponse, response_model=None)
async def save_config_form(
    request: Request, profile: Profile = Depends(profile_dep)
) -> HTMLResponse | RedirectResponse:
    path = paths.config_path()
    try:
        current = settings_forms.current_config(path.read_text() if path.exists() else None)
    except yaml.YAMLError as exc:
        message = f"config.yaml is not valid YAML ({exc}); fix it under Advanced."
        return _render_settings(request, profile, config_errors={"_form": message}, code=400)
    data = settings_forms.config_data(await request.form(), current)
    try:
        config = Config.model_validate(data)
    except ValidationError as exc:
        errors = settings_forms.field_errors(exc, settings_forms.CONFIG_ERROR_NAMES)
        submitted = settings_forms.config_values(data)
        return _render_settings(
            request, profile, config_values=submitted, config_errors=errors, code=400
        )
    _write_with_backup(path, settings_forms.to_yaml(settings_forms.CONFIG_HEADER, config))
    return _saved(profile)


def _save_yaml(
    request: Request,
    profile: Profile,
    path: Path,
    text: str,
    parse: Callable[[str], object],
    *,
    editing_config: bool,
) -> HTMLResponse | RedirectResponse:
    """Validate `text`, then write it verbatim so comments and ordering survive."""
    try:
        parse(text)
    except Exception as exc:  # noqa: BLE001 — yaml and pydantic raise unrelated types
        return _render_settings(
            request, profile, error=str(exc), text=text, code=400, editing_config=editing_config
        )
    _write_with_backup(path, text)
    return _saved(profile)


@router.post("/settings/prefs", response_class=HTMLResponse, response_model=None)
def save_prefs(
    request: Request,
    profile: Profile = Depends(profile_dep),
    text: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    return _save_yaml(
        request,
        profile,
        profile.prefs_path,
        text,
        lambda s: Prefs(**(yaml.safe_load(s) or {})),
        editing_config=False,
    )


@router.post("/settings/config", response_class=HTMLResponse, response_model=None)
def save_config(
    request: Request,
    profile: Profile = Depends(profile_dep),
    text: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    return _save_yaml(
        request,
        profile,
        paths.config_path(),
        text,
        lambda s: Config(**(yaml.safe_load(s) or {})),
        editing_config=True,
    )
