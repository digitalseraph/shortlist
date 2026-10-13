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


def test_get_last_profile_handles_malformed_yaml(env: Path) -> None:
    from shortlist import paths
    state_file = paths.config_dir() / "state.yaml"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("invalid: yaml: content: [")
    assert state.get_last_profile() is None


def test_get_last_profile_handles_non_mapping_yaml(env: Path) -> None:
    from shortlist import paths
    state_file = paths.config_dir() / "state.yaml"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("just-a-string")
    assert state.get_last_profile() is None


def test_set_last_profile_repairs_corrupt_state(env: Path) -> None:
    from shortlist import paths
    state_file = paths.config_dir() / "state.yaml"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("invalid: yaml: [")
    state.set_last_profile("alice")
    assert state.get_last_profile() == "alice"


def test_set_last_profile_preserves_unrelated_keys(env: Path) -> None:
    import yaml

    from shortlist import paths

    state_file = paths.config_dir() / "state.yaml"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(yaml.safe_dump({"other_key": "other_value"}, sort_keys=False))
    state.set_last_profile("bob")
    data = yaml.safe_load(state_file.read_text())
    assert data["last_profile"] == "bob"
    assert data["other_key"] == "other_value"
