# Shortlist — Plan 1 of 6 (Foundation)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the `shortlist` repo and ship a minimal end-to-end vertical: pull jobs from Greenhouse public boards, persist to SQLite, hard-filter against a `prefs.yaml`, list results from a Typer CLI. No LLM, no TUI, no scraped sources, no tailoring — those land in Plans 2–6.

**Architecture:** Python 3.12 package with `pyproject.toml` (hatchling). Three layers: `shortlist.sources` (Source ABC + Greenhouse client), `shortlist.store` (SQLite + hand-rolled migrations), `shortlist.cli` (Typer commands `fetch`, `rank`, `db`, `config`, `list`). Hard-filter ranker only (no embeddings/LLM in Plan 1). All HTTP via `httpx`, all retry via `tenacity`. Pydantic v2 models for `Config`, `Prefs`, `RawJob`, `Job`.

**Tech Stack:** Python 3.12, Typer, Pydantic v2, httpx, tenacity, SQLite, pytest + pytest-asyncio + hypothesis + respx, ruff, mypy.

**Plan-1 file map:**

```
shortlist/
├── pyproject.toml
├── README.md
├── LICENSE                (MIT)
├── .gitignore
├── .python-version
├── shortlist/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── paths.py
│   ├── store/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   └── _migrations/
│   │       └── 001_initial.sql
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── ats/
│   │       ├── __init__.py
│   │       └── greenhouse.py
│   ├── ranker/
│   │   ├── __init__.py
│   │   └── hard_filter.py
│   └── cli.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_models.py
│   │   ├── test_paths.py
│   │   └── test_hard_filter.py
│   ├── integration/
│   │   ├── test_store.py
│   │   ├── test_greenhouse.py
│   │   └── test_cli.py
│   └── fixtures/
│       ├── greenhouse_acme_page1.json
│       ├── greenhouse_acme_page2.json
│       ├── prefs_default.yaml
│       └── config_default.yaml
└── .github/
    └── workflows/
        └── ci.yml
```

**Note on plan location:** This plan currently lives at `<monorepo>/docs/superpowers/plans/2026-04-28-shortlist-plan-1-foundation.md`. After Task 1 scaffolds the standalone `shortlist` repo, copy this file verbatim to `<shortlist-repo>/docs/plans/2026-04-28-shortlist-plan-1-foundation.md` per the project's plan-to-repo workflow rule (Task 18 below does this).

---

## Task 1: Scaffold repo

**Files:**
- Create: `~/dev/repos/shortlist/` (new git repo, sibling of `throughline`)
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `LICENSE`
- Create: `.gitignore`
- Create: `.python-version`
- Create: `shortlist/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create the repo directory and init git**

```bash
mkdir -p ~/dev/repos/shortlist
cd ~/dev/repos/shortlist
git init -b main
git config user.name "David Miller"
git config user.email "davidmiller.avatar@gmail.com"
```

- [ ] **Step 2: Create `.python-version`**

```bash
echo "3.12" > .python-version
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "shortlist"
version = "0.0.1"
description = "Personal job-search assistant: discover, rank, tailor, track."
readme = "README.md"
requires-python = ">=3.12"
license = { file = "LICENSE" }
authors = [{ name = "David Miller", email = "davidmiller.avatar@gmail.com" }]
dependencies = [
    "typer>=0.12",
    "rich>=13.7",
    "pydantic>=2.7",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "tenacity>=8.5",
    "platformdirs>=4.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "hypothesis>=6.100",
    "respx>=0.21",
    "ruff>=0.5",
    "mypy>=1.10",
    "types-PyYAML",
]

[project.scripts]
shortlist = "shortlist.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["shortlist"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["shortlist"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
    "browser: tests requiring a real browser (Playwright); not run in CI",
    "live: tests hitting live network APIs; gated by RUN_LIVE=1",
]
```

- [ ] **Step 4: Create `.gitignore`**

```
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage
dist/
build/
*.sqlite
*.sqlite-journal
.DS_Store
```

- [ ] **Step 5: Create `LICENSE` (MIT)**

```
MIT License

Copyright (c) 2026 David Miller

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 6: Create skeleton README.md**

```markdown
# Shortlist

Personal job-search assistant — CLI + (eventually) Textual TUI.

Plan 1 (foundation): Greenhouse ingestion, SQLite store, hard-filter ranking, CLI list.

See `docs/plans/` for implementation plans and `docs/spec.md` for the design.
```

- [ ] **Step 7: Create empty package files**

```bash
mkdir -p shortlist/store/_migrations shortlist/sources/ats shortlist/ranker tests/unit tests/integration tests/fixtures docs/plans
touch shortlist/__init__.py shortlist/store/__init__.py shortlist/sources/__init__.py shortlist/sources/ats/__init__.py shortlist/ranker/__init__.py tests/__init__.py
```

- [ ] **Step 8: Create venv and install**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

Expected: install succeeds, `shortlist` script available.

- [ ] **Step 9: Verify ruff + mypy + pytest run clean on empty project**

```bash
ruff check .
ruff format --check .
mypy shortlist
pytest
```

Expected: ruff and ruff format pass, mypy passes (no files to check yet but no error), pytest collects 0 tests successfully.

- [ ] **Step 10: First commit**

```bash
git add -A
git commit -m "chore: scaffold repo with pyproject, license, gitignore"
```

---

## Task 2: Pydantic models — `RawJob` and `Job`

**Files:**
- Create: `shortlist/models.py`
- Test: `tests/unit/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_models.py
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from shortlist.models import Job, RawJob


def test_rawjob_minimum_fields():
    raw = RawJob(
        source="greenhouse",
        external_id="gh_4521",
        company="Acme Corp",
        title="Senior Backend Engineer",
        url="https://example.com/jobs/4521",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=timezone.utc),
    )
    assert raw.source == "greenhouse"
    assert raw.external_id == "gh_4521"
    assert raw.location is None
    assert raw.remote is False


def test_rawjob_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        RawJob(
            source="greenhouse",
            external_id="gh_1",
            company="Acme",
            title="Eng",
            url="https://example.com",
            posted_at=datetime(2026, 4, 25, 9, 0),  # no tz
        )


def test_job_status_default_is_new():
    job = Job(
        id=1,
        source="greenhouse",
        external_id="gh_1",
        company="Acme",
        title="Eng",
        url="https://example.com",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=timezone.utc),
        discovered_at=datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc),
    )
    assert job.status == "new"


def test_job_score_bounds():
    with pytest.raises(ValidationError):
        Job(
            id=1, source="x", external_id="x", company="x", title="x",
            url="https://x", posted_at=datetime.now(timezone.utc),
            discovered_at=datetime.now(timezone.utc), score=101,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_models.py -v
```

Expected: ImportError / ModuleNotFoundError on `shortlist.models`.

- [ ] **Step 3: Implement `shortlist/models.py`**

```python
"""Pydantic models for jobs in Shortlist.

RawJob: shape returned by source clients before persistence.
Job:    shape after the row is in SQLite (has id, status, scoring fields).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

JobStatus = Literal[
    "new", "tailored", "applied", "screen", "interview",
    "offer", "rejected", "withdrawn",
]


class RawJob(BaseModel):
    """Source-agnostic normalized job record before storage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    external_id: str
    company: str
    title: str
    url: HttpUrl
    posted_at: datetime

    location: str | None = None
    remote: bool = False
    comp_min: int | None = None
    comp_max: int | None = None
    description_md: str | None = None

    @field_validator("posted_at")
    @classmethod
    def _require_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("posted_at must be timezone-aware")
        return v


class Job(BaseModel):
    """Stored job. Includes scoring + status fields managed by the store."""

    model_config = ConfigDict(extra="forbid")

    id: int
    source: str
    external_id: str
    company: str
    title: str
    url: HttpUrl
    posted_at: datetime
    discovered_at: datetime

    location: str | None = None
    remote: bool = False
    comp_min: int | None = None
    comp_max: int | None = None
    description_md: str | None = None

    score: int | None = Field(default=None, ge=0, le=100)
    score_reason: str | None = None
    status: JobStatus = "new"
    status_changed_at: datetime | None = None
    scored_with_prefs_at: datetime | None = None
    scored_with_model: str | None = None
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/unit/test_models.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add shortlist/models.py tests/unit/test_models.py
git commit -m "feat(models): RawJob and Job pydantic models with status + scoring"
```

