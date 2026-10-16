# Architecture

Shortlist is a single-user, on-demand CLI + TUI tool. Everything runs locally; the only external
calls are to ATS/job-board APIs (public, no auth) and the Anthropic API (Haiku for ranking,
Sonnet for tailoring). The SQLite database, embeddings, and output files live on your machine.

---

## ASCII architecture diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  shortlist_tui  (Textual)                                        │
│  JobListScreen · JobDetailScreen · ApplicationsBoardScreen       │
│  SettingsScreen · workers.py (background threads)                │
└────────────────────────────┬─────────────────────────────────────┘
                             │  calls shortlist.* via workers
┌────────────────────────────▼─────────────────────────────────────┐
│  shortlist.cli  (Typer)                                          │
│  db · config · fetch · rank · list · tailor · track             │
│  contacts · sources                                              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
          ┌──────────────────┼───────────────────────┐
          │                  │                       │
┌─────────▼───────┐ ┌────────▼────────┐ ┌───────────▼──────────┐
│ shortlist.      │ │ shortlist.      │ │ shortlist.           │
│ sources/        │ │ ranker/         │ │ tailor/              │
│                 │ │                 │ │                      │
│ ats/            │ │ hard_filter.py  │ │ sonnet.py  (Sonnet)  │
│  greenhouse.py  │ │ embeddings.py   │ │ orchestrator.py      │
│  lever.py       │ │ llm_rerank.py   │ │ parser.py            │
│  ashby.py       │ │  (Haiku)        │ │ pdf.py  (pandoc)     │
│  workable.py    │ │ pipeline.py     │ │ prompt.py            │
│  smartrec.py    │ └────────┬────────┘ └───────────┬──────────┘
│ scraped/        │          │                      │
│  _browser.py ◄──┼──────────┼──  shared Playwright │
│  indeed.py      │          │    launch helper     │
│  linkedin.py    │          │                      │
│  glassdoor.py   │          │                      │
│  wellfound.py   │          │                      │
│  otta.py        │          │                      │
│ curated/        │          │                      │
│  hn_who_hiring  │          │                      │
│  remoteok.py    │          │                      │
│ feeds/          │          │                      │
│  rss.py         │          │                      │
│ base.py         │          │                      │
└─────────┬───────┘          │                      │
          │                  │                      │
          └──────────────────┴──────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │ shortlist.store             │
              │  db.py  (connect · migrate  │
              │  · upsert · query helpers)  │
              │  _migrations/               │
              │   001_initial.sql           │
              │   002_embeddings.sql        │
              │   003_applications.sql      │
              └──────────────┬──────────────┘
                             │
                 ┌───────────▼───────────┐
                 │ SQLite + sqlite-vec   │
                 │ ~/.local/share/       │
                 │ shortlist/db.sqlite   │
                 └───────────────────────┘

External:   Anthropic API (Sonnet 4.6 + Haiku 4.5)
            ATS APIs (Greenhouse, Lever, Ashby, Workable, SmartRecruiters)
            Job boards (HN Algolia API, RemoteOK JSON, RSS/Atom feeds)
            Playwright → Chromium (scraped sources only)
```

---

## Layer rules

These constraints are enforced by import discipline and mypy strict mode:

- `shortlist_tui` never imports HTTP clients or DB code directly. It calls `shortlist.*`
  through background workers (`workers.py`).
- `shortlist.cli` never imports `shortlist_tui`.
- `shortlist.sources`, `shortlist.ranker`, `shortlist.tailor`, and `shortlist.tracker` talk to
  each other only through the SQLite store — no in-process pub/sub or shared state.
- `shortlist.store.db` is the sole module that opens SQLite connections. All connections use the
  `connect()` context manager, which commits on success and rolls back on exception, then closes.

---

## Profiles and directory layout

Shortlist supports more than one person per installation. A profile straddles the same two
roots everything else uses - config is settings, data is state - under a `profiles/<slug>/`
subtree in each:

```
~/.config/shortlist/
  config.yaml                 # shared: Anthropic key, model names, budget
  pdf-template.tex            # shared: tailor PDF template
  state.yaml                  # which profile slug was used last
  profiles/
    david/
      prefs.yaml               # per-profile: source queries, filters
    alex/
      prefs.yaml

