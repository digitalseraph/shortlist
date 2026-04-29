from pathlib import Path

import pytest

from shortlist.sources.scraped.otta import OttaBanDetectedError, parse_search_html

FIXTURES = Path(__file__).parent.parent / "fixtures/scraped"


def test_parse_synthetic_otta():
    html = (FIXTURES / "otta_search.html").read_text()
    jobs = parse_search_html(html)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "otta"
    assert j0.external_id == "ot-501"
    assert j0.company == "Acme Inc"
    assert j0.remote is True


def test_parse_detects_captcha():
    html = "<html><body>captcha required.</body></html>"
    with pytest.raises(OttaBanDetectedError):
        parse_search_html(html)
