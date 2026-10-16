"""Cost dashboard — aggregates rank + tailor spend from SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from shortlist import profiles
from shortlist.profiles import Profile
from shortlist.store import db as store_db
from shortlist_web.routes._shared import page_context, profile_dep

router = APIRouter()


def _get_env(request: Request) -> Environment:
    templates_dir: Path = request.app.state.templates_dir
    return Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)


@dataclass(frozen=True)
class RunRow:
    started_at: datetime | None
    model: str
    job_count: int
    cost_usd: float
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class TailorRow:
    job_id: int
    company: str
    title: str
    rendered_at: datetime | None
    cost_usd: float
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class ModelTotal:
    model: str
    runs: int
    cost_usd: float
    tokens_in: int
    tokens_out: int


def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _aggregate(db_path: Path) -> dict[str, object]:
    with store_db.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        rank_total = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS cost, "
            "       COALESCE(SUM(tokens_in), 0) AS tin, "
            "       COALESCE(SUM(tokens_out), 0) AS tout, "
            "       COUNT(*) AS n "
            "FROM scoring_runs"
        ).fetchone()

        tailor_total = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS cost, "
            "       COALESCE(SUM(tokens_in), 0) AS tin, "
            "       COALESCE(SUM(tokens_out), 0) AS tout, "
            "       COUNT(*) AS n "
            "FROM tailor_outputs"
        ).fetchone()

        rank_runs = [
            RunRow(
                started_at=_parse(r["started_at"]),
                model=r["model"],
                job_count=r["job_count"],
                cost_usd=r["cost_usd"] or 0.0,
                tokens_in=r["tokens_in"] or 0,
                tokens_out=r["tokens_out"] or 0,
            )
            for r in conn.execute(
                "SELECT started_at, model, job_count, cost_usd, tokens_in, tokens_out "
                "FROM scoring_runs ORDER BY started_at DESC LIMIT 20"
            ).fetchall()
        ]

        tailor_rows = [
            TailorRow(
                job_id=r["job_id"],
                company=r["company"],
                title=r["title"],
                rendered_at=_parse(r["rendered_at"]),
                cost_usd=r["cost_usd"] or 0.0,
                tokens_in=r["tokens_in"] or 0,
                tokens_out=r["tokens_out"] or 0,
            )
            for r in conn.execute(
                "SELECT t.job_id, j.company, j.title, t.rendered_at, "
                "       t.cost_usd, t.tokens_in, t.tokens_out "
                "FROM tailor_outputs t JOIN jobs j ON j.id = t.job_id "
                "ORDER BY t.rendered_at DESC LIMIT 20"
            ).fetchall()
        ]

        by_model = [
            ModelTotal(
                model=r["model"],
                runs=r["runs"],
                cost_usd=r["cost"] or 0.0,
                tokens_in=r["tin"] or 0,
                tokens_out=r["tout"] or 0,
            )
            for r in conn.execute(
                "SELECT model, COUNT(*) AS runs, SUM(cost_usd) AS cost, "
                "       SUM(tokens_in) AS tin, SUM(tokens_out) AS tout "
                "FROM scoring_runs GROUP BY model ORDER BY cost DESC"
            ).fetchall()
        ]

    rank_cost = rank_total["cost"] or 0.0
    tailor_cost = tailor_total["cost"] or 0.0
    return {
        "rank_total": {
            "cost": rank_cost,
            "tokens_in": rank_total["tin"] or 0,
            "tokens_out": rank_total["tout"] or 0,
            "n": rank_total["n"] or 0,
        },
        "tailor_total": {
            "cost": tailor_cost,
            "tokens_in": tailor_total["tin"] or 0,
            "tokens_out": tailor_total["tout"] or 0,
            "n": tailor_total["n"] or 0,
        },
        "grand_total": rank_cost + tailor_cost,
        "rank_runs": rank_runs,
        "tailor_rows": tailor_rows,
        "by_model": by_model,
    }


def combined_totals() -> list[tuple[Profile, float]]:
    """Total spend per profile, read from each database.

    A fan-out read rather than a shared ledger: cost rows stay attached to the
    scoring run and tailor output that caused them, so this view cannot drift
    from the per-person numbers.
    """
    totals: list[tuple[Profile, float]] = []
    for prof in profiles.list_profiles():
        if not prof.db_path.exists():
            continue
        with store_db.connect(prof.db_path) as conn:
            runs = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM scoring_runs").fetchone()[0]
            tailors = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM tailor_outputs"
            ).fetchone()[0]
        totals.append((prof, float(runs) + float(tailors)))
    return totals


@router.get("/costs", response_class=HTMLResponse)
def costs(request: Request, profile: Profile = Depends(profile_dep)) -> HTMLResponse:
    combined = combined_totals()
    combined_sum = sum(total for _prof, total in combined)
    ctx = page_context(
        request,
        profile,
        combined=combined,
        combined_sum=combined_sum,
        **_aggregate(profile.db_path),
    )
    html = _get_env(request).get_template("costs.html").render(**ctx)
    return HTMLResponse(html)