---

## Task 3: Pydantic models — `Config` and `Prefs`

**Files:**
- Create: `shortlist/config.py`
- Create: `tests/fixtures/config_default.yaml`
- Create: `tests/fixtures/prefs_default.yaml`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Create fixture YAML files**

`tests/fixtures/config_default.yaml`:

```yaml
anthropic:
  key_source: env
  key_env_var: ANTHROPIC_API_KEY
budget:
  daily_usd: 5.00
  monthly_usd: 60.00
paths:
  resume: ~/jobs/resume.md
  output_dir: ~/jobs
sources:
  greenhouse:
    enabled: true
    rate_limit_rpm: 30
ranker:
  top_k_for_llm_rerank: 30
  embedding_model: bge-small-en-v1.5
  rerank_model: claude-haiku-4-5-20251001
tailor:
  model: claude-sonnet-4-6
  cover_paragraphs: 3
```

`tests/fixtures/prefs_default.yaml`:

```yaml
titles:
  - "Senior Backend Engineer"
  - "Staff Engineer"
locations:
  - "Remote - US"
  - "Atlanta, GA"
remote_ok: true
comp_floor_usd: 180000
exclude_keywords:
  - "C++"
  - "on-site only"
seniority:
  - senior
  - staff
greenhouse_companies:
  - acme
  - globex
```

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_config.py
from pathlib import Path
import pytest
from pydantic import ValidationError

from shortlist.config import Config, Prefs, load_config, load_prefs

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_load_config_defaults():
    cfg = load_config(FIXTURES / "config_default.yaml")
    assert cfg.anthropic.key_env_var == "ANTHROPIC_API_KEY"
    assert cfg.budget.daily_usd == 5.0
    assert cfg.sources["greenhouse"].enabled is True
    assert cfg.sources["greenhouse"].rate_limit_rpm == 30


def test_load_prefs_defaults():
    prefs = load_prefs(FIXTURES / "prefs_default.yaml")
    assert "Senior Backend Engineer" in prefs.titles
    assert prefs.comp_floor_usd == 180000
    assert "acme" in prefs.greenhouse_companies


def test_config_rejects_negative_budget():
    with pytest.raises(ValidationError):
        Config.model_validate({
            "anthropic": {"key_source": "env", "key_env_var": "X"},
            "budget": {"daily_usd": -1.0, "monthly_usd": 60.0},
            "paths": {"resume": "~/r.md", "output_dir": "~/jobs"},
            "sources": {},
            "ranker": {"top_k_for_llm_rerank": 30, "embedding_model": "bge",
                       "rerank_model": "x"},
            "tailor": {"model": "x", "cover_paragraphs": 3},
        })


def test_prefs_rejects_empty_titles():
    with pytest.raises(ValidationError):
        Prefs.model_validate({
            "titles": [], "locations": ["Remote"], "remote_ok": True,
            "comp_floor_usd": 100000, "exclude_keywords": [],
            "seniority": [], "greenhouse_companies": [],
        })
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/unit/test_config.py -v
```

Expected: ImportError on `shortlist.config`.

- [ ] **Step 4: Implement `shortlist/config.py`**

```python
"""Configuration loading + validation for Shortlist."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnthropicConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key_source: Literal["env", "keyring"] = "env"
    key_env_var: str = "ANTHROPIC_API_KEY"


class BudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_usd: float = Field(ge=0)
    monthly_usd: float = Field(ge=0)


class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resume: Path
    output_dir: Path
    pdf_template: Path | None = None


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    rate_limit_rpm: int = Field(default=30, ge=1)
    urls: list[str] = Field(default_factory=list)  # for RSS


class RankerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    top_k_for_llm_rerank: int = Field(default=30, ge=1)
    embedding_model: str
    rerank_model: str


class TailorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    cover_paragraphs: int = Field(default=3, ge=1, le=10)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anthropic: AnthropicConfig
    budget: BudgetConfig
    paths: PathsConfig
    sources: dict[str, SourceConfig]
    ranker: RankerConfig
    tailor: TailorConfig


class Prefs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titles: list[str] = Field(min_length=1)
    locations: list[str]
    remote_ok: bool
    comp_floor_usd: int = Field(ge=0)
    exclude_keywords: list[str]
    seniority: list[str]
    greenhouse_companies: list[str] = Field(default_factory=list)

    @field_validator("titles", "locations", "exclude_keywords", "seniority",
                     "greenhouse_companies")
    @classmethod
    def _strip(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s.strip()]


def load_config(path: Path) -> Config:
    with path.expanduser().open() as f:
        data = yaml.safe_load(f)
    return Config.model_validate(data)


def load_prefs(path: Path) -> Prefs:
    with path.expanduser().open() as f:
        data = yaml.safe_load(f)
    return Prefs.model_validate(data)
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
pytest tests/unit/test_config.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add shortlist/config.py tests/unit/test_config.py tests/fixtures/config_default.yaml tests/fixtures/prefs_default.yaml
git commit -m "feat(config): pydantic Config and Prefs with YAML loaders"
```

---

## Task 4: Migration runner

**Files:**
- Create: `shortlist/store/db.py` (initial: connection + migration runner only)
- Create: `shortlist/store/_migrations/001_initial.sql`
- Test: `tests/integration/test_store.py` (migration tests only)

- [ ] **Step 1: Write the initial migration**

`shortlist/store/_migrations/001_initial.sql`:

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source                  TEXT    NOT NULL,
    external_id             TEXT    NOT NULL,
    company                 TEXT    NOT NULL,
    title                   TEXT    NOT NULL,
    url                     TEXT    NOT NULL,
    posted_at               TEXT    NOT NULL,
    discovered_at           TEXT    NOT NULL,
    location                TEXT,
    remote                  INTEGER NOT NULL DEFAULT 0,
    comp_min                INTEGER,
    comp_max                INTEGER,
    description_md          TEXT,
    score                   INTEGER,
    score_reason            TEXT,
    status                  TEXT    NOT NULL DEFAULT 'new',
    status_changed_at       TEXT,
    scored_with_prefs_at    TEXT,
    scored_with_model       TEXT,
    UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_score  ON jobs (score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs (source);

CREATE TABLE IF NOT EXISTS sources (
    name              TEXT PRIMARY KEY,
    last_fetched_at   TEXT,
    last_error        TEXT,
    cooldown_until    TEXT,
    enabled           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    type         TEXT    NOT NULL,
    payload_json TEXT    NOT NULL DEFAULT '{}',
    cost_usd     REAL,
    tokens       INTEGER,
    created_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_job_id ON events (job_id);
CREATE INDEX IF NOT EXISTS idx_events_type   ON events (type);
```

- [ ] **Step 2: Write failing tests**

```python
# tests/integration/test_store.py
from pathlib import Path

import pytest

from shortlist.store.db import (
    connect,
    current_version,
    migrate,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "shortlist.sqlite"


def test_migrate_from_zero_to_latest(db_path: Path):
    migrate(db_path)
    assert current_version(db_path) == 1


def test_migrate_is_idempotent(db_path: Path):
    migrate(db_path)
    migrate(db_path)
    migrate(db_path)
    assert current_version(db_path) == 1


def test_migrate_creates_jobs_table(db_path: Path):
    migrate(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"jobs", "sources", "events", "_schema_version"} <= names


def test_jobs_unique_constraint(db_path: Path):
    import sqlite3
    migrate(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO jobs (source, external_id, company, title, url, "
            "posted_at, discovered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("greenhouse", "gh_1", "Acme", "Eng", "https://x", "2026-04-25T09:00:00Z",
             "2026-04-28T12:00:00Z"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO jobs (source, external_id, company, title, url, "
                "posted_at, discovered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("greenhouse", "gh_1", "Acme", "Eng", "https://x",
                 "2026-04-25T09:00:00Z", "2026-04-28T12:00:00Z"),
            )
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/integration/test_store.py -v
```

Expected: ImportError on `shortlist.store.db`.

- [ ] **Step 4: Implement `shortlist/store/db.py`**

```python
"""SQLite connection + migration runner for Shortlist.

