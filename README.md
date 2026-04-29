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
