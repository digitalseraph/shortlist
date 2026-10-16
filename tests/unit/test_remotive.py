"""Remotive API item parsing."""

from __future__ import annotations

from datetime import UTC, datetime

from shortlist.sources.curated.remotive import parse_job

ITEM = {
    "id": 123,
    "company_name": "Acme",
    "title": "French Tutor",
    "url": "https://remotive.com/remote-jobs/123",
    "candidate_required_location": "USA",
}


def test_naive_publication_date_is_read_as_utc() -> None:
    """Remotive sends dates without an offset; RawJob requires one."""
    job = parse_job(ITEM | {"publication_date": "2026-10-14T20:33:44"})
    assert job is not None
    assert job.posted_at == datetime(2026, 10, 14, 20, 33, 44, tzinfo=UTC)


def test_zulu_publication_date_still_parses() -> None:
    job = parse_job(ITEM | {"publication_date": "2026-10-14T20:33:44Z"})
    assert job is not None
    assert job.posted_at == datetime(2026, 10, 14, 20, 33, 44, tzinfo=UTC)
