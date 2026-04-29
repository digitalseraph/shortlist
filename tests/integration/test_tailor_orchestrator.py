from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from shortlist.config import Prefs
from shortlist.models import RawJob
from shortlist.store.db import migrate, upsert_job
from shortlist.tailor.orchestrator import TailorOrchestrator


def _fake_msg(text):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage.input_tokens = 1500
    msg.usage.output_tokens = 1200
    return msg


def _prefs() -> Prefs:
    return Prefs.model_validate(
        dict(
            titles=["Senior Backend Engineer"],
            locations=["Remote"],
            remote_ok=True,
            comp_floor_usd=180000,
            exclude_keywords=[],
            seniority=["senior"],
            greenhouse_companies=[],
        )
    )


def test_orchestrator_writes_three_md_files(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    job = upsert_job(
        db,
        RawJob(
            source="greenhouse",
            external_id="acme:1",
            company="Acme Corp",
            title="Senior Backend Engineer",
            url="https://example.com/jobs/1",
            posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
            location="Remote - US",
            remote=True,
            description_md="Build distributed systems in Python.",
        ),
    )
    resume = tmp_path / "resume.md"
    resume.write_text("Senior backend engineer with 6 years Python.")
    output_root = tmp_path / "jobs"

    fixture = Path(__file__).parent.parent / "fixtures/llm_responses/sonnet_tailor_sample.md"
    fake_anth = MagicMock()
    fake_anth.messages.create.return_value = _fake_msg(fixture.read_text())

    orch = TailorOrchestrator(
        db_path=db,
        output_root=output_root,
        anthropic_client=fake_anth,
        model="claude-sonnet-4-6",
        pdf_template=None,
    )
    result = orch.tailor(job_id=job.id, resume_path=resume, prefs=_prefs())

    assert (result.output_dir / "resume.md").exists()
    assert (result.output_dir / "cover.md").exists()
    assert (result.output_dir / "notes.md").exists()
    assert "acme" in result.output_dir.name.lower()
    assert result.cost_usd > 0


def test_orchestrator_records_status_transition(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    job = upsert_job(
        db,
        RawJob(
            source="greenhouse",
            external_id="acme:2",
            company="Acme",
            title="Senior Backend Engineer",
            url="https://example.com/jobs/2",
            posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
            location="Remote",
            remote=True,
            description_md="Python work.",
        ),
    )
    resume = tmp_path / "resume.md"
    resume.write_text("R")

    fixture = Path(__file__).parent.parent / "fixtures/llm_responses/sonnet_tailor_sample.md"
    fake_anth = MagicMock()
    fake_anth.messages.create.return_value = _fake_msg(fixture.read_text())

    orch = TailorOrchestrator(
        db_path=db,
        output_root=tmp_path / "jobs",
        anthropic_client=fake_anth,
        model="claude-sonnet-4-6",
        pdf_template=None,
    )
    orch.tailor(job_id=job.id, resume_path=resume, prefs=_prefs())

    from shortlist.store.db import list_jobs

    refreshed = next(j for j in list_jobs(db) if j.id == job.id)
    assert refreshed.status == "tailored"
