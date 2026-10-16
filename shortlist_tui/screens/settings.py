"""Settings screen — read-only view of config + prefs."""

from __future__ import annotations

import os
import subprocess

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from shortlist import paths
from shortlist.config import load_config, load_prefs
from shortlist.profiles import Profile


class SettingsScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.pop_screen", "Back"),
        Binding("e", "edit_externally", "Edit (external)"),
    ]

    def __init__(self, profile: Profile) -> None:
        super().__init__()
        self.profile = profile

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static(id="config-summary"),
            Static(id="prefs-summary"),
            Static(id="paths-summary"),
        )
        yield Footer()

    def on_mount(self) -> None:
        try:
            cfg = load_config(paths.config_path())
            self.query_one("#config-summary", Static).update(
                f"[bold]Config[/bold] — {paths.config_path()}\n"
                f"  budget daily ${cfg.budget.daily_usd:.2f} / "
                f"monthly ${cfg.budget.monthly_usd:.2f}\n"
                f"  rerank model: {cfg.ranker.rerank_model}\n"
                f"  tailor model: {cfg.tailor.model}\n"
                f"  enabled sources: " + ", ".join(k for k, v in cfg.sources.items() if v.enabled)
            )
        except FileNotFoundError:
            self.query_one("#config-summary", Static).update(
                "[red]config.yaml missing — run `shortlist config init`[/red]"
            )

        try:
            prefs = load_prefs(self.profile.prefs_path)
            self.query_one("#prefs-summary", Static).update(
                f"[bold]Prefs[/bold] — {self.profile.prefs_path}\n"
                f"  titles: {', '.join(prefs.titles)}\n"
                f"  locations: {', '.join(prefs.locations)}\n"
                f"  comp floor: ${prefs.comp_floor_usd:,}\n"
                f"  greenhouse: {len(prefs.greenhouse_companies)} companies\n"
                f"  lever: {len(prefs.lever_companies)} | "
                f"ashby: {len(prefs.ashby_companies)} | "
                f"workable: {len(prefs.workable_companies)} | "
                f"smartrecruiters: {len(prefs.smartrecruiters_companies)}"
            )
        except FileNotFoundError:
            self.query_one("#prefs-summary", Static).update("[red]prefs.yaml missing[/red]")

        self.query_one("#paths-summary", Static).update(
            f"[bold]Paths[/bold]\n  data: {paths.data_dir()}\n  db: {self.profile.db_path}"
        )

    def action_edit_externally(self) -> None:
        editor = os.environ.get("EDITOR", "nano")
        subprocess.Popen([editor, str(paths.config_path())])
