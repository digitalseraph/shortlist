"""Shortlist TUI main app — minimal scaffold; later tasks add screens."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static


class ShortlistApp(App[None]):
    """Top-level Textual app. Screens are added in later tasks."""

    TITLE = "Shortlist"
    SUB_TITLE = "Personal job-search assistant"
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Shortlist TUI — scaffold only.\nPress q to quit.", id="placeholder")
        yield Footer()


def run_tui() -> None:
    ShortlistApp().run()
