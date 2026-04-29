from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from shortlist.config import Config, Prefs
from shortlist.models import RawJob
from shortlist.store.db import migrate, upsert_job
from shortlist_tui.workers import fetch_all, tailor_one


def _prefs(**ov) -> Prefs:
    base = dict(
        titles=["Senior Backend Engineer"],
        locations=["Remote"],
        remote_ok=True,
        comp_floor_usd=180000,
        exclude_keywords=[],
        seniority=["senior"],
        greenhouse_companies=[],
    )
    base.update(ov)
    return Prefs.model_validate(base)


def test_fetch_all_empty_prefs_returns_zero(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    msg = fetch_all(db, _prefs())
    assert "fetched 0 jobs" in msg


def test_tailor_one_writes_outputs(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    job = upsert_job(
        db,
        RawJob(
            source="greenhouse",
            external_id="acme:1",
            company="Acme",
            title="Senior Backend Engineer",
            url="https://example.com/1",
            posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
            location="Remote",
            remote=True,
            description_md="Python work.",
        ),
    )
    resume = tmp_path / "resume.md"
    resume.write_text("R")
    out_root = tmp_path / "jobs"

    fixture = Path(__file__).parent.parent / "fixtures/llm_responses/sonnet_tailor_sample.md"
    fake_anth = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=fixture.read_text())]
    msg.usage.input_tokens = 1500
    msg.usage.output_tokens = 1200
    fake_anth.messages.create.return_value = msg

    cfg = Config.model_validate(
        {
            "anthropic": {"key_source": "env", "key_env_var": "ANTHROPIC_API_KEY"},
            "budget": {"daily_usd": 5.0, "monthly_usd": 60.0},
            "paths": {"resume": str(resume), "output_dir": str(out_root)},
            "sources": {},
            "ranker": {
                "top_k_for_llm_rerank": 30,
                "embedding_model": "bge-small-en-v1.5",
                "rerank_model": "claude-haiku-4-5-20251001",
            },
            "tailor": {"model": "claude-sonnet-4-6", "cover_paragraphs": 3},
        }
    )

    summary = tailor_one(
        db, job.id, cfg=cfg, prefs=_prefs(), resume_path=resume, anthropic_client=fake_anth
    )
    assert "tailored" in summary
    dirs = list(out_root.iterdir())
    assert len(dirs) == 1
