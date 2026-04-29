# Shortlist — Plan 3 of 6 (Tailoring + Application Tracking)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-job material tailoring (Sonnet 4.6 generates a focused `resume.md`, `cover.md`, and `notes.md` per job; pandoc renders MD → PDF) and the application lifecycle tracker (state machine + `applications` + `contacts` tables + `events` rows). After Plan 3, `shortlist tailor <id>` produces a folder of submission-ready materials and `shortlist track <id> --status applied` records the application in the database.

**Architecture:** Same three layers (`sources` / `store` / `cli`) plus a new `tailor/` package (Sonnet client + 3-section parser + pandoc subprocess wrapper) and a new `tracker/` package (status state machine + applications/contacts helpers). Migration 003 adds `applications`, `contacts`, and `tailor_outputs` tables. `events` rows record every transition + tailor cost. The user **applies manually** — Shortlist outputs files; you submit them.

**Tech Stack additions:** `subprocess` (stdlib) for pandoc; **system pandoc + pdflatex must be present** for PDF rendering (MD output works without them; PDF rendering errors gracefully if missing). No new pip deps.

**Plan-3 file map (added/modified relative to Plan 2):**

```
shortlist/
├── shortlist/
│   ├── store/
│   │   ├── db.py                          (modify — application/contact helpers)
│   │   └── _migrations/
│   │       └── 003_applications.sql       (new)
│   ├── tailor/
│   │   ├── __init__.py                    (new)
│   │   ├── prompt.py                      (new — system + user prompts)
│   │   ├── parser.py                      (new — split LLM output into 3 sections)
│   │   ├── pdf.py                         (new — pandoc subprocess wrapper)
│   │   ├── sonnet.py                      (new — SonnetTailorClient)
│   │   └── orchestrator.py                (new — load → LLM → parse → write → render)
│   ├── tracker/
│   │   ├── __init__.py                    (new)
│   │   └── state.py                       (new — JobStatus transitions)
│   ├── templates/
│   │   ├── __init__.py                    (new — package marker)
│   │   └── pdf-template.tex               (new — bundled LaTeX template)
│   ├── models.py                          (modify — Application/Contact pydantic models)
│   └── cli.py                             (modify — tailor / track / contacts commands)
└── tests/
    ├── fixtures/
    │   ├── llm_responses/
    │   │   └── sonnet_tailor_sample.md    (new — synthetic Sonnet output)
    │   └── pdf-template.tex               (new — minimal LaTeX template for tests)
    ├── unit/
    │   ├── test_tailor_parser.py          (new)
    │   ├── test_tailor_sonnet.py          (new)
    │   ├── test_tracker_state.py          (new)
    │   └── test_application_models.py     (new)
    └── integration/
        ├── test_applications_store.py     (new)
        ├── test_tailor_pdf.py             (new — skipif pandoc missing)
        ├── test_tailor_orchestrator.py    (new — mocked Sonnet)
        └── test_cli.py                    (extend — tailor/track/contacts commands)
```

**Plan location:** Currently in monorepo at `<monorepo>/docs/superpowers/plans/2026-04-29-shortlist-plan-3-tailor-track.md`. Task 12 migrates it to `~/dev/repos/shortlist/docs/plans/`.

**Decisions on Plan-2 open questions:**
- **PDF backend:** `pandoc` + `pdflatex`. Lighter user-facing latency than `weasyprint`. Plan 1 spec already mentioned `~/.config/shortlist/pdf-template.tex`. If pandoc/pdflatex absent on the system, MD writes succeed and PDF rendering emits a warning (does NOT fail the command).
- **Resume base format:** Markdown only. Future plans may accept PDF + OCR.
- **Contact CRUD UX:** mix — `shortlist contacts add` accepts `--name=… --email=…` flags but uses Typer prompts (`prompt="Name"`) so missing required fields are asked interactively.

---

## Task 1: Migration 003 — applications + contacts + tailor_outputs

**Files:**
- Create: `shortlist/store/_migrations/003_applications.sql`
- Modify: `tests/integration/test_store.py` (extend with v3 migration test)
- Modify: `tests/integration/test_cli.py` (bump `"schema version: 2"` → `"3"`)

- [ ] **Step 1: Write migration**

`shortlist/store/_migrations/003_applications.sql`:

```sql
CREATE TABLE IF NOT EXISTS applications (
    job_id            INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    applied_at        TEXT,
    applied_via       TEXT,
    follow_up_due     TEXT,
    salary_offered    INTEGER,
    decision          TEXT,
    decision_reason   TEXT,
    lessons           TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER NOT NULL REFERENCES applications(job_id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    email           TEXT,
    role            TEXT,
    source          TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_application_id ON contacts (application_id);

CREATE TABLE IF NOT EXISTS tailor_outputs (
    job_id     INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    output_dir TEXT NOT NULL,
    rendered_at TEXT NOT NULL,
    cost_usd   REAL NOT NULL DEFAULT 0.0,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0
);
```

- [ ] **Step 2: Append failing tests**

To `tests/integration/test_store.py`:

```python
def test_migrate_to_v3_creates_applications_and_contacts(db_path: Path):
    migrate(db_path)
    assert current_version(db_path) == 3
    with connect(db_path) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert "applications" in names
    assert "contacts" in names
    assert "tailor_outputs" in names


def test_contacts_cascade_delete_with_application(db_path: Path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO applications (job_id, applied_at) VALUES (?, ?)",
            (job.id, "2026-04-28T12:00:00Z"),
        )
        conn.execute(
            "INSERT INTO contacts (application_id, name, created_at) VALUES (?, ?, ?)",
            (job.id, "Jane Doe", "2026-04-28T12:00:00Z"),
        )
    with connect(db_path) as conn:
        conn.execute("DELETE FROM applications WHERE job_id = ?", (job.id,))
    with connect(db_path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()
    assert rows[0] == 0
```

Also bump existing `current_version == 2` assertions in `test_migrate_from_zero_to_latest` and `test_migrate_is_idempotent` to `== 3`. And update CLI test `test_db_status_reports_version` from `"schema version: 2"` to `"schema version: 3"`.

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/store/_migrations/003_applications.sql tests/integration/test_store.py tests/integration/test_cli.py
git commit -m "feat(store): migration 003 — applications + contacts + tailor_outputs"
```

Expected: 2 new + 87 prior = 89 total (the version-bump assertions don't change count).

---

## Task 2: Pydantic Application + Contact models

**Files:**
- Modify: `shortlist/models.py`
- Create: `tests/unit/test_application_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_application_models.py
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from shortlist.models import Application, Contact


def test_application_minimum_fields():
    a = Application(job_id=1)
    assert a.job_id == 1
    assert a.applied_at is None
    assert a.decision is None


