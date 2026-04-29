# Shortlist — Design Spec

**Date:** 2026-04-28
**Status:** draft
**Author:** David Miller
**Target repo:** standalone (`shortlist`), extracted from this monorepo on scaffold (Throughline pattern)

## 1. Purpose

Personal job-search assistant. CLI + Textual TUI. Discovers postings from ATS APIs, scraped aggregators, curated boards, and RSS feeds; ranks them against a resume + preferences file; tailors a per-job resume, cover letter, and notes file; tracks the application lifecycle. The user submits applications manually — the tool surfaces and prepares; it never auto-applies.

## 2. Scope

### In scope (v1)

- Job discovery from four source classes (ATS APIs, scraped aggregators, curated boards, RSS).
- Hard-filter + embedding pre-rank + Haiku LLM rerank.
- Sonnet-driven tailoring → Markdown + PDF output per job.
- Full application tracking: status state machine, dates, contacts, outcomes.
- Single-user, on-demand execution via Textual TUI; equivalent Typer CLI subcommands.
- SQLite + sqlite-vec local store; local sentence-transformers embeddings.

### Explicitly out of scope (v1)

- Auto-submit / form-fill (user applies manually).
- Daemon / cron / background polling.
- Notifications (email, desktop, push).
- Multi-user / multi-profile / SaaS.
- Multi-LLM-provider abstraction (Anthropic only).

## 3. Tech Stack

| Layer | Choice | Reason |
|------|--------|--------|
| Language | Python 3.12+ | LLM/embeddings/Playwright/PDF tooling |
| CLI | Typer | type-safe subcommands, Click-compatible |
| TUI | Textual | rich, modern, async |
| Store | SQLite + `sqlite-vec` | zero-setup, single file, vector search built-in |
| Embeddings | `sentence-transformers` (`bge-small-en-v1.5`) | local, free, offline |
| LLM | Anthropic Claude API (Sonnet 4.6 default, Haiku 4.5 rerank) | quality + cost mix |
| Browser | Playwright + `playwright-stealth` | aggregator scraping |
| HTTP | `httpx` | async, modern |
| PDF | `pandoc` (system) + LaTeX template | reliable MD → PDF |
| Config | Pydantic + YAML | typed, readable |
| Resilience | `tenacity` | backoff/retry |
| Test | pytest, pytest-asyncio, hypothesis, vcrpy, respx | layered |
| Lint/Type | ruff, mypy strict on `core/` | quality gate |

## 4. Architecture

```
┌─────────────────────────────────────────────────────┐
│  Textual TUI (shortlist_tui)                        │
│  thin: lists, detail, key-bindings → calls core     │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  Typer CLI (shortlist)                              │
│  fetch / rank / tailor / track / config / db        │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  shortlist core (lib)                               │
│  ┌───────────┐ ┌─────────┐ ┌────────┐ ┌──────────┐  │
│  │ sources/  │ │ ranker/ │ │tailor/ │ │ tracker/ │  │
│  │ ATS+scrap │ │ embed+  │ │ LLM +  │ │ status   │  │
│  │ +curated  │ │ Haiku   │ │ pandoc │ │ +contacts│  │
│  └─────┬─────┘ └────┬────┘ └───┬────┘ └────┬─────┘  │
│        └────────────┴──────────┴───────────┘        │
│                       │                             │
│              ┌────────▼────────┐                    │
│              │ store (SQLite + │                    │
│              │ sqlite-vec)     │                    │
│              └─────────────────┘                    │
└─────────────────────────────────────────────────────┘
              │                  │
   ┌──────────▼─────┐   ┌────────▼──────┐
   │ Anthropic API  │   │ Playwright    │
   │ (Sonnet+Haiku) │   │ (scrapers)    │
   └────────────────┘   └───────────────┘
```

**Layer rules:**

- TUI never imports HTTP/DB. Only `shortlist.core`.
- CLI never imports `shortlist_tui`.
- `core` modules talk via SQLite, no in-process pubsub.

## 5. Components

