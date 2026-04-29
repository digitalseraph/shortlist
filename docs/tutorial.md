# Tutorial: Zero to Tailored Job in One Session

By the end of this walkthrough you will have:

- Fetched ranked jobs from five ATS providers plus HN Who is Hiring? and RemoteOK
- Reviewed the top matches in the Textual TUI
- Generated a tailored resume, cover letter, and notes PDF for your top match
- Logged the application and added a recruiter contact

The whole thing costs under $0.50 in API fees on a typical run.

---

## 1. What you'll build

A local job-search pipeline that runs entirely on your machine. External calls are limited to:

- ATS APIs and curated job boards (public, no auth required)
- Anthropic API (Haiku for ranking, Sonnet for tailoring)

Everything else — the database, embeddings, and output files — stays local. No SaaS account,
no job-board login, no subscription.

---

## 2. Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.12+ | 3.14 also works |
| Anthropic API key | `sk-ant-...` from console.anthropic.com |
| `pandoc` + `pdflatex` | PDF rendering (optional — Markdown still works without it) |
| `git` | To clone the repo |

Install system deps on Arch / CachyOS:

```bash
sudo pacman -S pandoc texlive-core texlive-latex
```

On macOS:

```bash
brew install pandoc basictex
```

Without pandoc/pdflatex, `shortlist tailor` still writes Markdown — only the PDF render step is
skipped with a warning. See [troubleshooting.md](troubleshooting.md) for PDF error details.

---

## 3. Install

```bash
git clone https://github.com/digitalseraph/shortlist
cd shortlist
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium   # only needed for scraped sources (Indeed/LinkedIn/Glassdoor)
```

Verify:

```bash
shortlist --help
# Usage: shortlist [OPTIONS] COMMAND [ARGS]...
#   Shortlist — personal job search.
```

The first time `shortlist rank` runs it will download the embedding model
(`bge-small-en-v1.5`, ~90 MB) to `~/.cache/`. This is a one-time download.

---

## 4. Configure

Initialize the database and write default config files:

```bash
shortlist db init
# ok db at /home/you/.local/share/shortlist/db.sqlite

shortlist config init
# wrote /home/you/.config/shortlist/config.yaml
# wrote /home/you/.config/shortlist/prefs.yaml
```

### config.yaml — the machine config

Open `~/.config/shortlist/config.yaml`. Defaults are sensible; change these sections:

```yaml
anthropic:
  key_source: env           # reads ANTHROPIC_API_KEY from the shell environment
  key_env_var: ANTHROPIC_API_KEY

budget:
  daily_usd: 5.00           # hard cap on LLM spend per calendar day (UTC)
  monthly_usd: 60.00        # hard cap per month

paths:
  resume: ~/jobs/resume.md  # your Markdown resume — source of truth for tailoring
  output_dir: ~/jobs        # tailored output lands here as ~/jobs/<company-role-id>/

sources:
  greenhouse:      { enabled: true,  rate_limit_rpm: 30 }
  lever:           { enabled: true,  rate_limit_rpm: 30 }
  ashby:           { enabled: true,  rate_limit_rpm: 30 }
  workable:        { enabled: true,  rate_limit_rpm: 30 }
  smartrecruiters: { enabled: true,  rate_limit_rpm: 30 }
  indeed:          { enabled: false }   # scraped — leave disabled until you opt in
  linkedin:        { enabled: false }
  glassdoor:       { enabled: false }
  hn_who_hiring:   { enabled: true }
  remoteok:        { enabled: true }
  wellfound:       { enabled: true }
  otta:            { enabled: true }
  rss:             { enabled: true, urls: [] }

ranker:
  top_k_for_llm_rerank: 30           # how many cosine candidates go to Haiku
  embedding_model: bge-small-en-v1.5
  rerank_model: claude-haiku-4-5-20251001

tailor:
  model: claude-sonnet-4-6
  cover_paragraphs: 3
```

### prefs.yaml — what you're looking for

Open `~/.config/shortlist/prefs.yaml` and fill in your actual preferences:

```yaml
titles:
  - "Senior Backend Engineer"
  - "Staff Engineer"
  - "Platform Engineer"

locations:
  - "Atlanta, GA"
  - "Remote"

remote_ok: true

comp_floor_usd: 140000      # hard minimum — jobs below this are filtered out entirely

exclude_keywords:
  - "PHP"
  - "Sales"
  - "Blockchain"

seniority:
  - "senior"
  - "staff"
  - "principal"

# ATS companies to watch (one slug per line).
# The slug is the company subdomain on each platform.
# Example: https://boards.greenhouse.io/acme → slug is "acme"
greenhouse_companies:
  - acme
  - globex
  - initech

lever_companies:
  - umbrella-corp

ashby_companies:
  - capsule-corp

workable_companies: []
smartrecruiters_companies: []

# Curated sources — flip to true to enable
hn_enabled: true
remoteok_enabled: true

# Company career page RSS feeds
rss_urls:
  - https://jobs.acme.com/feed.xml
```

