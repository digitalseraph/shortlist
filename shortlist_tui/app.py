"""Shortlist TUI main app."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from shortlist import paths
from shortlist_tui.screens.job_list import JobListScreen


class ShortlistApp(App[None]):
    TITLE = "Shortlist"
    SUB_TITLE = "Personal job-search assistant"
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("a", "push_applications", "Applications"),
        ("s", "push_settings", "Settings"),
    ]

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self._db_path = db_path or paths.db_path()

    def on_mount(self) -> None:
        self.push_screen(JobListScreen(self._db_path))

    def action_push_applications(self) -> None:
        from shortlist_tui.screens.applications import ApplicationsBoardScreen

        self.push_screen(ApplicationsBoardScreen(self._db_path))

    def action_push_settings(self) -> None:
        from shortlist_tui.screens.settings import SettingsScreen

        self.push_screen(SettingsScreen())


def run_tui(db_path: Path | None = None) -> None:
    ShortlistApp(db_path=db_path).run()