def test_application_with_decision():
    a = Application(
        job_id=1,
        applied_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
        applied_via="company website",
        salary_offered=210000,
        decision="offer",
        decision_reason="Strong technical interview",
    )
    assert a.salary_offered == 210000
    assert a.decision == "offer"


def test_contact_requires_name():
    with pytest.raises(ValidationError):
        Contact(application_id=1, name="", role="recruiter",
                created_at=datetime.now(UTC))


def test_contact_minimum_fields():
    c = Contact(
        application_id=1,
        name="Jane Doe",
        created_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
    )
    assert c.name == "Jane Doe"
    assert c.email is None
```

- [ ] **Step 2: Append to `shortlist/models.py`**

```python
class Application(BaseModel):
    """Lifecycle state for a job we've engaged with."""

    model_config = ConfigDict(extra="forbid")

    job_id: int
    applied_at: datetime | None = None
    applied_via: str | None = None
    follow_up_due: datetime | None = None
    salary_offered: int | None = Field(default=None, ge=0)
    decision: str | None = None
    decision_reason: str | None = None
    lessons: str | None = None


class Contact(BaseModel):
    """A person tied to an application (recruiter, hiring manager, etc.)."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    application_id: int
    name: str = Field(min_length=1)
    email: str | None = None
    role: str | None = None
    source: str | None = None
    created_at: datetime
```

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_application_models.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/models.py tests/unit/test_application_models.py
git commit -m "feat(models): Application + Contact pydantic models"
```

Expected: 4 new pass + 89 prior = 93 total.

---

## Task 3: Tracker state machine

**Files:**
- Create: `shortlist/tracker/__init__.py`
- Create: `shortlist/tracker/state.py`
- Create: `tests/unit/test_tracker_state.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tracker_state.py
import pytest

from shortlist.tracker.state import (
    InvalidStatusTransitionError,
    allowed_next,
    validate_transition,
)


def test_new_to_tailored_allowed():
    validate_transition("new", "tailored")  # no raise


def test_tailored_to_applied_allowed():
    validate_transition("tailored", "applied")


def test_applied_to_screen_allowed():
    validate_transition("applied", "screen")


def test_invalid_backwards_transition_raises():
    with pytest.raises(InvalidStatusTransitionError):
        validate_transition("applied", "new")


def test_invalid_skip_forward_raises():
    with pytest.raises(InvalidStatusTransitionError):
        validate_transition("new", "interview")


def test_withdrawn_allowed_from_any_non_terminal_state():
    for src in ("new", "tailored", "applied", "screen", "interview"):
        validate_transition(src, "withdrawn")


def test_terminal_states_have_no_transitions():
    assert allowed_next("offer") == set()
    assert allowed_next("rejected") == set()
    assert allowed_next("withdrawn") == set()


def test_allowed_next_listing():
    assert "tailored" in allowed_next("new")
    assert "applied" in allowed_next("tailored")
    assert "withdrawn" in allowed_next("new")
```

- [ ] **Step 2: Implement `shortlist/tracker/state.py`**

```python
"""Job status state machine.

Linear-with-branches: new → tailored → applied → screen → interview → offer
                                                               ↘ rejected
                      `withdrawn` reachable from any non-terminal state.
                      Terminal states (offer, rejected, withdrawn) have no
                      outgoing transitions.
