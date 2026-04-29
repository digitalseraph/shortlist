"""JobList screen — sortable table of all jobs."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from shortlist_tui.data import JobRow, list_job_rows


class JobListScreen(Screen[None]):
    """Sortable table of jobs."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "select_job", "Open"),
    ]

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self._db = db_path
        self._rows: list[JobRow] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Jobs (j/k navigate, enter=open, r=refresh, q=quit)", id="hint")
        yield DataTable(id="jobs", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Score", "Company", "Title", "Location", "Status")
        self._reload()

    def _reload(self) -> None:
        self._rows = list_job_rows(self._db)
        table = self.query_one(DataTable)
        table.clear()
        for r in self._rows:
            table.add_row(
                r.score_display,
                r.company,
                r.title,
                r.location,
                r.status_display,
                key=str(r.id),
            )

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def action_cursor_top(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count > 0:
            table.move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count > 0:
            table.move_cursor(row=table.row_count - 1)

    def action_refresh(self) -> None:
        self._reload()

    def action_select_job(self) -> None:
        # Detail screen lands in T4 — for now no-op.
        pass
