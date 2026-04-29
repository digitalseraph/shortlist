"""Shortlist TUI main app."""

from __future__ import annotations

import os
from pathlib import Path

from textual import work
from textual.app import App

from shortlist import paths
from shortlist.config import load_config, load_prefs
from shortlist_tui.screens.job_list import JobListScreen
from shortlist_tui.workers import fetch_all, rank_all, tailor_one


class ShortlistApp(App[None]):
    TITLE = "Shortlist"
    SUB_TITLE = "Personal job-search assistant"
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("a", "push_applications", "Applications"),
        ("s", "push_settings", "Settings"),
        ("f", "fetch", "Fetch"),
        ("R", "rank", "Rank"),
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

    @work(thread=True, exclusive=True, group="fetch")
    def _fetch_worker(self) -> None:
        prefs = load_prefs(paths.prefs_path())
        msg = fetch_all(self._db_path, prefs)
        self.notify(msg, severity="information")
        screen = self.screen_stack[-1]
        if hasattr(screen, "_reload"):
            self.call_from_thread(screen._reload)

    @work(thread=True, exclusive=True, group="rank")
    def _rank_worker(self) -> None:
        cfg = load_config(paths.config_path())
        prefs = load_prefs(paths.prefs_path())
        resume = cfg.paths.resume.expanduser()
        key = os.environ.get(cfg.anthropic.key_env_var, "")
        if not key:
            self.notify(
                "ANTHROPIC_API_KEY not set — skipping LLM rerank",
                severity="warning",
            )
            client = None
        else:
            from anthropic import Anthropic

            client = Anthropic(api_key=key)
        msg = rank_all(
            self._db_path,
            cfg=cfg,
            prefs=prefs,
            resume_path=resume,
            anthropic_client=client,
        )
        self.notify(msg, severity="information")
        screen = self.screen_stack[-1]
        if hasattr(screen, "_reload"):
            self.call_from_thread(screen._reload)

    @work(thread=True, exclusive=True, group="tailor")
    def _tailor_worker(self, job_id: int) -> None:
        cfg = load_config(paths.config_path())
        prefs = load_prefs(paths.prefs_path())
        resume = cfg.paths.resume.expanduser()
        key = os.environ.get(cfg.anthropic.key_env_var, "")
        if not key:
            self.notify("ANTHROPIC_API_KEY not set", severity="error")
            return
        from anthropic import Anthropic

        msg = tailor_one(
            self._db_path,
            job_id,
            cfg=cfg,
            prefs=prefs,
            resume_path=resume,
            anthropic_client=Anthropic(api_key=key),
        )
        self.notify(msg, severity="information")
        screen = self.screen_stack[-1]
        if hasattr(screen, "_reload"):
            self.call_from_thread(screen._reload)

    def action_fetch(self) -> None:
        self.notify("fetching…")
        self._fetch_worker()

    def action_rank(self) -> None:
        self.notify("ranking…")
        self._rank_worker()


def run_tui(db_path: Path | None = None) -> None:
    ShortlistApp(db_path=db_path).run()
