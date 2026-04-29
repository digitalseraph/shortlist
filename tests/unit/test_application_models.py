from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from shortlist.models import Application, Contact


def test_application_minimum_fields():
    a = Application(job_id=1)
    assert a.job_id == 1
    assert a.applied_at is None
    assert a.decision is None


def test_application_with_decision():
    a = Application(
        job_id=1,
        applied_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
        applied_via="company website",
        salary_offered=210000,
        decision="offer",
        decision_reason="Strong technical interview",
    )
    assert a.salary_offered == 210000
    assert a.decision == "offer"


def test_contact_requires_name():
    with pytest.raises(ValidationError):
        Contact(application_id=1, name="", role="recruiter", created_at=datetime.now(UTC))


def test_contact_minimum_fields():
    c = Contact(
        application_id=1,
        name="Jane Doe",
        created_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
    )
    assert c.name == "Jane Doe"
    assert c.email is None
