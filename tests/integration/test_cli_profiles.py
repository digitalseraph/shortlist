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
