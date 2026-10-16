# Usage Reference

## Multiple people

Shortlist can track more than one person's job search in a single installation - useful if
you and a partner, or you and a friend, both use the same machine.

### Managing people

```bash
shortlist profile create david --name "David"   # creates the "david" profile
shortlist profile create alex --name "Alex"
shortlist profile list                           # david  David
                                                  # alex   Alex
shortlist profile delete alex --yes              # removes alex's data; irreversible
```

A slug is 1-32 characters of lowercase letters, digits and hyphens. The display name is what
shows up in the web UI header and TUI title bar; a blank or whitespace-only name is rejected,
since it could never be typed back exactly to confirm a delete.

### Choosing a person

Every CLI data command (`fetch`, `rank`, `tailor`, `list`, `track`, `contacts`, `sources`,
`db`, `config show`, `tui`) takes `--profile` / `-p`:

```bash
shortlist fetch --profile alex
shortlist tui -p david
```

If you omit `--profile`, Shortlist resolves one automatically, in this order:

1. `--profile` / `-p` on the command line
2. the `SHORTLIST_PROFILE` environment variable
3. the only profile, if exactly one exists
4. whichever profile you used last

If none of those settle it - two or more profiles and no prior "last used" - the command exits
with a list of the available slugs instead of guessing.

The TUI has no in-app switcher, so `--profile` is the only way to open it against someone other
than the resolved default.

### Web UI

Every page in the web UI is scoped to a person at `/p/<slug>/...` - for example
`/p/david/applications`. A header dropdown switches between people without restarting the
server, and "add a new person" is one click away from there. Bookmarked pre-multi-person URLs
like `/applications` still work: they redirect to the active profile's version.

### What's shared vs. separate

| Shared across everyone | Separate per person |
|---|---|
| Anthropic API key | Resume |
| Model names (ranker, tailor) | Jobs and scores |
| Budget caps | Kanban board / application status |
| Combined cost view (sum across everyone) | Source preferences (`prefs.yaml`) |
| | Tailored output (resume/cover/notes per job) |

The combined figure on the costs page adds up every person's spend so you can see the total
against your budget cap at a glance, while each person's own cost breakdown stays theirs.

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
shortlist tui --profile alex  Launch the TUI for a specific person

shortlist profile create <slug> --name "David"   Create a person, e.g. `profile create david --name David`
shortlist profile list                           List every person
shortlist profile delete <slug>                  Delete a person and all of their data
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
