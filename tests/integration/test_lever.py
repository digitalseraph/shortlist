import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from shortlist.models import RawJob
from shortlist.sources.ats.lever import LeverClient, LeverSource, _normalize

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_lever_client_returns_postings():
    payload = json.loads((FIXTURES / "lever_acme.json").read_text())
    respx.get("https://api.lever.co/v0/postings/acme", params={"mode": "json"}).mock(
        return_value=httpx.Response(200, json=payload)
    )
    client = LeverClient()
    postings = list(client.fetch_company("acme"))
    assert len(postings) == 2
    assert postings[0]["id"] == "lev_001"


@respx.mock
def test_lever_client_404_returns_empty():
    respx.get("https://api.lever.co/v0/postings/nope", params={"mode": "json"}).mock(
        return_value=httpx.Response(404)
    )
    assert list(LeverClient().fetch_company("nope")) == []


def test_normalize_returns_rawjob():
    posting = {
        "id": "lev_001",
        "text": "Senior Backend Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/lev_001",
        "categories": {
            "team": "Platform",
            "location": "Remote - US",
            "commitment": "Full-time",
        },
        "descriptionPlain": "Build stuff in Python.",
        "createdAt": 1745580000000,
    }
    raw = _normalize(posting, company="Acme")
    assert isinstance(raw, RawJob)
    assert raw.source == "lever"
    assert raw.external_id == "lev_001"
    assert raw.title == "Senior Backend Engineer"
    assert raw.location == "Remote - US"
    assert raw.remote is True
    assert raw.posted_at == datetime.fromtimestamp(1745580000, tz=UTC)
    assert "Build stuff in Python." in (raw.description_md or "")


@respx.mock
def test_lever_source_fetch_yields_normalized():
    payload = json.loads((FIXTURES / "lever_acme.json").read_text())
    respx.get("https://api.lever.co/v0/postings/acme", params={"mode": "json"}).mock(
        return_value=httpx.Response(200, json=payload)
    )
    src = LeverSource(companies={"acme": "Acme Corp"})
    out = list(src.fetch(since=None))
    assert len(out) == 2
    assert out[0].external_id == "acme:lev_001"
    assert out[0].company == "Acme Corp"
