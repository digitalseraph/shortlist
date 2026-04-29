# Usage Reference

## CLI subcommands

```
shortlist db init          Create the SQLite database and run migrations
shortlist db status        Show schema version and db path
shortlist db backup        Write a timestamped backup copy

shortlist config init      Write default config.yaml + prefs.yaml to ~/.config/shortlist/
shortlist config show      Print current config + prefs

shortlist fetch            Pull jobs from all enabled, non-cooled sources
shortlist rank             Hard filter → cosine → Haiku rerank (requires ANTHROPIC_API_KEY)
shortlist rank --no-llm    Hard filter + cosine only; no API call
shortlist list             Print stored jobs sorted by score
shortlist list --status new

shortlist tailor <id>      Generate resume.md, cover.md, notes.md + PDF via Sonnet
shortlist track <id> --status applied --applied-via "company website"

shortlist contacts add <id> --name "Jane" --email jane@acme.com --role recruiter
shortlist contacts list <id>
shortlist contacts remove <contact_id>

shortlist sources status           List sources, last fetch time, cooldown state
shortlist sources clear-cooldown <name>  Unblock a cooled source

shortlist tui              Launch the Textual TUI
```

## TUI key bindings

### Global (any screen)

| Key | Action |
|-----|--------|
| `q` | Quit |
| `f` | Fetch all sources (background worker) |
| `R` | Rank (full pipeline, background worker) |
| `a` | Open Applications Board |
| `s` | Open Settings |

### Job List screen

| Key | Action |
|-----|--------|
| `j` / `k` | Move cursor down / up |
| `g` / `G` | Jump to top / bottom |
| `enter` | Open Job Detail |
| `t` | Tailor selected job |
| `r` | Refresh list from DB |
| `/` | Focus search box (filter by company or title) |
| `escape` | Clear search |

### Job Detail screen

| Key | Action |
|-----|--------|
| `o` | Open job URL in system browser |
| `escape` / `q` | Go back to Job List |
