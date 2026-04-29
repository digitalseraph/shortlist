---
marp: true
theme: default
paginate: true
---

# Shortlist
## A personal job-search assistant

David Miller · 2026

---

# Why

- Job search is friction-heavy, repetitive, and attention-poor
- ATS sites expose public JSON APIs — almost nobody uses them well
- Copy-pasting your resume into every application wastes hours
- Per-job tailoring is highest-ROI, yet most often skipped
- LLMs make per-job tailoring affordable at last

**Goal:** a single local tool, runs on your machine, no SaaS lock-in

---

# What it does

1. **Fetch** — ingests jobs from 13 sources (ATS APIs, scraped boards, curated, RSS)
2. **Rank** — scores each job against your resume + preferences (cosine + Haiku LLM)
3. **Tailor** — generates a per-job resume, cover letter, and notes via Sonnet
4. **Track** — follows each application through a state machine lifecycle
5. **Browse** — Textual TUI with vim bindings, live search, kanban board

You apply manually. Shortlist surfaces and prepares — it never auto-submits.

---

# Architecture

```
shortlist_tui  (Textual — 4 screens, background workers)
      |
shortlist.cli  (Typer — fetch / rank / tailor / track / tui)
      |
  +---+----------------------------+
  |           |                   |
sources/   ranker/             tailor/
  |        hard_filter          Sonnet 4.6
  |        bge-small embed      pandoc -> PDF
  |        Haiku 4.5 rerank
  |           |                   |
  +------- store/ ----------------+
       SQLite + sqlite-vec
       ~/.local/share/shortlist/db.sqlite

External: Anthropic API + ATS public APIs + Playwright (scrapers only)
```

---

# Sources: ATS APIs (5)

Public REST APIs — no scraping risk, no credentials needed

| Source | API style |
|--------|-----------|
| Greenhouse | REST — `/v1/boards/{company}/jobs` |
| Lever | REST — `/v1/postings/{company}` |
| Ashby | GraphQL job board endpoint |
| Workable | REST — `/spi/v3/jobs` |
| SmartRecruiters | REST — `/v1/companies/{id}/postings` |

Configure by adding company slugs to `prefs.yaml`:

```yaml
greenhouse_companies: [acme, globex, initech]
lever_companies: [umbrella-corp]
```

---

# Sources: scraped boards (5)

Playwright + Chromium — higher yield, higher risk

| Source | Default | Risk |
|--------|---------|------|
| Indeed | **disabled** | Aggressive bot detection |
| LinkedIn | **disabled** | Aggressive bot detection |
| Glassdoor | **disabled** | Aggressive bot detection |
| Wellfound | enabled | Moderate |
| Otta | enabled | Moderate |

Ban detected → 24 h auto-cooldown recorded in DB.
`shortlist sources clear-cooldown indeed` to unblock manually.

---

# Sources: curated + RSS (3)

Low risk, high signal

| Source | Type | Mechanism |
|--------|------|-----------|
| HN Who is Hiring? | Curated | Algolia search on monthly thread |
| RemoteOK | Curated | Public JSON API, no auth |
| RSS feeds | RSS/Atom | Any careers feed via `feedparser` |

```yaml
# prefs.yaml
hn_enabled: true
remoteok_enabled: true
rss_urls:
  - https://jobs.acme.com/feed.xml
```

---

# Ranking pipeline

Three stages, increasing cost:

```
All jobs in DB
   |
   v  Stage 1: Hard filter  (free)
   location / comp floor / exclude keywords / seniority
   |
   v  Stage 2: Cosine similarity  (free, local model)
   bge-small-en-v1.5 -> 384-dim embeddings
   sqlite-vec ANN query -> top 30 nearest to resume
   |
   v  Stage 3: Haiku 4.5 rerank  (~$0.01-0.05 / run)
   batch: title + company + first 1000 chars JD
   -> score 0-100 + one-line reason per job
```

`shortlist rank --no-llm` stops after Stage 2.

---

# Tailoring with Sonnet

```bash
shortlist tailor 42
```

Sonnet 4.6 receives: full resume + job description + preferences

Output written to `~/jobs/acme-corp-senior-backend-engineer-42/`:

```
resume.md   <- bullets reordered to match the JD
cover.md    <- 3-paragraph cover letter
notes.md    <- talking points, gaps, questions to ask
resume.pdf
cover.pdf
```

**System prompt constraint:** no fabrication — every bullet must trace
back to the original resume. Only ordering and phrasing may change.

Cost: **$0.10–0.30** per call.

---

# Application tracker state machine

