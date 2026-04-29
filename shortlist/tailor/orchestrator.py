"""Tailor orchestrator: load → Sonnet → parse → write 3 MD + 2 PDFs → record."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shortlist.config import Prefs
from shortlist.store import db as store_db
from shortlist.tailor.pdf import PandocMissingError, render_md_to_pdf
from shortlist.tailor.sonnet import SonnetTailorClient, TailorRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TailorOutput:
    output_dir: Path
    cost_usd: float
    tokens_in: int
    tokens_out: int


def _slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "job"


def _prefs_summary(prefs: Prefs) -> str:
    return (
        f"titles: {', '.join(prefs.titles)}\n"
        f"seniority: {', '.join(prefs.seniority)}\n"
        f"locations: {', '.join(prefs.locations)}\n"
        f"remote_ok: {prefs.remote_ok}\n"
        f"comp_floor_usd: {prefs.comp_floor_usd}"
    )


class TailorOrchestrator:
    def __init__(
        self,
        *,
        db_path: Path,
        output_root: Path,
        anthropic_client: Any,
        model: str = "claude-sonnet-4-6",
        pdf_template: Path | None = None,
        cover_paragraphs: int = 3,
    ):
        self._db = db_path
        self._root = output_root
        self._client = SonnetTailorClient(client=anthropic_client, model=model)
        self._template = pdf_template
        self._cover_paragraphs = cover_paragraphs

    def tailor(
        self,
        *,
        job_id: int,
        resume_path: Path,
        prefs: Prefs,
    ) -> TailorOutput:
        jobs = [j for j in store_db.list_jobs(self._db) if j.id == job_id]
        if not jobs:
            raise ValueError(f"job {job_id} not found")
        job = jobs[0]

        req = TailorRequest(
            resume=resume_path.read_text(),
            prefs_summary=_prefs_summary(prefs),
            job_title=job.title,
            company=job.company,
            job_description=job.description_md or "",
            cover_paragraphs=self._cover_paragraphs,
        )
        result = self._client.tailor(req)

        out_dir = self._root / f"{_slug(job.company)}-{_slug(job.title)}-{job.id}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "resume.md").write_text(result.sections.resume + "\n")
        (out_dir / "cover.md").write_text(result.sections.cover + "\n")
        (out_dir / "notes.md").write_text(result.sections.notes + "\n")

        # Render PDFs (best-effort).
        for stem in ("resume", "cover"):
            md = out_dir / f"{stem}.md"
            pdf = out_dir / f"{stem}.pdf"
            try:
                render_md_to_pdf(md, pdf, template=self._template)
            except PandocMissingError as e:
                logger.warning("PDF skipped (%s): %s", stem, e)
            except Exception as e:  # noqa: BLE001 — render is best-effort
                logger.warning("PDF render failed (%s): %s", stem, e)

        # Record in store.
        with store_db.connect(self._db) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tailor_outputs "
                "(job_id, output_dir, rendered_at, cost_usd, tokens_in, tokens_out) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    str(out_dir),
                    store_db._utc_iso(datetime.now(UTC)),
                    result.cost_usd,
                    result.tokens_in,
                    result.tokens_out,
                ),
            )

        # Transition status if currently `new`.
        if job.status == "new":
            store_db.transition_status(self._db, job_id, "tailored")
        store_db.log_event(
            self._db,
            job_id=job_id,
            type="tailor.complete",
            payload={"output_dir": str(out_dir)},
            cost_usd=result.cost_usd,
            tokens=result.tokens_in + result.tokens_out,
        )

        return TailorOutput(
            output_dir=out_dir,
            cost_usd=result.cost_usd,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
        )
