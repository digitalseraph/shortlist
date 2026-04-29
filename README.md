# Shortlist

Personal job-search assistant. Discovers postings, ranks them against your resume + preferences, tailors per-job materials, and tracks the application lifecycle. **You apply manually** — Shortlist surfaces and prepares; it never auto-submits.

This is **Plan 2 of 6** (ATS expansion + LLM rerank). Cumulative status:

- ✅ Plan 1 (foundation): Greenhouse + SQLite + hard filter + CLI
- ✅ Plan 2 (this): Lever, Ashby, Workable, SmartRecruiters; embeddings via `sentence-transformers`; Haiku 4.5 rerank with budget guard
- ⏳ Plan 3: tailoring (resume + cover + notes via Sonnet 4.6) + status tracker
- ⏳ Plan 4: Textual TUI
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
