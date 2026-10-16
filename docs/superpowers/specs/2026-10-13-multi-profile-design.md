# Multi-profile support

Date: 2026-10-13
Status: approved design, not yet implemented

## Problem

Shortlist assumes one job seeker. `paths.db_path()` and `paths.prefs_path()`
take no arguments, so "whose data is this" is invisible at all 67 call sites
across `cli.py`, the TUI and the web routes. Running a search on behalf of a
second person means a second machine account or a second data directory.

The goal is to track several people - the owner plus family and friends - in
one installation, with separate resumes, job lists, kanban boards and source
preferences, while sharing one Anthropic API key and one budget.

## Decisions

| Concern | Decision |
|---|---|
| Shared | API key, model names, budget, cost ledger view |
| Per person | Resume, jobs, kanban, source preferences, tailored output |
| Isolation | One SQLite database per person, in its own directory |
| Switching | Live, in one server, no restart |
| Profile scope | In the URL, so two people can be open in two tabs |
| Resume formats | Markdown, plain text, PDF, DOCX |
| Existing data | Profiles start empty; the current `db.sqlite` is left on disk, unread |

### Why separate databases rather than a `profile_id` column

A `profile_id` column on every table makes cross-person aggregates a `GROUP BY`,
but requires a correct `WHERE profile_id = ?` at roughly 60 query sites. The
failure mode of missing one is another person's jobs appearing on your board.
Separate files make that leak impossible: the isolation is physical, deleting a
person is removing a directory, and the existing migration runner works per
database without modification.

The cost is that the combined cost view opens every database. At this scale that
is microseconds, and it is the only place that pays.

A shared `costs.sqlite` was also considered and rejected: it adds a second write
to every LLM call, detaches cost rows from the jobs that incurred them, and
orphans rows when a profile is deleted.

## Layout

```
config_dir/config.yaml                    shared: anthropic, models, budget
config_dir/state.yaml                     most recently used slug
config_dir/profiles/<slug>/prefs.yaml     per person: titles, locations, boards
data_dir/profiles/<slug>/profile.yaml     display_name
data_dir/profiles/<slug>/db.sqlite
data_dir/profiles/<slug>/resume.md        extracted text; what the pipeline reads
data_dir/profiles/<slug>/resume.original  the file as uploaded
data_dir/profiles/<slug>/output/          tailored resumes and covers
```

`Config` and `Prefs` keep their current pydantic definitions. The split falls
along the existing file boundary: `Config` is shared, `Prefs` moves under the
profile.

A profile straddles two trees, following the existing convention that
preferences are configuration and the database is data. `create` and `delete`
therefore operate on both `config_dir/profiles/<slug>/` and
`data_dir/profiles/<slug>/`.

The registry is the directory listing. `list_profiles()` globs
`data_dir/profiles/*/profile.yaml`. A separate index file would be a second
source of truth that can disagree with the directory. A profile whose data
directory exists without its config counterpart is repaired on load by writing
a default `prefs.yaml`, rather than being hidden from the list.

## Components

### `shortlist/profiles.py` (new)

```python
@dataclass(frozen=True)
class Profile:
    slug: str  # url-safe [a-z0-9-], immutable once created
    display_name: str  # free text, renameable
    db_path: Path
    prefs_path: Path
    resume_path: Path
    output_dir: Path
```

Public surface: `list_profiles()`, `load(slug)`, `create(slug, display_name)`,
`delete(slug)`, `resolve(explicit=None)`, and `ProfileNotFound`.

`create` runs `migrate()` on the new database so a profile is usable the moment
it exists.

`resolve` is for the CLI and TUI: explicit `--profile`, else `$SHORTLIST_PROFILE`,
else the only profile if exactly one exists, else raise listing the choices.

### `shortlist/paths.py` (changed)

Keeps `config_dir()`, `data_dir()`, `config_path()` - all still correct, now
shared-only.

Removes `db_path()` and `prefs_path()`. A process-wide answer to those questions
is the bug being fixed; deleting them makes the test suite and mypy locate every
site that assumed one person, rather than leaving a global that silently
resolves to the wrong one.

### Web layer

Routers mount under `/p/{slug}`. One dependency resolves the profile:

```python
def profile_dep(slug: str) -> Profile:
    try:
        return profiles.load(slug)
    except ProfileNotFound:
        raise HTTPException(404, f"no profile {slug!r}")
```

Handlers declare `profile: Profile = Depends(profile_dep)` and use
`profile.db_path`. A handler that does not declare the parameter has no database
to reach for, so it cannot silently fall back.

An unknown slug is a 404, never a redirect to the default - a stale or mistyped
link must not act on the wrong person.

Bare paths (`/applications`) redirect to `/p/<default>/applications`, where the
default comes from `config_dir/state.yaml`.