Migrations live in `_migrations/NNN_*.sql`, applied in lexical order.
A `_schema_version` table records the highest applied migration number.
Every `migrate()` is idempotent.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_MIGRATIONS_DIR = Path(__file__).parent / "_migrations"
_VERSION_RE = re.compile(r"^(\d{3})_.*\.sql$")


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with WAL mode + FK enforcement."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_version "
        "(version INTEGER NOT NULL PRIMARY KEY)"
    )


def current_version(path: Path) -> int:
    with connect(path) as conn:
        _ensure_version_table(conn)
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM _schema_version"
        ).fetchone()
    return int(row[0])


def _discover_migrations() -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for p in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        m = _VERSION_RE.match(p.name)
        if not m:
            continue
        out.append((int(m.group(1)), p))
    return out


def migrate(path: Path) -> None:
    """Apply all pending migrations. Idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    applied = current_version(path)
    with connect(path) as conn:
        _ensure_version_table(conn)
        for version, mig_path in _discover_migrations():
            if version <= applied:
                continue
            conn.executescript(mig_path.read_text())
            conn.execute("INSERT INTO _schema_version (version) VALUES (?)", (version,))
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
pytest tests/integration/test_store.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add shortlist/store/db.py shortlist/store/_migrations/001_initial.sql tests/integration/test_store.py
git commit -m "feat(store): SQLite migration runner + 001_initial schema"
```

---

## Task 5: Store — `upsert_job`, `list_jobs`, source-fetched marker

**Files:**
- Modify: `shortlist/store/db.py` (add `upsert_job`, `list_jobs`, `mark_source_fetched`, `source_last_fetched`)
- Modify: `tests/integration/test_store.py` (extend)

- [ ] **Step 1: Append failing tests**

Append to `tests/integration/test_store.py`:

```python
from datetime import datetime, timezone

from shortlist.models import Job, RawJob
from shortlist.store.db import (
    list_jobs,
    mark_source_fetched,
    source_last_fetched,
    upsert_job,
)


def _raw(external_id: str = "gh_1", *, title: str = "Senior Backend Engineer") -> RawJob:
    return RawJob(
        source="greenhouse",
        external_id=external_id,
        company="Acme",
        title=title,
        url="https://example.com/jobs/" + external_id,
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=timezone.utc),
        location="Remote - US",
        remote=True,
    )


def test_upsert_inserts_new_job(db_path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    assert isinstance(job, Job)
    assert job.id > 0
    assert job.title == "Senior Backend Engineer"
    assert job.status == "new"


def test_upsert_updates_existing_job(db_path):
    migrate(db_path)
    a = upsert_job(db_path, _raw(title="Old Title"))
    b = upsert_job(db_path, _raw(title="New Title"))
    assert a.id == b.id
    assert b.title == "New Title"


def test_list_jobs_returns_all(db_path):
    migrate(db_path)
    upsert_job(db_path, _raw("gh_1"))
    upsert_job(db_path, _raw("gh_2"))
    jobs = list_jobs(db_path)
    assert len(jobs) == 2


def test_list_jobs_filters_by_status(db_path):
    migrate(db_path)
    upsert_job(db_path, _raw("gh_1"))
    upsert_job(db_path, _raw("gh_2"))
    jobs = list_jobs(db_path, status="new")
    assert len(jobs) == 2
    jobs = list_jobs(db_path, status="applied")
    assert jobs == []


def test_source_fetched_marker(db_path):
    migrate(db_path)
    assert source_last_fetched(db_path, "greenhouse") is None
    when = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    mark_source_fetched(db_path, "greenhouse", when)
    got = source_last_fetched(db_path, "greenhouse")
    assert got == when
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_store.py -v -k "upsert or list_jobs or source_fetched"
```

Expected: ImportError on the new symbols.

- [ ] **Step 3: Append to `shortlist/store/db.py`**

```python
# --- additions to shortlist/store/db.py ---

from datetime import datetime, timezone

from shortlist.models import Job, JobStatus, RawJob


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        source=row["source"],
        external_id=row["external_id"],
        company=row["company"],
        title=row["title"],
        url=row["url"],
        posted_at=datetime.fromisoformat(row["posted_at"].replace("Z", "+00:00")),
        discovered_at=datetime.fromisoformat(
            row["discovered_at"].replace("Z", "+00:00")
        ),
        location=row["location"],
        remote=bool(row["remote"]),
        comp_min=row["comp_min"],
        comp_max=row["comp_max"],
        description_md=row["description_md"],
        score=row["score"],
        score_reason=row["score_reason"],
        status=row["status"],
        status_changed_at=(
            datetime.fromisoformat(row["status_changed_at"].replace("Z", "+00:00"))
            if row["status_changed_at"] else None
        ),
        scored_with_prefs_at=(
            datetime.fromisoformat(row["scored_with_prefs_at"].replace("Z", "+00:00"))
            if row["scored_with_prefs_at"] else None
        ),
        scored_with_model=row["scored_with_model"],
    )


def upsert_job(path: Path, raw: RawJob, *, now: datetime | None = None) -> Job:
    """Insert or update a job by (source, external_id). Returns the persisted Job."""
    discovered = now or datetime.now(timezone.utc)
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO jobs (source, external_id, company, title, url, posted_at,
                              discovered_at, location, remote, comp_min, comp_max,
                              description_md)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source, external_id) DO UPDATE SET
                company        = excluded.company,
                title          = excluded.title,
                url            = excluded.url,
                posted_at      = excluded.posted_at,
                location       = excluded.location,
                remote         = excluded.remote,
                comp_min       = excluded.comp_min,
                comp_max       = excluded.comp_max,
                description_md = excluded.description_md
            """,
            (
                raw.source, raw.external_id, raw.company, raw.title, str(raw.url),
                _utc_iso(raw.posted_at), _utc_iso(discovered),
                raw.location, int(raw.remote), raw.comp_min, raw.comp_max,
                raw.description_md,
            ),
        )
        row = conn.execute(
            "SELECT * FROM jobs WHERE source = ? AND external_id = ?",
            (raw.source, raw.external_id),
        ).fetchone()
    return _row_to_job(row)


def list_jobs(
    path: Path,
    *,
    status: JobStatus | None = None,
    min_score: int | None = None,
    limit: int | None = None,
) -> list[Job]:
    """Read jobs ordered by score DESC NULLS LAST, then discovered_at DESC."""
    sql = "SELECT * FROM jobs"
    clauses: list[str] = []
    params: list[object] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if min_score is not None:
        clauses.append("score >= ?")
        params.append(min_score)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY (score IS NULL), score DESC, discovered_at DESC"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    with connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_job(r) for r in rows]