~/.local/share/shortlist/
  profiles/
    david/
      profile.yaml              # display name
      db.sqlite                 # jobs, scores, applications, cost history
      resume.md                 # extracted resume text used for ranking/tailoring
      resume.original           # the uploaded file as received (pdf/docx/md)
      output/                   # tailored resume/cover/notes per job
    alex/
      profile.yaml
      db.sqlite
      resume.md
      resume.original
      output/
```

There is no separate registry file - the directory listing under `data_dir/profiles/` *is*
the registry, and `profile.yaml` existing there is what makes a slug "a profile" to `load()`
and `list_profiles()`. `profiles.create()` builds both trees, seeds `prefs.yaml`, and runs a
fresh `migrate()` against the new `db.sqlite`; `profiles.delete()` removes both trees -
including the database and its cost history - with no undo.

`profiles.resolve()` is the single place that picks "which person": explicit argument →
`SHORTLIST_PROFILE` env var → the only profile if there is exactly one → `state.yaml`'s
last-used slug → otherwise it raises, listing the available slugs rather than guessing. Every
CLI data command and the TUI's `__init__` call through it (via `cli._resolve`, which turns the
exception into a clean exit).

The web layer scopes every page under `/p/{slug}/...`, resolved per request by a FastAPI
dependency (`profile_dep`) that 404s on an unknown or malformed slug rather than falling back
to someone else's data. A handful of pre-multi-person bare paths (`/`, `/applications`,
`/costs`, `/settings`, `/resume`) still resolve via middleware to the active profile's
`/p/{slug}/...` equivalent, so old bookmarks keep working.

---

## Module index

### `shortlist/`

| Module | Purpose |
|--------|---------|
| `cli.py` | Typer app and all CLI subcommands |
| `config.py` | Pydantic models for `config.yaml` and `prefs.yaml`; `load_config`, `load_prefs` |
| `models.py` | `RawJob`, `Job`, `Application`, `Contact`, `JobStatus` Literal |
| `paths.py` | XDG-compliant roots - `config_dir()`, `data_dir()`, `config_path()` |
| `profiles.py` | `Profile` dataclass; `create`/`load`/`list_profiles`/`delete`/`resolve` |
| `state.py` | Cross-run state outside config - which profile slug was last used |

### `shortlist/store/`

| Module | Purpose |
|--------|---------|
| `db.py` | `connect()` context manager; all DB query helpers (upsert, list, score, track, embed) |
| `_migrations/001_initial.sql` | `jobs`, `sources`, `events` tables and indexes |
| `_migrations/002_embeddings.sql` | `job_embeddings` (sqlite-vec virtual), `resume_embeddings`, `scoring_runs` |
| `_migrations/003_applications.sql` | `applications`, `contacts`, `tailor_outputs` |

### `shortlist/sources/`

| Module | Purpose |
|--------|---------|
| `base.py` | `Source` abstract base class — `fetch(since) -> Iterator[RawJob]` |
| `_browser.py` | Shared Playwright browser launch helper used by all scraped sources |
| `ats/greenhouse.py` | Greenhouse ATS REST API client |
| `ats/lever.py` | Lever ATS REST API client |
| `ats/ashby.py` | Ashby ATS REST API client |
| `ats/workable.py` | Workable ATS REST API client |
| `ats/smartrecruiters.py` | SmartRecruiters ATS REST API client |
| `scraped/indeed.py` | Indeed scraper via Playwright (disabled by default) |
| `scraped/linkedin.py` | LinkedIn scraper via Playwright (disabled by default) |
| `scraped/glassdoor.py` | Glassdoor scraper via Playwright (disabled by default) |
| `scraped/wellfound.py` | Wellfound scraper via Playwright |
| `scraped/otta.py` | Otta scraper via Playwright |
| `curated/hn_who_hiring.py` | HN "Who is Hiring?" via Algolia search API |
| `curated/remoteok.py` | RemoteOK public JSON API |
| `feeds/rss.py` | Generic RSS/Atom feed reader via `feedparser` |

### `shortlist/ranker/`

| Module | Purpose |
|--------|---------|
| `hard_filter.py` | `passes(job, prefs) -> bool` — location, comp, keyword, seniority gates |
| `embeddings.py` | `EmbeddingService` wrapping `sentence-transformers`; `embed_resume_cached` |
| `llm_rerank.py` | `LLMReranker` — batches candidates to Haiku; parses scored JSON response |
| `pipeline.py` | `run_pipeline()` — orchestrates all three stages end-to-end |

### `shortlist/tailor/`

| Module | Purpose |
|--------|---------|
| `sonnet.py` | `SonnetTailorClient` — builds prompt and calls Sonnet 4.6 |
| `prompt.py` | System and user prompt templates (no-fabrication constraint) |
| `parser.py` | Parses the three-section `resume/cover/notes` response from the model |
| `pdf.py` | `render_md_to_pdf()` — subprocess wrapper for pandoc + LaTeX |
| `orchestrator.py` | `TailorOrchestrator.tailor()` — load → LLM → write → PDF → record |

### `shortlist/tracker/`

| Module | Purpose |
|--------|---------|
| `state.py` | `JobStatus` state machine, `validate_transition()`, `allowed_next()` |

### `shortlist_tui/`

| Module | Purpose |
|--------|---------|
| `app.py` | `ShortlistApp` — root Textual app, global key bindings, screen stack |
| `data.py` | `list_job_rows()` — thin DB read for the UI, returns `JobRow` dataclasses |
| `workers.py` | Thread workers: `fetch_all`, `rank_all`, `tailor_one` |
| `screens/job_list.py` | `JobListScreen` — sortable table, live search filter |
| `screens/job_detail.py` | `JobDetailScreen` — full description and action buttons |
| `screens/applications.py` | `ApplicationsBoardScreen` — jobs grouped by status |
| `screens/settings.py` | `SettingsScreen` — config and prefs display |

---

## Data flow walkthroughs

### Fetch

```
prefs.yaml → enabled sources → for each source (concurrent, per-source rate limit):
  source.fetch(since=last_fetched_at) → Iterator[RawJob]
    → store_db.upsert_job()              # dedup by (source, external_id)
  → store_db.mark_source_fetched()       # update last_fetched_at on success
  scraped source: ban detected
    → store_db.mark_source_cooldown(name, until=now+24h)
    → skip without blocking other sources
