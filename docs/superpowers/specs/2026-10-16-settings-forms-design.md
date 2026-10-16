# Settings forms and search locations

Date: 2026-10-16
Status: approved design, not yet implemented

## Problem

Settings are edited as raw YAML. That works for the owner but not for the
family members the multi-profile work added: a new profile starts from the
engineering template, and changing it means hand-editing a YAML file with 21
fields, 15 of them lists.

Separately, the scraped sources cannot search a place. Indeed and Glassdoor
always search `Remote`, LinkedIn always searches `United States`. Prefs
`locations` only filters jobs after they are fetched, so a profile looking for
local work in Brunswick, GA never runs a Brunswick search.

## Decisions

| Concern | Decision |
|---|---|
| Editing | Forms for prefs and config; raw YAML editors kept in a collapsed "Advanced" section |
| List fields | One item per line in a small textarea |
| Location fields | One input per location with add and remove, plus autocomplete |
| Search location | New `search_locations` list; each query runs once per location |
| Autocomplete data | Bundled US place list from GeoNames, served locally |
| Strictness | `search_locations` must be a known place or `Remote`; filter `locations` stays free text |
| Extra LLM calls | None |

## Data and validation

### `search_locations`

`Prefs` gains `search_locations: list[str]`, default empty. Each entry must be
`Remote` or a place in the bundled list, compared case-insensitively and stored
in the list's canonical spelling. The check is a pydantic validator on `Prefs`,
so the web form, the CLI and hand-edited YAML share one rule. The error names
the entry: `not a known place: 'Brunswik, GA'`.

Filter `locations` is unchanged. It matches as a substring of a job's location,
so partial values such as `GA` or `St. Simons` are useful there.

Prefs files without the field still load.

### Place list

`shortlist/data/us_places.txt`, one `City, ST` per line, deduplicated, largest
population first so suggestions lead with the likeliest place.
Built from GeoNames `cities1000` (populated places of 1,000 or more) filtered
to country `US`, by `scripts/build_us_places.py`. The output is committed; the
application never downloads anything. GeoNames data is CC BY 4.0 and the README
credits it.

`shortlist/places.py` loads the list once (cached) and exposes:

- `canonical(name) -> str | None` - the list's spelling of `name` (or `Remote`),
  case-insensitive, else `None`.
- `suggest(query, limit=10) -> list[str]` - prefix matches first, then
  substring matches, each group in list order. A query under two characters
  returns nothing.

### Sources

`IndeedSource`, `LinkedInSource` and `GlassdoorSource` take
`locations: list[str] | None` in place of `location: str`. Each query runs once
per location. An empty or missing list keeps each source's current default, so
existing profiles behave exactly as before.

URL construction moves into a `search_urls()` method on each source so it can
be tested without a browser.

LinkedIn has no `Remote` location; for that entry it searches `United States`
with its remote filter (`f_WT=2`).

`_build_sources` in `shortlist/cli.py` and `shortlist_tui/workers.py` pass
`prefs.search_locations` to all three.

## Settings page

Top to bottom:

**Prefs form**, for this person, in three groups:

- What: titles, seniority, exclude keywords (one per line), minimum salary.
- Where: filter locations (location inputs, free text), remote OK, search
  locations (location inputs, must be known places).
- Sources: Indeed, LinkedIn, Glassdoor, Wellfound and Otta queries; Greenhouse,
  Lever, Ashby, Workable and SmartRecruiters companies; RSS URLs (one per
  line); HN, RemoteOK and Remotive toggles.

**Config form**, shared: key environment variable name (never its value),
daily and monthly budget, embedding model, rerank model, rerank top K, tailor
model, cover paragraphs, PDF template path.

Not in the config form: `anthropic.key_source`, `sources`, and the legacy
`paths.resume` and `paths.output_dir`. The config save reads the current file,
updates only the fields the form shows, and writes the result, so these are
kept exactly.

**Advanced: edit YAML**, a collapsed `<details>` holding today's two raw
editors with their routes and behaviour unchanged.

### Location inputs

Each location is a text input bound to one shared `<datalist>`. Typing
requests `GET /places?q=<text>` after a 200 ms pause; the response is up to 10
`<option>` elements that replace the datalist's contents. This is a few lines
of plain JavaScript in `static/settings.js` rather than HTMX, because HTMX
would send the value under the input's own name (`search_locations`) rather
than `q`. Add and remove live in the same file and use event delegation, so
added rows need no wiring. Without JavaScript the inputs still submit;
there are no suggestions.

## Saving

New routes `POST /p/<slug>/settings/prefs/form` and
`POST /p/<slug>/settings/config/form`.

The route converts form fields to a dict: textareas split on newlines with
blanks dropped, location inputs collected as lists, checkboxes to booleans,
numbers parsed. The dict is validated through `Prefs` or `Config`.

On success the existing file is copied to `.bak`, then the new YAML is written
with `yaml.safe_dump(sort_keys=False)` under a fixed header comment.

On failure nothing is written. The form re-renders with the submitted values,
and each error appears beside its field, mapped from the pydantic error's
`loc`.

## Error handling

| Situation | Behaviour |
|---|---|
| Unknown search location | Field error naming the entry; nothing written |
| Missing or unparseable number | Field error; nothing written |
| No titles | Field error (model requires one); nothing written |
| `/places` query under two characters | Empty response |
| `config.yaml` missing | Form shows the built-in default; saving creates the file |

## Testing

Written test-first:

- `places`: canonical lookup, case-insensitivity, unknown names, prefix before
  substring ordering, limit, short query.
- `Prefs`: valid `search_locations` passes and is canonicalised, invalid fails
  naming the entry, empty passes, a prefs file without the field loads.
- Sources: `search_urls()` yields one URL per query per location, defaults are
  unchanged for an empty list, LinkedIn `Remote` uses `f_WT=2`.
- Web: prefs form round trip; a bad search location re-renders with the error
  and leaves the file unchanged; config form save keeps `sources` and
  `key_source`; a save writes `.bak`; `/places?q=brun` includes
  `Brunswick, GA`.

## Out of scope

- Places outside the US.
- Editing `sources` through a form.
- Changing the default prefs template.