def mark_source_fetched(path: Path, name: str, when: datetime) -> None:
    with connect(path) as conn:
        conn.execute(
            """
            INSERT INTO sources (name, last_fetched_at) VALUES (?, ?)
            ON CONFLICT (name) DO UPDATE SET last_fetched_at = excluded.last_fetched_at,
                                             last_error = NULL
            """,
            (name, _utc_iso(when)),
        )


def source_last_fetched(path: Path, name: str) -> datetime | None:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT last_fetched_at FROM sources WHERE name = ?", (name,)
        ).fetchone()
    if row is None or row[0] is None:
        return None
    return datetime.fromisoformat(row[0].replace("Z", "+00:00"))
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/integration/test_store.py -v
```

Expected: 9 passed (4 migration + 5 new).

- [ ] **Step 5: Commit**

```bash
git add shortlist/store/db.py tests/integration/test_store.py
git commit -m "feat(store): upsert_job, list_jobs, source-fetched marker"
```

---

## Task 6: `Source` ABC + base contract

**Files:**
- Create: `shortlist/sources/base.py`
- Modify: `tests/unit/test_models.py` (extend with source ABC tests)

- [ ] **Step 1: Append failing test**

Append to `tests/unit/test_models.py`:

```python
from typing import Iterator

from shortlist.sources.base import Source


def test_source_abc_requires_fetch():
    class Bad(Source):
        name = "bad"

    with pytest.raises(TypeError):
        Bad()  # abstract method not implemented


def test_concrete_source_fetch_yields_rawjob():
    class Fake(Source):
        name = "fake"
        def fetch(self, since):
            yield RawJob(
                source="fake", external_id="x_1", company="Acme",
                title="Eng", url="https://example.com",
                posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=timezone.utc),
            )

    out = list(Fake().fetch(None))
    assert len(out) == 1
    assert out[0].source == "fake"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_models.py -v -k source
```

Expected: ImportError on `shortlist.sources.base`.

- [ ] **Step 3: Implement `shortlist/sources/base.py`**

```python
"""Source base class — every fetcher implements this contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar, Iterator

from shortlist.models import RawJob


class Source(ABC):
    """A pull-mode job source.

    Implementations set `name` to a short identifier matching the
    `sources.<name>` key in `config.yaml` and implement `fetch()`.
    """

    name: ClassVar[str]

    @abstractmethod
    def fetch(self, since: datetime | None) -> Iterator[RawJob]:
        """Yield jobs posted/updated at-or-after `since`. Iterator, not list,
        so callers can persist as they go."""
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/unit/test_models.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add shortlist/sources/base.py tests/unit/test_models.py
git commit -m "feat(sources): Source ABC defining fetch(since) -> Iterator[RawJob]"
```

---

## Task 7: Greenhouse client — pure HTTP

**Files:**
- Create: `tests/fixtures/greenhouse_acme_page1.json`
- Create: `tests/fixtures/greenhouse_acme_page2.json`
- Create: `shortlist/sources/ats/greenhouse.py` (HTTP layer only)
- Test: `tests/integration/test_greenhouse.py`

- [ ] **Step 1: Create fixture JSON (page 1)**

`tests/fixtures/greenhouse_acme_page1.json`:

```json
{
  "jobs": [
    {
      "id": 4521,
      "internal_job_id": 4521,
      "title": "Senior Backend Engineer",
      "absolute_url": "https://boards.greenhouse.io/acme/jobs/4521",
      "updated_at": "2026-04-25T09:00:00-04:00",
      "location": {"name": "Remote - US"},
      "content": "%3Cp%3EBuild distributed systems in Python.%3C%2Fp%3E",
      "metadata": null
    },
    {
      "id": 4522,
      "internal_job_id": 4522,
      "title": "Staff Platform Engineer",
      "absolute_url": "https://boards.greenhouse.io/acme/jobs/4522",
      "updated_at": "2026-04-26T10:30:00-04:00",
      "location": {"name": "Atlanta, GA"},
      "content": "%3Cp%3ELead infrastructure.%3C%2Fp%3E",
      "metadata": null
    }
  ],
  "meta": {"total": 3}
}
```

- [ ] **Step 2: Create fixture JSON (page 2)**

`tests/fixtures/greenhouse_acme_page2.json`:

```json
{
  "jobs": [
    {
      "id": 4523,
      "internal_job_id": 4523,
      "title": "Engineering Manager",
      "absolute_url": "https://boards.greenhouse.io/acme/jobs/4523",
      "updated_at": "2026-04-27T08:00:00-04:00",
      "location": {"name": "New York, NY"},
      "content": "%3Cp%3EManage 6 ICs.%3C%2Fp%3E",
      "metadata": null
    }
  ],
  "meta": {"total": 3}
}
```

- [ ] **Step 3: Write failing tests**

```python
# tests/integration/test_greenhouse.py
import json
from pathlib import Path

import httpx
import pytest
import respx

from shortlist.sources.ats.greenhouse import GreenhouseClient

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_greenhouse_fetch_jobs_single_page():
    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))

    client = GreenhouseClient()
    raw_payloads = list(client.fetch_company("acme"))
    assert len(raw_payloads) == 2
    assert raw_payloads[0]["id"] == 4521


@respx.mock
def test_greenhouse_fetch_retries_on_500():
    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    route = respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(side_effect=[
        httpx.Response(500),
        httpx.Response(500),
        httpx.Response(200, json=payload),
    ])

    client = GreenhouseClient()
    raw_payloads = list(client.fetch_company("acme"))
    assert len(raw_payloads) == 2
    assert route.call_count == 3


@respx.mock
def test_greenhouse_fetch_404_returns_empty():
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/nopecorp/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(404))

    client = GreenhouseClient()
    raw_payloads = list(client.fetch_company("nopecorp"))
    assert raw_payloads == []
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
pytest tests/integration/test_greenhouse.py -v
```

Expected: ImportError on `shortlist.sources.ats.greenhouse`.

- [ ] **Step 5: Implement HTTP client**

`shortlist/sources/ats/greenhouse.py`:

```python
"""Greenhouse Job Boards API client.

Public, unauthenticated. Endpoint:
  GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

`content=true` returns the URL-encoded HTML description with the job, avoiding
a per-job follow-up call.
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

_BASE = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseClient:
    def __init__(self, *, timeout: float = 30.0):
        self._client = httpx.Client(timeout=timeout)

    def __del__(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, params: dict[str, str]) -> httpx.Response:
        resp = self._client.get(url, params=params)
        if resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_company(self, board_token: str) -> Iterator[dict[str, Any]]:
        """Yield raw job dicts for a Greenhouse board.

        Greenhouse returns the full list in one response (no pagination on
        the boards endpoint), but we treat it as an iterator so the calling
        Source can stream-persist."""
        url = f"{_BASE}/{board_token}/jobs"
        try:
            resp = self._get(url, {"content": "true"})
        except httpx.HTTPStatusError as e:
            logger.warning("greenhouse fetch failed for %s: %s", board_token, e)
            return
        if resp.status_code == 404:
            logger.info("greenhouse board not found: %s", board_token)
            return
        resp.raise_for_status()
        payload = resp.json()
        for job in payload.get("jobs", []):
            yield job
```

- [ ] **Step 6: Run tests, verify they pass**

```bash
pytest tests/integration/test_greenhouse.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add shortlist/sources/ats/greenhouse.py tests/integration/test_greenhouse.py tests/fixtures/greenhouse_acme_page1.json tests/fixtures/greenhouse_acme_page2.json
git commit -m "feat(sources/greenhouse): HTTP client with tenacity retry"
```

---

## Task 8: Greenhouse `Source` — normalize and fetch

**Files:**
- Modify: `shortlist/sources/ats/greenhouse.py` (add `_normalize`, `GreenhouseSource`)
- Modify: `tests/integration/test_greenhouse.py` (add normalize + Source tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/integration/test_greenhouse.py`:

