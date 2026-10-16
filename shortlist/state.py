"""Small cross-run state that is not configuration: which profile was last used."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from yaml import YAMLError

from shortlist import paths


def _state_path() -> Path:
    return paths.config_dir() / "state.yaml"


def get_last_profile() -> str | None:
    """The slug last used, or None if unknown."""
    path = _state_path()
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            return None
    except YAMLError:
        return None
    value = data.get("last_profile")
    return str(value) if value else None


def set_last_profile(slug: str) -> None:
    """Remember `slug` as the most recently used profile.

    "Most recently used" is a convenience, not a correctness guarantee - an
    unwritable config dir (read-only filesystem, read-only state.yaml, ...)
    must never turn a page view into a 500. `OSError` from the mkdir/write
    below is swallowed; anything else (a genuine bug) still propagates.
    """
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if path.exists():
            try:
                loaded = yaml.safe_load(path.read_text())
                if isinstance(loaded, dict):
                    data = loaded
            except YAMLError:
                pass
        data["last_profile"] = slug
        path.write_text(yaml.safe_dump(data, sort_keys=False))
    except OSError:
        pass
