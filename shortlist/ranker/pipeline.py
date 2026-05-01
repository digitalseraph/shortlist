"""End-to-end ranking pipeline.

Stage 1: hard filter — drop jobs that obviously don't match prefs.
Stage 2: cosine score — embed surviving jobs, score every survivor 0–100 by
         cosine similarity against the resume embedding.
Stage 3 (optional): Haiku rerank — for the top-K cosine survivors, let an LLM
         produce a final 0–100 + one-line reason, overwriting the cosine score.

Filtered-out jobs always get score 0 + reason "filtered".

`rerank_jobs` is a separate entry point for re-running the LLM stage on an
explicit list of job IDs (used by the web "Rank Selected (LLM)" button).
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


def _distance_to_score(distance: float) -> int:
    """Map sqlite-vec L2 distance on unit vectors to a 0-100 score.

    For normalized vectors: cos_sim = 1 - distance**2 / 2.
    Clamp negative similarity to 0 so unrelated jobs don't score weirdly.
    """
    sim = 1.0 - (distance * distance) / 2.0
    sim = max(0.0, min(1.0, sim))
    return int(round(sim * 100))


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

    # Stage 2: embed survivors and cosine-score every one of them.
    resume_vec = embed_resume_cached(db_path, resume_path, service=embedder)
    for job in survivors:
        if store_db.get_embedding(db_path, job.id) is None:
            text = f"{job.title}\n\n{job.description_md or ''}"
            store_db.upsert_embedding(db_path, job.id, embedder.encode(text))

    # Pull every survivor's distance to the resume vector in one query.
    ranked = store_db.cosine_top_k(db_path, resume_vec, k=len(survivors))
    distance_by_id = {jid: dist for (jid, dist) in ranked}
    for j in survivors:
        dist = distance_by_id.get(j.id)
        score = _distance_to_score(dist) if dist is not None else 0
        store_db.update_score(
            db_path,
            j.id,
            score=score,
            reason=f"cosine sim ({score}/100)",
            model="cosine_only",
        )

    # Pick the top-K survivors by cosine for optional LLM rerank.
    top_ids = {jid for (jid, _d) in ranked[:top_k]}
    top_jobs = [j for j in survivors if j.id in top_ids]

    # Stage 3: LLM rerank (if reranker provided) — overwrites cosine scores.
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
                if s is not None:
                    store_db.update_score(
                        db_path,
                        j.id,
                        score=s.score,
                        reason=s.reason,
                        model="claude-haiku-4-5",
                    )
                # If LLM omitted this id, leave the cosine score in place.
        except LLMRerankParseError as e:
            logger.warning("LLM rerank failed: %s — keeping cosine scores", e)

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


@dataclass(frozen=True)
class RerankSummary:
    """Result of `rerank_jobs` — LLM-only rerank over an explicit ID list."""

    requested: int
    scored: int
    cost_usd: float
    tokens_in: int
    tokens_out: int


def rerank_jobs(
    db_path: Path,
    job_ids: list[int],
    *,
    prefs: Prefs,
    resume_path: Path,
    reranker: LLMReranker,
) -> RerankSummary:
    """Run LLM rerank on a specific list of job IDs and persist the new scores."""
    if not job_ids:
        return RerankSummary(0, 0, 0.0, 0, 0)

    all_jobs = store_db.list_jobs(db_path)
    by_id = {j.id: j for j in all_jobs}
    targets = [by_id[i] for i in job_ids if i in by_id]
    if not targets:
        return RerankSummary(len(job_ids), 0, 0.0, 0, 0)

    req = RerankRequest(
        resume=resume_path.read_text(),
        prefs_summary=_prefs_summary(prefs),
        candidates=_candidates_for_llm(targets),
    )
    cost = 0.0
    tokens_in = 0
    tokens_out = 0
    scored_count = 0
    try:
        result: RerankResult = reranker.rerank(req)
        cost = result.cost_usd
        tokens_in = result.tokens_in
        tokens_out = result.tokens_out
        id_to_score = {s.id: s for s in result.scored}
        for j in targets:
            s = id_to_score.get(j.id)
            if s is not None:
                store_db.update_score(
                    db_path,
                    j.id,
                    score=s.score,
                    reason=s.reason,
                    model="claude-haiku-4-5",
                )
                scored_count += 1
    except LLMRerankParseError as e:
        logger.warning("LLM rerank failed for selected jobs: %s", e)

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
                "claude-haiku-4-5",
                len(targets),
                cost,
                tokens_in,
                tokens_out,
            ),
        )

    return RerankSummary(len(job_ids), scored_count, cost, tokens_in, tokens_out)
