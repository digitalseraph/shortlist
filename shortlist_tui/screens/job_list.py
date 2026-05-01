"""JobList screen — sortable table of all jobs."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static

from shortlist_tui.data import JobRow, list_job_rows


class JobListScreen(Screen[None]):
    """Sortable table of jobs."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "tailor", "Tailor"),
        Binding("slash", "focus_search", "Search"),
        Binding("escape", "clear_search", "Clear", show=False),
    ]

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self._db = db_path
        self._rows: list[JobRow] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Jobs (j/k navigate, enter=open, t=tailor, /=search, q=quit)", id="hint")
        yield Input(placeholder="filter by company or title…", id="search")
        yield DataTable(id="jobs", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Score", "Company", "Title", "Location", "Comp", "Status")
        self._reload()
        table.focus()

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
                r.comp_display,
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

    def action_focus_search(self) -> None:
        self.query_one(Input).focus()

    def action_clear_search(self) -> None:
        inp = self.query_one(Input)
        inp.value = ""
        self._reload()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._render_filtered(event.value.lower().strip())

    def _render_filtered(self, q: str) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for r in self._rows:
            if q and q not in r.company.lower() and q not in r.title.lower():
                continue
            table.add_row(
                r.score_display,
                r.company,
                r.title,
                r.location,
                r.comp_display,
                r.status_display,
                key=str(r.id),
            )

    def action_select_job(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row < 0 or table.cursor_row >= len(self._rows):
            return
        row = self._rows[table.cursor_row]
        from shortlist_tui.screens.job_detail import JobDetailScreen

        self.app.push_screen(JobDetailScreen(self._db, row.id))

    def action_tailor(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row < 0 or table.cursor_row >= len(self._rows):
            return
        row = self._rows[table.cursor_row]
        self.app._tailor_worker(row.id)  # type: ignore[attr-defined]

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open JobDetail when the user confirms a row (enter key on DataTable)."""
        self.action_select_job()
