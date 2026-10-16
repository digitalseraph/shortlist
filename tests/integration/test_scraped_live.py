"""Live smoke tests for scraped sources.

Gated by both `@pytest.mark.browser` and `@pytest.mark.live`. Skip
unless `RUN_LIVE=1` is set. Real Indeed/LinkedIn/Glassdoor — expect
occasional bans (test treats ban as skip, not failure).
"""

import os

import pytest

from shortlist.sources.scraped.glassdoor import (
    GlassdoorBanDetectedError,
    GlassdoorSource,
)
from shortlist.sources.scraped.indeed import IndeedBanDetectedError, IndeedSource
from shortlist.sources.scraped.linkedin import (
    LinkedInBanDetectedError,
    LinkedInSource,
)

LIVE = os.environ.get("RUN_LIVE") == "1"
pytestmark = [
    pytest.mark.browser,
    pytest.mark.live,
    pytest.mark.skipif(not LIVE, reason="RUN_LIVE=1 required"),
]


def test_indeed_live_returns_some_results_or_bans():
    src = IndeedSource(
        queries=["senior backend engineer"],
        locations=["Remote"],
        rate_limit_seconds=2.0,
    )
    try:
        jobs = list(src.fetch(since=None))
    except IndeedBanDetectedError:
        pytest.skip("Indeed banned us — expected sometimes")
        return
    if jobs:
        assert all(j.source == "indeed" for j in jobs)
        assert all(j.title for j in jobs)


def test_linkedin_live_returns_some_results_or_bans():
    src = LinkedInSource(
        queries=["platform engineer"],
        locations=["United States"],
        rate_limit_seconds=4.0,
        max_pages=1,
    )
    try:
        jobs = list(src.fetch(since=None))
    except LinkedInBanDetectedError:
        pytest.skip("LinkedIn banned us — expected sometimes")
        return
    if jobs:
        assert all(j.source == "linkedin" for j in jobs)


def test_glassdoor_live_returns_some_results_or_bans():
    src = GlassdoorSource(
        queries=["staff engineer"],
        locations=["Remote"],
        rate_limit_seconds=3.0,
    )
    try:
        jobs = list(src.fetch(since=None))
    except GlassdoorBanDetectedError:
        pytest.skip("Glassdoor banned us — expected sometimes")
        return
    if jobs:
        assert all(j.source == "glassdoor" for j in jobs)