The header gains a profile dropdown. Switching rewrites the slug in the current
path, so you stay on the same page for a different person.

With no profiles, every page redirects to a first-run creation screen.

### Resume upload and editing

`POST /p/<slug>/resume/upload` accepts `.md`, `.txt`, `.pdf`, `.docx`, validated
by extension and by leading bytes, capped at 2 MB.

Extraction uses `pypdf` for PDF and `python-docx` for DOCX. The extracted text is
shown in an editable textarea and **nothing is written yet**. Saving writes
`resume.md` and stores the upload as `resume.original`.

The preview step is the reason PDF can be accepted at all: extraction from a
multi-column resume interleaves text, and without a visible check the only
symptom is quietly worse job scores, because that text becomes the embedding.

The uploaded filename is never used to construct a path. The destination is
always `resume.md` / `resume.original` with a sniffed extension, so there is no
traversal surface.

`GET /p/<slug>/resume` is the same textarea pre-filled from `resume.md`. Saving
bumps the file mtime, and `embed_resume_cached` keys on `(path, mtime, model)`,
so the next rank re-embeds automatically. No invalidation code, and no stale
vector to forget.

### Config and prefs editing

Raw YAML textareas: one for the shared `config.yaml`, one per person for
`prefs.yaml`.

Typed forms would mean hand-building about twenty list fields and rebuilding them
whenever the models change. The YAML editor covers every field, and writing back
exactly the submitted bytes preserves comments and ordering that a
`safe_load` + `dump` round trip would destroy.

Saving parses through the existing pydantic models first. Invalid YAML or a
failed constraint re-renders the submitted text with the error inline and writes
nothing, so a broken config cannot be saved from the browser. A `.bak` copy is
written before each successful overwrite.

`config.yaml` holds `key_env_var: ANTHROPIC_API_KEY` - the name of the variable,
never its value - so editing config in a browser exposes no secret.

### Background tasks

Handlers pass `profile.db_path` to the task, capturing the profile at enqueue.
Reading a global inside the task would let a fetch that starts under one person
and finishes after a switch write into the other person's database.

`app.state.task_log` entries become `(slug, timestamp, message)` and
`/p/<slug>/status` filters to that person. Without this, one person's fetch
progress streams into another's status feed.

Two people fetching at once write to different SQLite files, so there is no lock
contention between them.

### Costs

`/p/<slug>/costs` shows that person's spend plus a combined section listing every
profile's total and the sum against the shared cap. Cost data stays in
`scoring_runs.cost_usd` and `tailor_outputs.cost_usd` as today; the combined view
is a fan-out read, so it cannot drift from the per-person numbers.

Budget remains display-only. It is not enforced today and this work does not add
enforcement.

### CLI and TUI

CLI gains `shortlist profile list | create | delete` and `--profile <slug>` on
existing commands.

The TUI resolves one profile at startup and shows it in the header. Live
switching in the TUI is **out of scope**: each Textual screen would need the same
rework the web routes receive, for a surface that was not requested. Switching
people in the TUI means restarting it.

## Error handling

| Situation | Behaviour |
|---|---|
| Unknown slug in URL | 404 |
| No profiles exist | Redirect to first-run creation |
| Duplicate slug on create | Rejected with the conflict named |
| Invalid slug characters | Rejected; slugs are `[a-z0-9-]` |
| Unsupported upload type | Rejected by extension and content sniff |
| Upload over 2 MB | Rejected |
| Invalid YAML or failed validation | Nothing written; submitted text re-rendered with the error |
| Profile deletion | Both directories removed - `data_dir/profiles/<slug>/` and `config_dir/profiles/<slug>/` - confirmed by typing the display name; cost history goes with it |

## Testing

Existing `tests/integration/test_web_app.py` fixtures (`env`, `client`, `_seed`)
build a database at `data/db.sqlite` directly and move to the profile layout.
Comparable churn applies to the store tests.

New coverage, written test-first:

- **Isolation**, the load-bearing test: write a job and a status move in profile
  A, assert profile B's board is empty and its database has zero rows.
- Slug validation, duplicate creation rejected, unknown slug 404s rather than
  falling back to a default.
- Upload: text, generated PDF and DOCX through extract → preview → save; an
  `.exe` renamed to `.pdf` is rejected.
- Config editor: invalid YAML and a constraint violation each write nothing and
  preserve the submitted text.
- A background task writes to the profile captured at enqueue, after a switch.
- Cost fan-out sums across three profiles.

## Dependencies

Adds `pypdf` and `python-docx`.

## Out of scope

- Live profile switching in the TUI.
- Budget enforcement.
- Importing the existing `db.sqlite` into a profile.
- Cross-person reporting beyond the combined cost total.
- Any access control between profiles; this is a single-user installation where
  one person manages several job searches.
