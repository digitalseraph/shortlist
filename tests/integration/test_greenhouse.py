import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from shortlist.models import RawJob
from shortlist.sources.ats.greenhouse import GreenhouseClient, GreenhouseSource, _normalize

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_greenhouse_fetch_jobs_single_page():
    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))

    client = GreenhouseClient()
    raw_payloads = list(client.fetch_company("acme"))
    assert len(raw_payloads) == 2
    assert raw_payloads[0]["id"] == 4521


@respx.mock
def test_greenhouse_fetch_retries_on_500():
    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    route = respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(200, json=payload),
        ]
    )

    client = GreenhouseClient()
    raw_payloads = list(client.fetch_company("acme"))
    assert len(raw_payloads) == 2
    assert route.call_count == 3


@respx.mock
def test_greenhouse_fetch_404_returns_empty():
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/nopecorp/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(404))

    client = GreenhouseClient()
    raw_payloads = list(client.fetch_company("nopecorp"))
    assert raw_payloads == []


def _sample_job() -> dict:
    return {
        "id": 4521,
        "title": "Senior Backend Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/4521",
        "updated_at": "2026-04-25T09:00:00-04:00",
        "location": {"name": "Remote - US"},
        "content": "%3Cp%3EBuild stuff.%3C%2Fp%3E",
    }


def test_normalize_returns_rawjob():
    raw = _normalize(_sample_job(), company="Acme")
    assert isinstance(raw, RawJob)
    assert raw.source == "greenhouse"
    assert raw.external_id == "4521"
    assert raw.company == "Acme"
    assert raw.title == "Senior Backend Engineer"
    assert raw.location == "Remote - US"
    assert raw.remote is True
    assert raw.posted_at == datetime(2026, 4, 25, 13, 0, tzinfo=UTC)
    assert "Build stuff." in (raw.description_md or "")


def test_normalize_remote_false_when_location_lacks_remote_word():
    job = _sample_job()
    job["location"] = {"name": "Atlanta, GA"}
    raw = _normalize(job, company="Acme")
    assert raw.remote is False


@respx.mock
def test_greenhouse_source_fetch_yields_normalized():
    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))

    src = GreenhouseSource(companies={"acme": "Acme Corp"})
    out = list(src.fetch(since=None))
    assert len(out) == 2
    assert all(isinstance(j, RawJob) for j in out)
    assert out[0].company == "Acme Corp"
    # external_id is namespaced by board token
    assert out[0].external_id == "acme:4521"
