"""Background work: fetch, rank, tailor.

Each function is a synchronous, side-effecting wrapper over shortlist.*
suitable for Textual `@work(thread=True)`. They return summary strings
that screens can display.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from shortlist.config import Config, Prefs
from shortlist.ranker.embeddings import EmbeddingService
from shortlist.ranker.llm_rerank import LLMReranker
from shortlist.ranker.pipeline import rerank_jobs, run_pipeline
from shortlist.sources.ats.applitrack import AppliTrackSource
from shortlist.sources.ats.ashby import AshbySource
from shortlist.sources.ats.greenhouse import GreenhouseSource
from shortlist.sources.ats.lever import LeverSource
from shortlist.sources.ats.smartrecruiters import SmartRecruitersSource
from shortlist.sources.ats.workable import WorkableSource
from shortlist.sources.base import Source
from shortlist.sources.curated.hn_who_hiring import HNWhoHiringSource
from shortlist.sources.curated.remoteok import RemoteOKSource
from shortlist.sources.curated.remotive import RemotiveSource
from shortlist.sources.curated.usajobs import USAJobsSource
from shortlist.sources.feeds.rss import RSSSource
from shortlist.sources.scraped.glassdoor import GlassdoorBanDetectedError, GlassdoorSource
from shortlist.sources.scraped.indeed import IndeedBanDetectedError, IndeedSource
from shortlist.sources.scraped.linkedin import LinkedInBanDetectedError, LinkedInSource
from shortlist.sources.scraped.otta import OttaBanDetectedError, OttaSource
from shortlist.sources.scraped.wellfound import WellfoundBanDetectedError, WellfoundSource
from shortlist.store import db as store_db
from shortlist.tailor.orchestrator import TailorOrchestrator

ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    return None


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
    if prefs.indeed_queries:
        sources.append(IndeedSource(queries=prefs.indeed_queries, locations=prefs.search_locations))
    if prefs.linkedin_queries:
        sources.append(
            LinkedInSource(queries=prefs.linkedin_queries, locations=prefs.search_locations)
        )
    if prefs.glassdoor_queries:
        sources.append(
            GlassdoorSource(queries=prefs.glassdoor_queries, locations=prefs.search_locations)
        )
    if prefs.hn_enabled:
        sources.append(HNWhoHiringSource())
    if prefs.remoteok_enabled:
        sources.append(RemoteOKSource())
    if prefs.remotive_enabled:
        sources.append(RemotiveSource())
    if prefs.wellfound_queries:
        sources.append(WellfoundSource(queries=prefs.wellfound_queries))
    if prefs.otta_queries:
        sources.append(OttaSource(queries=prefs.otta_queries))
    if prefs.rss_urls:
        sources.append(RSSSource(urls=prefs.rss_urls))
    if prefs.applitrack_districts:
        sources.append(AppliTrackSource(districts=prefs.applitrack_districts))
    if prefs.usajobs_queries:
        sources.append(
            USAJobsSource(queries=prefs.usajobs_queries, locations=prefs.search_locations)
        )
    return sources


def fetch_all(db_path: Path, prefs: Prefs, *, progress: ProgressFn | None = None) -> str:
    """Pull jobs from every configured source. Returns a summary line."""
    on = progress or _noop
    sources = _build_sources(prefs)
    on(f"fetch: {len(sources)} sources configured")
    total = 0
    errors: list[str] = []
    cooled: list[str] = []
    for src in sources:
        if store_db.is_source_in_cooldown(db_path, src.name):
            cooled.append(src.name)
            on(f"fetch[{src.name}]: cooled, skipping")
            continue
        on(f"fetch[{src.name}]: starting…")
        try:
            n = 0
            for raw in src.fetch(since=store_db.source_last_fetched(db_path, src.name)):
                store_db.upsert_job(db_path, raw)
                total += 1
                n += 1
            store_db.mark_source_fetched(db_path, src.name, datetime.now(UTC))
            on(f"fetch[{src.name}]: +{n} jobs")
        except (
            IndeedBanDetectedError,
            LinkedInBanDetectedError,
            GlassdoorBanDetectedError,
            WellfoundBanDetectedError,
            OttaBanDetectedError,
        ):
            store_db.mark_source_cooldown(
                db_path,
                src.name,
                until=datetime.now(UTC) + timedelta(hours=24),
            )
            errors.append(f"{src.name}: banned, cooled 24h")
            on(f"fetch[{src.name}]: banned, cooled 24h")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{src.name}: {e}")
            on(f"fetch[{src.name}]: error — {e}")
    parts = [f"fetched {total} jobs"]
    if cooled:
        parts.append(f"({len(cooled)} cooled)")
    if errors:
        parts.append(f"({len(errors)} errors)")
    return " ".join(parts)


def rank_all(
    db_path: Path,
    *,
    cfg: Config,
    prefs: Prefs,
    resume_path: Path,
    anthropic_client: Any | None,
    top_k: int = 30,
    progress: ProgressFn | None = None,
) -> str:
    on = progress or _noop
    on("rank: loading embedding model…")
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
        progress=on,
    )
    return (
        f"cosine_scored={summary.cosine_scored} | filtered={summary.filtered} | "
        f"llm_top_k={summary.cosine_top_k} | llm={summary.llm_scored} | "
        f"cost=${summary.cost_usd:.4f}"
    )


def rerank_selected(
    db_path: Path,
    job_ids: list[int],
    *,
    cfg: Config,
    prefs: Prefs,
    resume_path: Path,
    anthropic_client: Any,
    progress: ProgressFn | None = None,
) -> str:
    """LLM rerank a specific list of job IDs. Caller supplies a real client."""
    on = progress or _noop
    on(f"rerank: {len(job_ids)} job(s) → Claude Haiku")
    reranker = LLMReranker(client=anthropic_client, model=cfg.ranker.rerank_model)
    summary = rerank_jobs(
        db_path,
        job_ids,
        prefs=prefs,
        resume_path=resume_path,
        reranker=reranker,
        progress=on,
    )
    return (
        f"reranked {summary.scored}/{summary.requested} | "
        f"cost=${summary.cost_usd:.4f} | tokens={summary.tokens_in}/{summary.tokens_out}"
    )


def tailor_one(
    db_path: Path,
    job_id: int,
    *,
    cfg: Config,
    prefs: Prefs,
    resume_path: Path,
    output_root: Path,
    anthropic_client: Any,
) -> str:
    orch = TailorOrchestrator(
        db_path=db_path,
        output_root=output_root,
        anthropic_client=anthropic_client,
        model=cfg.tailor.model,
        pdf_template=cfg.paths.pdf_template,
    )
    out = orch.tailor(job_id=job_id, resume_path=resume_path, prefs=prefs)
    return f"tailored → {out.output_dir} (${out.cost_usd:.4f})"