"""
from __future__ import annotations

from shortlist.models import JobStatus

_GRAPH: dict[JobStatus, set[JobStatus]] = {
    "new":       {"tailored", "withdrawn"},
    "tailored":  {"applied", "withdrawn"},
    "applied":   {"screen", "rejected", "withdrawn"},
    "screen":    {"interview", "rejected", "withdrawn"},
    "interview": {"offer", "rejected", "withdrawn"},
    "offer":     set(),
    "rejected":  set(),
    "withdrawn": set(),
}


class InvalidStatusTransitionError(ValueError):
    pass


def allowed_next(current: JobStatus) -> set[JobStatus]:
    return _GRAPH.get(current, set())


def validate_transition(current: JobStatus, target: JobStatus) -> None:
    if target not in _GRAPH:
        raise InvalidStatusTransitionError(f"unknown status {target!r}")
    if target not in allowed_next(current):
        raise InvalidStatusTransitionError(
            f"cannot transition {current!r} → {target!r}; "
            f"allowed: {sorted(allowed_next(current))}"
        )
```

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_tracker_state.py -v
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/tracker/__init__.py shortlist/tracker/state.py tests/unit/test_tracker_state.py
git commit -m "feat(tracker): job status state machine with allowed_next + validate"
```

Expected: 8 new pass + 93 prior = 101 total.

---

## Task 4: Store helpers — applications, contacts, transitions, events

**Files:**
- Modify: `shortlist/store/db.py`
- Create: `tests/integration/test_applications_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/integration/test_applications_store.py
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.models import RawJob
from shortlist.store.db import (
    add_contact,
    get_application,
    list_contacts,
    log_event,
    migrate,
    remove_contact,
    transition_status,
    update_application,
    upsert_job,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "shortlist.sqlite"


def _raw(eid: str = "gh_1") -> RawJob:
    return RawJob(
        source="greenhouse", external_id=eid, company="Acme",
        title="Senior Backend Engineer", url="https://example.com/" + eid,
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote - US", remote=True,
    )


def test_transition_status_updates_jobs_row(db_path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    transition_status(db_path, job.id, "tailored")
    from shortlist.store.db import list_jobs
    refreshed = next(j for j in list_jobs(db_path) if j.id == job.id)
    assert refreshed.status == "tailored"
    assert refreshed.status_changed_at is not None


def test_transition_status_rejects_invalid(db_path):
    from shortlist.tracker.state import InvalidStatusTransitionError
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    with pytest.raises(InvalidStatusTransitionError):
        transition_status(db_path, job.id, "interview")


def test_update_application_creates_then_updates(db_path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    update_application(
        db_path, job.id,
        applied_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
        applied_via="company website",
    )
    update_application(db_path, job.id, salary_offered=210000)
    a = get_application(db_path, job.id)
    assert a is not None
    assert a.applied_via == "company website"
    assert a.salary_offered == 210000


def test_contact_add_list_remove(db_path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    update_application(db_path, job.id,
                       applied_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC))
    cid = add_contact(db_path, job.id, name="Jane Doe", email="jane@acme.com",
                      role="recruiter")
    rows = list_contacts(db_path, job.id)
    assert len(rows) == 1
    assert rows[0].name == "Jane Doe"
    assert rows[0].email == "jane@acme.com"
    remove_contact(db_path, cid)
    assert list_contacts(db_path, job.id) == []


def test_log_event_records_transition(db_path):
    import sqlite3
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    log_event(db_path, job_id=job.id, type="status.transition",
              payload={"from": "new", "to": "tailored"})
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT type, payload_json FROM events WHERE job_id = ?", (job.id,)
        ).fetchall()
    assert rows[0][0] == "status.transition"
    assert "tailored" in rows[0][1]
```

- [ ] **Step 2: Append to `shortlist/store/db.py`**

Imports near top:

```python
import json

from shortlist.models import Application, Contact
from shortlist.tracker.state import validate_transition
```

Append helpers:

```python
def transition_status(
    path: Path, job_id: int, target: JobStatus, *,
    when: datetime | None = None,
) -> None:
    """Validate + apply a status transition; record an event."""
    when = when or datetime.now(UTC)
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError(f"job {job_id} not found")
        current: JobStatus = row["status"]
        validate_transition(current, target)
        conn.execute(
            "UPDATE jobs SET status = ?, status_changed_at = ? WHERE id = ?",
            (target, _utc_iso(when), job_id),
        )
        conn.execute(
            "INSERT INTO events (job_id, type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (job_id, "status.transition",
             json.dumps({"from": current, "to": target}), _utc_iso(when)),
        )


def update_application(path: Path, job_id: int, **fields: object) -> None:
    """Upsert the applications row for `job_id`. Only provided fields change."""
    if not fields:
        return
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    sets = ", ".join(f"{k} = excluded.{k}" for k in fields)
    values: list[object] = []
    for v in fields.values():
        if isinstance(v, datetime):
            values.append(_utc_iso(v))
        else:
            values.append(v)
    with connect(path) as conn:
        conn.execute(
            f"INSERT INTO applications (job_id, {cols}) VALUES (?, {placeholders}) "
            f"ON CONFLICT (job_id) DO UPDATE SET {sets}",
            (job_id, *values),
        )


def get_application(path: Path, job_id: int) -> Application | None:
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return Application(
        job_id=row["job_id"],
        applied_at=_parse_dt(row["applied_at"]),
        applied_via=row["applied_via"],
        follow_up_due=_parse_dt(row["follow_up_due"]),
        salary_offered=row["salary_offered"],
        decision=row["decision"],
        decision_reason=row["decision_reason"],
        lessons=row["lessons"],
    )


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def add_contact(
    path: Path, application_id: int, *,
    name: str, email: str | None = None,
    role: str | None = None, source: str | None = None,
    when: datetime | None = None,
) -> int:
    when = when or datetime.now(UTC)
    with connect(path) as conn:
        cursor = conn.execute(
            "INSERT INTO contacts (application_id, name, email, role, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (application_id, name, email, role, source, _utc_iso(when)),
        )
        return int(cursor.lastrowid or 0)


def list_contacts(path: Path, application_id: int) -> list[Contact]:
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM contacts WHERE application_id = ? ORDER BY created_at",
            (application_id,),
        ).fetchall()
    return [
        Contact(
            id=r["id"], application_id=r["application_id"],
            name=r["name"], email=r["email"], role=r["role"], source=r["source"],
            created_at=_parse_dt(r["created_at"]) or datetime.now(UTC),
        )
        for r in rows
    ]


def remove_contact(path: Path, contact_id: int) -> None:
    with connect(path) as conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def log_event(
    path: Path, *, job_id: int | None, type: str,
    payload: dict[str, object] | None = None,
    cost_usd: float | None = None, tokens: int | None = None,
    when: datetime | None = None,
) -> None:
    when = when or datetime.now(UTC)
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO events (job_id, type, payload_json, cost_usd, tokens, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, type, json.dumps(payload or {}), cost_usd, tokens, _utc_iso(when)),
        )
```

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_applications_store.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/store/db.py tests/integration/test_applications_store.py
git commit -m "feat(store): transition_status, update_application, contacts, log_event"
```

Expected: 5 new pass + 101 prior = 106 total.

---

## Task 5: Tailor parser — split LLM output into 3 sections

**Files:**
- Create: `shortlist/tailor/__init__.py`
- Create: `shortlist/tailor/parser.py`
- Create: `tests/fixtures/llm_responses/sonnet_tailor_sample.md`
- Create: `tests/unit/test_tailor_parser.py`

- [ ] **Step 1: Create fixture**

`tests/fixtures/llm_responses/sonnet_tailor_sample.md`:

````markdown
# RESUME

## David Miller

**Senior Backend Engineer** · Atlanta, GA · david@example.com

### Experience

**Acme Inc** — Senior Engineer · 2022–present
- Built distributed services in Python and Postgres
- Led migration from monolith to event-driven microservices
- Mentored 3 engineers and drove on-call rotation policy

**Globex** — Engineer · 2019–2022
- Owned billing service serving 12M users
- Reduced p99 latency 40% via indexed materialized views

### Skills

Python · Postgres · Kubernetes · gRPC · OpenTelemetry

# COVER

Hi Acme team,

I'm applying for the Senior Backend Engineer role because the platform you describe — Python services, Postgres at scale, an explicit bias toward observability — maps directly to the work I've done for the past four years. I built and maintained a similar stack at my current employer, including the move from a monolith to event-driven services, and I've shipped Kubernetes and gRPC work end-to-end.

What stood out in your posting is the emphasis on the migration's people-side: documentation, on-call rotation, and mentorship. Those are the parts of platform work I find most energizing, and they're where I've spent the past year as much as on the code itself.

I'd love to talk about how I could contribute. Resume attached; happy to schedule.

— David Miller

# NOTES

**Why this fits:** Direct stack overlap (Python + Postgres + K8s); my migration experience matches the JD's "moving from monolith" callout; my mentorship/on-call work answers the "lead through ambiguity" line.

**Gaps to address:** They mention Kafka explicitly; I've used RabbitMQ and SQS but not Kafka in production. Worth being upfront — emphasize transferable streaming/event-driven experience.

**Questions for interviewer:**
1. How is the platform team structured today vs. where you want it in 18 months?
2. What's the biggest technical debt item the new senior IC is expected to tackle in their first 90 days?
3. How does on-call work — pager rotation, severity bands, blameless postmortems?
````

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_tailor_parser.py
from pathlib import Path

import pytest

from shortlist.tailor.parser import TailorParseError, parse_tailor_output

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_three_sections():
    text = (FIXTURES / "llm_responses/sonnet_tailor_sample.md").read_text()
    parsed = parse_tailor_output(text)
    assert "David Miller" in parsed.resume
    assert "Hi Acme team," in parsed.cover
    assert "Why this fits:" in parsed.notes


def test_parse_missing_section_raises():
    text = "# RESUME\n\nfoo\n\n# COVER\n\nbar\n"  # no NOTES
    with pytest.raises(TailorParseError):
        parse_tailor_output(text)


def test_parse_strips_section_markers_from_body():
    text = "# RESUME\n\nbody1\n\n# COVER\n\nbody2\n\n# NOTES\n\nbody3\n"
    parsed = parse_tailor_output(text)
    assert parsed.resume == "body1"
    assert parsed.cover == "body2"
    assert parsed.notes == "body3"


def test_parse_handles_extra_whitespace():
    text = "\n\n# RESUME\n\n\nbody1\n\n\n# COVER\n\n\nbody2\n\n# NOTES\n\n\nbody3\n\n\n"
    parsed = parse_tailor_output(text)
    assert parsed.resume == "body1"
    assert parsed.notes == "body3"
```

- [ ] **Step 3: Implement `shortlist/tailor/parser.py`**

```python
"""Parse Sonnet's tailor output into three named sections.

