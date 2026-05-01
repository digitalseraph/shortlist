# Shortlist

Personal job-search assistant. Discovers postings from ATS APIs, scraped boards, curated sources,
and RSS feeds; ranks them against your resume and preferences; generates a tailored resume, cover
letter, and notes for each target role; and tracks the full application lifecycle. **You apply
manually** — Shortlist surfaces and prepares; it never auto-submits.

**Status: v0.1.0 — feature-complete.**

| Plan | What shipped |
|------|-------------|
| 1 | Greenhouse ATS, SQLite store, hard filter, Typer CLI |
| 2 | Lever / Ashby / Workable / SmartRecruiters; sentence-transformers embeddings; Haiku rerank |
| 3 | Sonnet tailoring → Markdown + PDF; status state machine; contacts CRUD |
| 4 | Textual TUI — job list, detail, applications board, settings |
| 5 | Scraped aggregators (Indeed, LinkedIn, Glassdoor) via Playwright; 24 h auto-cooldown |
| 6 | Curated boards (HN, RemoteOK), Wellfound, Otta, generic RSS; tag-driven GitHub Release |

---

## Quick install

```bash
git clone https://github.com/digitalseraph/shortlist
cd shortlist
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium  # only needed for scraped sources
```

## First run

One-time setup, then a golden-path session:

```bash
shortlist db init                              # create ~/.local/share/shortlist/db.sqlite
shortlist config init                          # write config + prefs defaults to ~/.config/shortlist/
$EDITOR ~/.config/shortlist/prefs.yaml         # add company lists, job title prefs, location

shortlist fetch                                # pull jobs from all enabled sources
shortlist rank --no-llm                        # cheap pass: hard filter + cosine similarity
shortlist list                                 # inspect results

export ANTHROPIC_API_KEY=sk-ant-...
shortlist rank                                 # full pipeline: adds Haiku rerank (Prefs key)
shortlist tailor <job_id>                      # Sonnet: resume.md + cover.md + notes.md → PDF
shortlist track <job_id> --status applied --applied-via "company website"
shortlist contacts add <job_id> --name "Jane Doe" --email jane@acme.com --role recruiter
shortlist tui                                  # browse everything in the TUI
shortlist web                                  # launch browser UI at http://127.0.0.1:8765
```

## Web UI

`shortlist web` launches a server-rendered browser interface (FastAPI + HTMX) on
`http://127.0.0.1:8765` by default. No Node, no build step — just `pip install` and go.

```bash
shortlist web                        # default: 127.0.0.1:8765
shortlist web --port 9000            # custom port
shortlist web --host 0.0.0.0         # expose on LAN (single-user only — no auth)
```

Pages mirror the TUI:

| Page | URL | What it shows |
|------|-----|---------------|
| Jobs | `/` | Scored job table with live search filter and per-row Tailor button |
| Job detail | `/job/{id}` | Full JD, tailored resume/cover/notes previews, status tracker |
| Applications | `/applications` | Kanban columns by status (tailored → offer / rejected) |
| Settings | `/settings` | Read-only view of config.yaml, prefs.yaml, and data paths |

Global **Fetch** and **Rank** buttons in the header dispatch background tasks and report
results in a polling status strip at the top of every page. The `shortlist web` command
is a thin wrapper — all job logic runs through the same `shortlist_tui.workers` path
used by the TUI.

## Sources

| Source | Type | Default | Prefs key |
|--------|------|---------|-----------|
| Greenhouse | ATS API | enabled | `greenhouse_companies` |
| Lever | ATS API | enabled | `lever_companies` |
| Ashby | ATS API | enabled | `ashby_companies` |
| Workable | ATS API | enabled | `workable_companies` |
| SmartRecruiters | ATS API | enabled | `smartrecruiters_companies` |
| Indeed | Scraped | **disabled** | `indeed_queries` |
| LinkedIn | Scraped | **disabled** | `linkedin_queries` |
| Glassdoor | Scraped | **disabled** | `glassdoor_queries` |
| Wellfound | Scraped | enabled | `wellfound_queries` |
| Otta | Scraped | enabled | `otta_queries` |
| HN Who is Hiring? | Curated | enabled | `hn_enabled: true` |
| RemoteOK | Curated | enabled | `remoteok_enabled: true` |
| RSS feeds | RSS | enabled | `rss_urls` |

ATS APIs are the recommended primary path — public JSON, no scraping risk. Scraped sources are
best-effort and may trigger cooldowns. See [docs/troubleshooting.md](docs/troubleshooting.md).

## Cost guide

| Operation | Model | Typical cost |
|-----------|-------|-------------|
| `rank` (30 jobs) | Haiku 4.5 | $0.01 – $0.05 |
| `tailor` (1 job) | Sonnet 4.6 | $0.10 – $0.30 |
| `--no-llm` path | none | $0.00 |

Set `budget.daily_usd` and `budget.monthly_usd` in `~/.config/shortlist/config.yaml` to cap
spending. The tool will stop calling the API when a cap is reached.

## System dependencies

PDF rendering requires `pandoc` and `pdflatex` on PATH:

- Arch / CachyOS: `sudo pacman -S pandoc texlive-core texlive-latex`
- macOS: `brew install pandoc basictex`

Without them, `shortlist tailor` still writes Markdown — only the PDF step is skipped.

## Docs

| Document | Purpose |
|----------|---------|
| [docs/tutorial.md](docs/tutorial.md) | Zero-to-tailored walkthrough |
| [docs/architecture.md](docs/architecture.md) | Module map, data flow, schema |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Scraped source bans, PDF issues, API errors |
| [docs/usage.md](docs/usage.md) | TUI key bindings and CLI reference |
| [docs/presentation.md](docs/presentation.md) | Marp slide deck for meetup / portfolio |
| [docs/spec.md](docs/spec.md) | Original design spec |
| [docs/plans/](docs/plans/) | Per-plan implementation notes |

## Testing

```bash
pytest -m "not browser and not live"            # unit + integration (CI default)
RUN_LIVE=1 pytest -m live                       # opt-in: network smoke tests
RUN_LIVE=1 pytest -m "browser and live"         # opt-in: live scrape smoke
```

Coverage target: 80%. Current: 82.96%.

## License

MIT.
