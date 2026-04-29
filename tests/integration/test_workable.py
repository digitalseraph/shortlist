import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from shortlist.models import RawJob
from shortlist.sources.ats.workable import WorkableClient, WorkableSource, _normalize

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_workable_client_returns_jobs():
    payload = json.loads((FIXTURES / "workable_acme.json").read_text())
    respx.get(re.compile(r"^https://apply\.workable\.com/api/v1/widget/accounts/acme")).mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = list(WorkableClient().fetch_company("acme"))
    assert len(out) == 2
    assert out[0]["shortcode"] == "WRK001"


def test_normalize_combines_description_and_requirements():
    job = {
        "shortcode": "WRK001",
        "title": "Senior Backend Engineer",
        "location": {
            "city": "Remote",
            "country": "United States",
            "location_str": "Remote, United States",
        },
        "application_url": "https://apply.workable.com/acme/j/WRK001/",
        "description": "<p>Build services.</p>",
        "requirements": "<p>5+ yrs.</p>",
        "posted_date": "2026-04-25",
    }
    raw = _normalize(job, company="Acme")
    assert isinstance(raw, RawJob)
    assert raw.source == "workable"
    assert raw.external_id == "WRK001"
    assert raw.location == "Remote, United States"
    assert raw.remote is True
    assert raw.posted_at == datetime(2026, 4, 25, 0, 0, tzinfo=UTC)
    assert "Build services." in (raw.description_md or "")
    assert "5+ yrs." in (raw.description_md or "")


def test_normalize_handles_missing_requirements():
    job = {
        "shortcode": "WRK002",
        "title": "Staff Engineer",
        "location": {"location_str": "Atlanta, GA, United States"},
        "application_url": "https://apply.workable.com/acme/j/WRK002/",
        "description": "<p>Lead.</p>",
        "requirements": None,
        "posted_date": "2026-04-26",
    }
    raw = _normalize(job, company="Acme")
    assert raw.remote is False
    assert "Lead." in (raw.description_md or "")


@respx.mock
def test_workable_source_namespaces_external_id():
    payload = json.loads((FIXTURES / "workable_acme.json").read_text())
    respx.get(re.compile(r"^https://apply\.workable\.com/api/v1/widget/accounts/acme")).mock(
        return_value=httpx.Response(200, json=payload)
    )
    src = WorkableSource(companies={"acme": "Acme Corp"})
    out = list(src.fetch(since=None))
    assert out[0].external_id == "acme:WRK001"