The `*_companies` lists tell each ATS source which job boards to poll. Find your target
companies' slugs by visiting their careers page and reading the subdomain in the URL
(e.g., `https://boards.greenhouse.io/acme` → slug `acme`).

---

## 5. Write your resume

Shortlist uses a Markdown resume as its source of truth. Sonnet reads it verbatim and rewrites
bullets to align with each job description — but the system prompt explicitly forbids fabrication.
Only facts already present in your resume may appear in the output.

Create `~/jobs/resume.md`. Below is a synthetic example:

```markdown
# David Miller
david@example.com | github.com/dmiller | Atlanta, GA

## Summary

Backend engineer with 10 years building distributed systems at scale.
Specialties: Python, PostgreSQL, Kafka, Kubernetes. Led platform teams of 4–8.

## Experience

### Senior Backend Engineer — Initech Corp (2021 – present)
- Redesigned the data ingestion pipeline in Python + Kafka; cut P99 latency from 4 s to 380 ms
- Migrated PostgreSQL 13 → 16 with zero downtime across 12 services
- Mentored 3 junior engineers; introduced ADR practice to the team

### Backend Engineer — Globex Inc (2018 – 2021)
- Built REST + GraphQL API layer serving 50 M requests/day on FastAPI + PostgreSQL
- Introduced contract testing (Pact); reduced integration defect rate by 40%

### Software Engineer — Capsule Corp (2015 – 2018)
- Core contributor to internal job scheduling system (Python + Celery + Redis)

## Skills

Python, PostgreSQL, Kafka, Redis, Kubernetes, Docker, FastAPI, SQLAlchemy,
Terraform, AWS (ECS, RDS, S3), Linux, Git

## Education

B.S. Computer Science — Georgia Tech, 2015
```

Replace all content with your own. The more specific the resume, the better the tailoring.

---

## 6. Fetch jobs

```bash
shortlist fetch
```

Expected output (abbreviated):

```
[greenhouse] acme: 12 new, 0 updated
[greenhouse] globex: 4 new, 1 updated
[greenhouse] initech: 0 new, 0 updated
[lever] umbrella-corp: 7 new, 0 updated
[ashby] capsule-corp: 3 new, 0 updated
[hn_who_hiring] April 2026: 41 new
[remoteok] 28 new
fetch complete — 95 jobs stored
```

What's happening behind the scenes:

- Each enabled, non-cooled source is polled concurrently (respecting per-source rate limits).
- Jobs are upserted by `(source, external_id)` — running `fetch` again is safe and idempotent.
  Existing jobs are updated if the posting changed; no job is deleted.
- `last_fetched_at` is recorded per source on success. Failed sources log an error and continue
  without blocking the others.
- Scraped sources (Indeed, LinkedIn, Glassdoor) are disabled by default. See
  [troubleshooting.md](troubleshooting.md) if you want to enable them.

---

## 7. Rank without LLM — the $0 path

```bash
shortlist rank --no-llm
```

This runs two pipeline stages at zero cost:

**Stage 1 — Hard filter.** Each job is checked against your preferences:
- Compensation below `comp_floor_usd` → filtered out
- Title or description contains an `exclude_keywords` entry → filtered out
- Location mismatch (and `remote_ok: false`) → filtered out
- Seniority mismatch → filtered out

Filtered jobs get `score=0`, reason `"filtered out"`.

**Stage 2 — Cosine similarity.** Surviving jobs are embedded with `bge-small-en-v1.5`
(a 384-dimension local model, downloaded once to `~/.cache/`). Cosine distance against your
embedded resume determines the top-30 candidates. Top-30 get `score=70`; the rest get `score=40`.

```bash
shortlist list
#  ID   Score  Company      Title                          Location       Status
#  12    70    Acme Corp    Senior Backend Engineer        Remote         new
#  34    70    Globex Inc   Staff Platform Engineer        Atlanta, GA    new
#  56    70    Capsule Corp Platform Engineer              Remote         new
#  ...
```

No API calls. No cost.

---

## 8. Rank with LLM — full pipeline

```bash
export ANTHROPIC_API_KEY=sk-ant-...
shortlist rank
```

This adds a third stage on top of the cosine pass:

**Stage 3 — Haiku rerank.** The top-30 cosine candidates (title, company, first 1000 chars of
the job description) are sent together with your resume and preferences to `claude-haiku-4-5`.
The model returns a score 0–100 with a one-line reason for each candidate.

```
ranked 95 jobs (12 filtered, 30 LLM-scored) — cost $0.02, 4 800 tokens
```

Expected cost per run: **$0.01 – $0.05** depending on candidate count and description lengths.

