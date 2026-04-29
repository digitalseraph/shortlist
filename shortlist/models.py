"""Pydantic models for jobs in Shortlist.

RawJob: shape returned by source clients before persistence.
Job:    shape after the row is in SQLite (has id, status, scoring fields).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

JobStatus = Literal[
    "new",
    "tailored",
    "applied",
    "screen",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
]


class RawJob(BaseModel):
    """Source-agnostic normalized job record before storage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    external_id: str
    company: str
    title: str
    url: HttpUrl
    posted_at: datetime

    location: str | None = None
    remote: bool = False
    comp_min: int | None = None
    comp_max: int | None = None
    description_md: str | None = None

    @field_validator("posted_at")
    @classmethod
    def _require_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("posted_at must be timezone-aware")
        return v


class Job(BaseModel):
    """Stored job. Includes scoring + status fields managed by the store."""

    model_config = ConfigDict(extra="forbid")

    id: int
    source: str
    external_id: str
    company: str
    title: str
    url: HttpUrl
    posted_at: datetime
    discovered_at: datetime

    location: str | None = None
    remote: bool = False
    comp_min: int | None = None
    comp_max: int | None = None
    description_md: str | None = None

    score: int | None = Field(default=None, ge=0, le=100)
    score_reason: str | None = None
    status: JobStatus = "new"
    status_changed_at: datetime | None = None
    scored_with_prefs_at: datetime | None = None
    scored_with_model: str | None = None


class Application(BaseModel):
    """Lifecycle state for a job we've engaged with."""

    model_config = ConfigDict(extra="forbid")

    job_id: int
    applied_at: datetime | None = None
    applied_via: str | None = None
    follow_up_due: datetime | None = None
    salary_offered: int | None = Field(default=None, ge=0)
    decision: str | None = None
    decision_reason: str | None = None
    lessons: str | None = None


class Contact(BaseModel):
    """A person tied to an application (recruiter, hiring manager, etc.)."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    application_id: int
    name: str = Field(min_length=1)
    email: str | None = None
    role: str | None = None
    source: str | None = None
    created_at: datetime
