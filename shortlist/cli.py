"""Shortlist Typer CLI.

Subcommand groups:
  config  — view config + write defaults
  db      — init / status / backup
  fetch   — pull jobs from enabled sources
  rank    — hard filter → cosine top-K → Haiku rerank
  list    — print stored jobs
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from shortlist import paths
from shortlist.config import Prefs, load_prefs
from shortlist.sources.ats.ashby import AshbySource
from shortlist.sources.ats.greenhouse import GreenhouseSource
from shortlist.sources.ats.lever import LeverSource
from shortlist.sources.ats.smartrecruiters import SmartRecruitersSource
from shortlist.sources.ats.workable import WorkableSource
from shortlist.sources.base import Source
from shortlist.store import db as store_db

app = typer.Typer(no_args_is_help=True, help="Shortlist — personal job search.")
console = Console()

# --- db subgroup ----------------------------------------------------------

db_app = typer.Typer(help="Database admin.")
app.add_typer(db_app, name="db")


@db_app.command("init")
def db_init() -> None:
    """Create the SQLite database and apply migrations."""
    target = paths.db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    store_db.migrate(target)
    console.print(f"[green]ok[/green] db at {target}")


@db_app.command("status")
def db_status() -> None:
    """Print schema version + db location."""
    target = paths.db_path()
    if not target.exists():
        console.print(f"db not present at {target}")
        console.print("schema version: 0")
        return
    version = store_db.current_version(target)
    console.print(f"db: {target}")
    console.print(f"schema version: {version}")


@db_app.command("backup")
def db_backup() -> None:
    """Copy the SQLite file to a timestamped backup."""
    src = paths.db_path()
    if not src.exists():
        console.print(f"[yellow]no db at {src}[/yellow]")
        raise typer.Exit(code=1)
    backup_dir = paths.data_dir() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dst = backup_dir / f"db-{stamp}.sqlite"
    shutil.copy2(src, dst)
    console.print(f"[green]ok[/green] backup at {dst}")


# --- config subgroup ------------------------------------------------------

config_app = typer.Typer(help="Manage configuration.")
app.add_typer(config_app, name="config")


_DEFAULT_CONFIG = """\
# Shortlist configuration. See docs/spec.md for the full reference.
anthropic:
  key_source: env
  key_env_var: ANTHROPIC_API_KEY
budget:
  daily_usd: 5.00
  monthly_usd: 60.00
paths:
  resume: ~/jobs/resume.md
  output_dir: ~/jobs
sources:
  greenhouse:
    enabled: true
    rate_limit_rpm: 30
ranker:
  top_k_for_llm_rerank: 30
  embedding_model: bge-small-en-v1.5
  rerank_model: claude-haiku-4-5-20251001
tailor:
  model: claude-sonnet-4-6
  cover_paragraphs: 3
"""

_DEFAULT_PREFS = """\
# Shortlist preferences. Edit these to taste.
titles:
  - "Senior Backend Engineer"
  - "Staff Engineer"
locations:
  - "Remote - US"
  - "Atlanta, GA"
remote_ok: true
comp_floor_usd: 180000
exclude_keywords: []
seniority:
  - senior
  - staff