```

### Rank

```
store_db.list_jobs()
  → hard_filter.passes(job, prefs)         # Stage 1: discard non-matches → score=0
  → embed_resume_cached(db, resume_path)   # cache keyed by path + mtime
  → for each survivor: embedder.encode(jd) # embed job descriptions
  → store_db.cosine_top_k(resume_vec, k=30)# ANN via sqlite-vec → top-K
  → LLMReranker.rerank(top_jobs)           # Stage 3: Haiku batch → 0-100 + reason
  → store_db.update_score() per job
  → INSERT INTO scoring_runs (cost_usd, tokens_in, tokens_out)
```

### Tailor

```
store_db.list_jobs() → find job by job_id
  → SonnetTailorClient.tailor(resume, prefs_summary, job)   # Sonnet 4.6
  → parser.parse(response) → {resume_md, cover_md, notes_md}
  → write three .md files to output_dir/<company-role-id>/
  → pdf.render_md_to_pdf() for resume + cover (best-effort; skipped if pandoc missing)
  → store_db.transition_status(job_id, "tailored")
  → store_db.log_event("tailor.complete", cost_usd, tokens)
  → INSERT INTO tailor_outputs (job_id, output_dir, cost_usd, tokens)
```

---

## Schema summary

All timestamp columns store ISO-8601 UTC strings (e.g., `2026-04-28T13:45:00Z`).

**Migration 001 — initial schema:**
- `jobs` — core posting fields (`source`, `external_id`, `company`, `title`, `url`,
  `posted_at`, `location`, `remote`, `comp_min`, `comp_max`, `description_md`) plus scoring
  columns (`score`, `score_reason`, `scored_with_model`) and status columns (`status`,
  `status_changed_at`). Unique on `(source, external_id)`.
- `sources` — per-source state: `last_fetched_at`, `last_error`, `cooldown_until`, `enabled`.
- `events` — append-only log: `job_id`, `type`, `payload_json`, `cost_usd`, `tokens`,
  `created_at`. Used for cost accounting and audit.

**Migration 002 — embeddings:**
- `job_embeddings` — sqlite-vec virtual table; 384-dim float32 vectors keyed by `job_id`.
- `resume_embeddings` — cache keyed by `(path, mtime, model)`; avoids re-embedding an
  unchanged resume on every run.
- `scoring_runs` — aggregate record per `rank` invocation: model, job count, total cost,
  token counts, start/finish timestamps.

**Migration 003 — applications:**
- `applications` — one row per applied job: `applied_at`, `applied_via`, `follow_up_due`,
  `salary_offered`, `decision`, `decision_reason`, `lessons`.
- `contacts` — people tied to an application: `name`, `email`, `role`, `source`.
- `tailor_outputs` — output directory, render timestamp, cost, and token counts per tailor call.

---

## Testing pyramid

| Tier | Marker | Approx count | What it covers |
|------|--------|-------------|----------------|
| Unit | (none) | ~120 | Models, hard filter, parser, state machine, embeddings mock |
| Integration | (none) | ~40 | DB round-trips, pipeline with mock LLM, tailor with mock Sonnet |
| Browser | `browser` | 5 | Playwright smoke against real sites (deselected from default run) |
| Live network | `live` | 5 | Real ATS API calls, gated by `RUN_LIVE=1` env var |

Default CI command: `pytest -m "not browser and not live"` → 292 passed, 1 skipped.

Coverage: 82% total. Minimum required: 80%.

---

## Extension points

### Add a new ATS source

1. Create `shortlist/sources/ats/<name>.py`; subclass `Source` from `sources/base.py`.
2. Implement `fetch(since: datetime) -> Iterator[RawJob]` using `httpx` with pagination.
3. Register in `shortlist/cli.py` alongside other ATS imports and in the `fetch` command loop.
4. Add `<name>_companies: []` to `Prefs` in `shortlist/config.py` and the prefs YAML template.
5. Write unit tests with `respx` mocking HTTP responses.

### Add a scraped source

1. Create `shortlist/sources/scraped/<name>.py`; use `_browser.py`'s shared launch helper.
2. Raise a `<Name>BanDetectedError` on CAPTCHA or block detection.
3. Handle the error in the CLI `fetch` loop by calling
   `store_db.mark_source_cooldown(name, until=now + timedelta(hours=24))`.
4. Default `enabled: false` in the config template — scraped sources are always opt-in.

### Add a curated or RSS source

Copy `curated/hn_who_hiring.py` (simple `httpx` GET + JSON parse, ~80 lines) or `feeds/rss.py`
(`feedparser` wrapper, ~60 lines) as a starting point.

### Add a migration

1. Create `shortlist/store/_migrations/004_<description>.sql`.
2. `migrate()` in `db.py` discovers new `.sql` files by lexical order and applies them
   automatically on next `shortlist db init`.
3. Use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` to keep migrations
   idempotent.