### `shortlist.config`
Loads `~/.config/shortlist/config.yaml`, `prefs.yaml`, and resume path. Anthropic API key from env or OS keyring (`keyring` package). Pydantic models with full validation on load.

`config.yaml` shape (synthetic example):

```yaml
anthropic:
  key_source: env       # or "keyring"
  key_env_var: ANTHROPIC_API_KEY
budget:
  daily_usd: 5.00
  monthly_usd: 60.00
paths:
  resume: ~/jobs/resume.md
  output_dir: ~/jobs
  pdf_template: ~/.config/shortlist/pdf-template.tex
sources:
  greenhouse: { enabled: true,  rate_limit_rpm: 30 }
  lever:      { enabled: true,  rate_limit_rpm: 30 }
  ashby:      { enabled: true,  rate_limit_rpm: 30 }
  workable:   { enabled: true,  rate_limit_rpm: 30 }
  smartrecruiters: { enabled: true,  rate_limit_rpm: 30 }
  indeed:     { enabled: false, rate_limit_rpm: 6 }   # scraped — off by default
  linkedin:   { enabled: false, rate_limit_rpm: 4 }
  glassdoor:  { enabled: false, rate_limit_rpm: 6 }
  hn_who_hiring: { enabled: true }
  wellfound:     { enabled: true }
  otta:          { enabled: true }
  remoteok:      { enabled: true }
  rss:           { enabled: true, urls: [] }
ranker:
  top_k_for_llm_rerank: 30
  embedding_model: bge-small-en-v1.5
  rerank_model: claude-haiku-4-5-20251001
tailor:
  model: claude-sonnet-4-6
  cover_paragraphs: 3
```

### `shortlist.store`
SQLite at `~/.local/share/shortlist/db.sqlite`. WAL mode. Connection-per-call. Tables: `jobs`, `sources`, `embeddings` (sqlite-vec virtual table), `applications`, `contacts`, `events`. Hand-rolled `_migrations/NNN.sql` with version table. `shortlist db backup` writes a timestamped copy.

### `shortlist.sources`
One module per source. Common base `Source` ABC with `fetch(since: datetime) -> Iterator[RawJob]`.

| Class | Modules |
|-------|---------|
| ATS APIs | `ats/greenhouse.py`, `ats/lever.py`, `ats/ashby.py`, `ats/workable.py`, `ats/smartrecruiters.py` |
| Scraped aggregators | `scraped/indeed.py`, `scraped/linkedin.py`, `scraped/glassdoor.py` |
| Curated boards | `curated/hn_who_hiring.py`, `curated/wellfound.py`, `curated/otta.py`, `curated/remoteok.py` |
| Feeds | `feeds/rss.py` (generic, configured URLs from prefs) |

ATS clients use REST + pagination + dedup by `external_id`. Scraped sources use Playwright with stealth, per-source rate limit, captcha → skip+log.

### `shortlist.ranker`

1. Hard filters from `prefs.yaml`: location, comp floor, exclusion keywords, seniority.
2. Embed JD + resume (`bge-small-en-v1.5`) → cosine similarity stored.
3. Top-K (default 30) → Haiku 4.5 rerank batch → final score 0–100 + one-line reason.
4. Persist `jobs.score`, `jobs.score_reason`.

### `shortlist.tailor`
Input: `job_id`. Sonnet 4.6 prompt receives full resume + JD + prefs. Outputs three Markdown sections written to `~/jobs/<company>-<role-slug>-<job_id_short>/`:

- `resume.md` — rewritten bullets, **system prompt forbids fabrication** (preserve facts only, reorder/rephrase only).
- `cover.md` — three-paragraph default, template configurable.
- `notes.md` — talking points, gaps vs JD, candidate questions for interviewer.

Pandoc renders both `resume.md` and `cover.md` to PDF using `~/.config/shortlist/pdf-template.tex`.

### `shortlist.tracker`
State machine:

```
new → tailored → applied → screen → interview → offer
                                              ↘ rejected
                                              ↘ withdrawn
```

