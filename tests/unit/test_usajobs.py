"""USAJOBS search parsing, search parameters and fetching."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from shortlist.sources.curated.usajobs import (
    EMAIL_ENV,
    KEY_ENV,
    USAJobsSource,
    parse_item,
    parse_payload,
)

ITEM = {
    "MatchedObjectId": "812345600",
    "MatchedObjectDescriptor": {
        "PositionTitle": "Teacher (French)",
        "PositionURI": "https://www.usajobs.gov/job/812345600",
        "OrganizationName": "Department of Defense Education Activity",
        "PositionLocationDisplay": "Brunswick, Georgia",
        "PositionLocation": [{"LocationName": "Brunswick, Georgia"}],
        "PositionRemuneration": [
            {"MinimumRange": "52000.0", "MaximumRange": "101000.0", "RateIntervalCode": "PA"}
        ],
        "PublicationStartDate": "2026-10-10T00:00:00.0000",
        "UserArea": {"Details": {"JobSummary": "Teach French to students."}},
    },
}


def _with(**changes: object) -> dict[str, object]:
    return {**ITEM, "MatchedObjectDescriptor": {**ITEM["MatchedObjectDescriptor"], **changes}}


def test_parses_an_item() -> None:
    job = parse_item(ITEM)
    assert job is not None
    assert job.source == "usajobs"
    assert job.external_id == "812345600"
    assert job.title == "Teacher (French)"
    assert job.company == "Department of Defense Education Activity"
    assert job.posted_at == datetime(2026, 10, 10, tzinfo=UTC)
    assert (job.comp_min, job.comp_max) == (52000, 101000)
    assert job.description_md == "Teach French to students."
    assert job.remote is False


def test_states_are_abbreviated_so_prefs_locations_match() -> None:
    two = [{"LocationName": "Brunswick, Georgia"}, {"LocationName": "Fort Novosel, Alabama"}]
    job = parse_item(_with(PositionLocation=two))
    assert job is not None
    assert job.location == "Brunswick, GA; Fort Novosel, AL"


def test_overseas_location_is_kept_as_is() -> None:
    job = parse_item(_with(PositionLocation=[{"LocationName": "Wiesbaden, Germany"}]))
    assert job is not None
    assert job.location == "Wiesbaden, Germany"


def test_display_location_is_used_without_a_location_list() -> None:
    job = parse_item(_with(PositionLocation=[]))
    assert job is not None
    assert job.location == "Brunswick, GA"


def test_hourly_pay_is_not_read_as_salary() -> None:
    hourly = [{"MinimumRange": "20", "MaximumRange": "30", "RateIntervalCode": "PH"}]
    job = parse_item(_with(PositionRemuneration=hourly))
    assert job is not None
    assert (job.comp_min, job.comp_max) == (None, None)


def test_item_without_required_fields_is_skipped() -> None:
    jobs = parse_payload({"SearchResult": {"SearchResultItems": [{"x": 1}, ITEM]}})
    assert [j.external_id for j in jobs] == ["812345600"]


def test_search_params_cover_each_query_and_location() -> None:
    src = USAJobsSource(queries=["French teacher"], locations=["Brunswick, GA", "Remote"])
    assert src.search_params() == [
        {"Keyword": "French teacher", "ResultsPerPage": "500", "LocationName": "Brunswick, GA"},
        {"Keyword": "French teacher", "ResultsPerPage": "500", "RemoteIndicator": "True"},
    ]


def test_no_locations_searches_nationwide() -> None:
    assert USAJobsSource(queries=["teacher"]).search_params() == [
        {"Keyword": "teacher", "ResultsPerPage": "500"}
    ]


def test_fetch_without_key_explains_what_to_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.delenv(EMAIL_ENV, raising=False)
    with pytest.raises(RuntimeError, match=KEY_ENV):
        USAJobsSource(queries=["teacher"]).fetch(since=None)


@respx.mock
def test_fetch_sends_key_headers_and_marks_remote_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(KEY_ENV, "test-key")
    monkeypatch.setenv(EMAIL_ENV, "me@example.com")
    route = respx.get("https://data.usajobs.gov/api/search").mock(
        return_value=httpx.Response(200, json={"SearchResult": {"SearchResultItems": [ITEM]}})
    )
    jobs = list(USAJobsSource(queries=["teacher"], locations=["Remote"]).fetch(since=None))
    request = route.calls.last.request
    assert request.headers["Authorization-Key"] == "test-key"
    assert request.headers["User-Agent"] == "me@example.com"
    assert request.url.params["RemoteIndicator"] == "True"
    assert [j.remote for j in jobs] == [True]
