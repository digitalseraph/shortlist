from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from shortlist.config import Prefs
from shortlist.models import Job
from shortlist.ranker.hard_filter import passes


def _prefs(**overrides) -> Prefs:
    base = dict(
        titles=["Senior Backend Engineer", "Staff Engineer"],
        locations=["Remote - US", "Atlanta, GA"],
        remote_ok=True,
        comp_floor_usd=180000,
        exclude_keywords=["C++", "on-site only"],
        seniority=["senior", "staff"],
        greenhouse_companies=["acme"],
    )
    base.update(overrides)
    return Prefs.model_validate(base)


def _job(**overrides) -> Job:
    base = dict(
        id=1,
        source="greenhouse",
        external_id="acme:1",
        company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/jobs/1",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        discovered_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
        location="Remote - US",
        remote=True,
        comp_min=200000,
        comp_max=240000,
        description_md="Python, Postgres, distributed systems.",
    )
    base.update(overrides)
    return Job.model_validate(base)


def test_passes_happy_path():
    assert passes(_job(), _prefs()) is True


def test_fails_below_comp_floor():
    assert passes(_job(comp_max=150000), _prefs()) is False


def test_passes_when_comp_unknown():
    # Missing comp shouldn't disqualify — many ATS jobs omit it.
    assert passes(_job(comp_min=None, comp_max=None), _prefs()) is True


def test_fails_excluded_keyword_in_description():
    assert passes(_job(description_md="C++ heavy systems"), _prefs()) is False


def test_fails_excluded_keyword_in_title():
    assert passes(_job(title="C++ Engineer"), _prefs()) is False


def test_fails_when_not_remote_and_remote_only_pref():
    assert passes(_job(remote=False, location="Berlin"), _prefs()) is False


def test_passes_when_not_remote_but_location_in_allowlist():
    assert passes(_job(remote=False, location="Atlanta, GA"), _prefs()) is True


def test_fails_when_no_seniority_match():
    job = _job(title="Junior Backend Engineer")
    prefs = _prefs(titles=["Junior Backend Engineer"])  # title matches
    # but seniority doesn't include "junior", so still fails
    assert passes(job, prefs) is False


@given(st.text(min_size=2, max_size=20).filter(lambda s: s.strip()))
def test_random_excluded_keyword_filters(kw: str):
    prefs = _prefs(exclude_keywords=[kw])
    job = _job(description_md=f"This role uses {kw} extensively.")
    assert passes(job, prefs) is False
