import json
import re
from pathlib import Path

import click
import httpx
import pytest
import respx
from typer.testing import CliRunner

from shortlist import profiles
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
    monkeypatch.delenv("SHORTLIST_PROFILE", raising=False)
    # A single profile so every command below resolves it automatically.
    prof = profiles.create("david", "David")
    return cfg, data, prof


def test_db_init_creates_sqlite_file(env):
    cfg, data, prof = env
    prof.db_path.unlink()  # created by profiles.create(); start from "missing"
    result = runner.invoke(app, ["db", "init"])
    assert result.exit_code == 0, result.output
    assert prof.db_path.exists()


def test_db_init_is_idempotent(env):
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["db", "init"])
    assert result.exit_code == 0


def test_db_status_reports_version(env):
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["db", "status"])
    assert result.exit_code == 0
    assert "schema version: 3" in result.output.lower()


def test_db_status_when_uninitialized(env):
    _, _, prof = env
    prof.db_path.unlink()
    result = runner.invoke(app, ["db", "status"])
    assert result.exit_code == 0
    assert "schema version: 0" in result.output.lower()


def test_db_backup_creates_file(env):
    cfg, data, prof = env
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["db", "backup"])
    assert result.exit_code == 0
    backups = list((prof.db_path.parent / "backups").glob("db-*.sqlite"))
    assert len(backups) == 1


def test_db_backup_errors_when_no_db(env):
    _, _, prof = env
    prof.db_path.unlink()
    result = runner.invoke(app, ["db", "backup"])
    assert result.exit_code == 1


def test_db_backup_is_per_profile(env):
    """Two people's backups land under their own profile tree, not one shared dir."""
    _, _, david = env
    alex = profiles.create("alex", "Alex")

    runner.invoke(app, ["db", "init", "--profile", "david"])
    runner.invoke(app, ["db", "init", "--profile", "alex"])
    runner.invoke(app, ["db", "backup", "--profile", "david"])
    runner.invoke(app, ["db", "backup", "--profile", "alex"])

    david_backups = list((david.db_path.parent / "backups").glob("db-*.sqlite"))
    alex_backups = list((alex.db_path.parent / "backups").glob("db-*.sqlite"))
    assert len(david_backups) == 1
    assert len(alex_backups) == 1
    assert david.db_path.parent != alex.db_path.parent


def test_config_init_writes_default_files(env):
    cfg, data, prof = env
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0, result.output
    assert (cfg / "config.yaml").exists()
    assert (cfg / "pdf-template.tex").exists()
    assert "wrote" in result.output.lower()

    # Both already exist now; nothing left for init to do.
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0
    assert "no changes" in result.output.lower()


