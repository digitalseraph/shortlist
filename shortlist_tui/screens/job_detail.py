"""JobDetail screen — show JD + tailored docs preview."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Markdown, Static

from shortlist.store import db as store_db


def _load_tailor_dir(db_path: Path, job_id: int) -> Path | None:
    with store_db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT output_dir FROM tailor_outputs WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return Path(row[0])


class JobDetailScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.pop_screen", "Back"),
        Binding("o", "open_url", "Open URL"),
    ]

    def __init__(self, db_path: Path, job_id: int) -> None:
        super().__init__()
        self._db = db_path
        self._job_id = job_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static(id="title"),
            Static(id="meta"),
            Markdown(id="description"),
            Static("---", id="sep1"),
            Markdown(id="resume_md"),
            Markdown(id="cover_md"),
            Markdown(id="notes_md"),
            id="content",
        )
        yield Footer()

    def on_mount(self) -> None:
        jobs = [j for j in store_db.list_jobs(self._db) if j.id == self._job_id]
        if not jobs:
            self.query_one("#title", Static).update("[red]job not found[/red]")
            return
        job = jobs[0]
        from shortlist_tui.data import _format_comp

        comp_str = _format_comp(job.comp_min, job.comp_max)
        self.query_one("#title", Static).update(f"[bold]{job.company}[/bold] — {job.title}")
        self.query_one("#meta", Static).update(
            f"[dim]{job.location or '—'} · {comp_str} · "
            f"{job.status} · score={job.score or '—'}[/dim]\n"
            f"[blue]{job.url}[/blue]"
        )
        self.query_one("#description", Markdown).update(job.description_md or "")

        out_dir = _load_tailor_dir(self._db, job.id)
        if out_dir is None or not out_dir.exists():
            self.query_one("#resume_md", Markdown).update(
                "_No tailored materials yet. Press `t` to generate._"
            )
            self.query_one("#cover_md", Markdown).update("")
            self.query_one("#notes_md", Markdown).update("")
            return
        for stem, widget_id in (
            ("resume", "#resume_md"),
            ("cover", "#cover_md"),
            ("notes", "#notes_md"),
        ):
            md = out_dir / f"{stem}.md"
            self.query_one(widget_id, Markdown).update(
                md.read_text() if md.exists() else f"_{stem}.md missing_"
            )

    def action_open_url(self) -> None:
        jobs = [j for j in store_db.list_jobs(self._db) if j.id == self._job_id]
        if not jobs:
            return
        webbrowser.open(str(jobs[0].url))
