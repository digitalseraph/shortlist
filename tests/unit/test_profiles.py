"""Unit tests for profile creation, lookup and deletion."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortlist import profiles
from shortlist.config import load_prefs
from shortlist.store.db import current_version


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


@pytest.mark.parametrize("slug", ["david", "my-sister", "a", "a1-b2"])
def test_validate_slug_accepts_url_safe_names(slug: str) -> None:
    assert profiles.validate_slug(slug) == slug


@pytest.mark.parametrize(
    "slug",
    [
        "",
        "David",
        "has space",
        "dots.dots",
        "a" * 33,
        "../escape",
        "david\n",
        "a" * 32 + "\n",
    ],
)
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


def test_create_seeds_prefs_yaml(env: Path) -> None:
    prof = profiles.create("david", "David")
    assert prof.prefs_path.exists()
    prefs = load_prefs(prof.prefs_path)
    assert prefs.titles


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
    profiles.create("z", "Adam")
    profiles.create("a", "Zoe")
    assert [p.slug for p in profiles.list_profiles()] == ["z", "a"]


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


def test_delete_succeeds_when_config_dir_already_absent(env: Path) -> None:
    """The ignore_errors removed from delete() was only ever for this case."""
    prof = profiles.create("david", "David")
    config_root = prof.prefs_path.parent
    prof.prefs_path.unlink()
    config_root.rmdir()
    profiles.delete("david")
    assert not prof.db_path.parent.exists()
    with pytest.raises(profiles.ProfileNotFoundError):
        profiles.load("david")


def test_load_repairs_missing_config_dir(env: Path) -> None:
    """A data dir without its config counterpart is repaired, not hidden."""
    prof = profiles.create("david", "David")
    prof.prefs_path.unlink(missing_ok=True)
    prof.prefs_path.parent.rmdir()
    again = profiles.load("david")
    assert again.prefs_path.parent.is_dir()
    assert again.prefs_path.exists()
    load_prefs(again.prefs_path)


@pytest.mark.parametrize(
    "content",
    [
        "invalid: yaml: content: [",  # unparseable
        "- just\n- a\n- list\n",  # parses, but not a mapping
        "just a plain string",  # parses, but not a mapping
    ],
)
def test_load_raises_not_found_on_malformed_profile_yaml(env: Path, content: str) -> None:
    """A malformed profile.yaml must 404-equivalent (ProfileNotFoundError), not
    crash with an unhandled YAMLError or AttributeError (`str`/`list` has no
    `.get`).
    """
    prof = profiles.create("david", "David")
    (prof.db_path.parent / "profile.yaml").write_text(content)
    with pytest.raises(profiles.ProfileNotFoundError):
        profiles.load("david")


def test_load_accepts_empty_profile_yaml(env: Path) -> None:
    """An empty profile.yaml is fine - falls back to the slug as display name."""
    prof = profiles.create("david", "David")
    (prof.db_path.parent / "profile.yaml").write_text("")
    again = profiles.load("david")
    assert again.display_name == "david"


@pytest.mark.parametrize(
    "content",
    [
        "invalid: yaml: content: [",
        "- just\n- a\n- list\n",
        "just a plain string",
    ],
)
def test_list_profiles_skips_a_malformed_entry_rather_than_500ing(env: Path, content: str) -> None:
    """One profile with a malformed profile.yaml must not take down the
    listing for everyone else.
    """
    good = profiles.create("alex", "Alex")
    bad = profiles.create("david", "David")
    (bad.db_path.parent / "profile.yaml").write_text(content)
    found = profiles.list_profiles()
    assert [p.slug for p in found] == [good.slug]
