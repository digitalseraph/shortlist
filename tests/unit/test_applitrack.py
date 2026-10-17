"""AppliTrack postings parsing and fetching."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from shortlist.sources.ats.applitrack import (
    AppliTrackSource,
    parse_postings,
    postings_url,
    unwrap,
)

SCRIPT = (Path(__file__).parent.parent / "fixtures" / "applitrack_output.txt").read_text()


def test_unwrap_joins_document_write_calls_and_unescapes_quotes() -> None:
    assert unwrap("document.write('<a id=\\'x\\'>');\ndocument.write('</a>');") == "<a id='x'></a>"


def test_parses_each_posting() -> None:
    jobs = parse_postings(SCRIPT, district="example")
    assert [j.external_id for j in jobs] == ["example:5010", "example:4865"]
    french = jobs[0]
    assert french.source == "applitrack"
    assert french.title == "French Teacher - School Year 26/27"
    assert french.company == "Example County Schools"
    assert french.posted_at == datetime(2026, 10, 12, tzinfo=UTC)
    assert french.description_md == "Position type: High School Teaching/Foreign Language"
    assert str(french.url) == (
        "https://www.applitrack.com/example/onlineapp/default.aspx"
        "?AppliTrackJobId=5010&AppliTrackLayoutMode=detail&AppliTrackViewPosting=1"
    )
    assert french.remote is False


def test_location_names_the_district_so_prefs_can_match_it() -> None:
    french, bus = parse_postings(SCRIPT, district="example")
    assert french.location == "Brunswick High School, Example County Schools"
    assert bus.location == "Example County Schools"  # no Location item


def test_missing_district_name_falls_back_to_code() -> None:
    script = SCRIPT.replace("I found at Example County Schools.", "")
    assert parse_postings(script, district="example")[0].company == "example"


@respx.mock
def test_fetch_reads_every_district_and_skips_failures() -> None:
    respx.get(postings_url("good")).mock(return_value=httpx.Response(200, text=SCRIPT))
    respx.get(postings_url("gone")).mock(return_value=httpx.Response(404))
    jobs = list(AppliTrackSource(districts=["gone", "good"]).fetch(since=None))
    assert [j.external_id for j in jobs] == ["good:5010", "good:4865"]
