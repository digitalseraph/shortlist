# Multi-Profile Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one Shortlist installation track several people, each with their own resume, jobs, kanban board and source preferences, sharing one Anthropic API key and budget.

**Architecture:** One SQLite database per person under `data_dir/profiles/<slug>/`, selected by a `/p/<slug>/` URL prefix in the web layer and a `--profile` flag in the CLI. A frozen `Profile` dataclass carries the paths that used to be module globals. `paths.db_path()` and `paths.prefs_path()` are deleted so no code can silently resolve to the wrong person.

**Tech Stack:** Python 3.14, FastAPI, Jinja2, HTMX, SQLite, pydantic v2, pytest, ruff, mypy strict, uv.

**Spec:** `docs/superpowers/specs/2026-10-13-multi-profile-design.md`

## Global Constraints

- Python `>=3.12`; the venv runs 3.14.7. Every module starts with `from __future__ import annotations`.
- `mypy` runs in strict mode over `shortlist`, `shortlist_tui`, `shortlist_web`. Every new function is fully annotated.
- `ruff` line length is 100. Lint selects `E, F, I, B, UP, SIM`.
- Test coverage floor is 80%. Tests are written before implementation.
- Commit messages use conventional-commit types (`feat`, `fix`, `refactor`, `docs`, `test`, `chore`). **No AI attribution and no `Co-Authored-By` trailers of any kind.**
- Run tests with `.venv/bin/python -m pytest`, lint with `.venv/bin/python -m ruff check .`, types with `.venv/bin/python -m mypy`.
- Slugs are `[a-z0-9-]`, 1-32 characters.
- New dependencies: `pypdf`, `python-docx`. Add to `[project].dependencies` in `pyproject.toml`, then `uv lock` and `uv sync --extra dev`.

## Key Pre-Existing Fact

Every function in `shortlist/store/db.py` already takes `path: Path` as its first
parameter (`upsert_job(path, raw)`, `list_jobs(path, ...)`, `transition_status(path, ...)`),
and `shortlist_tui/data.py:88 list_job_rows(db_path, ...)` does too.

**The store and data layers need no changes.** Only the callers that *compute* the
path change. Do not refactor `db.py` in this plan.

## File Structure

| File | Responsibility |
|---|---|
| `shortlist/profiles.py` (new) | `Profile` dataclass, slug rules, create/load/list/delete, `resolve()` |
| `shortlist/state.py` (new) | Last-used slug in `config_dir/state.yaml` |
| `shortlist/resume_import.py` (new) | Extract text from md/txt/pdf/docx bytes |
| `shortlist/paths.py` (modify) | Drop `db_path()` and `prefs_path()` |
| `shortlist_web/routes/_shared.py` (modify) | Add `profile_dep` and `page_context` |
| `shortlist_web/routes/profiles.py` (new) | Create/delete profiles, first-run screen |
| `shortlist_web/routes/resume.py` (new) | Upload, preview, edit, save |
| `shortlist_web/routes/settings.py` (modify) | YAML editors for config and prefs |
| `shortlist_web/routes/{jobs,applications,actions,costs}.py` (modify) | Mount under `/p/{slug}`, take `profile` |
| `shortlist/cli.py` (modify) | `profile` command group, `--profile` option |
| `shortlist_tui/app.py` (modify) | Resolve one profile at startup |

---

### Task 1: Profile model and storage

**Files:**
- Create: `shortlist/profiles.py`
- Test: `tests/unit/test_profiles.py`

**Interfaces:**
- Consumes: `shortlist.paths.config_dir()`, `shortlist.paths.data_dir()`, `shortlist.store.db.migrate`
- Produces: `Profile` (frozen dataclass with `slug`, `display_name`, `db_path`, `prefs_path`, `resume_path`, `original_resume_path`, `output_dir`), `ProfileError`, `InvalidSlugError`, `DuplicateProfileError`, `ProfileNotFoundError`, `validate_slug(slug: str) -> str`, `profile_dirs(slug: str) -> tuple[Path, Path]`, `create(slug: str, display_name: str) -> Profile`, `load(slug: str) -> Profile`, `list_profiles() -> list[Profile]`, `delete(slug: str) -> None`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for profile creation, lookup and deletion."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortlist import profiles
from shortlist.store.db import current_version


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.mark.parametrize("slug", ["david", "my-sister", "a", "a1-b2"])
def test_validate_slug_accepts_url_safe_names(slug: str) -> None:
    assert profiles.validate_slug(slug) == slug


@pytest.mark.parametrize("slug", ["", "David", "has space", "dots.dots", "a" * 33, "../escape"])
def test_validate_slug_rejects_everything_else(slug: str) -> None:
    with pytest.raises(profiles.InvalidSlugError):
        profiles.validate_slug(slug)


def test_create_makes_both_directories_and_migrates_db(env: Path) -> None:
    prof = profiles.create("david", "David")
    assert prof.db_path.exists()
    assert current_version(prof.db_path) == 3
    assert prof.prefs_path.parent.is_dir()
    assert prof.output_dir.is_dir()
    assert (prof.db_path.parent / "profile.yaml").exists()


def test_create_rejects_duplicate(env: Path) -> None:
    profiles.create("david", "David")
    with pytest.raises(profiles.DuplicateProfileError):
        profiles.create("david", "David Again")


def test_load_returns_display_name(env: Path) -> None:
    profiles.create("my-sister", "Alex")
    assert profiles.load("my-sister").display_name == "Alex"


def test_load_unknown_slug_raises(env: Path) -> None:
    with pytest.raises(profiles.ProfileNotFoundError):
        profiles.load("nobody")


def test_list_profiles_sorted_by_display_name(env: Path) -> None:
    profiles.create("b", "Zoe")
    profiles.create("a", "Adam")
    assert [p.slug for p in profiles.list_profiles()] == ["a", "b"]


def test_list_profiles_empty_when_none_exist(env: Path) -> None:
    assert profiles.list_profiles() == []


def test_delete_removes_both_trees(env: Path) -> None:
    prof = profiles.create("david", "David")
    config_root = prof.prefs_path.parent
    data_root = prof.db_path.parent
    profiles.delete("david")
    assert not data_root.exists()
    assert not config_root.exists()
    with pytest.raises(profiles.ProfileNotFoundError):
        profiles.load("david")


def test_load_repairs_missing_config_dir(env: Path) -> None:
    """A data dir without its config counterpart is repaired, not hidden."""
    prof = profiles.create("david", "David")
    prof.prefs_path.unlink(missing_ok=True)
    prof.prefs_path.parent.rmdir()
    again = profiles.load("david")
    assert again.prefs_path.parent.is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_profiles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shortlist.profiles'`

- [ ] **Step 3: Write the implementation**

