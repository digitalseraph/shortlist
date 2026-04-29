# Shortlist

Personal job-search assistant. Discovers postings, ranks them against your resume + preferences, tailors per-job materials, and tracks the application lifecycle. **You apply manually** — Shortlist surfaces and prepares; it never auto-submits.

This is **Plan 4 of 6** (Textual TUI). Cumulative status:

- ✅ Plan 1 (foundation): Greenhouse + SQLite + hard filter + CLI
- ✅ Plan 2: Lever, Ashby, Workable, SmartRecruiters; embeddings via `sentence-transformers`; Haiku 4.5 rerank with budget guard
- ✅ Plan 3: Sonnet 4.6 per-job tailoring (resume + cover + notes); pandoc → PDF; status state machine; contacts CRUD
- ✅ Plan 4 (this): Textual TUI — JobList, JobDetail, ApplicationsBoard, Settings; vim-style key bindings; live search
- ⏳ Plan 5: scraped aggregators (Indeed, LinkedIn, Glassdoor) + Playwright
- ⏳ Plan 6: curated boards (HN/Wellfound/Otta/RemoteOK) + RSS + release polish

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
shortlist fetch                   # pull jobs for configured ATS companies
shortlist rank --no-llm           # cheap mode: hard filter + cosine pre-rank
shortlist rank                    # full pipeline (requires ANTHROPIC_API_KEY)
shortlist list                    # see what survived, sorted by score
shortlist tailor <job_id>         # generate per-job MD + PDF
shortlist track <job_id> --status tailored
shortlist track <job_id> --status applied --applied-via "company website"
shortlist contacts add <job_id> --name "Jane Doe" --email jane@acme.com --role recruiter
shortlist contacts list <job_id>
shortlist tui                     # launch the TUI
```

## System dependencies

For PDF rendering, `pandoc` and `pdflatex` (TeX Live, including LaTeX format files) must be on PATH:

- Arch / CachyOS: `sudo pacman -S pandoc texlive-core texlive-latex`
- macOS: `brew install pandoc basictex`

Without them, `shortlist tailor` still writes Markdown — only the PDF render step is skipped (with a warning).

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