The model is instructed to emit:

  # RESUME
  ...
  # COVER
  ...
  # NOTES
  ...

This parser splits the response on those headings (case-insensitive,
exact level-1 H1) and returns the bodies. Missing any section raises.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SECTION_RE = re.compile(r"^#\s+(RESUME|COVER|NOTES)\s*$",
                         re.IGNORECASE | re.MULTILINE)


class TailorParseError(ValueError):
    pass


@dataclass(frozen=True)
class TailorSections:
    resume: str
    cover: str
    notes: str


def parse_tailor_output(text: str) -> TailorSections:
    matches = list(_SECTION_RE.finditer(text))
    if len(matches) < 3:
        raise TailorParseError(
            f"expected 3 # H1 sections (RESUME, COVER, NOTES), got {len(matches)}"
        )
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    missing = {"RESUME", "COVER", "NOTES"} - sections.keys()
    if missing:
        raise TailorParseError(f"missing sections: {sorted(missing)}")
    return TailorSections(
        resume=sections["RESUME"],
        cover=sections["COVER"],
        notes=sections["NOTES"],
    )
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_tailor_parser.py -v
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/tailor/__init__.py shortlist/tailor/parser.py tests/unit/test_tailor_parser.py tests/fixtures/llm_responses/sonnet_tailor_sample.md
git commit -m "feat(tailor): parse Sonnet output into RESUME/COVER/NOTES sections"
```

Expected: 4 new pass + 106 prior = 110 total.

---

## Task 6: Sonnet tailor client + prompt

**Files:**
- Create: `shortlist/tailor/prompt.py`
- Create: `shortlist/tailor/sonnet.py`
- Create: `tests/unit/test_tailor_sonnet.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tailor_sonnet.py
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shortlist.tailor.sonnet import (
    SONNET_INPUT_PRICE_PER_MTOK,
    SonnetTailorClient,
    TailorRequest,
    estimate_tailor_cost,
)


def _fake_msg(text: str, in_tok: int = 2000, out_tok: int = 1500):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage.input_tokens = in_tok
    msg.usage.output_tokens = out_tok
    return msg


def test_estimate_tailor_cost():
    cost = estimate_tailor_cost(input_tokens=1_000_000, output_tokens=0)
    assert cost == pytest.approx(SONNET_INPUT_PRICE_PER_MTOK, rel=1e-6)


def test_sonnet_tailor_returns_3_sections():
    fixture = Path(__file__).parent.parent / "fixtures/llm_responses/sonnet_tailor_sample.md"
    text = fixture.read_text()
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_msg(text, 2000, 1500)

    client = SonnetTailorClient(client=fake_client, model="claude-sonnet-4-6")
    req = TailorRequest(
        resume="My resume.",
        prefs_summary="Python, Postgres.",
        job_title="Senior Backend Engineer",
        company="Acme",
        job_description="Build distributed systems.",
        cover_paragraphs=3,
    )
    result = client.tailor(req)
    assert "David Miller" in result.sections.resume
    assert "Hi Acme team," in result.sections.cover
    assert "Why this fits:" in result.sections.notes
    assert result.cost_usd > 0
    assert result.tokens_in == 2000
    assert result.tokens_out == 1500


def test_sonnet_tailor_retries_on_parse_failure():
    fixture = Path(__file__).parent.parent / "fixtures/llm_responses/sonnet_tailor_sample.md"
    good = fixture.read_text()
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _fake_msg("not valid output", 1000, 50),
        _fake_msg(good, 1500, 1500),
    ]
    client = SonnetTailorClient(client=fake_client, model="claude-sonnet-4-6")
    req = TailorRequest(
        resume="r", prefs_summary="p", job_title="t", company="c",
        job_description="d", cover_paragraphs=3,
    )
    result = client.tailor(req)
    assert "David Miller" in result.sections.resume
    assert fake_client.messages.create.call_count == 2
```

- [ ] **Step 2: Implement `shortlist/tailor/prompt.py`**

```python
"""Sonnet tailor prompts. Strict no-fabrication guardrail in the system prompt."""
from __future__ import annotations

SYSTEM = (
    "You tailor a candidate's resume + write a cover letter + write interview "
    "notes for a single job posting. Three rules:\n"
    "1. NEVER fabricate. Do not invent jobs, dates, employers, degrees, "
    "certifications, projects, technologies, or numbers. Only use facts "
    "present in the supplied resume. If a JD asks for something the resume "
    "doesn't show, say so honestly in the cover letter or notes.\n"
    "2. You may reorder, rephrase, condense, and expand on what's in the "
    "resume. You may emphasize relevant experience and de-emphasize the rest.\n"
    "3. Output exactly three top-level sections in this order, each marked "
    "by an H1: `# RESUME`, `# COVER`, `# NOTES`. No content outside these "
    "three sections. No markdown fences around the whole output.\n"
)


def build_user_prompt(
    *, resume: str, prefs_summary: str, job_title: str,
    company: str, job_description: str, cover_paragraphs: int,
) -> str:
    return (
        f"# CANDIDATE RESUME\n\n{resume.strip()}\n\n"
        f"# PREFERENCES\n\n{prefs_summary.strip()}\n\n"
        f"# JOB POSTING\n\n"
        f"**Company:** {company}\n"
        f"**Title:** {job_title}\n\n"
        f"{job_description.strip()}\n\n"
        f"# YOUR TASK\n\n"
        f"Produce three sections — `# RESUME`, `# COVER`, `# NOTES` — per the "
        f"system instructions. The cover letter should be {cover_paragraphs} "
        f"paragraphs."
    )
