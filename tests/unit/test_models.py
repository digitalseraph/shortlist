from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from shortlist.models import Job, RawJob


def test_rawjob_minimum_fields():
    raw = RawJob(
        source="greenhouse",
        external_id="gh_4521",
        company="Acme Corp",
        title="Senior Backend Engineer",
        url="https://example.com/jobs/4521",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
    )
    assert raw.source == "greenhouse"
    assert raw.external_id == "gh_4521"
    assert raw.location is None
    assert raw.remote is False


def test_rawjob_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        RawJob(
            source="greenhouse",
            external_id="gh_1",
            company="Acme",
            title="Eng",
            url="https://example.com",
            posted_at=datetime(2026, 4, 25, 9, 0),  # no tz
        )


def test_job_status_default_is_new():
    job = Job(
        id=1,
        source="greenhouse",
        external_id="gh_1",
        company="Acme",
        title="Eng",
        url="https://example.com",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        discovered_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
    )
    assert job.status == "new"


def test_job_score_bounds():
    with pytest.raises(ValidationError):
        Job(
            id=1,
            source="x",
            external_id="x",
            company="x",
            title="x",
            url="https://x",
            posted_at=datetime.now(UTC),
            discovered_at=datetime.now(UTC),
            score=101,
        )
