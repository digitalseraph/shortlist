from datetime import UTC, datetime
from unittest.mock import MagicMock

import numpy as np
import pytest

from shortlist.config import Prefs
from shortlist.models import RawJob
from shortlist.ranker.embeddings import EmbeddingService
from shortlist.ranker.llm_rerank import LLMReranker
from shortlist.ranker.pipeline import run_pipeline
from shortlist.store.db import list_jobs, migrate, upsert_job


@pytest.fixture
def fake_embedder():
    m = MagicMock()

    def _encode(text, **_):
        seed = sum(ord(c) for c in (text if isinstance(text, str) else text[0]))
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(384).astype("float32")
        return v / np.linalg.norm(v)

    m.encode = _encode
    m.get_sentence_embedding_dimension.return_value = 384
    return EmbeddingService(_model=m)


def _prefs() -> Prefs:
    return Prefs.model_validate(
        dict(
            titles=["Senior Backend Engineer", "Staff Engineer"],
            locations=["Remote - US", "Atlanta, GA"],
            remote_ok=True,
            comp_floor_usd=180000,
            exclude_keywords=["C++"],
            seniority=["senior", "staff"],
            greenhouse_companies=["acme"],
        )
    )


def _seed(db, n_pass=2, n_fail=1):
    base = dict(
        source="greenhouse",
        company="Acme",
        location="Remote - US",
        remote=True,
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
    )
    for i in range(n_pass):
        upsert_job(
            db,
            RawJob(
                **base,
                external_id=f"acme:p{i}",
                title="Senior Backend Engineer",
                url=f"https://example.com/p{i}",
                description_md="Python services.",
            ),
        )
    for i in range(n_fail):
        upsert_job(
            db,
            RawJob(
                **base,
                external_id=f"acme:f{i}",
                title="C++ Engineer",
                url=f"https://example.com/f{i}",
                description_md="Low-level work.",
            ),
        )


def test_pipeline_filters_then_cosine_then_llm(tmp_path, fake_embedder):
    db = tmp_path / "db.sqlite"
    migrate(db)
    _seed(db, n_pass=2, n_fail=1)
    resume = tmp_path / "resume.md"
    resume.write_text("Senior backend engineer.")

    fake_anth = MagicMock()
    msg = MagicMock()
    msg.content = [
        MagicMock(
            text=(
                '[{"id": 1, "score": 88, "reason": "great match"}, '
                '{"id": 2, "score": 71, "reason": "ok match"}]'
            )
        )
    ]
    msg.usage.input_tokens = 500
    msg.usage.output_tokens = 30
    fake_anth.messages.create.return_value = msg
    reranker = LLMReranker(client=fake_anth, model="claude-haiku-4-5-20251001")

    summary = run_pipeline(
        db,
        prefs=_prefs(),
        resume_path=resume,
        embedder=fake_embedder,
        reranker=reranker,
        top_k=5,
    )
    assert summary.filtered == 1
    assert summary.cosine_top_k >= 1
    assert summary.llm_scored == 2
    assert summary.cost_usd > 0

    jobs = list_jobs(db)
    # Every job — including filtered — gets a cosine score 0..100; filtered
    # jobs have their reason prefixed with "(filtered) ".
    assert all(j.score is not None for j in jobs)
    cpp = next(j for j in jobs if j.title == "C++ Engineer")
    assert cpp.score is not None
    assert (cpp.score_reason or "").startswith("(filtered)")


def test_pipeline_no_llm_path(tmp_path, fake_embedder):
    db = tmp_path / "db.sqlite"
    migrate(db)
    _seed(db, n_pass=1, n_fail=0)
    resume = tmp_path / "resume.md"
    resume.write_text("Senior backend engineer.")
    summary = run_pipeline(
        db,
        prefs=_prefs(),
        resume_path=resume,
        embedder=fake_embedder,
        reranker=None,
        top_k=5,
    )
    assert summary.cost_usd == 0.0
    assert summary.llm_scored == 0