```python
from datetime import datetime, timezone

from shortlist.models import RawJob
from shortlist.sources.ats.greenhouse import GreenhouseSource, _normalize


def _sample_job() -> dict:
    return {
        "id": 4521,
        "title": "Senior Backend Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/4521",
        "updated_at": "2026-04-25T09:00:00-04:00",
        "location": {"name": "Remote - US"},
        "content": "%3Cp%3EBuild stuff.%3C%2Fp%3E",
    }


def test_normalize_returns_rawjob():
    raw = _normalize(_sample_job(), company="Acme")
    assert isinstance(raw, RawJob)
    assert raw.source == "greenhouse"
    assert raw.external_id == "4521"
    assert raw.company == "Acme"
    assert raw.title == "Senior Backend Engineer"
    assert raw.location == "Remote - US"
    assert raw.remote is True
    assert raw.posted_at == datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc)
    assert "Build stuff." in (raw.description_md or "")


def test_normalize_remote_false_when_location_lacks_remote_word():
    job = _sample_job()
    job["location"] = {"name": "Atlanta, GA"}
    raw = _normalize(job, company="Acme")
    assert raw.remote is False


@respx.mock
def test_greenhouse_source_fetch_yields_normalized():
    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))

    src = GreenhouseSource(companies={"acme": "Acme Corp"})
    out = list(src.fetch(since=None))
    assert len(out) == 2
    assert all(isinstance(j, RawJob) for j in out)
    assert out[0].company == "Acme Corp"
    # external_id is namespaced by board token
    assert out[0].external_id == "acme:4521"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_greenhouse.py -v -k "normalize or source_fetch"
```

Expected: ImportError on `_normalize` / `GreenhouseSource`.

- [ ] **Step 3: Append to `shortlist/sources/ats/greenhouse.py`**

```python
# --- additions to shortlist/sources/ats/greenhouse.py ---

import html
import re
from datetime import datetime
from typing import ClassVar
from urllib.parse import unquote

from shortlist.models import RawJob
from shortlist.sources.base import Source

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG_RE.sub("", html.unescape(unquote(s))).strip()


def _is_remote(loc: str) -> bool:
    return "remote" in loc.lower()


def _normalize(job: dict[str, Any], *, company: str) -> RawJob:
    location = (job.get("location") or {}).get("name") or ""
    return RawJob(
        source="greenhouse",
        external_id=str(job["id"]),
        company=company,
        title=job["title"],
        url=job["absolute_url"],
        posted_at=datetime.fromisoformat(job["updated_at"]),
        location=location or None,
        remote=_is_remote(location),
        description_md=_strip_html(job.get("content") or "") or None,
    )


class GreenhouseSource(Source):
    """Pulls jobs from a configured set of Greenhouse boards.

    `companies` maps `board_token -> display_name`. The board token is the
    URL slug (e.g. "acme" in https://boards.greenhouse.io/acme).
    """

    name: ClassVar[str] = "greenhouse"

    def __init__(self, *, companies: dict[str, str], client: GreenhouseClient | None = None):
        self._companies = companies
        self._client = client or GreenhouseClient()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:
        for token, display in self._companies.items():
            for raw in self._client.fetch_company(token):
                normalized = _normalize(raw, company=display)
                # Make external_id unique across boards: prefix with token.
                yield normalized.model_copy(
                    update={"external_id": f"{token}:{normalized.external_id}"}
                )
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/integration/test_greenhouse.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add shortlist/sources/ats/greenhouse.py tests/integration/test_greenhouse.py
git commit -m "feat(sources/greenhouse): GreenhouseSource normalizes to RawJob"
```

---

## Task 9: Hard-filter ranker

**Files:**
- Create: `shortlist/ranker/hard_filter.py`
- Test: `tests/unit/test_hard_filter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_hard_filter.py
from datetime import datetime, timezone

import pytest
from hypothesis import given, strategies as st

from shortlist.config import Prefs
from shortlist.models import Job
from shortlist.ranker.hard_filter import passes


def _prefs(**overrides) -> Prefs:
    base = dict(
        titles=["Senior Backend Engineer", "Staff Engineer"],
        locations=["Remote - US", "Atlanta, GA"],
        remote_ok=True,
        comp_floor_usd=180000,
        exclude_keywords=["C++", "on-site only"],
        seniority=["senior", "staff"],
        greenhouse_companies=["acme"],
    )
    base.update(overrides)
    return Prefs.model_validate(base)


def _job(**overrides) -> Job:
    base = dict(
        id=1, source="greenhouse", external_id="acme:1", company="Acme",
        title="Senior Backend Engineer",
        url="https://example.com/jobs/1",
        posted_at=datetime(2026, 4, 25, 9, 0, tzinfo=timezone.utc),
        discovered_at=datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc),
        location="Remote - US", remote=True,
        comp_min=200000, comp_max=240000,
        description_md="Python, Postgres, distributed systems.",
    )
    base.update(overrides)
    return Job.model_validate(base)


def test_passes_happy_path():
    assert passes(_job(), _prefs()) is True


def test_fails_below_comp_floor():
    assert passes(_job(comp_max=150000), _prefs()) is False


def test_passes_when_comp_unknown():
    # Missing comp shouldn't disqualify — many ATS jobs omit it.
    assert passes(_job(comp_min=None, comp_max=None), _prefs()) is True


def test_fails_excluded_keyword_in_description():
    assert passes(_job(description_md="C++ heavy systems"), _prefs()) is False


def test_fails_excluded_keyword_in_title():
    assert passes(_job(title="C++ Engineer"), _prefs()) is False


def test_fails_when_not_remote_and_remote_only_pref():
    assert passes(_job(remote=False, location="Berlin"), _prefs()) is False


def test_passes_when_not_remote_but_location_in_allowlist():
    assert passes(_job(remote=False, location="Atlanta, GA"), _prefs()) is True


def test_fails_when_no_seniority_match():
    job = _job(title="Junior Backend Engineer")
    prefs = _prefs(titles=["Junior Backend Engineer"])  # title matches
    # but seniority doesn't include "junior", so still fails
    assert passes(job, prefs) is False


@given(st.text(min_size=2, max_size=20).filter(lambda s: s.strip()))
def test_random_excluded_keyword_filters(kw: str):
    prefs = _prefs(exclude_keywords=[kw])
    job = _job(description_md=f"This role uses {kw} extensively.")
    assert passes(job, prefs) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_hard_filter.py -v
```

Expected: ImportError on `shortlist.ranker.hard_filter`.

- [ ] **Step 3: Implement `shortlist/ranker/hard_filter.py`**

```python
"""Hard filter: deterministic disqualifier before any LLM scoring.

A job `passes` only if all of the following hold:
  - At least one preferred title matches as a case-insensitive substring of job.title.
  - At least one preferred seniority appears in job.title (case-insensitive).
  - No `exclude_keywords` appears (case-insensitive) in title or description.
  - Location is acceptable: `job.remote` and `prefs.remote_ok`, OR
    `job.location` substring-matches one of `prefs.locations`.
  - Compensation: if `job.comp_max` is known, it must be >= `prefs.comp_floor_usd`.
    Unknown compensation passes (ATS often omits it).
"""
from __future__ import annotations

from shortlist.config import Prefs
from shortlist.models import Job


def _ci_any(needles: list[str], haystack: str) -> bool:
    h = haystack.lower()
    return any(n.lower() in h for n in needles if n)


def passes(job: Job, prefs: Prefs) -> bool:
    title = job.title or ""
    desc = job.description_md or ""
    text = f"{title}\n{desc}"

    if _ci_any(prefs.exclude_keywords, text):
        return False

    if not _ci_any(prefs.titles, title):
        return False

    if not _ci_any(prefs.seniority, title):
        return False

    location_ok = (job.remote and prefs.remote_ok) or (
        job.location is not None and _ci_any(prefs.locations, job.location)
    )
    if not location_ok:
        return False

    if job.comp_max is not None and job.comp_max < prefs.comp_floor_usd:
        return False

    return True
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/unit/test_hard_filter.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add shortlist/ranker/hard_filter.py tests/unit/test_hard_filter.py
git commit -m "feat(ranker): deterministic hard filter against Prefs"
```

