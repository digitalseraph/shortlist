"""End-to-end ranking pipeline.

Stage 1: hard filter — drop jobs that obviously don't match prefs.
Stage 2: cosine pre-rank — embed surviving jobs, take top-K by sim to resume.
Stage 3: Haiku rerank — let an LLM produce final 0–100 + one-line reason for top-K.
Filtered-out jobs get score 0 + reason "filtered".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shortlist.config import Prefs
from shortlist.models import Job
from shortlist.ranker.embeddings import EmbeddingService, embed_resume_cached
from shortlist.ranker.hard_filter import passes
from shortlist.ranker.llm_rerank import (
    LLMReranker,
    LLMRerankParseError,
    RerankRequest,
    RerankResult,
)
from shortlist.store import db as store_db

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineSummary:
    filtered: int
    cosine_top_k: int
    llm_scored: int
    cost_usd: float


def _prefs_summary(prefs: Prefs) -> str:
    return (
        f"titles: {', '.join(prefs.titles)}\n"
        f"seniority: {', '.join(prefs.seniority)}\n"
        f"locations: {', '.join(prefs.locations)}\n"
        f"remote_ok: {prefs.remote_ok}\n"
        f"comp_floor_usd: {prefs.comp_floor_usd}\n"
        f"exclude: {', '.join(prefs.exclude_keywords)}"
    )


def _candidates_for_llm(jobs: list[Job]) -> list[dict[str, Any]]:
    return [
        {
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "description": (j.description_md or "")[:1000],
        }
        for j in jobs
    ]


def run_pipeline(
    db_path: Path,
    *,
    prefs: Prefs,
    resume_path: Path,
    embedder: EmbeddingService,
    reranker: LLMReranker | None,
    top_k: int = 30,
) -> PipelineSummary:
    """Score every job in the store. Returns a summary."""
    all_jobs = store_db.list_jobs(db_path)

    # Stage 1: hard filter.
    filtered_out: list[Job] = []
    survivors: list[Job] = []
    for job in all_jobs:
        if passes(job, prefs):
            survivors.append(job)
        else:
            filtered_out.append(job)
            store_db.update_score(
                db_path, job.id, score=0, reason="filtered out", model="hard_filter"
            )

    if not survivors:
        return PipelineSummary(len(filtered_out), 0, 0, 0.0)

    # Stage 2: embed survivors and pick top-K against resume.
    resume_vec = embed_resume_cached(db_path, resume_path, service=embedder)
    for job in survivors:
        if store_db.get_embedding(db_path, job.id) is None:
            text = f"{job.title}\n\n{job.description_md or ''}"
            store_db.upsert_embedding(db_path, job.id, embedder.encode(text))

    top = store_db.cosine_top_k(db_path, resume_vec, k=top_k)
    top_ids = {jid for (jid, _d) in top}
    top_jobs = [j for j in survivors if j.id in top_ids]

    # Survivors not in top-K get a placeholder score (passed filter, mid-band).
    for j in survivors:
        if j.id not in top_ids:
            store_db.update_score(
                db_path,
                j.id,
                score=40,
                reason="passed filter, below cosine top-K",
                model="cosine_only",
            )

    # Stage 3: LLM rerank (if reranker provided).
    cost = 0.0
    llm_scored = 0
    tokens_in = 0
    tokens_out = 0
    if reranker is not None and top_jobs:
        req = RerankRequest(
            resume=resume_path.read_text(),
            prefs_summary=_prefs_summary(prefs),
            candidates=_candidates_for_llm(top_jobs),
        )
        try:
            result: RerankResult = reranker.rerank(req)
            cost = result.cost_usd
            llm_scored = len(result.scored)
            tokens_in = result.tokens_in
            tokens_out = result.tokens_out
            id_to_score = {s.id: s for s in result.scored}
            for j in top_jobs:
                s = id_to_score.get(j.id)
                if s is None:
                    store_db.update_score(
                        db_path,
                        j.id,
                        score=50,
                        reason="LLM omitted from result",
                        model="cosine_then_llm",
                    )
                else:
                    store_db.update_score(
                        db_path,
                        j.id,
                        score=s.score,
                        reason=s.reason,
                        model="claude-haiku-4-5",
                    )
        except LLMRerankParseError as e:
            logger.warning("LLM rerank failed: %s — falling back to cosine scores", e)
            for j in top_jobs:
                store_db.update_score(
                    db_path,
                    j.id,
                    score=70,
                    reason="cosine top-K (LLM fallback)",
                    model="cosine_only",
                )
    else:
        # No reranker — give top-K cosine score 70 placeholder.
        for j in top_jobs:
            store_db.update_score(
                db_path,
                j.id,
                score=70,
                reason="cosine top-K (no LLM)",
                model="cosine_only",
            )

    # Record the run.
    with store_db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scoring_runs
                (started_at, finished_at, model, job_count, cost_usd, tokens_in, tokens_out)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                store_db._utc_iso(datetime.now(UTC)),
                store_db._utc_iso(datetime.now(UTC)),
                "claude-haiku-4-5" if reranker else "cosine_only",
                len(survivors),
                cost,
                tokens_in,
                tokens_out,
            ),
        )

    return PipelineSummary(len(filtered_out), len(top_jobs), llm_scored, cost)