```
new --> tailored --> applied --> screen --> interview --> offer
                                                     \-> rejected
withdrawn  (reachable from any non-terminal state)
```

```bash
shortlist track 42 --status applied --applied-via "company website"
shortlist contacts add 42 --name "Jane Doe" --role recruiter
shortlist track 42 --status screen
shortlist track 42 --status offer
```

Every transition logged to `events` table with timestamp and payload.

---

# Textual TUI

```bash
shortlist tui
```

[screenshot placeholder — run with sample data to capture]

**Job List** — score-ranked table, live `/` filter by company or title
**Job Detail** — full description, `o` opens URL in browser
**Applications Board** — kanban columns by status
**Settings** — config + prefs path display, source enable/disable

Fetch, rank, and tailor all run in background threads with notifications.

---

# Cost: a typical active-search day

| Operation | Model | Cost |
|-----------|-------|------|
| `fetch` | none | $0.00 |
| `rank --no-llm` | none | $0.00 |
| `rank` (full LLM pass, weekly) | Haiku 4.5 | ~$0.03 |
| `tailor` x 2 | Sonnet 4.6 | ~$0.35 |
| **Daily total** | | **~$0.35–1.00** |

Hard caps enforced before every API call:

```yaml
budget:
  daily_usd: 2.00
  monthly_usd: 30.00
```

---

# Privacy

- **Database:** `~/.local/share/shortlist/db.sqlite` — local only
- **Embeddings:** `bge-small-en-v1.5` runs locally via `sentence-transformers`
- **Output files:** `~/jobs/<slug>/` — local only
- **What leaves the machine:** resume + job description sent to Anthropic API

No job-board accounts required. No SaaS storage. No telemetry.

`--no-llm` path runs entirely offline.

---

# Tech stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.12+ |
| CLI | Typer |
| TUI | Textual |
| Store | SQLite + sqlite-vec |
| Embeddings | sentence-transformers (bge-small-en-v1.5, local) |
| LLM | Anthropic — Sonnet 4.6 (tailor), Haiku 4.5 (rerank) |
| Browser | Playwright + Chromium |
| HTTP | httpx + tenacity (3x retry, exponential backoff) |
| PDF | pandoc + LaTeX |
| Config | Pydantic v2 + YAML |
| Test | pytest, respx, hypothesis, pytest-asyncio |
| Lint/type | ruff, mypy strict |

---

# Build process

6 plans, executed sequentially with test-driven development:

| Plan | What shipped |
|------|-------------|
| 1 | Greenhouse + SQLite + hard filter + CLI skeleton |
| 2 | 4 more ATS sources + embeddings + Haiku rerank |
| 3 | Sonnet tailoring + pandoc PDF + state machine + contacts |
| 4 | Textual TUI — 4 screens + vim bindings + background workers |
| 5 | Scraped aggregators (Indeed/LinkedIn/Glassdoor) + 24 h cooldown |
| 6 | HN + RemoteOK + Wellfound + Otta + RSS + GitHub Release |

---

# What's not in v0.1.0 — by design

- **No auto-apply** — automated submissions violate most ToS; human review produces better outcomes
- **No daemon / background polling** — on-demand only
- **No notifications** — no email, push, or desktop alerts
- **No multi-user / SaaS** — single user, single machine
- **No multi-LLM-provider abstraction** — Anthropic only for now

These are scope decisions, not gaps.

---

# What's next

- **PyPI publish** — `pip install shortlist` (name availability check pending)
- **Source maintenance** — scraped selectors need periodic updates as sites change markup
- **Resume versioning** — record which resume version was used per tailor call
- **Follow-up reminders** — surface applications where `follow_up_due` has passed
- **Export** — CSV / JSON dump of full job + application history

---

# Demo

[live demo or recording placeholder]

```bash
# Golden path in ~60 seconds
shortlist fetch
shortlist rank --no-llm
shortlist list
shortlist tailor <top_id>
shortlist tui
```

---

# Code stats

| Metric | Value |
|--------|-------|
| Commits | 78 |
| Tests | 159 passing, 1 skipped, 10 deselected |
| Coverage | 82.96% |
| Modules | 28 |
| DB migrations | 3 |
| Sources | 13 |
| Lines (excl. tests) | ~3 200 |

---

# Links

| Resource | Location |
|----------|----------|
| GitHub | `github.com/digitalseraph/shortlist` |
| Tutorial | `docs/tutorial.md` |
| Architecture | `docs/architecture.md` |
| Troubleshooting | `docs/troubleshooting.md` |
| Design spec | `docs/spec.md` |

---

# Q&A

**David Miller**
`davidmiller.avatar@gmail.com`
`github.com/digitalseraph`