---

## Task 10: Application paths helper

**Files:**
- Create: `shortlist/paths.py`
- Test: `tests/unit/test_paths.py`

Reason: every command needs to resolve `~/.config/shortlist/...`, `~/.local/share/shortlist/...`. Using `platformdirs` keeps Linux/macOS/Windows consistent and tests can override via env.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_paths.py
import os
from pathlib import Path

import pytest

from shortlist import paths


def test_default_config_path(monkeypatch):
    monkeypatch.delenv("SHORTLIST_CONFIG_HOME", raising=False)
    assert paths.config_dir().name == "shortlist"


def test_env_overrides_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path))
    assert paths.config_dir() == tmp_path


def test_env_overrides_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path))
    assert paths.data_dir() == tmp_path


def test_db_path_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path))
    assert paths.db_path() == tmp_path / "db.sqlite"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_paths.py -v
```

Expected: ImportError on `shortlist.paths`.

- [ ] **Step 3: Implement `shortlist/paths.py`**

```python
"""Resolve shortlist paths.

Honors env overrides (used by tests):
  SHORTLIST_CONFIG_HOME → config_dir()
  SHORTLIST_DATA_HOME   → data_dir()
"""
from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

_APP = "shortlist"


def config_dir() -> Path:
    env = os.environ.get("SHORTLIST_CONFIG_HOME")
    if env:
        return Path(env)
    return Path(user_config_dir(_APP))


def data_dir() -> Path:
    env = os.environ.get("SHORTLIST_DATA_HOME")
    if env:
        return Path(env)
    return Path(user_data_dir(_APP))


def config_path() -> Path:
    return config_dir() / "config.yaml"


def prefs_path() -> Path:
    return config_dir() / "prefs.yaml"


def db_path() -> Path:
    return data_dir() / "db.sqlite"
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/unit/test_paths.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add shortlist/paths.py tests/unit/test_paths.py
git commit -m "feat(paths): platformdirs-backed config/data dir helpers with env overrides"
```

---

## Task 11: CLI scaffolding + `db init`, `db status`, `db backup`

**Files:**
- Create: `shortlist/cli.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/integration/test_cli.py
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shortlist.cli import app

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config"
    data = tmp_path / "data"
    cfg.mkdir()
    data.mkdir()
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(cfg))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(data))
    return cfg, data


def test_db_init_creates_sqlite_file(env):
    cfg, data = env
    result = runner.invoke(app, ["db", "init"])
    assert result.exit_code == 0, result.output
    assert (data / "db.sqlite").exists()


def test_db_init_is_idempotent(env):
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["db", "init"])
    assert result.exit_code == 0


def test_db_status_reports_version(env):
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["db", "status"])
    assert result.exit_code == 0
    assert "schema version: 1" in result.output.lower()


def test_db_status_when_uninitialized(env):
    result = runner.invoke(app, ["db", "status"])
    assert result.exit_code == 0
    assert "schema version: 0" in result.output.lower()


def test_db_backup_creates_file(env):
    cfg, data = env
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["db", "backup"])
    assert result.exit_code == 0
    backups = list((data / "backups").glob("db-*.sqlite"))
    assert len(backups) == 1


def test_db_backup_errors_when_no_db(env):
    result = runner.invoke(app, ["db", "backup"])
    assert result.exit_code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_cli.py -v -k "db"
```

Expected: ImportError on `shortlist.cli`.

- [ ] **Step 3: Implement initial `shortlist/cli.py`**

```python
"""Shortlist Typer CLI.

Subcommand groups:
  config  — view config + write defaults
  db      — init / status / backup
  fetch   — pull jobs from enabled sources
  rank    — apply hard filter (Plan 1) / LLM rerank (Plan 2)
  list    — print stored jobs
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from shortlist import paths
from shortlist.store import db as store_db

app = typer.Typer(no_args_is_help=True, help="Shortlist — personal job search.")
console = Console()

# --- db subgroup ----------------------------------------------------------

db_app = typer.Typer(help="Database admin.")
app.add_typer(db_app, name="db")


@db_app.command("init")
def db_init() -> None:
    """Create the SQLite database and apply migrations."""
    target = paths.db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    store_db.migrate(target)
    console.print(f"[green]ok[/green] db at {target}")


@db_app.command("status")
def db_status() -> None:
    """Print schema version + db location."""
    target = paths.db_path()
    if not target.exists():
        console.print(f"db not present at {target}")
        console.print("schema version: 0")
        return
    version = store_db.current_version(target)
    console.print(f"db: {target}")
    console.print(f"schema version: {version}")


@db_app.command("backup")
def db_backup() -> None:
    """Copy the SQLite file to a timestamped backup."""
    src = paths.db_path()
    if not src.exists():
        console.print(f"[yellow]no db at {src}[/yellow]")
        raise typer.Exit(code=1)
    backup_dir = paths.data_dir() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = backup_dir / f"db-{stamp}.sqlite"
    shutil.copy2(src, dst)
    console.print(f"[green]ok[/green] backup at {dst}")
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/integration/test_cli.py -v -k "db"
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add shortlist/cli.py tests/integration/test_cli.py
git commit -m "feat(cli): db init/status/backup commands"
```

---

## Task 12: CLI `config init` and `config show`

**Files:**
- Modify: `shortlist/cli.py` (add `config` subgroup)
- Modify: `tests/integration/test_cli.py` (add config tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/integration/test_cli.py`:

```python
def test_config_init_writes_default_files(env):
    cfg, data = env
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0, result.output
    assert (cfg / "config.yaml").exists()
    assert (cfg / "prefs.yaml").exists()


def test_config_init_does_not_overwrite(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "config.yaml").write_text("# user-edited\n")
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0
    assert "# user-edited" in (cfg / "config.yaml").read_text()


def test_config_show_after_init(env):
    runner.invoke(app, ["config", "init"])
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "anthropic:" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_cli.py -v -k "config"
```

Expected: "no such command 'config'".

- [ ] **Step 3: Append to `shortlist/cli.py`**

```python
# --- config subgroup ------------------------------------------------------

config_app = typer.Typer(help="Manage configuration.")
app.add_typer(config_app, name="config")


_DEFAULT_CONFIG = """\
# Shortlist configuration. See docs/spec.md for the full reference.
anthropic:
  key_source: env
  key_env_var: ANTHROPIC_API_KEY
budget:
  daily_usd: 5.00
  monthly_usd: 60.00
paths:
  resume: ~/jobs/resume.md
  output_dir: ~/jobs
sources:
  greenhouse:
    enabled: true
    rate_limit_rpm: 30
ranker:
  top_k_for_llm_rerank: 30
  embedding_model: bge-small-en-v1.5
  rerank_model: claude-haiku-4-5-20251001
tailor:
  model: claude-sonnet-4-6
  cover_paragraphs: 3
"""

_DEFAULT_PREFS = """\
# Shortlist preferences. Edit these to taste.
titles:
  - "Senior Backend Engineer"
  - "Staff Engineer"
