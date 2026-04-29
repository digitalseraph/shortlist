"""Background work: fetch, rank, tailor.

Each function is a synchronous, side-effecting wrapper over shortlist.*
suitable for Textual `@work(thread=True)`. They return summary strings
that screens can display.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shortlist.config import Config, Prefs
from shortlist.ranker.embeddings import EmbeddingService
from shortlist.ranker.llm_rerank import LLMReranker
from shortlist.ranker.pipeline import run_pipeline
from shortlist.sources.ats.ashby import AshbySource
from shortlist.sources.ats.greenhouse import GreenhouseSource
from shortlist.sources.ats.lever import LeverSource
from shortlist.sources.ats.smartrecruiters import SmartRecruitersSource
from shortlist.sources.ats.workable import WorkableSource
from shortlist.sources.base import Source
from shortlist.store import db as store_db
from shortlist.tailor.orchestrator import TailorOrchestrator


def _build_sources(prefs: Prefs) -> list[Source]:
    sources: list[Source] = []
    if prefs.greenhouse_companies:
        sources.append(
            GreenhouseSource(companies={t: t.title() for t in prefs.greenhouse_companies})
        )
    if prefs.lever_companies:
        sources.append(LeverSource(companies={t: t.title() for t in prefs.lever_companies}))
    if prefs.ashby_companies:
        sources.append(AshbySource(companies={t: t.title() for t in prefs.ashby_companies}))
    if prefs.workable_companies:
        sources.append(WorkableSource(companies={t: t.title() for t in prefs.workable_companies}))
    if prefs.smartrecruiters_companies:
        sources.append(
            SmartRecruitersSource(companies={t: t for t in prefs.smartrecruiters_companies})
        )
    return sources


def fetch_all(db_path: Path, prefs: Prefs) -> str:
    """Pull jobs from every configured source. Returns a summary line."""
    total = 0
    errors: list[str] = []
    for src in _build_sources(prefs):
        try:
            for raw in src.fetch(since=store_db.source_last_fetched(db_path, src.name)):
                store_db.upsert_job(db_path, raw)
                total += 1
            store_db.mark_source_fetched(db_path, src.name, datetime.now(UTC))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{src.name}: {e}")
    if errors:
        return f"fetched {total} jobs ({len(errors)} source errors)"
    return f"fetched {total} jobs"


def rank_all(
    db_path: Path,
    *,
    cfg: Config,
    prefs: Prefs,
    resume_path: Path,
    anthropic_client: Any | None,
    top_k: int = 30,
) -> str:
    embedder = EmbeddingService(model_name=cfg.ranker.embedding_model)
    reranker = (
        LLMReranker(client=anthropic_client, model=cfg.ranker.rerank_model)
        if anthropic_client is not None
        else None
    )
    summary = run_pipeline(
        db_path,
        prefs=prefs,
        resume_path=resume_path,
        embedder=embedder,
        reranker=reranker,
        top_k=top_k,
    )
    return (
        f"filtered={summary.filtered} | top_k={summary.cosine_top_k} | "
        f"llm={summary.llm_scored} | cost=${summary.cost_usd:.4f}"
    )


def tailor_one(
    db_path: Path,
    job_id: int,
    *,
    cfg: Config,
    prefs: Prefs,
    resume_path: Path,
    anthropic_client: Any,
) -> str:
    orch = TailorOrchestrator(
        db_path=db_path,
        output_root=cfg.paths.output_dir.expanduser(),
        anthropic_client=anthropic_client,
        model=cfg.tailor.model,
        pdf_template=cfg.paths.pdf_template,
    )
    out = orch.tailor(job_id=job_id, resume_path=resume_path, prefs=prefs)
    return f"tailored → {out.output_dir} (${out.cost_usd:.4f})"
