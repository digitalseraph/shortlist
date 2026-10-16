"""Place suggestions for the location inputs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from shortlist_web.app import create_app


def test_places_suggests_brunswick() -> None:
    r = TestClient(create_app()).get("/places", params={"q": "brun"})
    assert r.status_code == 200
    assert '<option value="Brunswick, GA">' in r.text


def test_places_short_query_is_empty() -> None:
    assert TestClient(create_app()).get("/places", params={"q": "b"}).text == ""
