import json
import re
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from shortlist.cli import app

runner = CliRunner()

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = tmp_path / "config"
    data = tmp_path / "data"
    cfg.mkdir()
    data.mkdir()
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(cfg))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(data))
    return cfg, data


def test_db_init_creates_sqlite_file(env):
    cfg, data = env
    result = runner.invoke(app, ["db", "init"])
    assert result.exit_code == 0, result.output
    assert (data / "db.sqlite").exists()


def test_db_init_is_idempotent(env):
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["db", "init"])
    assert result.exit_code == 0


def test_db_status_reports_version(env):
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["db", "status"])
    assert result.exit_code == 0
    assert "schema version: 2" in result.output.lower()


def test_db_status_when_uninitialized(env):
    result = runner.invoke(app, ["db", "status"])
    assert result.exit_code == 0
    assert "schema version: 0" in result.output.lower()


def test_db_backup_creates_file(env):
    cfg, data = env
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["db", "backup"])
    assert result.exit_code == 0
    backups = list((data / "backups").glob("db-*.sqlite"))
    assert len(backups) == 1


def test_db_backup_errors_when_no_db(env):
    result = runner.invoke(app, ["db", "backup"])
    assert result.exit_code == 1


def test_config_init_writes_default_files(env):
    cfg, data = env
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0, result.output
    assert (cfg / "config.yaml").exists()
    assert (cfg / "prefs.yaml").exists()


def test_config_init_does_not_overwrite(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "config.yaml").write_text("# user-edited\n")
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0
    assert "# user-edited" in (cfg / "config.yaml").read_text()


def test_config_show_after_init(env):
    runner.invoke(app, ["config", "init"])
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "anthropic:" in result.output


@respx.mock
def test_fetch_persists_jobs(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    prefs_yaml = (
        (cfg / "prefs.yaml")
        .read_text()
        .replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
    )
    (cfg / "prefs.yaml").write_text(prefs_yaml)
    runner.invoke(app, ["db", "init"])

    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))

    result = runner.invoke(app, ["fetch"])
    assert result.exit_code == 0, result.output
    assert "fetched 2 jobs" in result.output.lower()

    # Re-fetch is idempotent.
    result = runner.invoke(app, ["fetch"])
    assert result.exit_code == 0


@respx.mock
def test_fetch_handles_source_error_gracefully(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "prefs.yaml").write_text(
        (cfg / "prefs.yaml")
        .read_text()
        .replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - nopecorp",
        )
    )
    runner.invoke(app, ["db", "init"])

    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/nopecorp/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(500))

    result = runner.invoke(app, ["fetch"])
    # Source error must not crash the CLI.
    assert result.exit_code == 0
    assert "0 jobs" in result.output.lower() or "error" in result.output.lower()


@respx.mock
def test_rank_no_llm_runs_pipeline(env, tmp_path, monkeypatch):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "prefs.yaml").write_text(
        (cfg / "prefs.yaml")
        .read_text()
        .replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
    )
    resume = tmp_path / "resume.md"
    resume.write_text("Senior backend engineer with Python.")
    cfg_text = (
        (cfg / "config.yaml").read_text().replace("resume: ~/jobs/resume.md", f"resume: {resume}")
    )
    (cfg / "config.yaml").write_text(cfg_text)

    from unittest.mock import MagicMock

    import numpy as np

    fake = MagicMock()

    def _enc(t, **_):
        rng = np.random.default_rng(sum(ord(c) for c in (t if isinstance(t, str) else t[0])))
        v = rng.standard_normal(384).astype("float32")
        return v / np.linalg.norm(v)

    fake.encode = _enc

    import shortlist.ranker.embeddings as emb

    monkeypatch.setattr(emb, "_load_model", lambda *_a, **_k: fake)

    runner.invoke(app, ["db", "init"])
    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))
    runner.invoke(app, ["fetch"])

    result = runner.invoke(app, ["rank", "--no-llm"])
    assert result.exit_code == 0, result.output
    assert "filtered=" in result.output
    assert "cost=$0.0000" in result.output


@respx.mock
def test_list_shows_top_jobs(env, tmp_path, monkeypatch):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "prefs.yaml").write_text(
        (cfg / "prefs.yaml")
        .read_text()
        .replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
    )
    resume = tmp_path / "resume.md"
    resume.write_text("Senior backend engineer with Python.")
    (cfg / "config.yaml").write_text(
        (cfg / "config.yaml").read_text().replace("resume: ~/jobs/resume.md", f"resume: {resume}")
    )

    from unittest.mock import MagicMock

    import numpy as np

    fake = MagicMock()

    def _enc(t, **_):
        rng = np.random.default_rng(sum(ord(c) for c in (t if isinstance(t, str) else t[0])))
        v = rng.standard_normal(384).astype("float32")
        return v / np.linalg.norm(v)

    fake.encode = _enc

    import shortlist.ranker.embeddings as emb

    monkeypatch.setattr(emb, "_load_model", lambda *_a, **_k: fake)

    runner.invoke(app, ["db", "init"])
    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))
    runner.invoke(app, ["fetch"])
    runner.invoke(app, ["rank", "--no-llm"])

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Senior Backend Engineer" in result.output
    assert "Acme" in result.output


def test_list_min_score_filter(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["list", "--min-score", "1"])
    # No jobs yet; exit 0, empty table.
    assert result.exit_code == 0


@respx.mock
def test_fetch_iterates_all_configured_sources(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    prefs_yaml = (cfg / "prefs.yaml").read_text()
    prefs_yaml = (
        prefs_yaml.replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
        .replace(
            "lever_companies: []",
            "lever_companies:\n  - acme",
        )
        .replace(
            "ashby_companies: []",
            "ashby_companies:\n  - acme",
        )
    )
    (cfg / "prefs.yaml").write_text(prefs_yaml)
    runner.invoke(app, ["db", "init"])

    gh = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    lever = json.loads((FIXTURES / "lever_acme.json").read_text())
    ashby = json.loads((FIXTURES / "ashby_acme.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=gh))
    respx.get(
        "https://api.lever.co/v0/postings/acme",
        params={"mode": "json"},
    ).mock(return_value=httpx.Response(200, json=lever))
    respx.get(re.compile(r"^https://api\.ashbyhq\.com/posting-api/job-board/acme")).mock(
        return_value=httpx.Response(200, json=ashby)
    )

    result = runner.invoke(app, ["fetch"])
    assert result.exit_code == 0, result.output
    # 2 GH + 2 Lever + 2 Ashby = 6
    assert "fetched 6 jobs" in result.output.lower()
