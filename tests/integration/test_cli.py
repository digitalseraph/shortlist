from pathlib import Path

import pytest
from typer.testing import CliRunner

from shortlist.cli import app

runner = CliRunner()


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
    assert "schema version: 1" in result.output.lower()


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
