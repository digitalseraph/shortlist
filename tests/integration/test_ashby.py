import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from shortlist.models import RawJob
from shortlist.sources.ats.ashby import AshbyClient, AshbySource, _normalize

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_ashby_client_returns_jobs():
    payload = json.loads((FIXTURES / "ashby_acme.json").read_text())
    respx.get(re.compile(r"^https://api\.ashbyhq\.com/posting-api/job-board/acme")).mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = list(AshbyClient().fetch_company("acme"))
    assert len(out) == 2
    assert out[0]["id"] == "ash-uuid-1"


def test_normalize_handles_html_and_compensation():
    job = {
        "id": "ash-uuid-1",
        "title": "Senior Backend Engineer",
        "location": "Remote",
        "descriptionHtml": "<p>Build <b>distributed</b> systems.</p>",
        "jobUrl": "https://jobs.ashbyhq.com/acme/ash-uuid-1",
        "publishedAt": "2026-04-25T13:00:00.000Z",
        "compensationTierSummary": "$200k–$240k USD",
    }
    raw = _normalize(job, company="Acme")
    assert isinstance(raw, RawJob)
    assert raw.source == "ashby"
    assert raw.external_id == "ash-uuid-1"
    assert raw.remote is True
    assert raw.posted_at == datetime(2026, 4, 25, 13, 0, tzinfo=UTC)
    assert "<" not in (raw.description_md or "")
    assert "distributed" in (raw.description_md or "")
    assert raw.comp_min == 200000
    assert raw.comp_max == 240000


def test_normalize_handles_missing_comp():
    job = {
        "id": "ash-uuid-2",
        "title": "Eng",
        "location": "Atlanta",
        "descriptionHtml": "<p>Stuff.</p>",
        "jobUrl": "https://jobs.ashbyhq.com/acme/ash-uuid-2",
        "publishedAt": "2026-04-26T14:30:00.000Z",
        "compensationTierSummary": None,
    }
    raw = _normalize(job, company="Acme")
    assert raw.comp_min is None
    assert raw.comp_max is None
    assert raw.remote is False


@respx.mock
def test_ashby_source_yields_namespaced_external_id():
    payload = json.loads((FIXTURES / "ashby_acme.json").read_text())
    respx.get(re.compile(r"^https://api\.ashbyhq\.com/posting-api/job-board/acme")).mock(
        return_value=httpx.Response(200, json=payload)
    )
    src = AshbySource(companies={"acme": "Acme Corp"})
    out = list(src.fetch(since=None))
    assert out[0].external_id == "acme:ash-uuid-1"
