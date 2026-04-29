from shortlist import paths


def test_default_config_path(monkeypatch):
    monkeypatch.delenv("SHORTLIST_CONFIG_HOME", raising=False)
    assert paths.config_dir().name == "shortlist"


def test_env_overrides_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path))
    assert paths.config_dir() == tmp_path


def test_env_overrides_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path))
    assert paths.data_dir() == tmp_path


def test_db_path_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path))
    assert paths.db_path() == tmp_path / "db.sqlite"
