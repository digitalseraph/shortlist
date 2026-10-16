"""Profiles: one job seeker's resume, jobs, preferences and output.

A profile straddles two trees, following the existing convention that
preferences are configuration and the database is data:

    config_dir/profiles/<slug>/prefs.yaml
    data_dir/profiles/<slug>/{profile.yaml, db.sqlite, resume.md, output/}

The directory listing is the registry; there is no separate index file.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from shortlist import paths
from shortlist.config import DEFAULT_PREFS_YAML
from shortlist.store.db import migrate

_SLUG_RE = re.compile(r"^[a-z0-9-]{1,32}\Z")


class ProfileError(Exception):
    """Base for profile problems."""


class InvalidSlugError(ProfileError):
    pass


class DuplicateProfileError(ProfileError):
    pass


class ProfileNotFoundError(ProfileError):
    pass


@dataclass(frozen=True)
class Profile:
    slug: str
    display_name: str
    db_path: Path
    prefs_path: Path
    resume_path: Path
    original_resume_path: Path
    output_dir: Path


def validate_slug(slug: str) -> str:
    """Return `slug` if it is url-safe, else raise InvalidSlugError."""
    if not _SLUG_RE.match(slug):
        raise InvalidSlugError(
            f"invalid profile name {slug!r}; use 1-32 characters of a-z, 0-9 and -"
        )
    return slug


def profile_dirs(slug: str) -> tuple[Path, Path]:
    """Return (config_root, data_root) for `slug`. Does not touch the disk."""
    validate_slug(slug)
    return (
        paths.config_dir() / "profiles" / slug,
        paths.data_dir() / "profiles" / slug,
    )


def _build(slug: str, display_name: str) -> Profile:
    config_root, data_root = profile_dirs(slug)
    return Profile(
        slug=slug,
        display_name=display_name,
        db_path=data_root / "db.sqlite",
        prefs_path=config_root / "prefs.yaml",
        resume_path=data_root / "resume.md",
        original_resume_path=data_root / "resume.original",
        output_dir=data_root / "output",
    )


def create(slug: str, display_name: str) -> Profile:
    """Create both directories, seed prefs.yaml, migrate a fresh database, write profile.yaml.

    `profile.yaml` is written last: `list_profiles()`/`load()` key the
    registry on its presence, so writing it first would list (and block
    retrying) a profile that a later step in this function failed to finish
    setting up.
    """
    config_root, data_root = profile_dirs(slug)
    if (data_root / "profile.yaml").exists():
        raise DuplicateProfileError(f"profile {slug!r} already exists")
    config_root.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "output").mkdir(exist_ok=True)
    prof = _build(slug, display_name)
    prof.prefs_path.write_text(DEFAULT_PREFS_YAML)
    migrate(prof.db_path)
    (data_root / "profile.yaml").write_text(
        yaml.safe_dump({"display_name": display_name}, sort_keys=False)
    )
    return prof


def load(slug: str) -> Profile:
    """Load a profile, repairing missing config dir/prefs.yaml rather than hiding them.

    The repair (mkdir + seeding prefs.yaml below) runs on every load, not just
    the first - "repair, don't hide" per the design spec, so a config dir or
    prefs.yaml removed by hand comes back instead of 404ing forever.
    """
    config_root, data_root = profile_dirs(slug)
    meta = data_root / "profile.yaml"
    if not meta.exists():
        raise ProfileNotFoundError(f"no profile {slug!r}")
    try:
        data = yaml.safe_load(meta.read_text())
    except yaml.YAMLError as exc:
        raise ProfileNotFoundError(f"profile {slug!r} has a malformed profile.yaml") from exc
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        raise ProfileNotFoundError(f"profile {slug!r} has a malformed profile.yaml")
    config_root.mkdir(parents=True, exist_ok=True)
    prof = _build(slug, str(data.get("display_name", slug)))
    if not prof.prefs_path.exists():
        prof.prefs_path.write_text(DEFAULT_PREFS_YAML)
    return prof


def list_profiles() -> list[Profile]:
    """Every profile on disk, ordered by display name.

    A profile whose profile.yaml is malformed is skipped rather than taking
    the whole listing down with it - one bad file must not 500 every page.
    """
    root = paths.data_dir() / "profiles"
    if not root.is_dir():
        return []
    found: list[Profile] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / "profile.yaml").exists():
            continue
        try:
            found.append(load(child.name))
        except ProfileError:
            continue
    return sorted(found, key=lambda p: p.display_name.lower())


def delete(slug: str) -> None:
    """Remove both trees. The database and its cost history go with them."""
    config_root, data_root = profile_dirs(slug)
    if not (data_root / "profile.yaml").exists():
        raise ProfileNotFoundError(f"no profile {slug!r}")
    shutil.rmtree(data_root)
    if config_root.exists():
        shutil.rmtree(config_root)


class AmbiguousProfileError(ProfileError):
    pass


def resolve(explicit: str | None = None) -> Profile:
    """Pick the active profile.

    Order: explicit argument, then $SHORTLIST_PROFILE, then the only profile if
    there is exactly one, then the last used. Raise listing the choices if still
    unclear, rather than guessing at someone else's data.
    """
    from shortlist import state  # late import: state imports paths, profiles imports state

    if explicit:
        return load(explicit)
    env = os.environ.get("SHORTLIST_PROFILE")
    if env:
        return load(env)
    available = list_profiles()
    if not available:
        raise ProfileNotFoundError("no profiles yet; create one with `shortlist profile create`")
    if len(available) == 1:
        return available[0]
    last = state.get_last_profile()
    if last is not None:
        try:
            return load(last)
        except ProfileNotFoundError:
            pass
    names = ", ".join(p.slug for p in available)
    raise AmbiguousProfileError(f"several profiles exist ({names}); pass --profile")
