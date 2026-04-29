import json
from pathlib import Path

import httpx
import respx

from shortlist.sources.ats.greenhouse import GreenhouseClient

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
