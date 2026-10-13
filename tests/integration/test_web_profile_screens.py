"""First-run, creation, switching and deletion screens."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist_web.app import create_app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("SHORTLIST_PROFILE", raising=False)
    return tmp_path


@pytest.fixture
def client(env: Path) -> TestClient:
    return TestClient(create_app())


def test_first_run_screen_renders_with_no_profiles(client: TestClient) -> None:
    r = client.get("/profiles/new")
    assert r.status_code == 200
    assert "name" in r.text.lower()


def test_create_profile_redirects_into_it(client: TestClient) -> None:
    r = client.post(
        "/profiles", data={"slug": "david", "display_name": "David"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/p/david/"
    assert profiles.load("david").display_name == "David"


def test_create_rejects_bad_slug_without_writing(client: TestClient) -> None:
    r = client.post("/profiles", data={"slug": "Has Space", "display_name": "X"})
    assert r.status_code == 400
    assert profiles.list_profiles() == []


def test_create_rejects_duplicate(client: TestClient) -> None:
    profiles.create("david", "David")
    r = client.post("/profiles", data={"slug": "david", "display_name": "Again"})
    assert r.status_code == 400


def test_switcher_lists_every_profile(client: TestClient) -> None:
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    r = client.get("/p/david/applications")
    assert "Alex" in r.text
    assert "/p/alex/" in r.text


def test_delete_requires_matching_display_name(client: TestClient) -> None:
    profiles.create("david", "David")
    wrong = client.post("/profiles/david/delete", data={"confirm": "Dave"})
    assert wrong.status_code == 400
    assert profiles.load("david").slug == "david"

    right = client.post(
        "/profiles/david/delete", data={"confirm": "David"}, follow_redirects=False
    )
    assert right.status_code == 303
    assert profiles.list_profiles() == []


def test_create_rejects_blank_display_name_without_writing(client: TestClient) -> None:
    r = client.post("/profiles", data={"slug": "david", "display_name": "   "})
    assert r.status_code == 400
    assert profiles.list_profiles() == []


def test_create_trims_display_name_and_trimmed_form_deletes_it(client: TestClient) -> None:
    r = client.post(
        "/profiles", data={"slug": "david", "display_name": "  David  "}, follow_redirects=False
    )
    assert r.status_code == 303
    assert profiles.load("david").display_name == "David"

    right = client.post(
        "/profiles/david/delete", data={"confirm": "David"}, follow_redirects=False
    )
    assert right.status_code == 303
    assert profiles.list_profiles() == []


def test_delete_rejects_malformed_slug_with_404(client: TestClient) -> None:
    r = client.post("/profiles/Has Space/delete", data={"confirm": "whatever"})
    assert r.status_code == 404
