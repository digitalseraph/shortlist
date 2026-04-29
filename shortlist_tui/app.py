"""Shortlist TUI main app."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from shortlist import paths
from shortlist_tui.screens.job_list import JobListScreen


class ShortlistApp(App[None]):
    TITLE = "Shortlist"
    SUB_TITLE = "Personal job-search assistant"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self._db_path = db_path or paths.db_path()

    def on_mount(self) -> None:
        self.push_screen(JobListScreen(self._db_path))


def run_tui(db_path: Path | None = None) -> None:
    ShortlistApp(db_path=db_path).run()
