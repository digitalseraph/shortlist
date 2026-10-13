"""Profiles: one job seeker's resume, jobs, preferences and output.

A profile straddles two trees, following the existing convention that
preferences are configuration and the database is data:

    config_dir/profiles/<slug>/prefs.yaml
    data_dir/profiles/<slug>/{profile.yaml, db.sqlite, resume.md, output/}

The directory listing is the registry; there is no separate index file.
"""

from __future__ import annotations

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
    """Create both directories, seed prefs.yaml, write profile.yaml, migrate a fresh database."""
    config_root, data_root = profile_dirs(slug)
    if (data_root / "profile.yaml").exists():
        raise DuplicateProfileError(f"profile {slug!r} already exists")
    config_root.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "output").mkdir(exist_ok=True)
    (data_root / "profile.yaml").write_text(
        yaml.safe_dump({"display_name": display_name}, sort_keys=False)
    )
    prof = _build(slug, display_name)
    prof.prefs_path.write_text(DEFAULT_PREFS_YAML)
    migrate(prof.db_path)
    return prof


def load(slug: str) -> Profile:
    """Load a profile, repairing missing config dir/prefs.yaml rather than hiding them."""
    config_root, data_root = profile_dirs(slug)
    meta = data_root / "profile.yaml"
    if not meta.exists():
        raise ProfileNotFoundError(f"no profile {slug!r}")
    config_root.mkdir(parents=True, exist_ok=True)
    data = yaml.safe_load(meta.read_text()) or {}
    prof = _build(slug, str(data.get("display_name", slug)))
    if not prof.prefs_path.exists():
        prof.prefs_path.write_text(DEFAULT_PREFS_YAML)
    return prof


def list_profiles() -> list[Profile]:
    """Every profile on disk, ordered by display name."""
    root = paths.data_dir() / "profiles"
    if not root.is_dir():
        return []
    found = [
        load(child.name)
        for child in sorted(root.iterdir())
        if child.is_dir() and (child / "profile.yaml").exists()
    ]
    return sorted(found, key=lambda p: p.display_name.lower())


def delete(slug: str) -> None:
    """Remove both trees. The database and its cost history go with them."""
    config_root, data_root = profile_dirs(slug)
    if not (data_root / "profile.yaml").exists():
        raise ProfileNotFoundError(f"no profile {slug!r}")
    shutil.rmtree(data_root)
    if config_root.exists():
        shutil.rmtree(config_root)
