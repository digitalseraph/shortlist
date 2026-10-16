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

VALID_CONFIG = """\
anthropic:
  key_source: env
  key_env_var: ANTHROPIC_API_KEY
budget:
  daily_usd: 5.00
  monthly_usd: 60.00
paths:
  resume: ~/jobs/resume.md
  output_dir: ~/jobs
sources: {}
ranker:
  embedding_model: BAAI/bge-small-en-v1.5
  rerank_model: claude-haiku-4-5-20251001
tailor:
  model: claude-sonnet-4-6
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


def test_invalid_config_yaml_writes_nothing_and_keeps_your_text(client: TestClient) -> None:
    profiles.create("david", "David")
    paths.config_path().write_text(VALID_CONFIG)
    r = client.post("/p/david/settings/config", data={"text": "budget: [unclosed\n"})
    assert r.status_code == 400
    assert "unclosed" in r.text
    assert paths.config_path().read_text() == VALID_CONFIG


def test_config_constraint_violation_writes_nothing(client: TestClient) -> None:
    """budget.daily_usd has ge=0, so a negative value must be rejected."""
    profiles.create("david", "David")
    paths.config_path().write_text(VALID_CONFIG)
    r = client.post(
        "/p/david/settings/config",
        data={"text": VALID_CONFIG.replace("daily_usd: 5.00", "daily_usd: -5.00")},
    )
    assert r.status_code == 400
    assert paths.config_path().read_text() == VALID_CONFIG


def test_config_backup_written_before_overwrite(client: TestClient) -> None:
    profiles.create("david", "David")
    paths.config_path().write_text(VALID_CONFIG)
    client.post(
        "/p/david/settings/config",
        data={"text": VALID_CONFIG.replace("daily_usd: 5.00", "daily_usd: 6.00")},
    )
    backup = paths.config_path().parent / "config.yaml.bak"
    assert "daily_usd: 5.00" in backup.read_text()


def test_config_comment_survives_a_save(client: TestClient) -> None:
    profiles.create("david", "David")
    r = client.post("/p/david/settings/config", data={"text": "# my notes\n" + VALID_CONFIG})
    assert r.status_code == 200
    assert paths.config_path().read_text().startswith("# my notes")


def test_config_save_writes_the_shared_path_not_a_profile_directory(client: TestClient) -> None:
    profiles.create("david", "David")
    config_root, data_root = profiles.profile_dirs("david")
    client.post("/p/david/settings/config", data={"text": VALID_CONFIG})
    assert paths.config_path().read_text() == VALID_CONFIG
    assert not (config_root / "config.yaml").exists()
    assert not (data_root / "config.yaml").exists()
