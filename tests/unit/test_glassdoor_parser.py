from pathlib import Path

import pytest

from shortlist.sources.scraped.glassdoor import (
    GlassdoorBanDetectedError,
    parse_search_html,
)

FIXTURES = Path(__file__).parent.parent / "fixtures/scraped"


def test_parse_synthetic_glassdoor():
    html = (FIXTURES / "glassdoor_search.html").read_text()
    jobs = parse_search_html(html)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "glassdoor"
    assert j0.external_id == "1234567890"
    assert j0.company == "Acme Inc"
    assert j0.remote is True


def test_parse_detects_captcha():
    html = "<html><body>captcha: please verify</body></html>"
    with pytest.raises(GlassdoorBanDetectedError):
        parse_search_html(html)


def test_listings_page_mentioning_captcha_is_not_a_ban():
    """Real results pages load reCAPTCHA scripts and JSON with "blocked" flags."""
    html = (FIXTURES / "glassdoor_search.html").read_text()
    html = html.replace(
        "</body>", '<script src="/recaptcha.js"></script>{"isBlocked":false}</body>'
    )
    assert len(parse_search_html(html)) == 2
