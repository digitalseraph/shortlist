# Shortlist — Plan 4 of 6 (Textual TUI)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Textual TUI on top of the existing `shortlist.*` library. Four screens (JobList, JobDetail, ApplicationsBoard, Settings) + an action menu that fires fetch/rank/tailor/track in background workers. The TUI is a **thin client** — every action goes through the same library entry points the CLI uses, so no new core functionality.

**Architecture:** New top-level package `shortlist_tui/` (sibling of `shortlist/`). It depends on `shortlist.*` but never the reverse — `shortlist.cli` may import `shortlist_tui` to expose `shortlist tui` as a launcher, but `shortlist.*` library code never imports `shortlist_tui`. Long-running operations (Anthropic calls, fetches, embeddings) run in Textual's `@work(thread=True)` workers so the UI stays responsive.

**Tech Stack additions:** `textual>=0.85` (TUI framework), `textual-dev>=1.7` (dev-only — devtools/console). No new system deps.

**Decisions on Plan-3 open questions:**
- **Background tasks:** Textual `@work(thread=True)` workers — simple, built-in, no asyncio rewrite needed for sync `shortlist.*` lib calls.
- **Key bindings:** vim-leaning (`j/k` row nav, `g/G` top/bottom, `/` search, `q` quit) layered on Textual defaults (`tab`/`enter`/`esc`).
- **Entry point:** `shortlist tui` subcommand (single binary, simpler for users); `python -m shortlist_tui` also works.

**Plan-4 file map:**

```
shortlist/
├── pyproject.toml                         (modify — textual deps + entry script)
├── shortlist/
│   └── cli.py                             (modify — `tui` command launches the app)
├── shortlist_tui/
│   ├── __init__.py                        (new — export `run_tui()`)
│   ├── __main__.py                        (new — `python -m shortlist_tui`)
│   ├── app.py                             (new — main Textual App)
│   ├── styles.tcss                        (new — Textual CSS)
│   ├── data.py                            (new — read-only adapters over shortlist.store)
│   ├── workers.py                         (new — fetch/rank/tailor in @work threads)
│   └── screens/
│       ├── __init__.py                    (new)
│       ├── job_list.py                    (new — sortable jobs DataTable)
│       ├── job_detail.py                  (new — JD + tailored docs preview)
│       ├── applications.py                (new — kanban by status)
│       └── settings.py                    (new — config/prefs viewer)
└── tests/
    ├── unit/
    │   ├── test_tui_data.py               (new — adapter unit tests)
    │   └── test_tui_workers.py            (new — worker unit tests)
    └── integration/
        ├── test_tui_job_list.py           (new — JobList interactions)
        ├── test_tui_applications.py       (new)
        ├── test_tui_settings.py           (new)
        └── test_tui_actions.py            (new — fetch/rank/tailor triggered from TUI)
```

**Plan location:** Currently in monorepo at `<monorepo>/docs/superpowers/plans/2026-04-29-shortlist-plan-4-tui.md`. Task 12 migrates it.

---

## Task 1: Deps + `shortlist tui` launcher stub

**Files:**
- Modify: `pyproject.toml`
- Create: `shortlist_tui/__init__.py`
- Create: `shortlist_tui/__main__.py`
- Create: `shortlist_tui/app.py` (minimal — Hello World screen)
- Modify: `shortlist/cli.py` (add `tui` command)
- Modify: `tests/integration/test_cli.py` (add `tui --help` smoke test)

- [ ] **Step 1: Update `pyproject.toml`**

In `[project] dependencies`, append:

```toml
    "textual>=0.85",
```

In `[project.optional-dependencies] dev`, append:

```toml
    "textual-dev>=1.7",
```

In `[tool.hatch.build.targets.wheel] packages`, change to:

```toml
packages = ["shortlist", "shortlist_tui"]
```

In `[tool.mypy]`, the `files` line:

```toml
files = ["shortlist", "shortlist_tui"]
```

- [ ] **Step 2: Reinstall**

```bash
cd ~/dev/repos/shortlist
source .venv/bin/activate
pip install -e ".[dev]"
```

- [ ] **Step 3: Implement `shortlist_tui/__init__.py`**

```python
"""Shortlist Textual TUI."""
from __future__ import annotations

from shortlist_tui.app import run_tui

__all__ = ["run_tui"]
```

- [ ] **Step 4: Implement `shortlist_tui/__main__.py`**

```python
"""Allow `python -m shortlist_tui`."""
from shortlist_tui.app import run_tui

if __name__ == "__main__":
    run_tui()
```

