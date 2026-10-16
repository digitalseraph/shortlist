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
