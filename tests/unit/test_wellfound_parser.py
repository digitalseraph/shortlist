from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.sources.scraped.wellfound import (
    WellfoundBanDetectedError,
    parse_search_html,
)

FIXTURES = Path(__file__).parent.parent / "fixtures/scraped"


def test_parse_synthetic_wellfound():
    html = (FIXTURES / "wellfound_search.html").read_text()
    jobs = parse_search_html(html)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "wellfound"
    assert j0.external_id.startswith("wf-9001")
    assert j0.company == "Acme Inc"
    assert j0.remote is True
    assert j0.posted_at == datetime(2026, 4, 25, 0, 0, tzinfo=UTC)


def test_parse_detects_cloudflare():
    html = "<html><body>Cloudflare protection — captcha required.</body></html>"
    with pytest.raises(WellfoundBanDetectedError):
        parse_search_html(html)
