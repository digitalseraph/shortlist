"""First-run, creation, switching and deletion screens."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from shortlist import profiles, state
from shortlist_web.app import create_app
from shortlist_web.routes._shared import switch_suffix


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


def test_switcher_rewrites_the_slug_in_the_current_path(client: TestClient) -> None:
    """Switching from Costs must stay on Costs for the other person, not drop
    them on the job list - the switcher rewrites the slug, not the path.
    """
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    r = client.get("/p/david/costs")
    assert '/p/alex/costs"' in r.text


def test_switcher_falls_back_to_job_list_on_a_page_outside_the_profile_prefix(
    client: TestClient,
) -> None:
    """profiles_list.html ("/profiles") also extends a shared layout but is
    not a profile-scoped page - switch_suffix must not be asked to map a path
    that was never under /p/<slug>/ in the first place, and should fall back
    cleanly rather than produce a broken URL.
    """
    david = profiles.create("david", "David")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/profiles",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)
    assert switch_suffix(request, david) == "/"


def test_delete_requires_matching_display_name(client: TestClient) -> None:
    profiles.create("david", "David")
    wrong = client.post("/profiles/david/delete", data={"confirm": "Dave"})
    assert wrong.status_code == 400
    assert profiles.load("david").slug == "david"

    right = client.post("/profiles/david/delete", data={"confirm": "David"}, follow_redirects=False)
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

    right = client.post("/profiles/david/delete", data={"confirm": "David"}, follow_redirects=False)
    assert right.status_code == 303
    assert profiles.list_profiles() == []


def test_delete_rejects_malformed_slug_with_404(client: TestClient) -> None:
    r = client.post("/profiles/Has Space/delete", data={"confirm": "whatever"})
    assert r.status_code == 404


@pytest.mark.parametrize(
    "content",
    [
        "invalid: yaml: content: [",
        "- just\n- a\n- list\n",
        "just a plain string",
    ],
)
def test_a_malformed_profile_does_not_500_other_pages(client: TestClient, content: str) -> None:
    """One profile's unreadable profile.yaml must not take down every page -
    including /profiles, the only screen from which it could be deleted.
    """
    david = profiles.create("david", "David")
    broken = profiles.create("broken", "Broken")
    (broken.db_path.parent / "profile.yaml").write_text(content)

    assert client.get(f"/p/{david.slug}/").status_code == 200
    assert client.get("/profiles").status_code == 200


def test_viewing_a_profile_records_it_as_last_used(client: TestClient) -> None:
    """state.yaml must track the last person *viewed*, not the last created -
    creating david then alex, then only ever viewing david, must leave david
    recorded even though alex was created more recently.
    """
    profiles.create("david", "David")
    profiles.create("alex", "Alex")
    assert client.get("/p/david/").status_code == 200
    assert state.get_last_profile() == "david"


def test_viewing_the_same_profile_twice_does_not_rewrite_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    profiles.create("david", "David")
    assert client.get("/p/david/").status_code == 200

    calls: list[str] = []
    monkeypatch.setattr(
        "shortlist_web.routes._shared.state.set_last_profile",
        lambda slug: calls.append(slug),
    )
    assert client.get("/p/david/").status_code == 200
    assert calls == []