locations:
  - "Remote - US"
  - "Atlanta, GA"
remote_ok: true
comp_floor_usd: 180000
exclude_keywords: []
seniority:
  - senior
  - staff
greenhouse_companies: []
"""


@config_app.command("init")
def config_init() -> None:
    """Write default config.yaml and prefs.yaml if not present."""
    paths.config_dir().mkdir(parents=True, exist_ok=True)
    cfg_path = paths.config_path()
    prefs_path = paths.prefs_path()
    wrote: list[Path] = []
    if not cfg_path.exists():
        cfg_path.write_text(_DEFAULT_CONFIG)
        wrote.append(cfg_path)
    if not prefs_path.exists():
        prefs_path.write_text(_DEFAULT_PREFS)
        wrote.append(prefs_path)
    if wrote:
        for p in wrote:
            console.print(f"[green]wrote[/green] {p}")
    else:
        console.print("[yellow]no changes — both files exist[/yellow]")


@config_app.command("show")
def config_show() -> None:
    """Print current config.yaml + prefs.yaml."""
    for p in (paths.config_path(), paths.prefs_path()):
        if not p.exists():
            console.print(f"[yellow]missing[/yellow] {p}")
            continue
        console.rule(str(p))
        console.print(p.read_text())
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/integration/test_cli.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add shortlist/cli.py tests/integration/test_cli.py
git commit -m "feat(cli): config init/show commands with safe non-overwrite"
```

---

## Task 13: CLI `fetch` command

**Files:**
- Modify: `shortlist/cli.py` (add `fetch`)
- Modify: `tests/integration/test_cli.py` (add fetch tests with respx)

- [ ] **Step 1: Append failing tests**

Append to `tests/integration/test_cli.py`:

```python
import json
import httpx
import respx

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
def test_fetch_persists_jobs(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    prefs_yaml = (cfg / "prefs.yaml").read_text().replace(
        "greenhouse_companies: []",
        "greenhouse_companies:\n  - acme",
    )
    (cfg / "prefs.yaml").write_text(prefs_yaml)
    runner.invoke(app, ["db", "init"])

    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))

    result = runner.invoke(app, ["fetch"])
    assert result.exit_code == 0, result.output
    assert "fetched 2 jobs" in result.output.lower()

    # Re-fetch is idempotent.
    result = runner.invoke(app, ["fetch"])
    assert result.exit_code == 0


@respx.mock
def test_fetch_handles_source_error_gracefully(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "prefs.yaml").write_text(
        (cfg / "prefs.yaml").read_text().replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - nopecorp",
        )
    )
    runner.invoke(app, ["db", "init"])

    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/nopecorp/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(500))

    result = runner.invoke(app, ["fetch"])
    # Source error must not crash the CLI.
    assert result.exit_code == 0
    assert "0 jobs" in result.output.lower() or "error" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_cli.py -v -k "fetch"
```

Expected: "no such command 'fetch'".

- [ ] **Step 3: Append to `shortlist/cli.py`**

```python
# --- fetch ----------------------------------------------------------------

from shortlist.config import load_prefs
from shortlist.sources.ats.greenhouse import GreenhouseSource


@app.command("fetch")
def fetch() -> None:
    """Pull jobs from enabled sources and persist."""
    if not paths.prefs_path().exists():
        console.print("[red]error[/red] run `shortlist config init` first")
        raise typer.Exit(code=2)
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)

    prefs = load_prefs(paths.prefs_path())
    db = paths.db_path()

    total = 0
    if prefs.greenhouse_companies:
        # Without per-company display in prefs, use the token capitalised.
        companies = {tok: tok.title() for tok in prefs.greenhouse_companies}
        src = GreenhouseSource(companies=companies)
        try:
            for raw in src.fetch(since=store_db.source_last_fetched(db, src.name)):
                store_db.upsert_job(db, raw)
                total += 1
            store_db.mark_source_fetched(db, src.name, datetime.now(timezone.utc))
        except Exception as e:  # noqa: BLE001 — surface and continue
            console.print(f"[yellow]greenhouse error:[/yellow] {e}")

    console.print(f"fetched {total} jobs")
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/integration/test_cli.py -v -k "fetch"
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add shortlist/cli.py tests/integration/test_cli.py
git commit -m "feat(cli): fetch command pulls Greenhouse and persists"
```

---

## Task 14: CLI `rank` command (hard-filter only)

**Files:**
- Modify: `shortlist/cli.py` (add `rank`)
- Modify: `shortlist/store/db.py` (add `update_score`)
- Modify: `tests/integration/test_store.py` (add update_score test)
- Modify: `tests/integration/test_cli.py` (add rank test)

- [ ] **Step 1: Append store helper test**

Append to `tests/integration/test_store.py`:

```python
def test_update_score(db_path):
    migrate(db_path)
    job = upsert_job(db_path, _raw())
    from shortlist.store.db import update_score
    update_score(db_path, job.id, score=42, reason="hard filter pass",
                 model="hard_filter")
    out = list_jobs(db_path)[0]
    assert out.score == 42
    assert out.score_reason == "hard filter pass"
    assert out.scored_with_model == "hard_filter"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/integration/test_store.py::test_update_score -v
```

Expected: ImportError on `update_score`.

- [ ] **Step 3: Add `update_score` to `shortlist/store/db.py`**

```python
def update_score(
    path: Path, job_id: int, *, score: int, reason: str, model: str,
    when: datetime | None = None,
) -> None:
    when = when or datetime.now(timezone.utc)
    with connect(path) as conn:
        conn.execute(
            """
            UPDATE jobs SET score = ?, score_reason = ?, scored_with_model = ?,
                            scored_with_prefs_at = ?
            WHERE id = ?
            """,
            (score, reason, model, _utc_iso(when), job_id),
        )
```

- [ ] **Step 4: Verify store test passes**

```bash
pytest tests/integration/test_store.py::test_update_score -v
```

Expected: pass.

- [ ] **Step 5: Append failing CLI rank test**

Append to `tests/integration/test_cli.py`:

```python
@respx.mock
def test_rank_scores_passing_jobs_high_failing_low(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "prefs.yaml").write_text(
        (cfg / "prefs.yaml").read_text().replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
    )
    runner.invoke(app, ["db", "init"])

    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))
    runner.invoke(app, ["fetch"])

    result = runner.invoke(app, ["rank"])
    assert result.exit_code == 0, result.output

    # Two seeded jobs: "Senior Backend Engineer" (passes) and
    # "Staff Platform Engineer" (passes via "staff" seniority).
    # Both pass hard filter -> score 50 (placeholder for Plan 1).
    from shortlist.store.db import list_jobs
    jobs = list_jobs(data / "db.sqlite")
    scores = sorted(j.score for j in jobs if j.score is not None)
    assert scores == [50, 50]
```

- [ ] **Step 6: Run test to verify it fails**

```bash
pytest tests/integration/test_cli.py::test_rank_scores_passing_jobs_high_failing_low -v
```

Expected: "no such command 'rank'".

- [ ] **Step 7: Append `rank` command to `shortlist/cli.py`**

```python
# --- rank -----------------------------------------------------------------

from shortlist.ranker.hard_filter import passes


@app.command("rank")
def rank() -> None:
    """Score stored jobs.

    Plan 1: hard filter only. Passes -> score 50, fails -> score 0.
    Plan 2 will replace this with embeddings + Haiku rerank.
    """
    if not paths.prefs_path().exists():
        console.print("[red]error[/red] run `shortlist config init` first")
        raise typer.Exit(code=2)
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)

    prefs = load_prefs(paths.prefs_path())
    db = paths.db_path()
    pass_count = fail_count = 0

    for job in store_db.list_jobs(db):
        if passes(job, prefs):
            store_db.update_score(db, job.id, score=50,
                                  reason="passed hard filter", model="hard_filter")
            pass_count += 1
        else:
            store_db.update_score(db, job.id, score=0,
                                  reason="filtered out", model="hard_filter")
            fail_count += 1

    console.print(f"ranked: {pass_count} pass / {fail_count} filtered")
```

- [ ] **Step 8: Run rank test, verify it passes**

```bash
pytest tests/integration/test_cli.py::test_rank_scores_passing_jobs_high_failing_low -v
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add shortlist/cli.py shortlist/store/db.py tests/integration/test_cli.py tests/integration/test_store.py
git commit -m "feat(cli): rank command applies hard filter (placeholder scoring)"
```

---

## Task 15: CLI `list` command

**Files:**
- Modify: `shortlist/cli.py` (add `list`)
- Modify: `tests/integration/test_cli.py` (add list tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/integration/test_cli.py`:

```python
@respx.mock
def test_list_shows_top_jobs(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "prefs.yaml").write_text(
        (cfg / "prefs.yaml").read_text().replace(
            "greenhouse_companies: []",
            "greenhouse_companies:\n  - acme",
        )
    )
    runner.invoke(app, ["db", "init"])
    payload = json.loads((FIXTURES / "greenhouse_acme_page1.json").read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        params={"content": "true"},
    ).mock(return_value=httpx.Response(200, json=payload))
    runner.invoke(app, ["fetch"])
    runner.invoke(app, ["rank"])

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Senior Backend Engineer" in result.output
    assert "Acme" in result.output


def test_list_min_score_filter(env):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    runner.invoke(app, ["db", "init"])
    result = runner.invoke(app, ["list", "--min-score", "1"])
    # No jobs yet; exit 0, empty table.
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_cli.py -v -k "list"
```

Expected: "no such command 'list'".

- [ ] **Step 3: Append to `shortlist/cli.py`**

```python
# --- list -----------------------------------------------------------------


@app.command("list")
def list_jobs_cmd(
    min_score: int = typer.Option(0, "--min-score", help="Hide jobs scoring below."),
    limit: int = typer.Option(50, "--limit", help="Max rows to print."),
) -> None:
    """Print stored jobs as a table, ordered by score DESC."""
    if not paths.db_path().exists():
        console.print("[red]error[/red] run `shortlist db init` first")
        raise typer.Exit(code=2)
    rows = store_db.list_jobs(paths.db_path(), min_score=min_score, limit=limit)
    if not rows:
        console.print("[dim]no jobs[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Company")
    table.add_column("Title")
    table.add_column("Location")
    table.add_column("URL", overflow="fold")
    for j in rows:
        table.add_row(
            "—" if j.score is None else str(j.score),
            j.company,
            j.title,
            j.location or "",
            str(j.url),
        )
    console.print(table)
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/integration/test_cli.py -v
```

Expected: all CLI tests pass (13 total).

- [ ] **Step 5: Commit**

```bash
git add shortlist/cli.py tests/integration/test_cli.py
git commit -m "feat(cli): list command prints scored jobs as a Rich table"
```

---

## Task 16: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write CI workflow**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    env:
      # Force-fail any test that tries to reach Anthropic.
      ANTHROPIC_API_KEY: ""
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: install
        run: |
          python -m pip install -U pip
          pip install -e ".[dev]"

      - name: ruff
        run: |
          ruff check .
          ruff format --check .

      - name: mypy
        run: mypy shortlist

      - name: pytest
        run: pytest --cov=shortlist --cov-report=term-missing --cov-fail-under=80
```

- [ ] **Step 2: Run the same gates locally to validate**

```bash
ruff check .
ruff format --check .
mypy shortlist
pytest --cov=shortlist --cov-report=term-missing --cov-fail-under=80
```

Expected: every gate green, coverage ≥ 80% on `shortlist/`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: ruff + mypy + pytest with 80% coverage gate"
```

---

## Task 17: README quickstart + spec link

**Files:**
- Modify: `README.md` (replace skeleton)
- Create: `docs/spec.md` (copy of monorepo spec for self-contained repo)

- [ ] **Step 1: Copy spec into repo**

```bash
cp /run/media/seraph/Win1Tb/dev/repos/digitalseraph/docs/superpowers/specs/2026-04-28-shortlist-design.md docs/spec.md
```

- [ ] **Step 2: Replace README**

```markdown
# Shortlist

Personal job-search assistant. Discovers postings, ranks them against your resume + preferences, tailors per-job materials, and tracks the application lifecycle. **You apply manually** — Shortlist surfaces and prepares; it never auto-submits.

This is **Plan 1 of 6** (foundation). It ships:

- Greenhouse public-board ingestion
- SQLite store with versioned migrations
- Hard-filter ranking against `prefs.yaml`
- Typer CLI: `db`, `config`, `fetch`, `rank`, `list`

Plans 2–6 add the rest of the ATS sources, embeddings + LLM rerank, tailoring, the Textual TUI, scraped aggregators, curated boards, and RSS.

## Install (development)

```bash
git clone https://github.com/<user>/shortlist
cd shortlist
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## First run

```bash
shortlist db init                 # create ~/.local/share/shortlist/db.sqlite
shortlist config init             # write defaults to ~/.config/shortlist/
$EDITOR ~/.config/shortlist/prefs.yaml
shortlist fetch                   # pull Greenhouse jobs for configured companies
shortlist rank                    # apply hard filter
shortlist list                    # see what survived
```

## Design

See [`docs/spec.md`](docs/spec.md) for the full design.

## Testing

```bash
pytest                                          # unit + integration
pytest -m "not browser and not live"            # explicit (CI default)
RUN_LIVE=1 pytest -m live                       # opt-in network smoke
```

## License

MIT.
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/spec.md
git commit -m "docs: README quickstart + import design spec into repo"
```

---

## Task 18: Migrate this plan into the repo

**Files:**
- Create: `docs/plans/2026-04-28-shortlist-plan-1-foundation.md` (copy of this file)

- [ ] **Step 1: Copy plan**

```bash
cp /run/media/seraph/Win1Tb/dev/repos/digitalseraph/docs/superpowers/plans/2026-04-28-shortlist-plan-1-foundation.md docs/plans/2026-04-28-shortlist-plan-1-foundation.md
```

- [ ] **Step 2: Commit**

```bash
git add docs/plans/2026-04-28-shortlist-plan-1-foundation.md
git commit -m "docs: import Plan 1 (foundation) from monorepo"
```

- [ ] **Step 3: Final verification — full local CI**

```bash
ruff check .
ruff format --check .
mypy shortlist
pytest --cov=shortlist --cov-report=term-missing --cov-fail-under=80
```

Expected: all green, coverage ≥ 80% on `shortlist/`.

- [ ] **Step 4: Push and open the GitHub repo (manual)**

User-side step:

```bash
gh repo create shortlist --private --source=. --remote=origin --push
```

---

## Done definition (Plan 1)

- `shortlist db init && shortlist config init && shortlist fetch && shortlist rank && shortlist list` end-to-end against a live Greenhouse board (e.g., a real company token added to `prefs.yaml`) prints a sorted table of matching jobs.
- All tests pass; coverage ≥ 80%.
- CI green on first push.
- Repo at `~/dev/repos/shortlist` with 18 commits, MIT license, README + spec + Plan 1 in `docs/`.

## Next plan trigger

Plan 2 begins when the user says so. Plan 2 scope: `Lever`, `Ashby`, `Workable`, `SmartRecruiters`; embeddings via `sentence-transformers` (`bge-small-en-v1.5`); Haiku rerank batch; replaces the Plan-1 placeholder scoring in `rank`.
