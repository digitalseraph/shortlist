"""The settings forms validate, save and re-render like the YAML editors."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from shortlist import paths, profiles
from shortlist.config import DEFAULT_CONFIG_YAML, load_prefs
from shortlist_web.app import create_app

PREFS_FORM = {
    "titles": "French\nWorld Language",
    "seniority": "",
    "locations": ["Brunswick, GA", "St. Simons"],
    "search_locations": ["brunswick, ga", "Remote"],
    "remote_ok": "on",
    "comp_floor_usd": "0",
    "indeed_queries": "French teacher",
}

CONFIG_FORM = {
    "key_env_var": "ANTHROPIC_API_KEY",
    "daily_usd": "6",
    "monthly_usd": "60",
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "rerank_model": "claude-haiku-4-5-20251001",
    "top_k_for_llm_rerank": "30",
    "tailor_model": "claude-sonnet-4-6",
    "cover_paragraphs": "3",
    "pdf_template": "",
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    profiles.create("kat", "Katherine")
    return TestClient(create_app())


def _write_default_config() -> None:
    paths.config_path().parent.mkdir(parents=True, exist_ok=True)
    paths.config_path().write_text(DEFAULT_CONFIG_YAML)


def test_prefs_form_saves_and_reloads(client: TestClient) -> None:
    r = client.post("/p/kat/settings/prefs/form", data=PREFS_FORM)
    assert r.status_code == 200
    prefs = load_prefs(profiles.load("kat").prefs_path)
    assert prefs.titles == ["French", "World Language"]
    assert prefs.search_locations == ["Brunswick, GA", "Remote"]
    assert prefs.seniority == []
    assert prefs.indeed_queries == ["French teacher"]
    page = client.get("/p/kat/settings").text
    assert 'value="Brunswick, GA"' in page
    assert 'value="St. Simons"' in page


def test_prefs_form_bad_search_location_writes_nothing(client: TestClient) -> None:
    path = profiles.load("kat").prefs_path
    before = path.read_text()
    r = client.post(
        "/p/kat/settings/prefs/form", data=PREFS_FORM | {"search_locations": ["Brunswik, GA"]}
    )
    assert r.status_code == 400
    assert "not a known place: &#39;Brunswik, GA&#39;" in r.text
    assert 'value="Brunswik, GA"' in r.text  # submitted value kept
    assert path.read_text() == before


def test_prefs_form_writes_backup(client: TestClient) -> None:
    path = profiles.load("kat").prefs_path
    before = path.read_text()
    client.post("/p/kat/settings/prefs/form", data=PREFS_FORM)
    assert (path.parent / "prefs.yaml.bak").read_text() == before


def test_settings_page_shows_forms_and_advanced_yaml(client: TestClient) -> None:
    page = client.get("/p/kat/settings").text
    assert 'action="/p/kat/settings/prefs/form"' in page
    assert 'action="/p/kat/settings/config/form"' in page
    assert "<details" in page
    assert 'action="/p/kat/settings/prefs"' in page  # raw editor still there


def test_invalid_prefs_file_still_renders_page(client: TestClient) -> None:
    profiles.load("kat").prefs_path.write_text("titles: [unclosed\n")
    r = client.get("/p/kat/settings")
    assert r.status_code == 200
    assert "fix it under Advanced" in r.text


def test_config_form_keeps_fields_it_does_not_show(client: TestClient) -> None:
    _write_default_config()
    r = client.post("/p/kat/settings/config/form", data=CONFIG_FORM)
    assert r.status_code == 200
    saved = yaml.safe_load(paths.config_path().read_text())
    before = yaml.safe_load(DEFAULT_CONFIG_YAML)
    assert saved["sources"] == before["sources"]
    assert saved["anthropic"]["key_source"] == "env"
    assert saved["budget"]["daily_usd"] == 6.0
    assert "pdf_template" not in saved.get("paths", {})


def test_config_form_bad_number_writes_nothing(client: TestClient) -> None:
    _write_default_config()
    r = client.post("/p/kat/settings/config/form", data=CONFIG_FORM | {"daily_usd": "-1"})
    assert r.status_code == 400
    assert 'value="-1"' in r.text
    assert paths.config_path().read_text() == DEFAULT_CONFIG_YAML


def test_config_form_creates_missing_file(client: TestClient) -> None:
    assert not paths.config_path().exists()
    assert client.post("/p/kat/settings/config/form", data=CONFIG_FORM).status_code == 200
    assert paths.config_path().exists()


def test_config_form_writes_backup(client: TestClient) -> None:
    _write_default_config()
    client.post("/p/kat/settings/config/form", data=CONFIG_FORM)
    assert (paths.config_path().parent / "config.yaml.bak").read_text() == DEFAULT_CONFIG_YAML


def test_successful_save_redirects_to_the_settings_page(client: TestClient) -> None:
    """Post/redirect/get: refresh and the profile switcher then act on a GET page."""
    r = client.post("/p/kat/settings/prefs/form", data=PREFS_FORM, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/p/kat/settings?saved=1"
    assert "Saved." in client.get(r.headers["location"]).text