`withdrawn` reachable from any state. No downgrades. Contacts CRUD bound to `application_id`. Auto-events on every transition.

### `shortlist.cli`
Typer app. Subcommands map 1:1 to core functions: `fetch`, `rank`, `tailor`, `track`, `config`, `db`, `tui`. Every subcommand returns a non-zero exit on failure with a structured error.

### `shortlist_tui`
Textual app. Screens:

- `JobList` — sortable by score / discovered_at / status; filter by source.
- `JobDetail` — JD + tailored docs preview + actions (tailor, mark applied, open URL).
- `ApplicationsBoard` — kanban-ish columns by status.
- `Settings` — view/edit config + prefs paths, source enable/disable, budget caps.

## 6. Data Flow

### Fetch
```
prefs.yaml → enabled sources → for each source:
  source.fetch(since=last_fetched_at) → RawJob iter
  → normalize → store.upsert_job() (dedup by source+external_id)
  → emit event "job.discovered"
last_fetched_at updated per-source on success only
```

### Rank
```
SELECT jobs WHERE score IS NULL OR stale_score
  → hard_filter(prefs)            # drop disqualified
  → embed_if_missing()            # local model
  → cosine vs resume_embedding    # cached, recomputed only when resume.md mtime changes
  → top_K → Haiku rerank batch    # 0-100 + reason
  → store.update_scores()
```

`stale_score` = score predates the current `prefs.yaml` mtime OR `score_model_version` mismatch. Persisted as `jobs.scored_with_prefs_at` and `jobs.scored_with_model`.

### Tailor
```
load(job, resume, prefs)
  → Sonnet prompt (system: no fabrication, factual delta only)
  → parse 3 sections (resume/cover/notes)
  → write MD to ~/jobs/<dir>/
  → pandoc → PDF
  → store.set_status("tailored")
  → store.event("tailored", cost_usd, tokens)
```

### Track
```
state-machine validate transition
  → store.update_status + event
  → if status="applied": prompt for notes/contacts
```

### Schema sketch

All timestamp columns store ISO-8601 UTC strings (e.g., `2026-04-28T13:45:00Z`).

```sql
jobs(id, source, external_id UNIQUE, company, title, location, remote,
     comp_min, comp_max, url, description_md, posted_at, discovered_at,
     score, score_reason, status, status_changed_at);

embeddings(job_id, vector)  -- sqlite-vec virtual table

applications(job_id, applied_at, applied_via, follow_up_due, salary_offered,
             decision, decision_reason, lessons);

contacts(id, application_id, name, email, role, source);

events(id, job_id, type, payload_json, cost_usd, tokens, created_at);

sources(name, last_fetched_at, last_error, cooldown_until, enabled);
```

## 7. Error Handling

### Source failures
- Per-source try/except; one source's failure never blocks others.
- Exponential backoff via `tenacity`: 3 retries, 2/4/8s with jitter.
- HTTP 429 → respect `Retry-After`, mark source `cooldown_until`.
- Captcha or auth wall → mark `last_error`, skip rest of run, surface in TUI banner.
- Partial success: persist what came through; advance `last_fetched_at` only on a clean run (no silent gaps).

### Playwright (scraped)
- Headless with `playwright-stealth`.
- Per-source rate limit from config (`requests_per_minute`).
- 30s page timeout → kill + log.
- IP-ban heuristic (403 streak ≥ N) → disable source for 24h, TUI warns.

### LLM
- `anthropic.RateLimitError` → backoff + retry (max 5).
- Schema parse failure (tailor expects 3 sections) → 1 retry with corrective prompt → if still bad, save raw output + flag, never silently skip.
- Cost cap: per-run + monthly (`budget.daily_usd`, `budget.monthly_usd`); refuses to start if exceeded; TUI shows used/cap.

### Store
- Schema migrations idempotent, version-tracked.
- All writes in transactions; FKs enforced.
- `shortlist db backup` → timestamped copy in `~/.local/share/shortlist/backups/`.

