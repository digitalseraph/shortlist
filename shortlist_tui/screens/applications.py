"""ApplicationsBoard — kanban-style by status."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from shortlist.models import JobStatus
from shortlist_tui.data import list_job_rows

_COLUMNS: tuple[JobStatus, ...] = (
    "tailored",
    "applied",
    "screen",
    "interview",
    "offer",
    "rejected",
)


class ApplicationsBoardScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.pop_screen", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self._db = db_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            *[
                VerticalScroll(
                    Static(id=f"col-{s}-header"),
                    Static(id=f"col-{s}-body"),
                    id=f"col-{s}",
                    classes="kanban-col",
                )
                for s in _COLUMNS
            ],
            id="board",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._reload()

    def _reload(self) -> None:
        for status in _COLUMNS:
            rows = list_job_rows(self._db, status=status)
            self.query_one(f"#col-{status}-header", Static).update(
                f"[bold]{status}[/bold] ({len(rows)})"
            )
            lines: list[str] = []
            for r in rows:
                loc = r.location[:20] if r.location else "—"
                lines.append(
                    f"• [bold]{r.company}[/bold] — {r.title[:30]}\n"
                    f"  [dim]{loc} · {r.comp_display}[/dim]"
                )
            body = "\n".join(lines) or "[dim]none[/dim]"
            self.query_one(f"#col-{status}-body", Static).update(body)

    def action_refresh(self) -> None:
        self._reload()
