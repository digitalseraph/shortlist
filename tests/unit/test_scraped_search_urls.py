"""Search URL construction for the scraped sources (no browser)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from shortlist.sources.scraped.glassdoor import GlassdoorSource
from shortlist.sources.scraped.indeed import IndeedSource
from shortlist.sources.scraped.linkedin import LinkedInSource


def _qs(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_indeed_runs_each_query_in_each_location() -> None:
    src = IndeedSource(queries=["French teacher", "tutor"], locations=["Brunswick, GA", "Remote"])
    got = [(q, _qs(u)["l"]) for q, u in src.search_urls()]
    assert got == [
        ("French teacher", "Brunswick, GA"),
        ("French teacher", "Remote"),
        ("tutor", "Brunswick, GA"),
        ("tutor", "Remote"),
    ]


def test_indeed_defaults_to_remote() -> None:
    ((_, url),) = IndeedSource(queries=["x"], locations=[]).search_urls()
    assert _qs(url)["l"] == "Remote"


def test_glassdoor_runs_each_query_in_each_location() -> None:
    urls = GlassdoorSource(queries=["x"], locations=["Brunswick, GA", "Remote"]).search_urls()
    assert [_qs(u)["locKeyword"] for u in urls] == ["Brunswick, GA", "Remote"]


def test_glassdoor_defaults_to_remote() -> None:
    (url,) = GlassdoorSource(queries=["x"]).search_urls()
    assert _qs(url)["locKeyword"] == "Remote"


def test_linkedin_pages_per_search() -> None:
    searches = LinkedInSource(queries=["x"], locations=["Brunswick, GA"], max_pages=2).search_urls()
    assert len(searches) == 1
    assert [_qs(u)["start"] for u in searches[0]] == ["0", "25"]
    assert _qs(searches[0][0])["location"] == "Brunswick, GA"


def test_linkedin_remote_uses_remote_filter() -> None:
    (pages,) = LinkedInSource(queries=["x"], locations=["Remote"], max_pages=1).search_urls()
    params = _qs(pages[0])
    assert params["location"] == "United States"
    assert params["f_WT"] == "2"


def test_linkedin_defaults_to_united_states_without_remote_filter() -> None:
    (pages,) = LinkedInSource(queries=["x"], max_pages=1).search_urls()
    params = _qs(pages[0])
    assert params["location"] == "United States"
    assert "f_WT" not in params