greenhouse_companies: []
lever_companies: []
ashby_companies: []
workable_companies: []
smartrecruiters_companies: []
"""


@config_app.command("init")
def config_init() -> None:
    """Write default config.yaml and prefs.yaml if not present."""
    paths.config_dir().mkdir(parents=True, exist_ok=True)
    cfg_path = paths.config_path()
    prefs_path = paths.prefs_path()
    wrote: list[Path] = []
    if not cfg_path.exists():
        cfg_path.write_text(_DEFAULT_CONFIG)
        wrote.append(cfg_path)
    if not prefs_path.exists():
        prefs_path.write_text(_DEFAULT_PREFS)
        wrote.append(prefs_path)
    if wrote:
        for p in wrote:
            console.print(f"[green]wrote[/green] {p}")
    else:
        console.print("[yellow]no changes — both files exist[/yellow]")


@config_app.command("show")
def config_show() -> None:
    """Print current config.yaml + prefs.yaml."""
    for p in (paths.config_path(), paths.prefs_path()):
        if not p.exists():
            console.print(f"[yellow]missing[/yellow] {p}")
            continue
        console.rule(str(p))
        console.print(p.read_text())


# --- fetch ----------------------------------------------------------------


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


@app.command("fetch")
def fetch() -> None:
    """Pull jobs from all enabled sources."""
    if not paths.prefs_path().exists():
        console.print("[red]error[/red] run `shortlist config init` first")
        raise typer.Exit(code=2)
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)

    prefs = load_prefs(paths.prefs_path())
    db = paths.db_path()

    total = 0
    for src in _build_sources(prefs):
        try:
            for raw in src.fetch(since=store_db.source_last_fetched(db, src.name)):
                store_db.upsert_job(db, raw)
                total += 1
            store_db.mark_source_fetched(db, src.name, datetime.now(UTC))
        except Exception as e:  # noqa: BLE001 — surface and continue
            console.print(f"[yellow]{src.name} error:[/yellow] {e}")

    console.print(f"fetched {total} jobs")


# --- rank -----------------------------------------------------------------

from anthropic import Anthropic  # noqa: E402

from shortlist.config import load_config  # noqa: E402
from shortlist.ranker.embeddings import EmbeddingService  # noqa: E402
from shortlist.ranker.llm_rerank import LLMReranker  # noqa: E402
from shortlist.ranker.pipeline import run_pipeline  # noqa: E402
from shortlist.tailor.orchestrator import TailorOrchestrator  # noqa: E402


@app.command("rank")
def rank(
    top_k: int = typer.Option(30, "--top-k", help="Cosine pre-rank size."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip Haiku rerank ($0)."),
) -> None:
    """Score stored jobs: hard filter → cosine top-K → Haiku rerank."""
    if not paths.prefs_path().exists() or not paths.config_path().exists():
        console.print("[red]error[/red] run `shortlist config init` first")
        raise typer.Exit(code=2)
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)

    cfg = load_config(paths.config_path())
    prefs = load_prefs(paths.prefs_path())
    resume = cfg.paths.resume.expanduser()
    if not resume.exists():
        console.print(f"[red]error[/red] resume not found at {resume}")
        raise typer.Exit(code=2)

    embedder = EmbeddingService(model_name=cfg.ranker.embedding_model)

    reranker: LLMReranker | None = None
    if not no_llm:
        import os

        key = os.environ.get(cfg.anthropic.key_env_var, "")
        if not key:
            console.print(
                f"[yellow]{cfg.anthropic.key_env_var} not set — running with --no-llm[/yellow]"
            )
        else:
            reranker = LLMReranker(
                client=Anthropic(api_key=key),
                model=cfg.ranker.rerank_model,
            )

    summary = run_pipeline(
        paths.db_path(),
        prefs=prefs,
        resume_path=resume,
        embedder=embedder,
        reranker=reranker,
        top_k=top_k,
    )
    console.print(
        f"ranked: filtered={summary.filtered}, cosine_top_k={summary.cosine_top_k}, "
        f"llm_scored={summary.llm_scored}, cost=${summary.cost_usd:.4f}"
    )


@app.command("tailor")
def tailor_cmd(
    job_id: int = typer.Argument(..., help="Job id to tailor materials for."),
    cover_paragraphs: int = typer.Option(3, "--cover-paras"),
) -> None:
    """Generate per-job resume + cover + notes (Markdown + PDF)."""
    if not paths.config_path().exists() or not paths.prefs_path().exists():
        console.print("[red]error[/red] run `shortlist config init` first")
        raise typer.Exit(code=2)
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)

    cfg = load_config(paths.config_path())
    prefs = load_prefs(paths.prefs_path())
    resume = cfg.paths.resume.expanduser()
    if not resume.exists():
        console.print(f"[red]error[/red] resume not found at {resume}")
        raise typer.Exit(code=2)

    import os

    key = os.environ.get(cfg.anthropic.key_env_var, "")
    if not key:
        console.print(f"[red]error[/red] {cfg.anthropic.key_env_var} not set")
        raise typer.Exit(code=2)

    orch = TailorOrchestrator(
        db_path=paths.db_path(),
        output_root=cfg.paths.output_dir.expanduser(),
        anthropic_client=Anthropic(api_key=key),
        model=cfg.tailor.model,
        pdf_template=cfg.paths.pdf_template,
        cover_paragraphs=cover_paragraphs,
    )
    out = orch.tailor(job_id=job_id, resume_path=resume, prefs=prefs)
    console.print(
        f"[green]wrote[/green] {out.output_dir} "
        f"(${out.cost_usd:.4f}, {out.tokens_in + out.tokens_out} tok)"
    )


# --- list -----------------------------------------------------------------


@app.command("list")
def list_jobs_cmd(
    min_score: int = typer.Option(0, "--min-score", help="Hide jobs scoring below."),
    limit: int = typer.Option(50, "--limit", help="Max rows to print."),
) -> None:
    """Print stored jobs as a table, ordered by score DESC."""
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)
    rows = store_db.list_jobs(paths.db_path(), min_score=min_score, limit=limit)
    if not rows:
        console.print("[dim]no jobs[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Company")
    table.add_column("Title", no_wrap=True)
    table.add_column("Location")
    table.add_column("URL", overflow="fold")
    for j in rows:
        table.add_row(
            "—" if j.score is None else str(j.score),
            j.company,
            j.title,
            j.location or "",
            str(j.url),
        )
    console.print(table)