- [ ] **Step 5: Implement minimal `shortlist_tui/app.py`**

```python
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
```

- [ ] **Step 6: Add `tui` command to `shortlist/cli.py`**

Append:

```python
@app.command("tui")
def tui_cmd() -> None:
    """Launch the Textual TUI."""
    from shortlist_tui import run_tui
    run_tui()
```

(Lazy import keeps Textual out of the CLI hot path when users only run `fetch`/`rank`.)

- [ ] **Step 7: Append smoke test**

```python
def test_cli_tui_help_does_not_error(env):
    result = runner.invoke(app, ["tui", "--help"])
    assert result.exit_code == 0
    assert "TUI" in result.output or "tui" in result.output.lower()
```

- [ ] **Step 8: Run gates + commit**

```bash
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add pyproject.toml shortlist_tui/ shortlist/cli.py tests/integration/test_cli.py
git commit -m "feat(tui): scaffold shortlist_tui package + tui CLI launcher"
```

Expected: 1 new pass + 119 prior + 1 skip = 120 pass + 1 skip.

---

## Task 2: Read-only data adapters

**Files:**
- Create: `shortlist_tui/data.py`
- Create: `tests/unit/test_tui_data.py`

The TUI screens shouldn't talk to SQLite directly. `data.py` is a thin facade that returns view-friendly dataclasses (e.g., `JobRow`) from the existing `shortlist.store.db.list_jobs(...)` etc. Pure read; writes happen via `shortlist_tui/workers.py` in T7.

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_tui_data.py
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.models import RawJob
from shortlist.store.db import migrate, update_score, upsert_job
from shortlist_tui.data import JobRow, list_job_rows


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "db.sqlite"


def _seed(db: Path, eid: str = "gh_1", title: str = "Senior Backend Engineer") -> int:
    job = upsert_job(db, RawJob(
        source="greenhouse", external_id=eid, company="Acme",
        title=title, url=f"https://example.com/{eid}",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote - US", remote=True,
    ))
    return job.id


def test_list_job_rows_empty(db_path):
    migrate(db_path)
    rows = list_job_rows(db_path)
    assert rows == []


def test_list_job_rows_returns_jobrow(db_path):
    migrate(db_path)
    jid = _seed(db_path)
    update_score(db_path, jid, score=87, reason="great", model="haiku")
    rows = list_job_rows(db_path)
    assert len(rows) == 1
    assert isinstance(rows[0], JobRow)
    assert rows[0].id == jid
    assert rows[0].score == 87
    assert rows[0].score_display == "87"
    assert rows[0].title == "Senior Backend Engineer"
    assert rows[0].company == "Acme"
    assert rows[0].status_display == "new"


def test_list_job_rows_min_score_filter(db_path):
    migrate(db_path)
    jid1 = _seed(db_path, "a", "Senior Backend Engineer")
    jid2 = _seed(db_path, "b", "Junior Engineer")
    update_score(db_path, jid1, score=80, reason="ok", model="haiku")
    update_score(db_path, jid2, score=10, reason="weak", model="haiku")
    rows = list_job_rows(db_path, min_score=50)
    assert len(rows) == 1
    assert rows[0].id == jid1


def test_jobrow_score_display_handles_none(db_path):
    migrate(db_path)
    _seed(db_path)
    rows = list_job_rows(db_path)
    assert rows[0].score is None
    assert rows[0].score_display == "—"
