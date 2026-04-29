# Changelog

## [0.1.0] - 2026-04-29

First feature-complete release. Implements the full Shortlist spec across
six task plans:

### Added
- **Plan 1 — Foundation:** Greenhouse public-board ingestion, SQLite store
  with versioned migrations, hard-filter ranking against `prefs.yaml`,
  Typer CLI with `db`, `config`, `fetch`, `rank`, `list` commands.
- **Plan 2 — ATS expansion + LLM rerank:** Lever, Ashby, Workable,
  SmartRecruiters ATS sources. Local embeddings via
  `sentence-transformers` (`bge-small-en-v1.5`) + `sqlite-vec`. Anthropic
  Haiku 4.5 rerank with budget tracking.
- **Plan 3 — Tailoring + Tracker:** Sonnet 4.6 per-job resume + cover
  letter + interview notes generation with no-fabrication system prompt.
  Pandoc → PDF rendering with bundled LaTeX template. Application
  lifecycle state machine. Contacts CRUD.
- **Plan 4 — Textual TUI:** Four screens (JobList, JobDetail,
  ApplicationsBoard, Settings) with vim-style key bindings, live search
  filter, background workers for fetch/rank/tailor.
- **Plan 5 — Scraped aggregators:** Indeed, LinkedIn, Glassdoor via
  Playwright with stealth init script and 24h auto-cooldown on ban
  detection. Disabled by default.
- **Plan 6 — Curated boards + RSS + Release (this):** HN "Who is hiring?"
  via Algolia API, RemoteOK via REST, Wellfound + Otta via Playwright,
  generic RSS feeds via `feedparser`. Tag-driven GitHub Release workflow.

### Notes
- ATS APIs (Plans 1+2) are the recommended primary path. Scraped sources
  (Plan 5, plus Wellfound/Otta from this release) are best-effort and
  ship disabled by default.
- PDF rendering requires `pandoc` + `pdflatex` (TeX Live with LaTeX
  format files) on PATH. MD output works without them.
- Anthropic API key required for `rank` (Haiku) and `tailor` (Sonnet).
  Use `--no-llm` for embedding-only ranking at $0 cost.