```

- [ ] **Step 3: Implement `shortlist/tailor/sonnet.py`**

```python
"""Sonnet tailor client.

Pricing (USD per 1M tokens, public Anthropic pricing as of 2026-01):
  Sonnet 4.6 input  : $3.00
  Sonnet 4.6 output : $15.00
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from shortlist.tailor.parser import (
    TailorParseError,
    TailorSections,
    parse_tailor_output,
)
from shortlist.tailor.prompt import SYSTEM, build_user_prompt

logger = logging.getLogger(__name__)

SONNET_INPUT_PRICE_PER_MTOK = 3.00
SONNET_OUTPUT_PRICE_PER_MTOK = 15.00


def estimate_tailor_cost(*, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * SONNET_INPUT_PRICE_PER_MTOK
        + output_tokens / 1_000_000 * SONNET_OUTPUT_PRICE_PER_MTOK
    )


@dataclass(frozen=True)
class TailorRequest:
    resume: str
    prefs_summary: str
    job_title: str
    company: str
    job_description: str
    cover_paragraphs: int = 3


@dataclass(frozen=True)
class TailorResult:
    sections: TailorSections
    cost_usd: float
    tokens_in: int
    tokens_out: int


class SonnetTailorClient:
    def __init__(self, *, client: Any, model: str = "claude-sonnet-4-6",
                 max_tokens: int = 8192):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def tailor(self, req: TailorRequest) -> TailorResult:
        user = build_user_prompt(
            resume=req.resume, prefs_summary=req.prefs_summary,
            job_title=req.job_title, company=req.company,
            job_description=req.job_description,
            cover_paragraphs=req.cover_paragraphs,
        )
        msg = self._client.messages.create(
            model=self._model, max_tokens=self._max_tokens,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = msg.content[0].text
        in_tok = int(msg.usage.input_tokens)
        out_tok = int(msg.usage.output_tokens)
        try:
            sections = parse_tailor_output(text)
        except TailorParseError:
            logger.warning("sonnet tailor: first parse failed, retrying once")
            corrective = (
                "Your previous response was not in the required format. Output "
                "EXACTLY three top-level H1 sections in order: # RESUME, # COVER, "
                "# NOTES. No prose outside them."
            )
            msg2 = self._client.messages.create(
                model=self._model, max_tokens=self._max_tokens,
                system=SYSTEM + "\n" + corrective,
                messages=[
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": corrective},
                ],
            )
            in_tok += int(msg2.usage.input_tokens)
            out_tok += int(msg2.usage.output_tokens)
            sections = parse_tailor_output(msg2.content[0].text)
        return TailorResult(
            sections=sections,
            cost_usd=estimate_tailor_cost(input_tokens=in_tok, output_tokens=out_tok),
            tokens_in=in_tok, tokens_out=out_tok,
        )
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_tailor_sonnet.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/tailor/prompt.py shortlist/tailor/sonnet.py tests/unit/test_tailor_sonnet.py
git commit -m "feat(tailor): Sonnet client with no-fabrication system prompt + retry"
```

Expected: 3 new pass + 110 prior = 113 total.

---

## Task 7: Pandoc PDF wrapper

**Files:**
- Create: `shortlist/tailor/pdf.py`
- Create: `tests/fixtures/pdf-template.tex`
- Create: `tests/integration/test_tailor_pdf.py`

- [ ] **Step 1: Minimal LaTeX template**

`tests/fixtures/pdf-template.tex`:

```latex
\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{hyperref}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\begin{document}
$body$
\end{document}
```

- [ ] **Step 2: Failing tests**

```python
# tests/integration/test_tailor_pdf.py
import shutil
from pathlib import Path

import pytest

from shortlist.tailor.pdf import PandocMissingError, render_md_to_pdf

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


@pytest.mark.skipif(not (_have("pandoc") and _have("pdflatex")),
                    reason="pandoc + pdflatex required")
def test_render_md_to_pdf_writes_pdf(tmp_path: Path):
    md = tmp_path / "in.md"
    md.write_text("# Hello\n\nThis is a test.\n")
    pdf = tmp_path / "out.pdf"
    render_md_to_pdf(md, pdf, template=FIXTURES / "pdf-template.tex")
    assert pdf.exists()
    assert pdf.stat().st_size > 0


def test_render_md_to_pdf_raises_when_pandoc_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _c: None)
    md = tmp_path / "in.md"
    md.write_text("# x")
    pdf = tmp_path / "out.pdf"
    with pytest.raises(PandocMissingError):
        render_md_to_pdf(md, pdf)
```

- [ ] **Step 3: Implement `shortlist/tailor/pdf.py`**

```python
"""Pandoc subprocess wrapper.

If pandoc or pdflatex is missing on PATH, raise PandocMissingError. Callers
treat that as a soft failure — MD outputs are still useful.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class PandocMissingError(RuntimeError):
    pass


class PandocRenderError(RuntimeError):
    pass


def _check_tools() -> None:
    if not shutil.which("pandoc"):
        raise PandocMissingError("pandoc not found on PATH")
    if not shutil.which("pdflatex"):
        raise PandocMissingError("pdflatex not found on PATH (install texlive-core)")


def render_md_to_pdf(
    md_path: Path, pdf_path: Path, *, template: Path | None = None,
) -> None:
    _check_tools()
    cmd = ["pandoc", str(md_path), "-o", str(pdf_path), "--pdf-engine=pdflatex"]
    if template is not None:
        cmd.extend(["--template", str(template)])
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
    except subprocess.CalledProcessError as e:
        raise PandocRenderError(f"pandoc failed: {e.stderr.strip()}") from e
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_tailor_pdf.py -v
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/tailor/pdf.py tests/integration/test_tailor_pdf.py tests/fixtures/pdf-template.tex
git commit -m "feat(tailor): pandoc PDF wrapper with PandocMissingError"
```

Expected: 1 pass + 1 skip (or 2 pass if pandoc present) + 113 prior.

---

## Task 8: Tailor orchestrator (write 3 MD + 2 PDFs + record)

**Files:**
- Create: `shortlist/tailor/orchestrator.py`
- Create: `tests/integration/test_tailor_orchestrator.py`

- [ ] **Step 1: Failing tests**

```python
# tests/integration/test_tailor_orchestrator.py
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from shortlist.config import Prefs
from shortlist.models import RawJob
from shortlist.store.db import migrate, upsert_job
from shortlist.tailor.orchestrator import TailorOrchestrator


def _fake_msg(text):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage.input_tokens = 1500
    msg.usage.output_tokens = 1200
    return msg


def _prefs() -> Prefs:
    return Prefs.model_validate(dict(
        titles=["Senior Backend Engineer"], locations=["Remote"], remote_ok=True,
        comp_floor_usd=180000, exclude_keywords=[], seniority=["senior"],
        greenhouse_companies=[],
    ))