```bash
shortlist list
#  ID   Score  Company      Title                          Location       Status
#  12    88    Acme Corp    Senior Backend Engineer        Remote         new
#  34    81    Globex Inc   Staff Platform Engineer        Atlanta, GA    new
#  56    74    Capsule Corp Platform Engineer              Remote         new
```

The daily and monthly budget caps in `config.yaml` are hard limits enforced before each API call.

---

## 9. Tailor a top match

Pick the top result — job ID 12 (Acme Corp, Senior Backend Engineer, score 88):

```bash
shortlist tailor 12
```

What happens:

1. Loads `~/jobs/resume.md` and the job's full description from the DB.
2. Sends a Sonnet 4.6 prompt. The system prompt forbids fabrication — every bullet in the output
   must be traceable to your original resume. Only ordering and phrasing may change.
3. Parses three Markdown sections from the model response.
4. Writes to `~/jobs/acme-corp-senior-backend-engineer-12/`:
   - `resume.md` — bullets reordered/rephrased to match the JD
   - `cover.md` — three-paragraph cover letter (paragraph count configurable)
   - `notes.md` — talking points, gaps vs JD, questions to ask the interviewer
5. Renders `resume.pdf` and `cover.pdf` via pandoc + LaTeX (skipped with a warning if missing).
6. Transitions job status `new → tailored` in the database.
7. Logs a `tailor.complete` event with cost and token counts.

```
tailored job 12 → ~/jobs/acme-corp-senior-backend-engineer-12/
  resume.md  (1 847 chars)
  cover.md   (912 chars)
  notes.md   (654 chars)
  resume.pdf ✓
  cover.pdf  ✓
cost $0.18, 3 200 tokens
```

Expected cost per tailor call: **$0.10 – $0.30**.

---

## 10. Apply manually and track

Apply on the company's own careers page (Shortlist does not auto-submit), then record it:

```bash
shortlist track 12 --status applied --applied-via "company website"
```

Add the recruiter who emailed you:

```bash
shortlist contacts add 12 \
  --name "Jane Doe" \
  --email jane@acme.com \
  --role recruiter
```

List contacts for a job:

```bash
shortlist contacts list 12
#  ID  Name      Email           Role
#   1  Jane Doe  jane@acme.com   recruiter
```

The full status state machine — transitions flow forward only:

```
new → tailored → applied → screen → interview → offer
                                             ↘ rejected
withdrawn  (reachable from any non-terminal state)
```

---

## 11. Browse with the TUI

```bash
shortlist tui
```

Opens on the Job List screen — a sortable table ranked by score.

**Job List key bindings:**

| Key | Action |
|-----|--------|
| `j` / `k` | Move cursor down / up |
| `g` / `G` | Jump to top / bottom |
| `enter` | Open Job Detail (full description + tailored docs preview) |
| `t` | Tailor selected job (runs in background, shows notification when done) |
| `r` | Refresh list from DB |
| `/` | Filter by company or title |
| `escape` | Clear filter |
| `f` | Fetch all sources (background) |
| `R` | Full rank pipeline (background, requires `ANTHROPIC_API_KEY`) |
| `a` | Applications Board — kanban view by status |
| `s` | Settings screen |
| `q` | Quit |

The Applications Board (`a`) shows jobs grouped in status columns — useful for a quick
pipeline overview when you have multiple applications in flight.

---

## 12. Daily routine

A sustainable cadence for an active search:

```bash
# Morning (2–3 min, $0 cost)
shortlist fetch
shortlist rank --no-llm
shortlist tui          # browse top 10, pick 1–3 to tailor today

# Tailor chosen jobs (~$0.15–0.25 each)
shortlist tailor <id1>
shortlist tailor <id2>

# Apply on company sites, then record
shortlist track <id1> --status applied --applied-via "company website"
shortlist track <id2> --status applied --applied-via "LinkedIn Easy Apply"

# Weekly: full LLM rank when prefs or candidate pool changes (~$0.02–0.05)
shortlist rank
```

Typical daily cost for an active search: **$0.30 – $1.00**, almost entirely from `tailor` calls.

---

## 13. Cost ceiling

Two independent hard caps in `config.yaml`:

```yaml
budget:
  daily_usd: 2.00     # resets at UTC midnight
  monthly_usd: 30.00  # resets on the 1st of each month
```

When a cap is reached the tool prints a warning and skips the API call. Check cumulative spend:

```bash
sqlite3 ~/.local/share/shortlist/db.sqlite \
  "SELECT date(created_at), ROUND(SUM(cost_usd),4) \
   FROM events WHERE cost_usd IS NOT NULL \
   GROUP BY date(created_at) ORDER BY 1 DESC"
```

---

## Where to go next

- [docs/architecture.md](architecture.md) — how the pieces fit together internally
- [docs/troubleshooting.md](troubleshooting.md) — scraped source bans, PDF failures, API errors
- [docs/usage.md](usage.md) — full CLI and TUI key binding reference