```python
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
from shortlist.store.db import migrate

_SLUG_RE = re.compile(r"^[a-z0-9-]{1,32}$")


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
    """Create both directories, write profile.yaml, and migrate a fresh database."""
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
    migrate(prof.db_path)
    return prof


def load(slug: str) -> Profile:
    """Load a profile, repairing a missing config directory rather than hiding it."""
    config_root, data_root = profile_dirs(slug)
    meta = data_root / "profile.yaml"
    if not meta.exists():
        raise ProfileNotFoundError(f"no profile {slug!r}")
    config_root.mkdir(parents=True, exist_ok=True)
    data = yaml.safe_load(meta.read_text()) or {}
    return _build(slug, str(data.get("display_name", slug)))


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
    shutil.rmtree(config_root, ignore_errors=True)
```

`os` is imported here for `resolve()` in Task 2; if your linter objects to the
unused import at this point, add it in Task 2 instead.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_profiles.py -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Lint and typecheck**

Run: `.venv/bin/python -m ruff check shortlist/profiles.py tests/unit/test_profiles.py && .venv/bin/python -m mypy`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add shortlist/profiles.py tests/unit/test_profiles.py
git commit -m "feat(profiles): add profile model, creation and lookup"
```

---

### Task 2: Active-profile resolution and last-used state

**Files:**
- Create: `shortlist/state.py`
- Modify: `shortlist/profiles.py` (append `AmbiguousProfileError` and `resolve`)
- Test: `tests/unit/test_profiles_resolve.py`

**Interfaces:**
- Consumes: `profiles.list_profiles`, `profiles.load`, `paths.config_dir`
- Produces: `state.get_last_profile() -> str | None`, `state.set_last_profile(slug: str) -> None`, `profiles.resolve(explicit: str | None = None) -> Profile`, `profiles.AmbiguousProfileError`

- [ ] **Step 1: Write the failing tests**

```python
"""Resolution order for the active profile, and last-used persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortlist import profiles, state


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("SHORTLIST_PROFILE", raising=False)
    return tmp_path


def test_last_profile_round_trips(env: Path) -> None:
    assert state.get_last_profile() is None
    state.set_last_profile("david")
    assert state.get_last_profile() == "david"


def test_resolve_prefers_explicit(env: Path) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    assert profiles.resolve("alex").slug == "alex"


def test_resolve_falls_back_to_env_var(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    monkeypatch.setenv("SHORTLIST_PROFILE", "david")
    assert profiles.resolve().slug == "david"


def test_resolve_uses_sole_profile(env: Path) -> None:
    profiles.create("only", "Only")
    assert profiles.resolve().slug == "only"


def test_resolve_uses_last_used_when_several(env: Path) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    state.set_last_profile("alex")
    assert profiles.resolve().slug == "alex"


def test_resolve_raises_listing_choices_when_ambiguous(env: Path) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    with pytest.raises(profiles.AmbiguousProfileError) as exc:
        profiles.resolve()
    assert "alex" in str(exc.value)
    assert "david" in str(exc.value)


def test_resolve_raises_when_none_exist(env: Path) -> None:
    with pytest.raises(profiles.ProfileNotFoundError):
        profiles.resolve()


def test_resolve_ignores_stale_last_used(env: Path) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    state.set_last_profile("deleted-one")
    with pytest.raises(profiles.AmbiguousProfileError):
        profiles.resolve()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_profiles_resolve.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shortlist.state'`

- [ ] **Step 3: Write `shortlist/state.py`**

```python
"""Small cross-run state that is not configuration: which profile was last used."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from shortlist import paths


def _state_path() -> Path:
    return paths.config_dir() / "state.yaml"


def get_last_profile() -> str | None:
    """The slug last used, or None if unknown."""
    path = _state_path()
    if not path.exists():
        return None
    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    value = data.get("last_profile")
    return str(value) if value else None


def set_last_profile(slug: str) -> None:
    """Remember `slug` as the most recently used profile."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    data["last_profile"] = slug
    path.write_text(yaml.safe_dump(data, sort_keys=False))
```

- [ ] **Step 4: Append to `shortlist/profiles.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_profiles_resolve.py -v`
Expected: PASS, 8 tests

- [ ] **Step 6: Lint, typecheck and commit**

```bash
.venv/bin/python -m ruff check . && .venv/bin/python -m mypy
git add shortlist/state.py shortlist/profiles.py tests/unit/test_profiles_resolve.py
git commit -m "feat(profiles): resolve the active profile and remember the last used"
```

---

### Task 3: Delete the path globals and thread profiles through the CLI

**Files:**
- Modify: `shortlist/paths.py` (remove `db_path`, `prefs_path`)
- Modify: `shortlist/cli.py` (31 call sites)
- Test: `tests/integration/test_cli_profiles.py`

**Interfaces:**
- Consumes: `profiles.resolve`, `profiles.create`, `profiles.list_profiles`, `profiles.delete`, `profiles.ProfileError`
- Produces: CLI `shortlist profile list|create|delete`, a `--profile/-p` option on every data command, and `cli._resolve(explicit: str | None) -> Profile`

This task is large but mechanical. The deletions in `paths.py` are what locate every
site — let mypy drive.

- [ ] **Step 1: Write the failing tests**

```python
"""CLI profile management and --profile threading."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from shortlist import profiles
from shortlist.cli import app

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("SHORTLIST_PROFILE", raising=False)
    return tmp_path


def test_profile_create_then_list(env: Path) -> None:
    created = runner.invoke(app, ["profile", "create", "david", "--name", "David"])
    assert created.exit_code == 0
    listed = runner.invoke(app, ["profile", "list"])
    assert listed.exit_code == 0
    assert "david" in listed.stdout
    assert "David" in listed.stdout


def test_profile_create_rejects_bad_slug(env: Path) -> None:
    result = runner.invoke(app, ["profile", "create", "Has Space", "--name", "X"])
    assert result.exit_code != 0
    assert profiles.list_profiles() == []


def test_profile_delete_removes_it(env: Path) -> None:
    runner.invoke(app, ["profile", "create", "david", "--name", "David"])
    deleted = runner.invoke(app, ["profile", "delete", "david", "--yes"])
    assert deleted.exit_code == 0
    assert profiles.list_profiles() == []


def test_list_command_requires_a_profile_when_ambiguous(env: Path) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    result = runner.invoke(app, ["list"])
    assert result.exit_code != 0