def test_orchestrator_writes_three_md_files(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    job = upsert_job(db, RawJob(
        source="greenhouse", external_id="acme:1", company="Acme Corp",
        title="Senior Backend Engineer",
        url="https://example.com/jobs/1",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote - US", remote=True,
        description_md="Build distributed systems in Python.",
    ))
    resume = tmp_path / "resume.md"
    resume.write_text("Senior backend engineer with 6 years Python.")
    output_root = tmp_path / "jobs"

    fixture = (Path(__file__).parent.parent /
               "fixtures/llm_responses/sonnet_tailor_sample.md")
    fake_anth = MagicMock()
    fake_anth.messages.create.return_value = _fake_msg(fixture.read_text())

    orch = TailorOrchestrator(
        db_path=db, output_root=output_root, anthropic_client=fake_anth,
        model="claude-sonnet-4-6", pdf_template=None,
    )
    result = orch.tailor(job_id=job.id, resume_path=resume, prefs=_prefs())

    assert (result.output_dir / "resume.md").exists()
    assert (result.output_dir / "cover.md").exists()
    assert (result.output_dir / "notes.md").exists()
    assert "acme" in result.output_dir.name.lower()
    assert result.cost_usd > 0


def test_orchestrator_records_status_transition(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    migrate(db)
    job = upsert_job(db, RawJob(
        source="greenhouse", external_id="acme:2", company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/jobs/2",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote", remote=True, description_md="Python work.",
    ))
    resume = tmp_path / "resume.md"
    resume.write_text("R")

    fixture = (Path(__file__).parent.parent /
               "fixtures/llm_responses/sonnet_tailor_sample.md")
    fake_anth = MagicMock()
    fake_anth.messages.create.return_value = _fake_msg(fixture.read_text())

    orch = TailorOrchestrator(
        db_path=db, output_root=tmp_path / "jobs", anthropic_client=fake_anth,
        model="claude-sonnet-4-6", pdf_template=None,
    )
    orch.tailor(job_id=job.id, resume_path=resume, prefs=_prefs())

    from shortlist.store.db import list_jobs
    refreshed = next(j for j in list_jobs(db) if j.id == job.id)
    assert refreshed.status == "tailored"
```

- [ ] **Step 2: Implement `shortlist/tailor/orchestrator.py`**

```python
"""Tailor orchestrator: load → Sonnet → parse → write 3 MD + 2 PDFs → record."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shortlist.config import Prefs
from shortlist.store import db as store_db
from shortlist.tailor.pdf import PandocMissingError, render_md_to_pdf
from shortlist.tailor.sonnet import SonnetTailorClient, TailorRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TailorOutput:
    output_dir: Path
    cost_usd: float
    tokens_in: int
    tokens_out: int


def _slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "job"


def _prefs_summary(prefs: Prefs) -> str:
    return (
        f"titles: {', '.join(prefs.titles)}\n"
        f"seniority: {', '.join(prefs.seniority)}\n"
        f"locations: {', '.join(prefs.locations)}\n"
        f"remote_ok: {prefs.remote_ok}\n"
        f"comp_floor_usd: {prefs.comp_floor_usd}"
    )


class TailorOrchestrator:
    def __init__(
        self, *, db_path: Path, output_root: Path,
        anthropic_client: Any, model: str = "claude-sonnet-4-6",
        pdf_template: Path | None = None, cover_paragraphs: int = 3,
    ):
        self._db = db_path
        self._root = output_root
        self._client = SonnetTailorClient(client=anthropic_client, model=model)
        self._template = pdf_template
        self._cover_paragraphs = cover_paragraphs

    def tailor(
        self, *, job_id: int, resume_path: Path, prefs: Prefs,
    ) -> TailorOutput:
        jobs = [j for j in store_db.list_jobs(self._db) if j.id == job_id]
        if not jobs:
            raise ValueError(f"job {job_id} not found")
        job = jobs[0]

        req = TailorRequest(
            resume=resume_path.read_text(),
            prefs_summary=_prefs_summary(prefs),
            job_title=job.title,
            company=job.company,
            job_description=job.description_md or "",
            cover_paragraphs=self._cover_paragraphs,
        )
        result = self._client.tailor(req)

        out_dir = self._root / f"{_slug(job.company)}-{_slug(job.title)}-{job.id}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "resume.md").write_text(result.sections.resume + "\n")
        (out_dir / "cover.md").write_text(result.sections.cover + "\n")
        (out_dir / "notes.md").write_text(result.sections.notes + "\n")

        # Render PDFs (best-effort).
        for stem in ("resume", "cover"):
            md = out_dir / f"{stem}.md"
            pdf = out_dir / f"{stem}.pdf"
            try:
                render_md_to_pdf(md, pdf, template=self._template)
            except PandocMissingError as e:
                logger.warning("PDF skipped (%s): %s", stem, e)
            except Exception as e:  # noqa: BLE001 — render is best-effort
                logger.warning("PDF render failed (%s): %s", stem, e)

        # Record in store.
        with store_db.connect(self._db) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tailor_outputs "
                "(job_id, output_dir, rendered_at, cost_usd, tokens_in, tokens_out) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, str(out_dir),
                 store_db._utc_iso(datetime.now(UTC)),
                 result.cost_usd, result.tokens_in, result.tokens_out),
            )

        # Transition status if currently `new`.
        if job.status == "new":
            store_db.transition_status(self._db, job_id, "tailored")
        store_db.log_event(
            self._db, job_id=job_id, type="tailor.complete",
            payload={"output_dir": str(out_dir)},
            cost_usd=result.cost_usd,
            tokens=result.tokens_in + result.tokens_out,
        )

        return TailorOutput(
            output_dir=out_dir, cost_usd=result.cost_usd,
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
        )
```

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_tailor_orchestrator.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/tailor/orchestrator.py tests/integration/test_tailor_orchestrator.py
git commit -m "feat(tailor): orchestrator writes 3 MD + 2 PDFs + records run"
```

Expected: 2 new pass + ~114 prior = ~116 total.

---

## Task 9: CLI `tailor <id>`

**Files:**
- Modify: `shortlist/cli.py`
- Modify: `tests/integration/test_cli.py`

- [ ] **Step 1: Append failing test**

```python
def test_cli_tailor_writes_outputs(env, tmp_path, monkeypatch):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "prefs.yaml").write_text(
        (cfg / "prefs.yaml").read_text().replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
    )
    resume = tmp_path / "resume.md"
    resume.write_text("R")
    out_dir = tmp_path / "jobs"
    cfg_text = (cfg / "config.yaml").read_text()\
        .replace("resume: ~/jobs/resume.md", f"resume: {resume}")\
        .replace("output_dir: ~/jobs", f"output_dir: {out_dir}")
    (cfg / "config.yaml").write_text(cfg_text)

    runner.invoke(app, ["db", "init"])
    from datetime import UTC, datetime
    from shortlist.models import RawJob
    from shortlist.store.db import upsert_job
    j = upsert_job(data / "db.sqlite", RawJob(
        source="greenhouse", external_id="acme:1", company="Acme Corp",
        title="Senior Backend Engineer",
        url="https://example.com/1",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote - US", remote=True,
        description_md="Python services.",
    ))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    from unittest.mock import MagicMock
    fake_anth = MagicMock()
    msg = MagicMock()
    fixture = (Path(__file__).parent.parent /
               "fixtures/llm_responses/sonnet_tailor_sample.md")
    msg.content = [MagicMock(text=fixture.read_text())]
    msg.usage.input_tokens = 1500
    msg.usage.output_tokens = 1200
    fake_anth.messages.create.return_value = msg
    import shortlist.cli as cli_mod
    monkeypatch.setattr(cli_mod, "Anthropic", lambda **_kw: fake_anth)

    result = runner.invoke(app, ["tailor", str(j.id)])
    assert result.exit_code == 0, result.output
    dirs = list(out_dir.iterdir())
    assert len(dirs) == 1
    files = {p.name for p in dirs[0].iterdir()}
    assert {"resume.md", "cover.md", "notes.md"} <= files
```

- [ ] **Step 2: Add `tailor` command to `shortlist/cli.py`**

```python
from anthropic import Anthropic

from shortlist.tailor.orchestrator import TailorOrchestrator


@app.command("tailor")
def tailor_cmd(
    job_id: int = typer.Argument(..., help="Job id to tailor materials for."),
    cover_paragraphs: int = typer.Option(3, "--cover-paras"),
) -> None:
    """Generate per-job resume + cover + notes (Markdown + PDF)."""
    if not paths.config_path().exists() or not paths.prefs_path().exists():
        console.print("[red]error[/red] run `shortlist config init` first")
        raise typer.Exit(code=2)
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)

    cfg = load_config(paths.config_path())
    prefs = load_prefs(paths.prefs_path())
    resume = cfg.paths.resume.expanduser()
    if not resume.exists():
        console.print(f"[red]error[/red] resume not found at {resume}")
        raise typer.Exit(code=2)

    import os
    key = os.environ.get(cfg.anthropic.key_env_var, "")
    if not key:
        console.print(f"[red]error[/red] {cfg.anthropic.key_env_var} not set")
        raise typer.Exit(code=2)

    orch = TailorOrchestrator(
        db_path=paths.db_path(),
        output_root=cfg.paths.output_dir.expanduser(),
        anthropic_client=Anthropic(api_key=key),
        model=cfg.tailor.model,
        pdf_template=cfg.paths.pdf_template,
        cover_paragraphs=cover_paragraphs,
    )
    out = orch.tailor(job_id=job_id, resume_path=resume, prefs=prefs)
    console.print(f"[green]wrote[/green] {out.output_dir} "
                  f"(${out.cost_usd:.4f}, {out.tokens_in + out.tokens_out} tok)")
```

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_cli.py -v -k tailor
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/cli.py tests/integration/test_cli.py
git commit -m "feat(cli): tailor <id> generates per-job materials via Sonnet"
```

Expected: 1 new pass + 116 prior = 117 total.

---

## Task 10: CLI `track <id>` + `contacts` subgroup

**Files:**
- Modify: `shortlist/cli.py`
- Modify: `tests/integration/test_cli.py`

- [ ] **Step 1: Append failing tests**

```python
def test_track_status_transition(env, tmp_path):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    runner.invoke(app, ["db", "init"])
    from datetime import UTC, datetime
    from shortlist.models import RawJob
    from shortlist.store.db import upsert_job
    j = upsert_job(data / "db.sqlite", RawJob(
        source="greenhouse", external_id="acme:1", company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/1",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote", remote=True,
    ))
    result = runner.invoke(app, ["track", str(j.id), "--status", "tailored"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["track", str(j.id), "--status", "applied",
                                  "--applied-via", "company website"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["track", str(j.id), "--status", "interview"])
    assert result.exit_code != 0


def test_contacts_add_list_remove(env, tmp_path):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    runner.invoke(app, ["db", "init"])
    from datetime import UTC, datetime
    from shortlist.models import RawJob
    from shortlist.store.db import upsert_job
    j = upsert_job(data / "db.sqlite", RawJob(
        source="greenhouse", external_id="acme:1", company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/1",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=UTC),
        location="Remote", remote=True,
    ))
    runner.invoke(app, ["track", str(j.id), "--status", "tailored"])
    runner.invoke(app, ["track", str(j.id), "--status", "applied"])

    result = runner.invoke(app, ["contacts", "add", str(j.id),
                                  "--name", "Jane Doe",
                                  "--email", "jane@acme.com",
                                  "--role", "recruiter"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["contacts", "list", str(j.id)])
    assert "Jane Doe" in result.output
    assert "jane@acme.com" in result.output
```

- [ ] **Step 2: Add `track` command + `contacts` subgroup to `shortlist/cli.py`**

```python
from shortlist.store.db import (
    add_contact as store_add_contact,
    list_contacts as store_list_contacts,
    remove_contact as store_remove_contact,
    transition_status,
    update_application,
)
from shortlist.tracker.state import InvalidStatusTransitionError


@app.command("track")
def track_cmd(
    job_id: int = typer.Argument(...),
    status: str = typer.Option(..., "--status", help="Target status."),
    notes: str | None = typer.Option(None, "--notes"),
    applied_via: str | None = typer.Option(None, "--applied-via"),
) -> None:
    """Transition a job through the application lifecycle."""
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)
    try:
        transition_status(paths.db_path(), job_id, status)  # type: ignore[arg-type]
    except InvalidStatusTransitionError as e:
        console.print(f"[red]error[/red] {e}")
        raise typer.Exit(code=1) from e
    except ValueError as e:
        console.print(f"[red]error[/red] {e}")
        raise typer.Exit(code=2) from e

    if status == "applied":
        update_application(
            paths.db_path(), job_id,
            applied_at=datetime.now(timezone.utc),
            applied_via=applied_via or "(unspecified)",
        )
    if notes:
        update_application(paths.db_path(), job_id, lessons=notes)
    console.print(f"[green]ok[/green] job {job_id} → {status}")


contacts_app = typer.Typer(help="Manage contacts on applications.")
app.add_typer(contacts_app, name="contacts")


@contacts_app.command("add")
def contacts_add(
    job_id: int = typer.Argument(...),
    name: str = typer.Option(..., "--name", prompt="Name"),
    email: str | None = typer.Option(None, "--email"),
    role: str | None = typer.Option(None, "--role"),
    source: str | None = typer.Option(None, "--source"),
) -> None:
    cid = store_add_contact(
        paths.db_path(), job_id, name=name, email=email, role=role, source=source,
    )
    console.print(f"[green]added[/green] contact {cid} ({name})")


@contacts_app.command("list")
def contacts_list(job_id: int = typer.Argument(...)) -> None:
    rows = store_list_contacts(paths.db_path(), job_id)
    if not rows:
        console.print("[dim]no contacts[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", justify="right")
    table.add_column("Name")
    table.add_column("Email")
    table.add_column("Role")
    table.add_column("Source")
    for c in rows:
        table.add_row(str(c.id), c.name, c.email or "", c.role or "", c.source or "")
    console.print(table)


@contacts_app.command("remove")
def contacts_remove(contact_id: int = typer.Argument(...)) -> None:
    store_remove_contact(paths.db_path(), contact_id)
    console.print(f"[green]removed[/green] contact {contact_id}")
```

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest tests/integration/test_cli.py -v -k "track or contact"
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/cli.py tests/integration/test_cli.py
git commit -m "feat(cli): track <id> + contacts add/list/remove"
```

Expected: 2 new pass + 117 prior = 119 total.

---

## Task 11: Default PDF template + config wiring

**Files:**
- Create: `shortlist/templates/__init__.py` (empty)
- Create: `shortlist/templates/pdf-template.tex`
- Modify: `shortlist/cli.py` (`_DEFAULT_CONFIG`; `config init` copies bundled template)
- Modify: `tests/integration/test_cli.py` (assertion on bundled template)

- [ ] **Step 1: Ship default template inside the package**

`shortlist/templates/pdf-template.tex`:

```latex
\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{hyperref}
\usepackage{enumitem}
\setlist{nosep,itemsep=2pt,parsep=0pt}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\hypersetup{colorlinks=true,urlcolor=blue}
\begin{document}
$body$
\end{document}
```

Add `shortlist/templates/__init__.py` (empty file).

Confirm `pyproject.toml` `[tool.hatch.build.targets.wheel] packages = ["shortlist"]` already includes the `templates` subdir (it does — the templates dir is a Python package now).

To make the `.tex` file ship in the wheel, add to `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"shortlist/templates/pdf-template.tex" = "shortlist/templates/pdf-template.tex"
```

(Or use `[tool.hatch.build] include = ["shortlist/templates/*.tex"]`. Verify by inspecting the built wheel with `python -m zipfile -l dist/shortlist-*.whl` after `pip wheel .`.)

- [ ] **Step 2: Update `_DEFAULT_CONFIG` in `cli.py`**

```yaml
paths:
  resume: ~/jobs/resume.md
  output_dir: ~/jobs
  pdf_template: ~/.config/shortlist/pdf-template.tex
```

- [ ] **Step 3: Have `config init` copy the bundled template**

In `config_init()` in `cli.py`, after writing the YAML files:

```python
import importlib.resources as _ir

bundled = _ir.files("shortlist.templates").joinpath("pdf-template.tex")
target = paths.config_dir() / "pdf-template.tex"
if not target.exists():
    target.write_text(bundled.read_text())
    console.print(f"[green]wrote[/green] {target}")
```

- [ ] **Step 4: Update existing `test_config_init_writes_default_files`**

Add an assertion:

```python
    assert (cfg / "pdf-template.tex").exists()
```

- [ ] **Step 5: Run + commit**

```bash
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist
git add shortlist/cli.py shortlist/templates/ pyproject.toml tests/integration/test_cli.py
git commit -m "feat(tailor): ship default LaTeX template; config init writes pdf-template.tex"
```

Expected: 119 still pass.

---

## Task 12: README + plan migration + final CI + push

**Files:**
- Modify: `README.md`
- Create: `docs/plans/2026-04-29-shortlist-plan-3-tailor-track.md`

- [ ] **Step 1: Update README**

Replace the "Plan 2 of 6" section with:

```markdown
This is **Plan 3 of 6** (tailoring + tracker). Cumulative status:

- ✅ Plan 1 (foundation): Greenhouse + SQLite + hard filter + CLI
- ✅ Plan 2: Lever, Ashby, Workable, SmartRecruiters; embeddings via `sentence-transformers`; Haiku 4.5 rerank with budget guard
- ✅ Plan 3 (this): Sonnet 4.6 per-job tailoring (resume + cover + notes); pandoc → PDF; status state machine; contacts CRUD
- ⏳ Plan 4: Textual TUI
- ⏳ Plan 5: scraped aggregators (Indeed, LinkedIn, Glassdoor) + Playwright
- ⏳ Plan 6: curated boards (HN/Wellfound/Otta/RemoteOK) + RSS + release polish
```

In "First run" section, append after the existing pipeline:

```bash
shortlist tailor <job_id>         # generate per-job MD + PDF
shortlist track <job_id> --status tailored
shortlist track <job_id> --status applied --applied-via "company website"
shortlist contacts add <job_id> --name "Jane Doe" --email jane@acme.com --role recruiter
shortlist contacts list <job_id>
```

Add a "System dependencies" note:

```markdown
## System dependencies

For PDF rendering, `pandoc` and `pdflatex` (TeX Live) must be on PATH:

# Arch / CachyOS
sudo pacman -S pandoc texlive-core

# macOS
brew install pandoc basictex

Without them, `shortlist tailor` still writes Markdown — only the PDF render step is skipped (with a warning).
```

- [ ] **Step 2: Copy plan into repo**

```bash
cp /run/media/seraph/Win1Tb/dev/repos/digitalseraph/docs/superpowers/plans/2026-04-29-shortlist-plan-3-tailor-track.md ~/dev/repos/shortlist/docs/plans/
```

- [ ] **Step 3: Final CI**

```bash
cd ~/dev/repos/shortlist
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy shortlist
.venv/bin/pytest --cov=shortlist --cov-report=term-missing --cov-fail-under=80
```

Expected: green; coverage ≥ 80% on `shortlist/`.

- [ ] **Step 4: Commit + push**

```bash
git add README.md docs/plans/2026-04-29-shortlist-plan-3-tailor-track.md
git commit -m "docs: README + Plan 3 (tailoring + tracker)"
git push
```

---

## Done definition (Plan 3)

- `shortlist tailor <id>` writes `~/jobs/<company>-<role>-<id>/{resume,cover,notes}.md` + `{resume,cover}.pdf` (PDF skipped + warning if pandoc missing).
- `shortlist track <id> --status …` validates the state machine; rejects illegal transitions; auto-creates an `applications` row on `applied`.
- `shortlist contacts add/list/remove` works against an existing application.
- All tests pass; coverage ≥ 80% on `shortlist/`.
- ~12 task commits + plan migration commit on top of Plan 2's 13 commits.

## Next plan trigger

Plan 4 begins on user request. Plan 4 scope: Textual TUI (JobList, JobDetail, ApplicationsBoard, Settings screens) on top of the same `shortlist.*` lib. No new core functionality — TUI is a thin client over Plans 1–3.

## Open questions for Plan 4 brainstorm

- Single-process or background-task TUI for long ops (tailor takes 5–15s)?
- Color scheme + key bindings — vim-like, emacs-like, or Textual defaults?
- Optional `shortlist tui` shortcut vs. `shortlist_tui` separate entry point.
