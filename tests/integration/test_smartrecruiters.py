import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from shortlist.models import RawJob
from shortlist.sources.ats.smartrecruiters import (
    SmartRecruitersClient,
    SmartRecruitersSource,
    _normalize,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_client_returns_postings():
    payload = json.loads((FIXTURES / "smartrecruiters_acme.json").read_text())
    respx.get(re.compile(r"^https://api\.smartrecruiters\.com/v1/companies/Acme/postings")).mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = list(SmartRecruitersClient().fetch_company("Acme"))
    assert len(out) == 2
    assert out[0]["id"] == "sr_001"


@respx.mock
def test_client_paginates():
    page1 = {
        "offset": 0,
        "limit": 1,
        "totalFound": 2,
        "content": [
            {
                "id": "a",
                "name": "A",
                "releasedDate": "2026-04-25T00:00:00.000Z",
                "location": {"fullLocation": "Remote", "remote": True},
                "jobAd": {"sections": {}},
                "applyUrl": "https://x/a",
            }
        ],
    }
    page2 = {
        "offset": 1,
        "limit": 1,
        "totalFound": 2,
        "content": [
            {
                "id": "b",
                "name": "B",
                "releasedDate": "2026-04-26T00:00:00.000Z",
                "location": {"fullLocation": "Atlanta", "remote": False},
                "jobAd": {"sections": {}},
                "applyUrl": "https://x/b",
            }
        ],
    }
    respx.get(
        "https://api.smartrecruiters.com/v1/companies/Acme/postings",
        params={"limit": "1", "offset": "0"},
    ).mock(return_value=httpx.Response(200, json=page1))
    respx.get(
        "https://api.smartrecruiters.com/v1/companies/Acme/postings",
        params={"limit": "1", "offset": "1"},
    ).mock(return_value=httpx.Response(200, json=page2))

    client = SmartRecruitersClient(page_size=1)
    out = list(client.fetch_company("Acme"))
    assert [j["id"] for j in out] == ["a", "b"]


def test_normalize_concatenates_sections():
    job = {
        "id": "sr_001",
        "name": "Senior Backend Engineer",
        "releasedDate": "2026-04-25T09:00:00.000Z",
        "location": {"fullLocation": "Remote, US", "remote": True},
        "jobAd": {
            "sections": {
                "jobDescription": {"text": "<p>Build.</p>"},
                "qualifications": {"text": "<p>5y.</p>"},
            }
        },
        "applyUrl": "https://jobs.smartrecruiters.com/Acme/sr-uuid-1",
    }
    raw = _normalize(job, company="Acme")
    assert isinstance(raw, RawJob)
    assert raw.source == "smartrecruiters"
    assert raw.external_id == "sr_001"
    assert raw.remote is True
    assert raw.posted_at == datetime(2026, 4, 25, 9, 0, tzinfo=UTC)
    assert "Build." in (raw.description_md or "")
    assert "5y." in (raw.description_md or "")


@respx.mock
def test_source_namespaces_external_id():
    payload = json.loads((FIXTURES / "smartrecruiters_acme.json").read_text())
    respx.get(re.compile(r"^https://api\.smartrecruiters\.com/v1/companies/Acme/postings")).mock(
        return_value=httpx.Response(200, json=payload)
    )
    src = SmartRecruitersSource(companies={"Acme": "Acme Corp"})
    out = list(src.fetch(since=None))
    assert out[0].external_id == "Acme:sr_001"