def test_list_command_accepts_explicit_profile(env: Path) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    result = runner.invoke(app, ["list", "--profile", "alex"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/integration/test_cli_profiles.py -v`
Expected: FAIL — `No such command 'profile'`

- [ ] **Step 3: Remove the two functions from `shortlist/paths.py`**

Delete exactly these, leaving `config_dir`, `data_dir` and `config_path` in place:

```python
def prefs_path() -> Path:
    return config_dir() / "prefs.yaml"


def db_path() -> Path:
    return data_dir() / "db.sqlite"
```

- [ ] **Step 4: Find every broken site**

Run: `.venv/bin/python -m mypy`
Expected: errors in `cli.py`, `shortlist_tui/`, `shortlist_web/routes/`. Record the
list; tasks 4-10 clear the non-CLI ones.

- [ ] **Step 5: Add the profile command group to `shortlist/cli.py`**

```python
profile_app = typer.Typer(help="Manage people tracked in this installation.")
app.add_typer(profile_app, name="profile")


@profile_app.command("list")
def profile_list() -> None:
    """List every profile."""
    found = profiles.list_profiles()
    if not found:
        typer.echo("no profiles yet — create one with `shortlist profile create <slug>`")
        return
    for prof in found:
        typer.echo(f"{prof.slug}\t{prof.display_name}")


@profile_app.command("create")
def profile_create(
    slug: str = typer.Argument(...),
    name: str = typer.Option(..., "--name", help="Display name, e.g. 'David'"),
) -> None:
    """Create a profile with an empty database."""
    try:
        prof = profiles.create(slug, name)
    except profiles.ProfileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"created {prof.slug} at {prof.db_path.parent}")


@profile_app.command("delete")
def profile_delete(
    slug: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Delete a profile, its database and its cost history."""
    if not yes:
        typer.confirm(f"Delete profile {slug!r} and all of its data?", abort=True)
    try:
        profiles.delete(slug)
    except profiles.ProfileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"deleted {slug}")
```

- [ ] **Step 6: Add the shared resolver helper to `shortlist/cli.py`**

```python
def _resolve(explicit: str | None) -> profiles.Profile:
    """Resolve the active profile or exit with a useful message."""
    try:
        return profiles.resolve(explicit)
    except profiles.ProfileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
```

- [ ] **Step 7: Thread `--profile` through every data command**

For each of `fetch`, `rank`, `tailor_cmd`, `list_jobs_cmd`, `track_cmd`, `contacts_add`,
`contacts_list`, `contacts_remove`, `sources_clear_cooldown`, `sources_status`,
`db_init`, `db_status`, `db_backup`, add this as the last parameter:

```python
    profile: str | None = typer.Option(None, "--profile", "-p", help="Which person."),
```

open the body with:

```python
    prof = _resolve(profile)
```

and substitute within that body:

| Before | After |
|---|---|
| `paths.db_path()` | `prof.db_path` |
| `paths.prefs_path()` | `prof.prefs_path` |
| `cfg.paths.resume` | `prof.resume_path` |
| `cfg.paths.output_dir` | `prof.output_dir` |

`paths.config_path()` stays as it is — config is shared.

- [ ] **Step 8: Run the new tests, then the suite**

Run: `.venv/bin/python -m pytest tests/integration/test_cli_profiles.py -v`
Expected: PASS, 5 tests

Run: `.venv/bin/python -m pytest -q`
Expected: the web and TUI suites now fail — tasks 4-10 fix them. This is the one
red window in the plan.

- [ ] **Step 9: Commit**

```bash
git add shortlist/paths.py shortlist/cli.py tests/integration/test_cli_profiles.py
git commit -m "feat(cli): add profile commands and --profile, drop the path globals"
```

---

### Task 4: Web profile dependency and `/p/{slug}` routing

**Files:**
- Modify: `shortlist_web/routes/_shared.py`
- Modify: `shortlist_web/app.py`
- Modify: `shortlist_web/routes/jobs.py`, `applications.py`, `costs.py`
- Test: `tests/integration/test_web_profiles.py`

**Interfaces:**
- Consumes: `profiles.load`, `profiles.list_profiles`, `profiles.resolve`, `profiles.ProfileNotFoundError`
- Produces: `_shared.profile_dep(slug: str) -> Profile` for `Depends(profile_dep)`; all page routes served under `/p/{slug}/...`

- [ ] **Step 1: Write the failing tests**

```python
"""Profile scoping in the web layer: isolation, 404s and redirects."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist.models import RawJob
from shortlist.store.db import list_jobs, transition_status, upsert_job
from shortlist_web.app import create_app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("SHORTLIST_PROFILE", raising=False)
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def _seed(db: Path, eid: str, company: str) -> int:
    job = upsert_job(
        db,
        RawJob(
            source="greenhouse",
            external_id=eid,
            company=company,
            title="Senior Backend Engineer",
            url=f"https://example.com/{eid}",
            posted_at=datetime.now(UTC),
        ),
    )
    return job.id


def test_unknown_slug_is_404_not_a_fallback(client: TestClient) -> None:
    profiles.create("david", "David")
    assert client.get("/p/nobody/applications").status_code == 404


def test_bare_path_redirects_to_the_active_profile(client: TestClient) -> None:
    profiles.create("david", "David")
    r = client.get("/applications", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/p/david/applications"


def test_profiles_are_isolated(client: TestClient) -> None:
    """The load-bearing test: one person's data never appears on another's board."""
    david = profiles.create("david", "David")
    alex = profiles.create("alex", "Alex")
    jid = _seed(david.db_path, "gh_1", "Datadog")
    transition_status(david.db_path, jid, "tailored")

    mine = client.get("/p/david/applications")
    theirs = client.get("/p/alex/applications")

    assert "Datadog" in mine.text
    assert "Datadog" not in theirs.text
    assert list_jobs(alex.db_path) == []


def test_move_acts_on_the_profile_in_the_url(client: TestClient) -> None:
    david = profiles.create("david", "David")
    profiles.create("alex", "Alex")
    jid = _seed(david.db_path, "gh_1", "Datadog")
    transition_status(david.db_path, jid, "tailored")

    # The same job id under the other profile's URL must not touch David's job.
    r = client.post(f"/p/alex/applications/move/{jid}", data={"status": "applied"})
    assert r.status_code == 400
    assert next(j for j in list_jobs(david.db_path) if j.id == jid).status == "tailored"


def test_no_profiles_redirects_to_first_run(client: TestClient) -> None:
    r = client.get("/applications", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/profiles/new"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/integration/test_web_profiles.py -v`
Expected: FAIL — 404 on `/p/david/applications`; the prefix does not exist yet

- [ ] **Step 3: Add `profile_dep` and `page_context` to `shortlist_web/routes/_shared.py`**

```python
from fastapi import HTTPException, Request

from shortlist import profiles
from shortlist.profiles import Profile


def profile_dep(slug: str) -> Profile:
    """Resolve the `{slug}` path parameter, 404ing rather than falling back.

    A stale or mistyped link must never act on a different person's data.
    """
    try:
        return profiles.load(slug)
    except profiles.ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"no profile {slug!r}") from exc


def page_context(request: Request, profile: Profile, **extra: object) -> dict[str, object]:
    """Common template variables for any profile-scoped page."""
    return {
        "request": request,
        "active": profile,
        "all_profiles": profiles.list_profiles(),
        **extra,
    }
```

- [ ] **Step 4: Mount the page routers under the prefix in `shortlist_web/app.py`**

```python
    app.include_router(profiles_routes.router)  # unprefixed: /profiles/*
    for router in (
        jobs.router,
        applications.router,
        costs.router,
        settings.router,
        actions.router,
        resume.router,
    ):
        app.include_router(router, prefix="/p/{slug}")
```

`profiles_routes` and `resume` arrive in tasks 5 and 8; add each to this tuple as its
task lands.

- [ ] **Step 5: Add the bare-path redirect in `shortlist_web/app.py`**

```python
_BARE_PATHS = ("/", "/applications", "/costs", "/settings", "/resume")


@app.middleware("http")
async def _redirect_bare_paths(request: Request, call_next: Any) -> Response:
    """Send unprefixed page requests to the active profile, or to first-run setup."""
    path = request.url.path
    if path not in _BARE_PATHS:
        return await call_next(request)
    try:
        active = profiles.resolve()
    except profiles.ProfileError:
        return RedirectResponse("/profiles/new", status_code=307)
    suffix = "" if path == "/" else path
    return RedirectResponse(f"/p/{active.slug}{suffix}", status_code=307)
```

- [ ] **Step 6: Convert the three page routers**

In `jobs.py`, `applications.py` and `costs.py`, change each handler signature from

```python
def applications(request: Request) -> HTMLResponse:
```

to

```python
def applications(
    request: Request, profile: Profile = Depends(profile_dep)
) -> HTMLResponse:
```

replace `paths.db_path()` with `profile.db_path` throughout, and render with
`**page_context(request, profile, ...)` instead of `request=request, ...`.

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest tests/integration/test_web_profiles.py -v`
Expected: PASS, 5 tests

- [ ] **Step 8: Commit**

```bash
git add shortlist_web/ tests/integration/test_web_profiles.py
git commit -m "feat(web): scope pages to /p/{slug} with a profile dependency"
```

---

### Task 5: Profile screens and the header switcher

**Files:**
- Create: `shortlist_web/routes/profiles.py`
- Create: `shortlist_web/templates/profiles_new.html`, `shortlist_web/templates/profiles_list.html`
- Modify: `shortlist_web/templates/base.html`
- Test: `tests/integration/test_web_profile_screens.py`

**Interfaces:**
- Consumes: `profiles.create`, `profiles.delete`, `profiles.load`, `profiles.list_profiles`, `state.set_last_profile`, `_shared.get_env`, `_shared.toast`
- Produces: `GET /profiles`, `GET /profiles/new`, `POST /profiles`, `POST /profiles/{slug}/delete`

- [ ] **Step 1: Write the failing tests**

```python
"""First-run, creation, switching and deletion screens."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist_web.app import create_app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("SHORTLIST_PROFILE", raising=False)
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def test_first_run_screen_renders_with_no_profiles(client: TestClient) -> None:
    r = client.get("/profiles/new")
    assert r.status_code == 200
    assert "name" in r.text.lower()


def test_create_profile_redirects_into_it(client: TestClient) -> None:
    r = client.post(
        "/profiles", data={"slug": "david", "display_name": "David"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/p/david/"
    assert profiles.load("david").display_name == "David"


def test_create_rejects_bad_slug_without_writing(client: TestClient) -> None:
    r = client.post("/profiles", data={"slug": "Has Space", "display_name": "X"})
    assert r.status_code == 400
    assert profiles.list_profiles() == []


def test_create_rejects_duplicate(client: TestClient) -> None:
    profiles.create("david", "David")
    r = client.post("/profiles", data={"slug": "david", "display_name": "Again"})
    assert r.status_code == 400


def test_switcher_lists_every_profile(client: TestClient) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    r = client.get("/p/david/applications")
    assert "Alex" in r.text
    assert "/p/alex/" in r.text


def test_delete_requires_matching_display_name(client: TestClient) -> None:
    profiles.create("david", "David")
    wrong = client.post("/profiles/david/delete", data={"confirm": "Dave"})
    assert wrong.status_code == 400
    assert profiles.load("david").slug == "david"

    right = client.post(
        "/profiles/david/delete", data={"confirm": "David"}, follow_redirects=False
    )
    assert right.status_code == 303
    assert profiles.list_profiles() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/integration/test_web_profile_screens.py -v`
Expected: FAIL — 404 on `/profiles/new`

- [ ] **Step 3: Write `shortlist_web/routes/profiles.py`**

```python
"""Profile creation, switching and deletion. These routes are not profile-scoped."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from shortlist import profiles, state
from shortlist_web.routes._shared import get_env, toast

router = APIRouter()


@router.get("/profiles/new", response_class=HTMLResponse)
def new_profile_form(request: Request) -> HTMLResponse:
    html = get_env(request).get_template("profiles_new.html").render(request=request)
    return HTMLResponse(html)


@router.get("/profiles", response_class=HTMLResponse)
def list_profiles_view(request: Request) -> HTMLResponse:
    html = (
        get_env(request)
        .get_template("profiles_list.html")
        .render(request=request, profiles=profiles.list_profiles())
    )
    return HTMLResponse(html)


@router.post("/profiles", response_class=HTMLResponse, response_model=None)
def create_profile(
    request: Request, slug: str = Form(...), display_name: str = Form(...)
) -> Response:
    try:
        prof = profiles.create(slug, display_name)
    except profiles.ProfileError as exc:
        return toast(request, str(exc), "error", code=400)
    state.set_last_profile(prof.slug)
    return RedirectResponse(f"/p/{prof.slug}/", status_code=303)


@router.post("/profiles/{slug}/delete", response_class=HTMLResponse, response_model=None)
def delete_profile(request: Request, slug: str, confirm: str = Form(...)) -> Response:
    """Delete a profile. The typed display name is the confirmation."""
    try:
        prof = profiles.load(slug)
    except profiles.ProfileNotFoundError as exc:
        return toast(request, str(exc), "error", code=404)
    if confirm.strip() != prof.display_name:
        return toast(request, "type the display name exactly to confirm", "error", code=400)
    profiles.delete(slug)
    return RedirectResponse("/profiles", status_code=303)
```

- [ ] **Step 4: Write `shortlist_web/templates/profiles_new.html`**

```html
{% extends "base_plain.html" %}
{% block title %}Add a person — Shortlist{% endblock %}
{% block content %}
<h1>Add a person</h1>
<p class="dim">Each person gets their own resume, jobs and board. Your API key and
budget are shared.</p>
<form method="post" action="/profiles">
  <label>Display name <input name="display_name" required placeholder="David"></label>
  <label>Short name <input name="slug" required placeholder="david"
         pattern="[a-z0-9-]{1,32}" title="a-z, 0-9 and - only"></label>
  <button type="submit">Create</button>
</form>
{% endblock %}
```

`base_plain.html` is a copy of `base.html` without the nav and switcher, since there
may be no active profile yet. Create it in this step.

- [ ] **Step 5: Write `shortlist_web/templates/profiles_list.html`**

List each profile with a link to `/p/<slug>/` and a delete form whose `confirm` input
requires the display name. Include a link to `/profiles/new`.

- [ ] **Step 6: Add the switcher to `shortlist_web/templates/base.html`**

```html
    <nav>
      <a href="/p/{{ active.slug }}/">Jobs</a>
      <a href="/p/{{ active.slug }}/applications">Applications</a>
      <a href="/p/{{ active.slug }}/costs">Costs</a>
      <a href="/p/{{ active.slug }}/resume">Resume</a>
      <a href="/p/{{ active.slug }}/settings">Settings</a>
    </nav>
    <select class="profile-switcher" onchange="location.href=this.value">
      {% for p in all_profiles %}
      <option value="/p/{{ p.slug }}/" {% if p.slug == active.slug %}selected{% endif %}>
        {{ p.display_name }}
      </option>
      {% endfor %}
      <option value="/profiles">Manage people…</option>
    </select>
```

Switching lands on that person's job list rather than trying to preserve the current
sub-page, which keeps the template free of path-rewriting logic.

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest tests/integration/test_web_profile_screens.py -v`
Expected: PASS, 6 tests

- [ ] **Step 8: Commit**

```bash
git add shortlist_web/ tests/integration/test_web_profile_screens.py
git commit -m "feat(web): add profile screens and the header switcher"
```

---

### Task 6: Background tasks and the status feed

**Files:**
- Modify: `shortlist_web/routes/actions.py`
- Modify: `shortlist_web/templates/base.html` (status poller URL)
- Test: `tests/integration/test_web_actions_profile.py`

**Interfaces:**
- Consumes: `profile_dep`, `profile.db_path`, `profile.prefs_path`, `profile.resume_path`, `profile.output_dir`, `profile.slug`
- Produces: task-log entries shaped `(slug, stamp, message)`; `GET /p/{slug}/status` filtered to that slug; `_append_log(app: Any, slug: str, entry: str) -> None`; `_progress(app: Any, slug: str) -> Any`

- [ ] **Step 1: Write the failing tests**

```python
"""Background work is pinned to the profile that enqueued it."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist_web.app import create_app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def test_status_feed_only_shows_this_profile(client: TestClient) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    client.app.state.task_log = [
        ("david", "10:00:00", "fetch done: 3 jobs"),
        ("alex", "10:00:01", "fetch done: 7 jobs"),
    ]
    mine = client.get("/p/david/status")
    assert "3 jobs" in mine.text
    assert "7 jobs" not in mine.text


def test_purge_acts_on_the_url_profile(client: TestClient) -> None:
    david = profiles.create("david", "David")
    profiles.create("alex", "Alex")
    r = client.post("/p/alex/jobs/purge-untailored")
    assert r.status_code == 200
    assert client.app.state.task_log[-1][0] == "alex"
    assert david.db_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/integration/test_web_actions_profile.py -v`
Expected: FAIL — `/p/david/status` 404s and log entries are plain strings

- [ ] **Step 3: Retag the log in `shortlist_web/routes/actions.py`**

```python
def _append_log(app: Any, slug: str, entry: str) -> None:
    """Append a task-log line tagged with the profile that caused it."""
    from datetime import datetime as _dt

    log: list[tuple[str, str, str]] = app.state.task_log
    stamp = _dt.now().strftime("%H:%M:%S")
    log.append((slug, stamp, entry))
    if len(log) > _LOG_MAX:
        app.state.task_log = log[-_LOG_MAX:]


def _progress(app: Any, slug: str) -> Any:
    """Build a progress callback that tags each message with the profile."""
    return lambda msg: _append_log(app, slug, msg)
```

- [ ] **Step 4: Pass the profile into every handler and task**

Each action handler takes `profile: Profile = Depends(profile_dep)` and passes
`profile.db_path`, `profile.prefs_path`, `profile.resume_path`, `profile.output_dir`
and `profile.slug` into its `_run_*` wrapper. Each `_run_*` gains a leading
`slug: str` parameter and forwards it to `_append_log` and `_progress`.

**Never resolve a profile inside a `_run_*` function.** A fetch that starts under one
person and finishes after a switch would otherwise write into the wrong database.

- [ ] **Step 5: Filter the status route**

```python
@router.get("/status", response_class=HTMLResponse)
def status(request: Request, profile: Profile = Depends(profile_dep)) -> HTMLResponse:
    """HTMX-polled status feed, scoped to this profile."""
    log: list[tuple[str, str, str]] = list(getattr(request.app.state, "task_log", []))
    mine = [f"[{stamp}] {msg}" for slug, stamp, msg in log if slug == profile.slug]
    html = (
        get_env(request)
        .get_template("_status.html")
        .render(request=request, log=mine[-25:][::-1])
    )
    return HTMLResponse(html)
```

- [ ] **Step 6: Point the poller and the action buttons at prefixed URLs**

In `base.html`, every `hx-post` and the status poller gain the prefix:

```html
      <button hx-post="/p/{{ active.slug }}/fetch" hx-target="#toast" hx-swap="innerHTML">Fetch</button>
```

```html
  <div id="status-feed" hx-get="/p/{{ active.slug }}/status" hx-trigger="load, every 2s" hx-swap="innerHTML"></div>
```

Do the same for the `Rank All` and `Purge Untailored` buttons, and for `hx-post` in
`_job_row.html` and `job_list.html`.

- [ ] **Step 7: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_web_actions_profile.py -v
git add shortlist_web/ tests/integration/test_web_actions_profile.py
git commit -m "feat(web): pin background tasks and the status feed to a profile"
```

---

### Task 7: Resume extraction

**Files:**
- Create: `shortlist/resume_import.py`
- Modify: `pyproject.toml` (add `pypdf`, `python-docx`)
- Test: `tests/unit/test_resume_import.py`

**Interfaces:**
- Consumes: `pypdf.PdfReader`, `docx.Document`
- Produces: `extract_text(data: bytes, filename: str) -> str`, `UnsupportedResumeError`, `MAX_RESUME_BYTES: int`

- [ ] **Step 1: Add the dependencies**

In `pyproject.toml`, after `"python-multipart>=0.0.31",` in `[project].dependencies`:

```toml
    "pypdf>=6.1",
    "python-docx>=1.2",
```

Then:

```bash
uv lock
uv sync --extra dev
```

- [ ] **Step 2: Write the failing tests**

```python
"""Resume text extraction from the four accepted formats."""

from __future__ import annotations

import io

import pytest

from shortlist.resume_import import MAX_RESUME_BYTES, UnsupportedResumeError, extract_text


def test_markdown_passes_through() -> None:
    assert extract_text(b"# David\n\nEngineer", "resume.md") == "# David\n\nEngineer"


def test_plain_text_passes_through() -> None:
    assert extract_text(b"David, engineer", "resume.txt") == "David, engineer"


def test_pdf_is_extracted() -> None:
    pytest.importorskip("reportlab")
    from reportlab.pdfgen.canvas import Canvas

    buf = io.BytesIO()
    canvas = Canvas(buf)
    canvas.drawString(72, 720, "David Miller Senior Engineer")
    canvas.save()
    assert "David Miller" in extract_text(buf.getvalue(), "resume.pdf")


def test_docx_is_extracted() -> None:
    from docx import Document

    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph("David Miller")
    doc.add_paragraph("Senior Engineer")
    doc.save(buf)
    text = extract_text(buf.getvalue(), "resume.docx")
    assert "David Miller" in text
    assert "Senior Engineer" in text


def test_unknown_extension_rejected() -> None:
    with pytest.raises(UnsupportedResumeError):
        extract_text(b"anything", "resume.rtf")


def test_renamed_executable_rejected_by_content() -> None:
    """An ELF binary renamed to .pdf must not be accepted on extension alone."""
    with pytest.raises(UnsupportedResumeError):
        extract_text(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64, "resume.pdf")


def test_oversize_rejected() -> None:
    with pytest.raises(UnsupportedResumeError):
        extract_text(b"x" * (MAX_RESUME_BYTES + 1), "resume.md")


def test_undecodable_text_rejected() -> None:
    with pytest.raises(UnsupportedResumeError):
        extract_text(b"\xff\xfe\x00\x00binary", "resume.txt")
```

If `reportlab` is not installed, the PDF test skips. To exercise it, add
`reportlab>=4.0` to the `dev` extra.

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_resume_import.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shortlist.resume_import'`

- [ ] **Step 4: Write the implementation**

```python
"""Turn an uploaded resume into the plain text the ranking pipeline reads.

`embed_resume_cached` calls `read_text()` on the stored file, so every accepted
format is normalised to text here. PDF extraction is lossy — the caller is
expected to show the result for review before saving it.
"""

from __future__ import annotations

import io
from pathlib import Path

MAX_RESUME_BYTES = 2 * 1024 * 1024

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"  # a .docx is a zip container


class UnsupportedResumeError(ValueError):
    """The upload is not a resume we can read."""


def _as_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedResumeError("file is not valid UTF-8 text") from exc


def _from_pdf(data: bytes) -> str:
    if not data.startswith(_PDF_MAGIC):
        raise UnsupportedResumeError("file does not look like a PDF")
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _from_docx(data: bytes) -> str:
    if not data.startswith(_ZIP_MAGIC):
        raise UnsupportedResumeError("file does not look like a .docx")
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs).strip()


def extract_text(data: bytes, filename: str) -> str:
    """Extract resume text, validating by extension and by leading bytes."""
    if len(data) > MAX_RESUME_BYTES:
        raise UnsupportedResumeError(f"file is larger than {MAX_RESUME_BYTES // (1024 * 1024)} MB")
    suffix = Path(filename).suffix.lower()
    if suffix in (".md", ".txt"):
        return _as_text(data)
    if suffix == ".pdf":
        return _from_pdf(data)
    if suffix == ".docx":
        return _from_docx(data)
    raise UnsupportedResumeError(f"unsupported file type {suffix or filename!r}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_resume_import.py -v`
Expected: PASS, 8 tests (the PDF test skips without `reportlab`)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock shortlist/resume_import.py tests/unit/test_resume_import.py
git commit -m "feat(resume): extract resume text from markdown, pdf and docx"
```

---

### Task 8: Resume upload, preview and editing

**Files:**
- Create: `shortlist_web/routes/resume.py`
- Create: `shortlist_web/templates/resume.html`
- Modify: `shortlist_web/app.py` (register the router)
- Test: `tests/integration/test_web_resume.py`

**Interfaces:**
- Consumes: `resume_import.extract_text`, `resume_import.UnsupportedResumeError`, `profile_dep`, `page_context`, `get_env`, `toast`
- Produces: `GET /p/{slug}/resume`, `POST /p/{slug}/resume/upload` (renders a preview, writes no `resume.md`), `POST /p/{slug}/resume` (saves)

- [ ] **Step 1: Write the failing tests**

```python
"""Upload shows a preview; only an explicit save writes resume.md."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist_web.app import create_app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def test_upload_previews_without_writing(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    r = client.post(
        "/p/david/resume/upload",
        files={"file": ("resume.md", b"# David\n\nStaff Engineer", "text/markdown")},
    )
    assert r.status_code == 200
    assert "Staff Engineer" in r.text
    assert not prof.resume_path.exists()


def test_save_writes_resume_md(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    r = client.post("/p/david/resume", data={"text": "# David\n\nStaff Engineer"})
    assert r.status_code == 200
    assert prof.resume_path.read_text() == "# David\n\nStaff Engineer"


def test_upload_keeps_the_original_file(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    client.post(
        "/p/david/resume/upload",
        files={"file": ("resume.md", b"# David", "text/markdown")},
    )
    assert prof.original_resume_path.read_bytes() == b"# David"


def test_unsupported_upload_rejected(client: TestClient) -> None:
    profiles.create("david", "David")
    r = client.post(
        "/p/david/resume/upload",
        files={"file": ("resume.rtf", b"{\\rtf1}", "application/rtf")},
    )
    assert r.status_code == 400


def test_editor_prefills_from_disk(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    prof.resume_path.write_text("# Existing resume")
    r = client.get("/p/david/resume")
    assert "# Existing resume" in r.text


def test_save_bumps_mtime_so_the_embedding_cache_misses(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    prof.resume_path.write_text("old")
    before = prof.resume_path.stat().st_mtime_ns
    client.post("/p/david/resume", data={"text": "new"})
    assert prof.resume_path.stat().st_mtime_ns != before


def test_upload_filename_cannot_escape_the_profile(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    client.post(
        "/p/david/resume/upload",
        files={"file": ("../../evil.md", b"x", "text/markdown")},
    )
    data_root = prof.db_path.parent
    assert not (data_root.parent.parent / "evil.md").exists()
    assert prof.original_resume_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/integration/test_web_resume.py -v`
Expected: FAIL — 404 on `/p/david/resume`

- [ ] **Step 3: Write `shortlist_web/routes/resume.py`**

```python
"""Resume upload, preview and editing.

Upload never writes `resume.md`. It extracts the text and hands it back for
review, because PDF extraction interleaves multi-column layouts and the only
other symptom would be quietly worse job scores — that text becomes the
embedding.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from shortlist.profiles import Profile
from shortlist.resume_import import UnsupportedResumeError, extract_text
from shortlist_web.routes._shared import get_env, page_context, profile_dep, toast

router = APIRouter()


def _render(request: Request, profile: Profile, text: str, note: str = "") -> HTMLResponse:
    html = (
        get_env(request)
        .get_template("resume.html")
        .render(**page_context(request, profile, text=text, note=note))
    )
    return HTMLResponse(html)


@router.get("/resume", response_class=HTMLResponse)
def resume_editor(request: Request, profile: Profile = Depends(profile_dep)) -> HTMLResponse:
    text = profile.resume_path.read_text() if profile.resume_path.exists() else ""
    return _render(request, profile, text)


@router.post("/resume/upload", response_class=HTMLResponse)
def upload_resume(
    request: Request,
    profile: Profile = Depends(profile_dep),
    file: UploadFile = File(...),
) -> HTMLResponse:
    """Extract and show the text. Writes nothing the pipeline reads until saved."""
    data = file.file.read()
    try:
        text = extract_text(data, file.filename or "")
    except UnsupportedResumeError as exc:
        return toast(request, str(exc), "error", code=400)
    # The uploaded filename is never used to build a path.
    profile.original_resume_path.parent.mkdir(parents=True, exist_ok=True)
    profile.original_resume_path.write_bytes(data)
    return _render(request, profile, text, note="Review the extracted text, then save.")


@router.post("/resume", response_class=HTMLResponse)
def save_resume(
    request: Request,
    profile: Profile = Depends(profile_dep),
    text: str = Form(...),
) -> HTMLResponse:
    profile.resume_path.parent.mkdir(parents=True, exist_ok=True)
    profile.resume_path.write_text(text)
    return _render(request, profile, text, note="Saved. The next rank will re-embed.")
```

- [ ] **Step 4: Register the router**

Add `resume.router` to the prefixed tuple in `shortlist_web/app.py` from Task 4 Step 4.

- [ ] **Step 5: Write `shortlist_web/templates/resume.html`**

```html
{% extends "base.html" %}
{% block title %}Resume — {{ active.display_name }}{% endblock %}
{% block content %}
<h1>Resume — {{ active.display_name }}</h1>
{% if note %}<p class="dim">{{ note }}</p>{% endif %}

<form method="post" action="/p/{{ active.slug }}/resume/upload" enctype="multipart/form-data">
  <input type="file" name="file" accept=".md,.txt,.pdf,.docx" required>
  <button type="submit">Upload</button>
  <span class="dim small">Markdown, text, PDF or DOCX, up to 2 MB. Nothing is saved
  until you press Save below.</span>
</form>

<form method="post" action="/p/{{ active.slug }}/resume">
  <textarea name="text" rows="30" spellcheck="false">{{ text }}</textarea>
  <button type="submit">Save</button>
</form>
{% endblock %}
```

- [ ] **Step 6: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_web_resume.py -v
git add shortlist_web/ tests/integration/test_web_resume.py
git commit -m "feat(web): upload, preview and edit a profile's resume"
```

---

### Task 9: YAML editors for config and prefs

**Files:**
- Modify: `shortlist_web/routes/settings.py`
- Modify: `shortlist_web/templates/settings.html`
- Test: `tests/integration/test_web_settings_edit.py`

**Interfaces:**
- Consumes: `Config`, `Prefs`, `paths.config_path`, `profile.prefs_path`, `profile_dep`, `page_context`
- Produces: `POST /p/{slug}/settings/config`, `POST /p/{slug}/settings/prefs`; a `.bak` written before each successful overwrite

- [ ] **Step 1: Write the failing tests**

```python
"""Config and prefs editing validates before it writes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import paths, profiles
from shortlist_web.app import create_app

VALID_PREFS = """\
titles: [Senior Backend Engineer]
locations: [Remote]
remote_ok: true
comp_floor_usd: 150000
exclude_keywords: []
seniority: [senior]
"""


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def test_valid_prefs_are_written(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    r = client.post("/p/david/settings/prefs", data={"text": VALID_PREFS})
    assert r.status_code == 200
    assert "Senior Backend Engineer" in prof.prefs_path.read_text()


def test_invalid_yaml_writes_nothing_and_keeps_your_text(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    prof.prefs_path.write_text(VALID_PREFS)
    r = client.post("/p/david/settings/prefs", data={"text": "titles: [unclosed\n"})
    assert r.status_code == 400
    assert "unclosed" in r.text
    assert prof.prefs_path.read_text() == VALID_PREFS


def test_constraint_violation_writes_nothing(client: TestClient) -> None:
    """titles has min_length=1, so an empty list must be rejected."""
    prof = profiles.create("david", "David")
    prof.prefs_path.write_text(VALID_PREFS)
    r = client.post(
        "/p/david/settings/prefs",
        data={"text": VALID_PREFS.replace("[Senior Backend Engineer]", "[]")},
    )
    assert r.status_code == 400
    assert prof.prefs_path.read_text() == VALID_PREFS


def test_backup_written_before_overwrite(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    prof.prefs_path.write_text(VALID_PREFS)
    client.post(
        "/p/david/settings/prefs",
        data={"text": VALID_PREFS.replace("150000", "160000")},
    )
    backup = prof.prefs_path.parent / "prefs.yaml.bak"
    assert "150000" in backup.read_text()


def test_comments_survive_a_save(client: TestClient) -> None:
    prof = profiles.create("david", "David")
    client.post("/p/david/settings/prefs", data={"text": "# my notes\n" + VALID_PREFS})
    assert prof.prefs_path.read_text().startswith("# my notes")


def test_config_editor_is_shared_not_per_profile(client: TestClient) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    r = client.get("/p/alex/settings")
    assert str(paths.config_path()) in r.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/integration/test_web_settings_edit.py -v`
Expected: FAIL — 404; the POST routes do not exist

- [ ] **Step 3: Add the save handlers to `shortlist_web/routes/settings.py`**

```python
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
```

`path.with_name(path.name + ".bak")` yields `prefs.yaml.bak`. Do not use
`with_suffix`, which would replace `.yaml` and produce `prefs.bak`.

- [ ] **Step 4: Rewrite `settings.html` with two textareas**

Each form posts to its route. When `error` is set, render it above the textarea and
keep the submitted text inside it, so nothing the user typed is lost. Show the
resolved file path above each editor, and label the config one as shared across
everyone.

- [ ] **Step 5: Convert `settings_view` to take a profile**

The GET handler gains `profile: Profile = Depends(profile_dep)`, loads
`profile.prefs_path` instead of `paths.prefs_path()`, and renders through
`page_context`.

- [ ] **Step 6: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_web_settings_edit.py -v
git add shortlist_web/ tests/integration/test_web_settings_edit.py
git commit -m "feat(web): edit config and prefs as validated yaml"
```

---

### Task 10: Combined cost view and TUI resolution

**Files:**
- Modify: `shortlist_web/routes/costs.py`
- Modify: `shortlist_web/templates/costs.html`
- Modify: `shortlist_tui/app.py`
- Test: `tests/integration/test_web_costs_combined.py`

**Interfaces:**
- Consumes: `profiles.list_profiles`, `profiles.resolve`, `store_db.connect`
- Produces: `costs.combined_totals() -> list[tuple[Profile, float]]`; TUI header showing the active profile

- [ ] **Step 1: Write the failing tests**

```python
"""The cost page shows this profile plus a combined total across everyone."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist_web.app import create_app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def _add_cost(db: Path, usd: float) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO scoring_runs (started_at, model, job_count, cost_usd) "
            "VALUES ('2026-10-13T00:00:00+00:00', 'claude-haiku-4-5', 1, ?)",
            (usd,),
        )


def test_combined_total_sums_every_profile(client: TestClient) -> None:
    david = profiles.create("david", "David")
    alex = profiles.create("alex", "Alex")
    _add_cost(david.db_path, 1.25)
    _add_cost(alex.db_path, 2.50)
    r = client.get("/p/david/costs")
    assert r.status_code == 200
    assert "3.75" in r.text
    assert "Alex" in r.text


def test_costs_page_works_with_one_profile(client: TestClient) -> None:
    david = profiles.create("david", "David")
    _add_cost(david.db_path, 0.40)
    r = client.get("/p/david/costs")
    assert "0.40" in r.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/integration/test_web_costs_combined.py -v`
Expected: FAIL — the combined section does not exist

- [ ] **Step 3: Add the fan-out to `shortlist_web/routes/costs.py`**

```python
def combined_totals() -> list[tuple[Profile, float]]:
    """Total spend per profile, read from each database.

    A fan-out read rather than a shared ledger: cost rows stay attached to the
    scoring run and tailor output that caused them, so this view cannot drift
    from the per-person numbers.
    """
    totals: list[tuple[Profile, float]] = []
    for prof in profiles.list_profiles():
        if not prof.db_path.exists():
            continue
        with store_db.connect(prof.db_path) as conn:
            runs = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM scoring_runs").fetchone()[0]
            tailors = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM tailor_outputs"
            ).fetchone()[0]
        totals.append((prof, float(runs) + float(tailors)))
    return totals
```

Convert `costs_view` to take `profile: Profile = Depends(profile_dep)`, use
`profile.db_path` for the existing per-run tables, and pass
`combined=combined_totals()` plus `combined_sum=sum(t for _p, t in combined_totals())`
into the template through `page_context`.

- [ ] **Step 4: Add the combined section to `costs.html`**

```html
<h2>All people</h2>
<table>
  <tr><th>Person</th><th>Total</th></tr>
  {% for prof, total in combined %}
  <tr><td>{{ prof.display_name }}</td><td>${{ "%.2f"|format(total) }}</td></tr>
  {% endfor %}
  <tr><th>Combined</th><th>${{ "%.2f"|format(combined_sum) }}</th></tr>
</table>
```

- [ ] **Step 5: Resolve one profile at TUI startup in `shortlist_tui/app.py`**

```python
    def __init__(self, profile: Profile | None = None) -> None:
        super().__init__()
        self.profile = profile if profile is not None else profiles.resolve()
```

Replace `paths.db_path()` with `self.profile.db_path` and `paths.prefs_path()` with
`self.profile.prefs_path` at all six sites, and show `self.profile.display_name` in
the header. Live switching in the TUI is out of scope — restarting selects a
different person.

- [ ] **Step 6: Run the full suite, lint and typecheck**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
```

Expected: `ruff` and `mypy` clean. `test_web_app.py` and `test_store.py` still fail —
Task 11 migrates their fixtures.

- [ ] **Step 7: Commit**

```bash
git add shortlist_web/ shortlist_tui/ tests/integration/test_web_costs_combined.py
git commit -m "feat: combined cost view and TUI profile resolution"
```

---

### Task 11: Migrate the existing fixtures and document the feature

**Files:**
- Modify: `tests/integration/test_web_app.py`, `tests/integration/test_store.py`
- Modify: `docs/usage.md`, `docs/architecture.md`, `README.md`
- Test: the whole suite

- [ ] **Step 1: Update the web fixtures to the profile layout**

```python
@pytest.fixture
def client(env: tuple[Path, Path]) -> tuple[TestClient, Profile]:
    prof = profiles.create("test", "Test Person")
    return TestClient(create_app()), prof
```

Every request path in that file gains the `/p/test` prefix, and `_seed` is called
with `prof.db_path` rather than `data / "db.sqlite"`.

- [ ] **Step 2: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS, no failures

- [ ] **Step 3: Check coverage against the 80% floor**

Run: `.venv/bin/python -m pytest --cov=shortlist --cov=shortlist_web --cov=shortlist_tui -q`
Expected: 80% or above. Add tests for any new module below it.

- [ ] **Step 4: Document the feature**

Add a "Multiple people" section to `docs/usage.md` covering `shortlist profile create`,
`--profile`, the `/p/<slug>/` URLs, and what is shared versus separate. Update
`docs/architecture.md` with the directory layout from the spec. Mention profiles in
the `README.md` feature list.

- [ ] **Step 5: Final verification**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```

Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add tests/ docs/ README.md
git commit -m "test: move fixtures to the profile layout; docs: document profiles"
```

---

## Self-Review

**Spec coverage**

| Spec section | Task |
|---|---|
| Layout, two trees, registry as directory listing | 1 |
| `Profile` dataclass and public surface | 1 |
| `resolve()` order, `state.yaml` | 2 |
| `paths.py` removals | 3 |
| CLI `profile` group and `--profile` | 3 |
| `profile_dep`, `/p/{slug}`, 404 on unknown slug | 4 |
| Bare-path redirect, first-run redirect | 4, 5 |
| Header switcher, create, delete with typed confirmation | 5 |
| Background task capture, status-feed tagging | 6 |
| Resume formats, extraction, size cap, content sniff | 7 |
| Upload preview before write, no traversal, mtime bump | 8 |
| YAML editors, validate-before-write, `.bak`, comments preserved | 9 |
| Combined cost fan-out | 10 |
| TUI resolution, no live switching | 10 |
| Fixture migration, isolation test, coverage floor | 4, 11 |

No spec requirement is unassigned.

**Type consistency**

`Profile` fields are used identically everywhere: `slug`, `display_name`, `db_path`,
`prefs_path`, `resume_path`, `original_resume_path`, `output_dir`. `profile_dep`
returns `Profile` in tasks 4, 6, 8, 9 and 10. After task 6 the log tuple is
`(slug, stamp, message)` in both the writer (`_append_log`) and the reader
(`/status`). `extract_text(data, filename)` keeps that argument order in tasks 7
and 8. `page_context(request, profile, **extra)` is defined in task 4 and used in
tasks 4, 8, 9 and 10.

**Known ordering constraint**

Task 3 deletes `paths.db_path()`, which breaks the web and TUI suites until tasks
4-11 land. The branch is red in between, by design: the deletion is what locates
every site that assumed a single person. Execute tasks 3 through 11 before merging.
If every intermediate commit must be green, defer only Step 3 of Task 3 to the end
and thread the CLI first.
