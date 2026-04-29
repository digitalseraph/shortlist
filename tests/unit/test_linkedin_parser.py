from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.sources.scraped.linkedin import (
    LinkedInBanDetectedError,
    parse_search_html,
)

FIXTURES = Path(__file__).parent.parent / "fixtures/scraped"


def test_parse_synthetic_linkedin_search():
    html = (FIXTURES / "linkedin_search.html").read_text()
    jobs = parse_search_html(html)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "linkedin"
    assert j0.external_id == "3987654321"
    assert j0.title == "Senior Backend Engineer"
    assert j0.company == "Acme Inc"
    assert j0.remote is True
    assert j0.posted_at == datetime(2026, 4, 25, 0, 0, tzinfo=UTC)


def test_parse_detects_authwall():
    html = "<html><body>authwall: Sign in to continue browsing.</body></html>"
    with pytest.raises(LinkedInBanDetectedError):
        parse_search_html(html)
