from pathlib import Path

import pytest

from shortlist.models import RawJob
from shortlist.sources.scraped.indeed import IndeedBanDetectedError, parse_search_html

FIXTURES = Path(__file__).parent.parent / "fixtures/scraped"


def test_parse_synthetic_indeed_search():
    html = (FIXTURES / "indeed_search.html").read_text()
    jobs = parse_search_html(html, query="senior backend")
    assert len(jobs) == 2
    j0 = jobs[0]
    assert isinstance(j0, RawJob)
    assert j0.source == "indeed"
    assert j0.external_id == "abc123"
    assert j0.title == "Senior Backend Engineer"
    assert j0.company == "Acme Inc"
    assert j0.remote is True
    assert "Build distributed" in (j0.description_md or "")


def test_parse_detects_ban_marker():
    html = "<html><body>Verify you are human before continuing</body></html>"
    with pytest.raises(IndeedBanDetectedError):
        parse_search_html(html, query="x")


def test_parse_handles_missing_optional_fields():
    html = """
    <ul class="jobsearch-ResultsList">
      <li class="result">
        <h2 class="jobTitle"><a href="/viewjob?jk=zzz" id="job_zzz">Some Title</a></h2>
      </li>
    </ul>
    """
    jobs = parse_search_html(html, query="x")
    assert len(jobs) == 1
    assert jobs[0].title == "Some Title"
    assert jobs[0].company == "Unknown"
    assert jobs[0].location is None