def test_config_init_does_not_overwrite(env):
    cfg, data, prof = env
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
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    prefs_yaml = prof.prefs_path.read_text().replace(
        "greenhouse_companies: []",
        "greenhouse_companies:\n  - acme",
    )
    prof.prefs_path.write_text(prefs_yaml)
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
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    prof.prefs_path.write_text(
        prof.prefs_path.read_text().replace(
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
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    prof.prefs_path.write_text(
        prof.prefs_path.read_text().replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
    )
    prof.resume_path.write_text("Senior backend engineer with Python.")

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
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    prof.prefs_path.write_text(
        prof.prefs_path.read_text().replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
    )
    prof.resume_path.write_text("Senior backend engineer with Python.")

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
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["list", "--min-score", "1"])
    # No jobs yet; exit 0, empty table.
    assert result.exit_code == 0


@respx.mock
def test_fetch_iterates_all_configured_sources(env):
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    prefs_yaml = prof.prefs_path.read_text()
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
    prof.prefs_path.write_text(prefs_yaml)
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


def test_cli_tailor_writes_outputs(env, tmp_path, monkeypatch):
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    prof.prefs_path.write_text(
        prof.prefs_path.read_text().replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
    )
    prof.resume_path.write_text("R")

    runner.invoke(app, ["db", "init"])
    from datetime import UTC, datetime

    from shortlist.models import RawJob
    from shortlist.store.db import upsert_job

    j = upsert_job(
        prof.db_path,
        RawJob(
            source="greenhouse",
            external_id="acme:1",
            company="Acme Corp",
            title="Senior Backend Engineer",
            url="https://example.com/1",
            posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
            location="Remote - US",
            remote=True,
            description_md="Python services.",
        ),
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    from unittest.mock import MagicMock

    fake_anth = MagicMock()
    msg = MagicMock()
    fixture = Path(__file__).parent.parent / "fixtures/llm_responses/sonnet_tailor_sample.md"
    msg.content = [MagicMock(text=fixture.read_text())]
    msg.usage.input_tokens = 1500
    msg.usage.output_tokens = 1200
    fake_anth.messages.create.return_value = msg
    import shortlist.cli as cli_mod

    monkeypatch.setattr(cli_mod, "Anthropic", lambda **_kw: fake_anth)

    result = runner.invoke(app, ["tailor", str(j.id)])
    assert result.exit_code == 0, result.output
    dirs = list(prof.output_dir.iterdir())
    assert len(dirs) == 1
    files = {p.name for p in dirs[0].iterdir()}
    assert {"resume.md", "cover.md", "notes.md"} <= files


def test_track_status_transition(env, tmp_path):
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    runner.invoke(app, ["db", "init"])
    from datetime import UTC, datetime

    from shortlist.models import RawJob
    from shortlist.store.db import upsert_job

    j = upsert_job(
        prof.db_path,
        RawJob(
            source="greenhouse",
            external_id="acme:1",
            company="Acme",
            title="Senior Backend Engineer",
            url="https://example.com/1",
            posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
            location="Remote",
            remote=True,
        ),
    )
    result = runner.invoke(app, ["track", str(j.id), "--status", "tailored"])
    assert result.exit_code == 0
    result = runner.invoke(
        app, ["track", str(j.id), "--status", "applied", "--applied-via", "company website"]
    )
    assert result.exit_code == 0
    result = runner.invoke(app, ["track", str(j.id), "--status", "interview"])
    assert result.exit_code != 0


def test_contacts_add_list_remove(env, tmp_path):
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    runner.invoke(app, ["db", "init"])
    from datetime import UTC, datetime

    from shortlist.models import RawJob
    from shortlist.store.db import upsert_job

    j = upsert_job(
        prof.db_path,
        RawJob(
            source="greenhouse",
            external_id="acme:1",
            company="Acme",
            title="Senior Backend Engineer",
            url="https://example.com/1",
            posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
            location="Remote",
            remote=True,
        ),
    )
    runner.invoke(app, ["track", str(j.id), "--status", "tailored"])
    runner.invoke(app, ["track", str(j.id), "--status", "applied"])

    result = runner.invoke(
        app,
        [
            "contacts",
            "add",
            str(j.id),
            "--name",
            "Jane Doe",
            "--email",
            "jane@acme.com",
            "--role",
            "recruiter",
        ],
    )
    assert result.exit_code == 0

    result = runner.invoke(app, ["contacts", "list", str(j.id)])
    assert "Jane Doe" in result.output
    assert "jane@acme.com" in result.output


def test_cli_tui_help_does_not_error(env):
    result = runner.invoke(app, ["tui", "--help"])
    assert result.exit_code == 0
    assert "TUI" in result.output or "tui" in result.output.lower()
    # The TUI has no in-app profile switcher, so --profile is its only way
    # to pick a person; every other data command has it too. Unstyled
    # because Rich colours help on GitHub Actions, splitting "--profile".
    assert "--profile" in click.unstyle(result.output)


def test_cli_tui_exits_cleanly_with_no_profiles(tmp_path, monkeypatch):
    """No profiles yet must exit with a message, not a traceback from __init__."""
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("SHORTLIST_PROFILE", raising=False)
    result = runner.invoke(app, ["tui"])
    assert result.exit_code == 1
    # A clean `_resolve` exit prints just the message and raises typer.Exit,
    # not an uncaught ProfileNotFoundError traceback.
    assert "no profiles yet" in result.output
    assert "Traceback" not in result.output


def test_fetch_skips_source_in_cooldown(env, monkeypatch):
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    prof.prefs_path.write_text(
        prof.prefs_path.read_text().replace(
            "indeed_queries: []",
            "indeed_queries:\n  - python backend",
        )
    )
    runner.invoke(app, ["db", "init"])
    from datetime import UTC, datetime, timedelta

    from shortlist.store.db import mark_source_cooldown

    mark_source_cooldown(
        prof.db_path,
        "indeed",
        until=datetime.now(UTC) + timedelta(hours=24),
    )

    result = runner.invoke(app, ["fetch"])
    assert result.exit_code == 0, result.output
    assert (
        "cooldown" in result.output.lower()
        or "cooled" in result.output.lower()
        or "skipping" in result.output.lower()
    )


def test_sources_clear_cooldown_cli(env):
    cfg, data, prof = env
    runner.invoke(app, ["db", "init"])
    from datetime import UTC, datetime, timedelta

    from shortlist.store.db import is_source_in_cooldown, mark_source_cooldown

    mark_source_cooldown(prof.db_path, "indeed", until=datetime.now(UTC) + timedelta(hours=24))
    assert is_source_in_cooldown(prof.db_path, "indeed") is True

    result = runner.invoke(app, ["sources", "clear-cooldown", "indeed"])
    assert result.exit_code == 0
    assert is_source_in_cooldown(prof.db_path, "indeed") is False


def test_fetch_with_curated_sources_runs_no_errors(env, monkeypatch):
    """Smoke: enabling HN + RemoteOK + RSS doesn't crash fetch (mocked)."""
    cfg, data, prof = env
    runner.invoke(app, ["config", "init"])
    prefs_yaml = (
        prof.prefs_path.read_text()
        .replace("hn_enabled: false", "hn_enabled: true")
        .replace("remoteok_enabled: false", "remoteok_enabled: true")
        .replace("rss_urls: []", "rss_urls:\n  - https://example.invalid/feed.rss")
    )
    prof.prefs_path.write_text(prefs_yaml)
    runner.invoke(app, ["db", "init"])

    class _Stub:
        def __init__(self, name):
            self.name = name

        def fetch(self, since=None):
            return iter([])

    import shortlist.cli as cli_mod

    monkeypatch.setattr(cli_mod, "HNWhoHiringSource", lambda: _Stub("hn_who_hiring"))
    monkeypatch.setattr(cli_mod, "RemoteOKSource", lambda: _Stub("remoteok"))
    monkeypatch.setattr(cli_mod, "RSSSource", lambda urls: _Stub("rss"))

    result = runner.invoke(app, ["fetch"])
    assert result.exit_code == 0, result.output