### State-machine guards
- Invalid transition raises `InvalidStatusError`; TUI shows allowed next states.
- No status downgrades except `withdrawn` from any state.

### No-silent-fail rule
Every except block either re-raises, logs at WARN+, persists an error to `events`, **or** surfaces to the TUI banner. `logging` configured to write to `~/.local/state/shortlist/shortlist.log` (rotating, 10MB × 5).

## 8. Testing

**Coverage target:** 80% per repo standard. Ranker, tailor parser, and state machine ≥ 95%.

### Unit (fast, no I/O)
- `config` — pydantic validation, env-precedence, missing-key cases.
- `ranker.hard_filter` — hypothesis: random jobs vs prefs; exclusion logic.
- `ranker.cosine` — golden vectors → known scores.
- `tailor.parse` — fixture LLM outputs → 3-section split, malformed retry path.
- `tracker` — every transition (valid + invalid).
- `store` migrations — apply N times → idempotent.

### Integration (SQLite real, network mocked)
- `sources/ats/*` — vcrpy cassettes per source with pagination, dedup verifies.
- `sources/scraped/*` — saved HTML fixture → parser asserts. Playwright NOT in CI; mark `@pytest.mark.browser`, opt-in local.
- `store` — upsert + dedup, embeddings round-trip, FTS search.
- LLM — `respx` mocks Anthropic API. One live smoke test gated by `RUN_LIVE=1`.

### E2E
- Typer: `CliRunner` per subcommand happy + error path.
- Textual: `Pilot` driver — load app, simulate keys, snapshot terminal output.
- Full pipeline: fixture sources → fetch → rank (mocked LLM) → tailor (mocked LLM) → assert files written + DB state.

### Fixtures
- `tests/fixtures/jobs/*.json` — normalized RawJob samples per source.
- `tests/fixtures/cassettes/` — vcrpy.
- `tests/fixtures/resume.md` + `prefs.yaml` — known inputs.
- `tests/fixtures/llm_responses/` — canned Sonnet/Haiku outputs.

### CI
GitHub Actions, py3.12, ruff, mypy strict (`core/`), pytest, coverage gate. `ANTHROPIC_API_KEY` unset in CI; tests fail loud if any code path attempts a live call.

## 9. Risks

| Risk | Mitigation |
|------|------------|
| Aggregator scrapers (LinkedIn especially) detect Playwright and IP-ban | Stealth plugin, per-source rate limits, 24h auto-cooldown on detection, scraped sources disabled by default in shipped config |
| LLM cost runaway on tailoring | Hard daily + monthly budget caps that refuse to start; cost shown in TUI before each run |
| Local embeddings model adds ~500MB torch + model download | First-run download with progress bar; documented; can be swapped for hosted embeddings later if painful |
| Resume hallucination | System-prompt fabrication prohibition + diff view in TUI before user marks "applied" |
| sqlite-vec is a young extension | Pin version; abstract embedding queries behind `store.embeddings.search()` so a future swap to FAISS or pgvector is local |

## 10. Repo Layout (target)

```
shortlist/
├── README.md
├── pyproject.toml
├── shortlist/
│   ├── __init__.py
│   ├── config.py
│   ├── store/
│   │   ├── __init__.py
│   │   └── _migrations/
│   ├── sources/
│   │   ├── base.py
│   │   ├── ats/
│   │   ├── scraped/
│   │   ├── curated/
│   │   └── feeds/
│   ├── ranker/
│   ├── tailor/
│   ├── tracker/
│   └── cli.py
├── shortlist_tui/
│   ├── __init__.py
│   ├── app.py
│   └── screens/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
├── docs/
│   └── plan.md          # implementation plan goes here per repo workflow
└── .github/workflows/ci.yml
```

## 11. Open questions for plan stage

- Source-by-source build order (ATS first → easiest? or one source per layer first to validate end-to-end?).
- Whether to ship a default `prefs.yaml` template or start blank.
- Initial set of HN Who's Hiring / Wellfound parsing depth (full text vs metadata only).