```

- [ ] **Step 2: Implement `shortlist_tui/data.py`**

```python
"""Read-only TUI data adapters over shortlist.store.

The TUI only consumes these. Writes go through shortlist_tui.workers
(which call the underlying lib) — never directly via SQL from screens.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shortlist.models import JobStatus
from shortlist.store import db as store_db


@dataclass(frozen=True)
class JobRow:
    """View-friendly job for table display."""

    id: int
    score: int | None
    company: str
    title: str
    location: str
    status: JobStatus
    url: str

    @property
    def score_display(self) -> str:
        return "—" if self.score is None else str(self.score)

    @property
    def status_display(self) -> str:
        return self.status


def list_job_rows(
    db_path: Path,
    *,
    status: JobStatus | None = None,
    min_score: int | None = None,
    limit: int | None = None,
) -> list[JobRow]:
    jobs = store_db.list_jobs(db_path, status=status, min_score=min_score, limit=limit)
    return [
        JobRow(
            id=j.id,
            score=j.score,
            company=j.company,
            title=j.title,
            location=j.location or "",
            status=j.status,
            url=str(j.url),
        )
        for j in jobs
    ]
```

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_tui_data.py -v
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist_tui/data.py tests/unit/test_tui_data.py
git commit -m "feat(tui): JobRow data adapter over shortlist.store"
```

Expected: 4 new pass + 120 prior + 1 skip = 124 pass + 1 skip.

---

## Task 3: JobList screen

**Files:**
- Create: `shortlist_tui/screens/__init__.py`
- Create: `shortlist_tui/screens/job_list.py`
- Modify: `shortlist_tui/app.py` (mount JobList as default screen)
- Create: `tests/integration/test_tui_job_list.py`

- [ ] **Step 1: Implement `shortlist_tui/screens/job_list.py`**

```python
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
        yield Static("Jobs (j/k navigate, enter=open, r=refresh, q=quit)",
                     id="hint")
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
                r.score_display, r.company, r.title, r.location, r.status_display,
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
```

- [ ] **Step 2: Update `shortlist_tui/app.py` to mount JobListScreen**

```python
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
```

- [ ] **Step 3: Failing test using Textual `Pilot`**

```python
# tests/integration/test_tui_job_list.py
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.models import RawJob
from shortlist.store.db import migrate, update_score, upsert_job
from shortlist_tui.app import ShortlistApp


@pytest.mark.asyncio
async def test_joblist_renders_seeded_jobs(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    job = upsert_job(db, RawJob(
        source="greenhouse", external_id="acme:1", company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/1",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote - US", remote=True,
    ))
    update_score(db, job.id, score=87, reason="x", model="m")

    async with ShortlistApp(db_path=db).run_test() as pilot:
        await pilot.pause()
        text = pilot.app.screen.render().__str__()
        assert "Acme" in text
        assert "87" in text


@pytest.mark.asyncio
async def test_joblist_quits_on_q(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    async with ShortlistApp(db_path=db).run_test() as pilot:
        await pilot.press("q")
        assert pilot.app.is_running is False or pilot.app.return_value is None
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_tui_job_list.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist_tui/screens/__init__.py shortlist_tui/screens/job_list.py shortlist_tui/app.py tests/integration/test_tui_job_list.py
git commit -m "feat(tui): JobList screen with vim-style key bindings"
```

Expected: 2 new pass + 124 prior + 1 skip = 126 pass + 1 skip.

## Important nuances
- Textual's `Pilot.pause()` flushes pending event queue — required after mount before snapshot.
- `pyproject.toml` already has `asyncio_mode = "strict"` — `@pytest.mark.asyncio` is the only way to run async tests.
- `pytest-asyncio` is in dev deps from Plan-1.

---

## Task 4: JobDetail screen

**Files:**
- Create: `shortlist_tui/screens/job_detail.py`
- Modify: `shortlist_tui/screens/job_list.py` (`enter` pushes JobDetail)
- Modify: `tests/integration/test_tui_job_list.py` (add detail nav test)

- [ ] **Step 1: Implement `shortlist_tui/screens/job_detail.py`**

```python
"""JobDetail screen — show JD + tailored docs preview."""
from __future__ import annotations

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
        self.query_one("#title", Static).update(
            f"[bold]{job.company}[/bold] — {job.title}"
        )
        self.query_one("#meta", Static).update(
            f"[dim]{job.location or ''} · {job.status} · score={job.score or '—'}[/dim]\n"
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
        for stem, widget_id in (("resume", "#resume_md"), ("cover", "#cover_md"),
                                 ("notes", "#notes_md")):
            md = out_dir / f"{stem}.md"
            self.query_one(widget_id, Markdown).update(
                md.read_text() if md.exists() else f"_{stem}.md missing_"
            )

    def action_open_url(self) -> None:
        jobs = [j for j in store_db.list_jobs(self._db) if j.id == self._job_id]
        if not jobs:
            return
        import webbrowser
        webbrowser.open(str(jobs[0].url))
```

- [ ] **Step 2: Wire enter-to-detail in `screens/job_list.py`**

Replace `action_select_job`:

```python
def action_select_job(self) -> None:
    table = self.query_one(DataTable)
    if table.cursor_row < 0 or table.cursor_row >= len(self._rows):
        return
    row = self._rows[table.cursor_row]
    from shortlist_tui.screens.job_detail import JobDetailScreen
    self.app.push_screen(JobDetailScreen(self._db, row.id))
```

- [ ] **Step 3: Append failing test**

```python
@pytest.mark.asyncio
async def test_enter_opens_job_detail(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    job = upsert_job(db, RawJob(
        source="greenhouse", external_id="acme:1", company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/1",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote - US", remote=True,
        description_md="Distributed Python systems.",
    ))
    update_score(db, job.id, score=80, reason="x", model="m")

    async with ShortlistApp(db_path=db).run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        text = pilot.app.screen.render().__str__()
        assert "Senior Backend Engineer" in text
        assert "Distributed Python" in text
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_tui_job_list.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist_tui/screens/job_detail.py shortlist_tui/screens/job_list.py tests/integration/test_tui_job_list.py
git commit -m "feat(tui): JobDetail screen with tailored docs preview"
```

Expected: 1 new pass + 126 prior + 1 skip = 127 pass + 1 skip.

---

## Task 5: ApplicationsBoard screen

**Files:**
- Create: `shortlist_tui/screens/applications.py`
- Create: `shortlist_tui/styles.tcss`
- Modify: `shortlist_tui/app.py` (binding `a`, CSS_PATH)
- Create: `tests/integration/test_tui_applications.py`

- [ ] **Step 1: Implement `shortlist_tui/screens/applications.py`**

```python
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
    "tailored", "applied", "screen", "interview", "offer", "rejected",
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
            *[VerticalScroll(Static(id=f"col-{s}-header"),
                              Static(id=f"col-{s}-body"),
                              id=f"col-{s}", classes="kanban-col")
              for s in _COLUMNS],
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
            body = "\n".join(
                f"• {r.company} — {r.title[:30]}" for r in rows
            ) or "[dim]none[/dim]"
            self.query_one(f"#col-{status}-body", Static).update(body)

    def action_refresh(self) -> None:
        self._reload()
```

- [ ] **Step 2: Create `shortlist_tui/styles.tcss`**

```css
.kanban-col {
    width: 1fr;
    min-width: 20;
    border: round $primary;
    padding: 1;
}

#hint {
    background: $boost;
    padding: 0 1;
}
```

- [ ] **Step 3: Update `shortlist_tui/app.py`**

```python
class ShortlistApp(App[None]):
    TITLE = "Shortlist"
    SUB_TITLE = "Personal job-search assistant"
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("a", "push_applications", "Applications"),
    ]

    def action_push_applications(self) -> None:
        from shortlist_tui.screens.applications import ApplicationsBoardScreen
        self.push_screen(ApplicationsBoardScreen(self._db_path))
```

- [ ] **Step 4: Failing test**

```python
# tests/integration/test_tui_applications.py
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.models import RawJob
from shortlist.store.db import migrate, transition_status, upsert_job
from shortlist_tui.app import ShortlistApp


@pytest.mark.asyncio
async def test_applications_board_groups_by_status(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    job = upsert_job(db, RawJob(
        source="greenhouse", external_id="acme:1", company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/1",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote - US", remote=True,
    ))
    transition_status(db, job.id, "tailored")

    async with ShortlistApp(db_path=db).run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        text = pilot.app.screen.render().__str__()
        assert "tailored" in text
        assert "Acme" in text
```

- [ ] **Step 5: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_tui_applications.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist_tui/screens/applications.py shortlist_tui/app.py shortlist_tui/styles.tcss tests/integration/test_tui_applications.py
git commit -m "feat(tui): ApplicationsBoard kanban + CSS"
```

Expected: 1 new pass + 127 prior + 1 skip = 128 pass + 1 skip.

---

## Task 6: Settings screen

**Files:**
- Create: `shortlist_tui/screens/settings.py`
- Modify: `shortlist_tui/app.py` (binding `s`)
- Create: `tests/integration/test_tui_settings.py`

- [ ] **Step 1: Implement `shortlist_tui/screens/settings.py`**

```python
"""Settings screen — read-only view of config + prefs."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from shortlist import paths
from shortlist.config import load_config, load_prefs


class SettingsScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.pop_screen", "Back"),
        Binding("e", "edit_externally", "Edit (external)"),
    ]

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
                f"  enabled sources: " +
                ", ".join(k for k, v in cfg.sources.items() if v.enabled)
            )
        except FileNotFoundError:
            self.query_one("#config-summary", Static).update(
                "[red]config.yaml missing — run `shortlist config init`[/red]"
            )

        try:
            prefs = load_prefs(paths.prefs_path())
            self.query_one("#prefs-summary", Static).update(
                f"[bold]Prefs[/bold] — {paths.prefs_path()}\n"
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
            self.query_one("#prefs-summary", Static).update(
                "[red]prefs.yaml missing[/red]"
            )

        self.query_one("#paths-summary", Static).update(
            f"[bold]Paths[/bold]\n"
            f"  data: {paths.data_dir()}\n"
            f"  db: {paths.db_path()}"
        )

    def action_edit_externally(self) -> None:
        import os
        import subprocess
        editor = os.environ.get("EDITOR", "nano")
        subprocess.Popen([editor, str(paths.config_path())])
```

- [ ] **Step 2: Add binding to `app.py`**

```python
BINDINGS = [
    ("q", "quit", "Quit"),
    ("a", "push_applications", "Applications"),
    ("s", "push_settings", "Settings"),
]

def action_push_settings(self) -> None:
    from shortlist_tui.screens.settings import SettingsScreen
    self.push_screen(SettingsScreen())
```

- [ ] **Step 3: Failing test**

```python
# tests/integration/test_tui_settings.py
from pathlib import Path

import pytest

from shortlist.store.db import migrate
from shortlist_tui.app import ShortlistApp


@pytest.mark.asyncio
async def test_settings_renders_when_config_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    db = tmp_path / "data" / "db.sqlite"
    migrate(db)
    async with ShortlistApp(db_path=db).run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        text = pilot.app.screen.render().__str__()
        assert "config.yaml missing" in text or "Config" in text
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_tui_settings.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist_tui/screens/settings.py shortlist_tui/app.py tests/integration/test_tui_settings.py
git commit -m "feat(tui): Settings screen with config/prefs summary"
```

Expected: 1 new pass + 128 prior + 1 skip = 129 pass + 1 skip.

---

## Task 7: Background workers (fetch / rank / tailor)

**Files:**
- Create: `shortlist_tui/workers.py`
- Create: `tests/unit/test_tui_workers.py`

The workers wrap CLI-equivalent operations as `@work(thread=True)` callables. They take simple closures (no Textual app reference) so they're unit-testable.

- [ ] **Step 1: Implement `shortlist_tui/workers.py`**

```python
"""Background work: fetch, rank, tailor.

Each function is a synchronous, side-effecting wrapper over shortlist.*
suitable for Textual `@work(thread=True)`. They return summary strings
that screens can display.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shortlist.config import Config, Prefs
from shortlist.ranker.embeddings import EmbeddingService
from shortlist.ranker.llm_rerank import LLMReranker
from shortlist.ranker.pipeline import run_pipeline
from shortlist.sources.ats.ashby import AshbySource
from shortlist.sources.ats.greenhouse import GreenhouseSource
from shortlist.sources.ats.lever import LeverSource
from shortlist.sources.ats.smartrecruiters import SmartRecruitersSource
from shortlist.sources.ats.workable import WorkableSource
from shortlist.sources.base import Source
from shortlist.store import db as store_db
from shortlist.tailor.orchestrator import TailorOrchestrator


def _build_sources(prefs: Prefs) -> list[Source]:
    sources: list[Source] = []
    if prefs.greenhouse_companies:
        sources.append(GreenhouseSource(
            companies={t: t.title() for t in prefs.greenhouse_companies}
        ))
    if prefs.lever_companies:
        sources.append(LeverSource(
            companies={t: t.title() for t in prefs.lever_companies}
        ))
    if prefs.ashby_companies:
        sources.append(AshbySource(
            companies={t: t.title() for t in prefs.ashby_companies}
        ))
    if prefs.workable_companies:
        sources.append(WorkableSource(
            companies={t: t.title() for t in prefs.workable_companies}
        ))
    if prefs.smartrecruiters_companies:
        sources.append(SmartRecruitersSource(
            companies={t: t for t in prefs.smartrecruiters_companies}
        ))
    return sources


def fetch_all(db_path: Path, prefs: Prefs) -> str:
    """Pull jobs from every configured source. Returns a summary line."""
    total = 0
    errors: list[str] = []
    for src in _build_sources(prefs):
        try:
            for raw in src.fetch(since=store_db.source_last_fetched(db_path, src.name)):
                store_db.upsert_job(db_path, raw)
                total += 1
            store_db.mark_source_fetched(db_path, src.name, datetime.now(UTC))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{src.name}: {e}")
    if errors:
        return f"fetched {total} jobs ({len(errors)} source errors)"
    return f"fetched {total} jobs"


def rank_all(
    db_path: Path, *, cfg: Config, prefs: Prefs, resume_path: Path,
    anthropic_client: Any | None, top_k: int = 30,
) -> str:
    embedder = EmbeddingService(model_name=cfg.ranker.embedding_model)
    reranker = (
        LLMReranker(client=anthropic_client, model=cfg.ranker.rerank_model)
        if anthropic_client is not None else None
    )
    summary = run_pipeline(
        db_path, prefs=prefs, resume_path=resume_path,
        embedder=embedder, reranker=reranker, top_k=top_k,
    )
    return (
        f"filtered={summary.filtered} | top_k={summary.cosine_top_k} | "
        f"llm={summary.llm_scored} | cost=${summary.cost_usd:.4f}"
    )


def tailor_one(
    db_path: Path, job_id: int, *, cfg: Config, prefs: Prefs,
    resume_path: Path, anthropic_client: Any,
) -> str:
    orch = TailorOrchestrator(
        db_path=db_path,
        output_root=cfg.paths.output_dir.expanduser(),
        anthropic_client=anthropic_client,
        model=cfg.tailor.model,
        pdf_template=cfg.paths.pdf_template,
    )
    out = orch.tailor(job_id=job_id, resume_path=resume_path, prefs=prefs)
    return f"tailored → {out.output_dir} (${out.cost_usd:.4f})"
```

- [ ] **Step 2: Failing tests**

```python
# tests/unit/test_tui_workers.py
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from shortlist.config import Config, Prefs
from shortlist.models import RawJob
from shortlist.store.db import migrate, upsert_job
from shortlist_tui.workers import fetch_all, tailor_one


def _prefs(**ov) -> Prefs:
    base = dict(
        titles=["Senior Backend Engineer"], locations=["Remote"], remote_ok=True,
        comp_floor_usd=180000, exclude_keywords=[], seniority=["senior"],
        greenhouse_companies=[],
    )
    base.update(ov)
    return Prefs.model_validate(base)


def test_fetch_all_empty_prefs_returns_zero(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    msg = fetch_all(db, _prefs())
    assert "fetched 0 jobs" in msg


def test_tailor_one_writes_outputs(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    job = upsert_job(db, RawJob(
        source="greenhouse", external_id="acme:1", company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/1",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote", remote=True,
        description_md="Python work.",
    ))
    resume = tmp_path / "resume.md"
    resume.write_text("R")
    out_root = tmp_path / "jobs"

    fixture = (Path(__file__).parent.parent /
               "fixtures/llm_responses/sonnet_tailor_sample.md")
    fake_anth = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=fixture.read_text())]
    msg.usage.input_tokens = 1500
    msg.usage.output_tokens = 1200
    fake_anth.messages.create.return_value = msg

    cfg = Config.model_validate({
        "anthropic": {"key_source": "env", "key_env_var": "ANTHROPIC_API_KEY"},
        "budget": {"daily_usd": 5.0, "monthly_usd": 60.0},
        "paths": {"resume": str(resume), "output_dir": str(out_root)},
        "sources": {},
        "ranker": {"top_k_for_llm_rerank": 30, "embedding_model": "bge-small-en-v1.5",
                   "rerank_model": "claude-haiku-4-5-20251001"},
        "tailor": {"model": "claude-sonnet-4-6", "cover_paragraphs": 3},
    })

    summary = tailor_one(db, job.id, cfg=cfg, prefs=_prefs(),
                        resume_path=resume, anthropic_client=fake_anth)
    assert "tailored" in summary
    dirs = list(out_root.iterdir())
    assert len(dirs) == 1
```

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_tui_workers.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist_tui/workers.py tests/unit/test_tui_workers.py
git commit -m "feat(tui): background worker wrappers for fetch/rank/tailor"
```

Expected: 2 new pass + 129 prior + 1 skip = 131 pass + 1 skip.

---

## Task 8: Action menu — trigger workers from TUI

**Files:**
- Modify: `shortlist_tui/app.py` (action menu binding `f` fetch, `R` rank, `t` tailor)
- Modify: `shortlist_tui/screens/job_list.py` (`t` triggers tailor on selected job)
- Create: `tests/integration/test_tui_actions.py`

- [ ] **Step 1: Add app-level fetch + rank + tailor actions in `app.py`**

```python
import os

from textual import work

from shortlist.config import load_config, load_prefs
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
            self.notify("ANTHROPIC_API_KEY not set — skipping LLM rerank",
                        severity="warning")
            client = None
        else:
            from anthropic import Anthropic
            client = Anthropic(api_key=key)
        msg = rank_all(self._db_path, cfg=cfg, prefs=prefs,
                       resume_path=resume, anthropic_client=client)
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
        msg = tailor_one(self._db_path, job_id, cfg=cfg, prefs=prefs,
                        resume_path=resume, anthropic_client=Anthropic(api_key=key))
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
```

- [ ] **Step 2: Add tailor action to JobList screen**

In `shortlist_tui/screens/job_list.py`:

```python
BINDINGS = [
    # ... existing ...
    Binding("t", "tailor", "Tailor"),
]


def action_tailor(self) -> None:
    table = self.query_one(DataTable)
    if table.cursor_row < 0 or table.cursor_row >= len(self._rows):
        return
    row = self._rows[table.cursor_row]
    self.app._tailor_worker(row.id)  # type: ignore[attr-defined]
```

- [ ] **Step 3: Failing test**

```python
# tests/integration/test_tui_actions.py
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shortlist.store.db import migrate
from shortlist_tui.app import ShortlistApp


@pytest.mark.asyncio
async def test_f_triggers_fetch(tmp_path: Path, monkeypatch):
    db = tmp_path / "db.sqlite"
    migrate(db)
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(cfg_dir))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))

    called: list[bool] = []
    def fake_fetch_all(*_a, **_k):
        called.append(True)
        return "fetched 0 jobs"
    import shortlist_tui.app as app_mod
    monkeypatch.setattr(app_mod, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(app_mod, "load_prefs", lambda *_a, **_k: MagicMock())

    async with ShortlistApp(db_path=db).run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.app.workers.wait_for_complete()
    assert called == [True]
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_tui_actions.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist_tui/app.py shortlist_tui/screens/job_list.py tests/integration/test_tui_actions.py
git commit -m "feat(tui): action menu (f fetch, R rank, t tailor) via @work threads"
```

Expected: 1 new pass + 131 prior + 1 skip = 132 pass + 1 skip.

## Important nuances
- Textual `@work(thread=True)` runs the function in a background thread — required because `shortlist.*` is sync (httpx, sentence-transformers, anthropic).
- `self.notify(...)` is thread-safe in modern Textual (>=0.50). Older versions need `self.call_from_thread(self.notify, ...)`.
- `exclusive=True, group="fetch"` ensures repeated `f` presses don't pile up duplicate fetches.
- Screen reload after worker completion uses `call_from_thread` because we're in a worker thread, not the main event loop.

---

## Task 9: Polish — search filter on JobList

**Files:**
- Modify: `shortlist_tui/screens/job_list.py` (add Input for `/` search)
- Modify: `tests/integration/test_tui_job_list.py` (add search test)

- [ ] **Step 1: Add search Input to compose + binding**

```python
from textual.widgets import Input


class JobListScreen(Screen[None]):
    BINDINGS = [
        # ... existing ...
        Binding("slash", "focus_search", "Search"),
        Binding("escape", "clear_search", "Clear", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Jobs (j/k navigate, enter=open, t=tailor, /=search, q=quit)",
                     id="hint")
        yield Input(placeholder="filter by company or title…", id="search")
        yield DataTable(id="jobs", cursor_type="row")
        yield Footer()

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
                r.score_display, r.company, r.title, r.location, r.status_display,
                key=str(r.id),
            )
```

- [ ] **Step 2: Append test**

```python
@pytest.mark.asyncio
async def test_search_filters_table(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    upsert_job(db, RawJob(
        source="greenhouse", external_id="a", company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/a",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote", remote=True,
    ))
    upsert_job(db, RawJob(
        source="greenhouse", external_id="b", company="Globex",
        title="Frontend Engineer",
        url="https://example.com/b",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote", remote=True,
    ))

    async with ShortlistApp(db_path=db).run_test() as pilot:
        await pilot.pause()
        await pilot.press("slash")
        await pilot.pause()
        for ch in "globex":
            await pilot.press(ch)
        await pilot.pause()
        text = pilot.app.screen.render().__str__()
        assert "Globex" in text
        assert "Acme" not in text
```

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_tui_job_list.py -v
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist_tui/screens/job_list.py tests/integration/test_tui_job_list.py
git commit -m "feat(tui): live search filter on JobList"
```

Expected: 1 new pass + 132 prior + 1 skip = 133 pass + 1 skip.

---

## Task 10: Theming + footer hints polish

**Files:**
- Modify: `shortlist_tui/styles.tcss`

- [ ] **Step 1: Expand `styles.tcss`**

```css
Screen {
    background: $surface;
}

#hint {
    background: $boost;
    color: $text;
    padding: 0 1;
    height: 1;
}

#search {
    margin: 0 1;
    height: 3;
}

DataTable {
    height: 1fr;
}

.kanban-col {
    width: 1fr;
    min-width: 20;
    border: round $primary;
    padding: 1;
    margin: 0 1;
}

#title {
    text-style: bold;
    padding: 1;
}

#meta {
    color: $text-muted;
    padding: 0 1;
}

Markdown {
    margin: 1;
}
```

- [ ] **Step 2: Run gates + commit (no new tests)**

```bash
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist_tui/styles.tcss
git commit -m "style(tui): expand stylesheet for screens + widgets"
```

---

## Task 11: README updates

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Replace "Plan 3 of 6" status block with:

```markdown
This is **Plan 4 of 6** (Textual TUI). Cumulative status:

- ✅ Plan 1 (foundation): Greenhouse + SQLite + hard filter + CLI
- ✅ Plan 2: Lever, Ashby, Workable, SmartRecruiters; embeddings via `sentence-transformers`; Haiku 4.5 rerank with budget guard
- ✅ Plan 3: Sonnet 4.6 per-job tailoring (resume + cover + notes); pandoc → PDF; status state machine; contacts CRUD
- ✅ Plan 4 (this): Textual TUI — JobList, JobDetail, ApplicationsBoard, Settings; vim-style key bindings; live search
- ⏳ Plan 5: scraped aggregators (Indeed, LinkedIn, Glassdoor) + Playwright
- ⏳ Plan 6: curated boards (HN/Wellfound/Otta/RemoteOK) + RSS + release polish
```

In "First run" section, append:

```bash
shortlist tui                     # launch the TUI
```

Add a "TUI key bindings" section:

```markdown
## TUI key bindings

Global:
- `q` — quit
- `f` — fetch all sources
- `R` — rank (full pipeline)
- `a` — applications board
- `s` — settings

JobList screen:
- `j`/`k` — down/up
- `g`/`G` — top/bottom
- `enter` — open job detail
- `t` — tailor selected job
- `r` — refresh
- `/` — search by company or title
- `escape` — clear search

JobDetail screen:
- `o` — open job URL in browser
- `escape`/`q` — back
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README — Plan 4 features + TUI key bindings"
```

---

## Task 12: Migrate plan + final CI + push

**Files:**
- Create: `docs/plans/2026-04-29-shortlist-plan-4-tui.md`

- [ ] **Step 1: Copy**

```bash
cp /run/media/seraph/Win1Tb/dev/repos/digitalseraph/docs/superpowers/plans/2026-04-29-shortlist-plan-4-tui.md ~/dev/repos/shortlist/docs/plans/
```

- [ ] **Step 2: Final CI**

```bash
cd ~/dev/repos/shortlist
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy shortlist shortlist_tui
.venv/bin/pytest --cov=shortlist --cov=shortlist_tui --cov-report=term-missing --cov-fail-under=80
```

Expected: green; coverage ≥ 80% combined.

- [ ] **Step 3: Commit + push**

```bash
git add docs/plans/2026-04-29-shortlist-plan-4-tui.md
git commit -m "docs: import Plan 4 (TUI) from monorepo"
git push
```

---

## Done definition (Plan 4)

- `shortlist tui` launches a working TUI with JobList, JobDetail, ApplicationsBoard, Settings.
- Vim-style navigation (`j/k/g/G`) + global hotkeys (`f`/`R`/`t`/`a`/`s`/`q`).
- Live search filter on JobList via `/`.
- Background workers run fetch/rank/tailor without blocking the UI.
- All tests pass (~13 new); coverage ≥ 80% combined on `shortlist/` + `shortlist_tui/`.
- ~12 task commits + plan migration on top of Plan 3's 13 commits.

## Next plan trigger

Plan 5 begins on user request. Plan 5 scope: scraped aggregator sources (Indeed, LinkedIn, Glassdoor) using Playwright with stealth + rate limiting + 24h auto-cooldown on IP-ban detection. Per spec these sources ship **disabled by default** in `_DEFAULT_CONFIG`.

## Open questions for Plan 5 brainstorm

- Playwright browser context: persistent profile (saves cookies, faster) or ephemeral (cleaner, slower per call)?
- Indeed/LinkedIn auth: anonymous-only or support user-authenticated sessions for richer data?
- Captcha policy: pause + prompt user to solve manually, or skip + log + cooldown?
