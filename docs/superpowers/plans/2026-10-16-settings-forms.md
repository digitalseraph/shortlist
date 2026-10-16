# Settings forms and search locations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw YAML settings editors with forms (raw editors kept under "Advanced"), and add validated, autocompleted `search_locations` that the Indeed, LinkedIn and Glassdoor sources search.

**Architecture:** A bundled GeoNames-derived place list backs a small `shortlist.places` module used both by a `Prefs` validator and a `/places` suggestion endpoint. Form-to-dict conversion and error mapping live in `shortlist_web/settings_forms.py`; `routes/settings.py` gains two form routes and saves through the pydantic models. Scraped sources take a list of locations and expose `search_urls()`.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2, pydantic v2, PyYAML, plain JavaScript, pytest.

**Spec:** `docs/superpowers/specs/2026-10-16-settings-forms-design.md`

## Global Constraints

- No new runtime dependencies and no LLM calls.
- `search_locations` entries must be `Remote` or a bundled place; filter `locations` stays free text.
- An empty `search_locations` keeps today's defaults: Indeed `Remote`, Glassdoor `Remote`, LinkedIn `United States`.
- Raw YAML routes `POST /p/<slug>/settings/prefs` and `/settings/config` keep their behaviour; their existing tests must still pass.
- Config form never shows or writes the API key value; it keeps `anthropic.key_source`, `sources` and legacy `paths` keys as they are.
- Every save writes a `.bak` copy first; a failed validation writes nothing.
- Run tools via `.venv/bin/python -m pytest`, `.venv/bin/ruff`, `.venv/bin/mypy`.

---

### Task 1: Place list and `shortlist.places`

**Files:**
- Create: `scripts/build_us_places.py`
- Create: `shortlist/data/us_places.txt` (generated)
- Create: `shortlist/places.py`
- Modify: `pyproject.toml` (force-include the data file)
- Modify: `README.md` (GeoNames credit)
- Test: `tests/unit/test_places.py`

**Interfaces:**
- Produces: `places.REMOTE = "Remote"`, `places.canonical(name: str) -> str | None`, `places.suggest(query: str, limit: int = 10) -> list[str]`, private `places._index() -> tuple[tuple[str, str], ...]` of `(lowercase, display)` pairs, Remote first, then largest places first.

- [ ] **Step 1: Write the build script and generate the list**

```python
"""Build shortlist/data/us_places.txt from GeoNames cities1000.

    curl -O https://download.geonames.org/export/dump/cities1000.zip
    python scripts/build_us_places.py cities1000.zip

Writes one "City, ST" per line, largest population first. GeoNames data is
CC BY 4.0 (https://www.geonames.org/).
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "shortlist" / "data" / "us_places.txt"
# Column positions in the GeoNames dump format.
_NAME, _FEATURE_CODE, _COUNTRY, _ADMIN1, _POPULATION = 1, 7, 8, 10, 14


def main(zip_path: str) -> None:
    best: dict[str, int] = {}
    with zipfile.ZipFile(zip_path) as zf, zf.open("cities1000.txt") as raw:
        rows = csv.reader(io.TextIOWrapper(raw, "utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE)
        for row in rows:
            # PPLQ marks an abandoned place.
            if row[_COUNTRY] != "US" or row[_FEATURE_CODE] == "PPLQ":
                continue
            place = f"{row[_NAME]}, {row[_ADMIN1]}"
            best[place] = max(best.get(place, 0), int(row[_POPULATION] or 0))
    ordered = sorted(best, key=lambda p: (-best[p], p))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(ordered) + "\n", encoding="utf-8")
    print(f"wrote {len(ordered)} places to {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
```

Run: `.venv/bin/python -I scripts/build_us_places.py <scratch>/cities1000.zip`
Expected: `wrote ~17000 places to .../shortlist/data/us_places.txt`

- [ ] **Step 2: Write failing tests** (`tests/unit/test_places.py`)

```python
"""Bundled US place list: validation and autocomplete."""

from __future__ import annotations

import pytest

from shortlist import places


def test_canonical_ignores_case_and_spacing() -> None:
    assert places.canonical("  brunswick,   ga ") == "Brunswick, GA"


def test_canonical_rejects_unknown_place() -> None:
    assert places.canonical("Brunswik, GA") is None


def test_remote_is_a_place() -> None:
    assert places.canonical("remote") == "Remote"


def test_suggest_finds_brunswick() -> None:
    assert "Brunswick, GA" in places.suggest("brun")


def test_suggest_short_query_returns_nothing() -> None:
    assert places.suggest("b") == []


def test_suggest_respects_limit() -> None:
    assert len(places.suggest("sa", limit=3)) == 3


def test_suggest_puts_prefix_matches_first(monkeypatch: pytest.MonkeyPatch) -> None:
    names = ["East Augusta, GA", "Augusta, GA", "Augusta, ME"]
    monkeypatch.setattr(places, "_index", lambda: tuple((n.lower(), n) for n in names))
    assert places.suggest("augusta") == ["Augusta, GA", "Augusta, ME", "East Augusta, GA"]
```

Run: `.venv/bin/python -m pytest tests/unit/test_places.py -q` - Expected: FAIL (no module `shortlist.places`).

- [ ] **Step 3: Implement `shortlist/places.py`**

```python
"""US place names for search-location validation and autocomplete.

The list is shortlist/data/us_places.txt, built by scripts/build_us_places.py
from GeoNames (CC BY 4.0): one "City, ST" per line, largest places first.
"""

from __future__ import annotations

import importlib.resources
from functools import cache

REMOTE = "Remote"
MIN_QUERY_CHARS = 2


def _normalise(text: str) -> str:
    return " ".join(text.split()).lower()


@cache
def _index() -> tuple[tuple[str, str], ...]:
    """(lowercase, display) pairs: Remote first, then largest places first."""
    data = importlib.resources.files("shortlist").joinpath("data/us_places.txt")
    names = [REMOTE, *data.read_text(encoding="utf-8").splitlines()]
    return tuple((n.lower(), n) for n in names if n)


@cache
def _lookup() -> dict[str, str]:
    # Built from the end so that, for names differing only in case, the
    # earlier (larger) place wins.
    return {low: name for low, name in reversed(_index())}


def canonical(name: str) -> str | None:
    """The list's spelling of `name`, or None when it is not a known place."""
    return _lookup().get(_normalise(name))


def suggest(query: str, limit: int = 10) -> list[str]:
    """Places starting with `query`, then places containing it."""
    q = _normalise(query)
    if len(q) < MIN_QUERY_CHARS:
        return []
    prefix = [name for low, name in _index() if low.startswith(q)]
    contains = [name for low, name in _index() if q in low and not low.startswith(q)]
    return (prefix + contains)[:limit]
```

- [ ] **Step 4: Package data and credit**

`pyproject.toml`, under `[tool.hatch.build.targets.wheel.force-include]`, add:
`"shortlist/data/us_places.txt" = "shortlist/data/us_places.txt"`

`README.md`: add a line "Place names for search-location autocomplete come from [GeoNames](https://www.geonames.org/) (CC BY 4.0)."

- [ ] **Step 5: Run tests** - Expected: PASS.

- [ ] **Step 6: Commit** - `feat: add a bundled US place list for search locations`

---

### Task 2: `Prefs.search_locations`

**Files:**
- Modify: `shortlist/config.py` (`Prefs`)
- Test: `tests/unit/test_config.py` (append)

**Interfaces:**
- Consumes: `places.canonical`.
- Produces: `Prefs.search_locations: list[str]`, canonicalised, default `[]`.

- [ ] **Step 1: Failing tests**

```python
def _prefs_data(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "titles": ["French Teacher"],
        "locations": [],
        "remote_ok": True,
        "comp_floor_usd": 0,
        "exclude_keywords": [],
        "seniority": [],
    }
    return base | overrides


def test_search_locations_default_empty() -> None:
    assert Prefs.model_validate(_prefs_data()).search_locations == []


def test_search_locations_are_canonicalised() -> None:
    prefs = Prefs.model_validate(_prefs_data(search_locations=["brunswick, ga", "REMOTE", " "]))
    assert prefs.search_locations == ["Brunswick, GA", "Remote"]


def test_unknown_search_location_is_named_in_the_error() -> None:
    with pytest.raises(ValidationError, match="not a known place: 'Brunswik, GA'"):
        Prefs.model_validate(_prefs_data(search_locations=["Brunswik, GA"]))
```

(Import `Prefs` from `shortlist.config` and `ValidationError` from `pydantic` if the file does not already.)

- [ ] **Step 2: Run, expect FAIL** (extra field forbidden).

- [ ] **Step 3: Implement** in `Prefs`, after `rss_urls`:

```python
    search_locations: list[str] = Field(default_factory=list)

    @field_validator("search_locations")
    @classmethod
    def _known_places(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in v:
            if not raw.strip():
                continue
            name = places.canonical(raw)
            if name is None:
                raise ValueError(f"not a known place: {raw.strip()!r}")
            out.append(name)
        return out
```

Add `from shortlist import places` to the imports.

- [ ] **Step 4: Run tests, expect PASS.** Run the whole suite too.

- [ ] **Step 5: Commit** - `feat: add validated search_locations to prefs`

---

### Task 3: Scraped sources search each location

**Files:**
- Modify: `shortlist/sources/scraped/indeed.py`, `linkedin.py`, `glassdoor.py`
- Modify: `shortlist/cli.py:241-246`, `shortlist_tui/workers.py:60-65`
- Modify: `tests/integration/test_scraped_live.py` (`location=` to `locations=[...]`)
- Test: `tests/unit/test_scraped_search_urls.py`

**Interfaces:**
- Consumes: `Prefs.search_locations`.
- Produces: `IndeedSource(*, queries, locations=None, rate_limit_seconds)` with `search_urls() -> list[tuple[str, str]]` (query, url); `GlassdoorSource(...).search_urls() -> list[str]`; `LinkedInSource(...).search_urls() -> list[list[str]]` (pages per search).

- [ ] **Step 1: Failing tests**

```python
"""Search URL construction for the scraped sources (no browser)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from shortlist.sources.scraped.glassdoor import GlassdoorSource
from shortlist.sources.scraped.indeed import IndeedSource
from shortlist.sources.scraped.linkedin import LinkedInSource


def _qs(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_indeed_runs_each_query_in_each_location() -> None:
    src = IndeedSource(queries=["French teacher", "tutor"], locations=["Brunswick, GA", "Remote"])
    got = [(q, _qs(u)["l"]) for q, u in src.search_urls()]
    assert got == [
        ("French teacher", "Brunswick, GA"),
        ("French teacher", "Remote"),
        ("tutor", "Brunswick, GA"),
        ("tutor", "Remote"),
    ]


def test_indeed_defaults_to_remote() -> None:
    ((_, url),) = IndeedSource(queries=["x"], locations=[]).search_urls()
    assert _qs(url)["l"] == "Remote"


def test_glassdoor_runs_each_query_in_each_location() -> None:
    urls = GlassdoorSource(queries=["x"], locations=["Brunswick, GA", "Remote"]).search_urls()
    assert [_qs(u)["locKeyword"] for u in urls] == ["Brunswick, GA", "Remote"]


def test_glassdoor_defaults_to_remote() -> None:
    (url,) = GlassdoorSource(queries=["x"]).search_urls()
    assert _qs(url)["locKeyword"] == "Remote"


def test_linkedin_pages_per_search() -> None:
    searches = LinkedInSource(queries=["x"], locations=["Brunswick, GA"], max_pages=2).search_urls()
    assert len(searches) == 1
    assert [_qs(u)["start"] for u in searches[0]] == ["0", "25"]
    assert _qs(searches[0][0])["location"] == "Brunswick, GA"


def test_linkedin_remote_uses_remote_filter() -> None:
    (pages,) = LinkedInSource(queries=["x"], locations=["Remote"], max_pages=1).search_urls()
    params = _qs(pages[0])
    assert params["location"] == "United States"
    assert params["f_WT"] == "2"


def test_linkedin_defaults_to_united_states_without_remote_filter() -> None:
    (pages,) = LinkedInSource(queries=["x"], max_pages=1).search_urls()
    params = _qs(pages[0])
    assert params["location"] == "United States"
    assert "f_WT" not in params
```

- [ ] **Step 2: Run, expect FAIL** (unexpected keyword `locations`).

- [ ] **Step 3: Indeed**

```python
    def __init__(
        self,
        *,
        queries: list[str],
        locations: list[str] | None = None,
        rate_limit_seconds: float = 8.0,
    ):
        self._queries = queries
        self._locations = locations or ["Remote"]
        self._rate = rate_limit_seconds

    def search_urls(self) -> list[tuple[str, str]]:
        """(query, url) for every query in every location."""
        return [
            (q, f"{_BASE}?{urlencode({'q': q, 'l': loc})}")
            for q in self._queries
            for loc in self._locations
        ]
```

In `_fetch_all` replace `for q in self._queries:` and the `url = ...` line with `for q, url in self.search_urls():`.

- [ ] **Step 4: Glassdoor**

```python
    def __init__(
        self,
        *,
        queries: list[str],
        locations: list[str] | None = None,
        rate_limit_seconds: float = 10.0,
    ):
        self._queries = queries
        self._locations = locations or ["Remote"]
        self._rate = rate_limit_seconds

    def search_urls(self) -> list[str]:
        """One URL for every query in every location."""
        return [
            f"{_BASE}?{urlencode({'sc.keyword': q, 'locKeyword': loc})}"
            for q in self._queries
            for loc in self._locations
        ]
```

In `_fetch_all`: `for url in self.search_urls():` replacing the query loop, `params` and `url` lines.

- [ ] **Step 5: LinkedIn**

```python
_DEFAULT_LOCATION = "United States"
_REMOTE_WORK_TYPE = "2"  # LinkedIn's f_WT value for remote jobs


def _search_params(query: str, location: str) -> dict[str, str]:
    # LinkedIn has no "Remote" place; remote is a filter on a country search.
    if location == "Remote":
        return {"keywords": query, "location": _DEFAULT_LOCATION, "f_WT": _REMOTE_WORK_TYPE}
    return {"keywords": query, "location": location}
```

Constructor: `locations: list[str] | None = None` replacing `location`, `self._locations = locations or [_DEFAULT_LOCATION]`.

```python
    def search_urls(self) -> list[list[str]]:
        """For every query in every location, the URLs of its result pages."""
        return [
            [
                f"{_BASE}?{urlencode({**_search_params(q, loc), 'start': p * 25})}"
                for p in range(self._max_pages)
            ]
            for q in self._queries
            for loc in self._locations
        ]
```

`_fetch_all`: `for pages in self.search_urls():` / `for url in pages:` keeping the `break` on load failure.

- [ ] **Step 6: Wire prefs**

In both `shortlist/cli.py` and `shortlist_tui/workers.py` `_build_sources`, pass `locations=prefs.search_locations` to `IndeedSource`, `LinkedInSource` and `GlassdoorSource`. In `tests/integration/test_scraped_live.py` change `location="Remote"` to `locations=["Remote"]` and `location="United States"` to `locations=["United States"]`.

- [ ] **Step 7: Run tests (new file + full suite) and mypy, expect PASS.**

- [ ] **Step 8: Commit** - `feat: search each configured location on Indeed, LinkedIn and Glassdoor`

---

### Task 4: `/places` suggestion endpoint

**Files:**
- Create: `shortlist_web/routes/places.py`
- Modify: `shortlist_web/app.py` (include router unprefixed)
- Test: `tests/integration/test_web_places.py`

**Interfaces:**
- Consumes: `places.suggest`.
- Produces: `GET /places?q=<text>` returning `<option value="...">` elements.

- [ ] **Step 1: Failing tests**

```python
"""Place suggestions for the location inputs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from shortlist_web.app import create_app


def test_places_suggests_brunswick() -> None:
    r = TestClient(create_app()).get("/places", params={"q": "brun"})
    assert r.status_code == 200
    assert '<option value="Brunswick, GA">' in r.text


def test_places_short_query_is_empty() -> None:
    assert TestClient(create_app()).get("/places", params={"q": "b"}).text == ""
```

- [ ] **Step 2: Run, expect FAIL** (404).

- [ ] **Step 3: Implement**

```python
"""Place-name suggestions for the settings page's location inputs."""

from __future__ import annotations

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from shortlist import places

router = APIRouter()


@router.get("/places", response_class=HTMLResponse)
def place_options(q: str = "") -> HTMLResponse:
    """`<option>` elements for the shared `#place-options` datalist."""
    return HTMLResponse("".join(f'<option value="{escape(p)}">' for p in places.suggest(q)))
```

`app.py`: import as `from shortlist_web.routes import places as places_router` and `app.include_router(places_router.router)` next to the profiles router (it is not profile-scoped).

- [ ] **Step 4: Run, expect PASS. Step 5: Commit** - `feat: serve place suggestions for location inputs`

---

### Task 5: Prefs form

**Files:**
- Create: `shortlist_web/settings_forms.py`
- Modify: `shortlist_web/routes/settings.py`
- Modify: `shortlist_web/templates/settings.html`
- Create: `shortlist_web/static/settings.js`
- Modify: `shortlist_web/static/style.css`
- Test: `tests/unit/test_settings_forms.py`, `tests/integration/test_web_settings_forms.py`

**Interfaces:**
- Consumes: `Prefs`, `places`.
- Produces (in `settings_forms`): `LINE_FIELDS`, `LOCATION_FIELDS`, `BOOL_FIELDS`, `prefs_data(form: FormData) -> dict[str, object]`, `prefs_values(prefs: Prefs) -> dict[str, object]`, `field_errors(exc: ValidationError, names: Mapping[tuple[str, ...], str]) -> dict[str, str]`, `PREFS_ERROR_NAMES`, `to_yaml(header: str, model: BaseModel) -> str`, `PREFS_HEADER`. In `routes/settings.py`: `_write_with_backup(path: Path, text: str) -> None`.

- [ ] **Step 1: Unit tests for conversion**

```python
"""Form <-> settings conversion."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError
from starlette.datastructures import FormData

from shortlist.config import Prefs
from shortlist_web import settings_forms as sf


def _form(**fields: str | list[str]) -> FormData:
    items: list[tuple[str, str]] = []
    for name, value in fields.items():
        for v in value if isinstance(value, list) else [value]:
            items.append((name, v))
    return FormData(items)


def test_prefs_data_splits_lines_and_reads_checkboxes() -> None:
    data = sf.prefs_data(
        _form(
            titles="French\n\n  World Language \n",
            search_locations=["Brunswick, GA", "", "Remote"],
            remote_ok="on",
            comp_floor_usd="0",
        )
    )
    assert data["titles"] == ["French", "World Language"]
    assert data["search_locations"] == ["Brunswick, GA", "Remote"]
    assert data["remote_ok"] is True
    assert data["hn_enabled"] is False
    assert data["comp_floor_usd"] == "0"


def test_prefs_values_round_trip() -> None:
    prefs = Prefs.model_validate(
        {
            "titles": ["French"],
            "locations": ["GA"],
            "remote_ok": True,
            "comp_floor_usd": 0,
            "exclude_keywords": [],
            "seniority": [],
            "search_locations": ["Remote"],
        }
    )
    values = sf.prefs_values(prefs)
    assert values["titles"] == ["French"]
    assert values["search_locations"] == ["Remote"]


def test_field_errors_maps_to_form_names() -> None:
    with pytest.raises(ValidationError) as info:
        Prefs.model_validate(sf.prefs_data(_form(search_locations=["Brunswik, GA"])))
    errors = sf.field_errors(info.value, sf.PREFS_ERROR_NAMES)
    assert errors["search_locations"] == "not a known place: 'Brunswik, GA'"
    assert "titles" in errors
    assert "comp_floor_usd" in errors


def test_to_yaml_writes_header_and_loads_back() -> None:
    prefs = Prefs.model_validate(
        {
            "titles": ["French"],
            "locations": [],
            "remote_ok": False,
            "comp_floor_usd": 0,
            "exclude_keywords": [],
            "seniority": [],
        }
    )
    text = sf.to_yaml(sf.PREFS_HEADER, prefs)
    assert text.startswith("#")
    assert Prefs.model_validate(yaml.safe_load(text)) == prefs
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `settings_forms.py`**

```python
"""Convert the settings forms to and from the pydantic settings models.

The forms post flat fields; the models want lists, booleans and numbers.
Validation stays in the models, so a form save and a YAML save obey the
same rules.
"""

from __future__ import annotations

from collections.abc import Mapping

import yaml
from pydantic import BaseModel, ValidationError
from starlette.datastructures import FormData

from shortlist.config import Prefs

PREFS_HEADER = "# Shortlist preferences. Saved from the settings form.\n"

# One item per line in a textarea.
LINE_FIELDS = (
    "titles",
    "seniority",
    "exclude_keywords",
    "indeed_queries",
    "linkedin_queries",
    "glassdoor_queries",
    "wellfound_queries",
    "otta_queries",
    "greenhouse_companies",
    "lever_companies",
    "ashby_companies",
    "workable_companies",
    "smartrecruiters_companies",
    "rss_urls",
)
# One input per location, with suggestions.
LOCATION_FIELDS = ("locations", "search_locations")
BOOL_FIELDS = ("remote_ok", "hn_enabled", "remoteok_enabled", "remotive_enabled")

PREFS_ERROR_NAMES: Mapping[tuple[str, ...], str] = {(f,): f for f in Prefs.model_fields}


def _lines(text: str) -> list[str]:
    return [s.strip() for s in text.splitlines() if s.strip()]


def prefs_data(form: FormData) -> dict[str, object]:
    """The prefs form as a dict ready for `Prefs.model_validate`."""
    data: dict[str, object] = {f: _lines(str(form.get(f, ""))) for f in LINE_FIELDS}
    for f in LOCATION_FIELDS:
        data[f] = [str(v).strip() for v in form.getlist(f) if str(v).strip()]
    for f in BOOL_FIELDS:
        data[f] = f in form
    # Left as text: pydantic parses it, and reports a bad number on the field.
    data["comp_floor_usd"] = str(form.get("comp_floor_usd", "")).strip()
    return data


def prefs_values(prefs: Prefs) -> dict[str, object]:
    """Field values for rendering the prefs form."""
    return prefs.model_dump()


def field_errors(exc: ValidationError, names: Mapping[tuple[str, ...], str]) -> dict[str, str]:
    """First error message per form field, keyed by the field's form name.

    `names` maps a pydantic error location (its first one or two parts) to a
    form field name. Errors with no matching field are keyed "_form".
    """
    out: dict[str, str] = {}
    for err in exc.errors():
        loc = tuple(str(part) for part in err["loc"])
        name = names.get(loc[:2]) or names.get(loc[:1]) or "_form"
        out.setdefault(name, err["msg"].removeprefix("Value error, "))
    return out


def to_yaml(header: str, model: BaseModel) -> str:
    """YAML for `model` as given (unset defaults and None left out)."""
    data = model.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    return header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
```

- [ ] **Step 4: Run unit tests, expect PASS.**

- [ ] **Step 5: Integration tests** (`tests/integration/test_web_settings_forms.py`)

```python
"""The settings forms validate, save and re-render like the YAML editors."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortlist import profiles
from shortlist.config import load_prefs
from shortlist_web.app import create_app

PREFS_FORM = {
    "titles": "French\nWorld Language",
    "seniority": "",
    "locations": ["Brunswick, GA", "St. Simons"],
    "search_locations": ["brunswick, ga", "Remote"],
    "remote_ok": "on",
    "comp_floor_usd": "0",
    "indeed_queries": "French teacher",
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SHORTLIST_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("SHORTLIST_DATA_HOME", str(tmp_path / "data"))
    profiles.create("kat", "Katherine")
    return TestClient(create_app())


def test_prefs_form_saves_and_reloads(client: TestClient) -> None:
    r = client.post("/p/kat/settings/prefs/form", data=PREFS_FORM)
    assert r.status_code == 200
    prefs = load_prefs(profiles.load("kat").prefs_path)
    assert prefs.titles == ["French", "World Language"]
    assert prefs.search_locations == ["Brunswick, GA", "Remote"]
    assert prefs.seniority == []
    assert prefs.indeed_queries == ["French teacher"]
    page = client.get("/p/kat/settings").text
    assert 'value="Brunswick, GA"' in page
    assert "St. Simons" in page


def test_prefs_form_bad_search_location_writes_nothing(client: TestClient) -> None:
    path = profiles.load("kat").prefs_path
    before = path.read_text()
    r = client.post(
        "/p/kat/settings/prefs/form", data=PREFS_FORM | {"search_locations": ["Brunswik, GA"]}
    )
    assert r.status_code == 400
    assert "not a known place: &#39;Brunswik, GA&#39;" in r.text
    assert 'value="Brunswik, GA"' in r.text  # submitted value kept
    assert path.read_text() == before


def test_prefs_form_writes_backup(client: TestClient) -> None:
    path = profiles.load("kat").prefs_path
    before = path.read_text()
    client.post("/p/kat/settings/prefs/form", data=PREFS_FORM)
    assert (path.parent / "prefs.yaml.bak").read_text() == before


def test_settings_page_shows_forms_and_advanced_yaml(client: TestClient) -> None:
    page = client.get("/p/kat/settings").text
    assert 'action="/p/kat/settings/prefs/form"' in page
    assert "<details" in page
    assert 'action="/p/kat/settings/prefs"' in page  # raw editor still there
```

- [ ] **Step 6: Run, expect FAIL** (route missing).

- [ ] **Step 7: Route changes in `routes/settings.py`**

Extract the backup-and-write from `_save_yaml`:

```python
def _write_with_backup(path: Path, text: str) -> None:
    """Copy the current file to `.bak`, then write `text`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.with_name(path.name + ".bak").write_text(path.read_text())
    path.write_text(text)
```

`_save_yaml` calls it in place of its inline lines.

Extend `_render_settings` with keyword arguments `prefs_values: dict[str, object] | None = None` and `prefs_errors: dict[str, str] | None = None`. When `prefs_values` is None, load it from disk:

```python
def _disk_prefs_values(profile: Profile) -> tuple[dict[str, object], str]:
    """Prefs form values from disk, or empty values plus a message if the file is invalid."""
    try:
        return settings_forms.prefs_values(load_prefs(profile.prefs_path)), ""
    except Exception as exc:  # noqa: BLE001 - yaml and pydantic raise unrelated types
        return {}, f"prefs.yaml could not be loaded ({exc}); fix it under Advanced."
```

Pass `prefs_values` and `prefs_errors` (default `{}`, with the load message under `"_form"` when present) into the template context.

New route:

```python
@router.post("/settings/prefs/form", response_class=HTMLResponse)
async def save_prefs_form(
    request: Request, profile: Profile = Depends(profile_dep)
) -> HTMLResponse:
    data = settings_forms.prefs_data(await request.form())
    try:
        prefs = Prefs.model_validate(data)
    except ValidationError as exc:
        errors = settings_forms.field_errors(exc, settings_forms.PREFS_ERROR_NAMES)
        return _render_settings(
            request, profile, prefs_values=data, prefs_errors=errors, code=400
        )
    text = settings_forms.to_yaml(settings_forms.PREFS_HEADER, prefs)
    _write_with_backup(profile.prefs_path, text)
    return _render_settings(request, profile, note="Saved.")
```

- [ ] **Step 8: Template**

`settings.html` becomes: note, prefs form, config form (Task 6), then `<details><summary>Advanced: edit YAML</summary>` wrapping the two existing raw sections unchanged. Add `<datalist id="place-options"></datalist>` once and `<script src="/static/settings.js" defer></script>`.

Macros at the top of the template:

```jinja
{% macro err(errors, name) %}{% if errors.get(name) %}<span class="error small">{{ errors[name] }}</span>{% endif %}{% endmacro %}

{% macro lines_field(values, errors, name, label, hint="") %}
<label class="field">
  <span>{{ label }}</span>
  <textarea name="{{ name }}" rows="3" spellcheck="false">{{ (values.get(name) or []) | join("\n") }}</textarea>
  {% if hint %}<span class="dim small">{{ hint }}</span>{% endif %}
  {{ err(errors, name) }}
</label>
{% endmacro %}

{% macro location_field(values, errors, name, label, hint) %}
<div class="field">
  <span>{{ label }}</span>
  <div class="location-list">
    {% for loc in (values.get(name) or []) + [""] %}
    <div class="location-row">
      <input name="{{ name }}" value="{{ loc }}" list="place-options" autocomplete="off">
      <button type="button" data-remove-location title="Remove">&times;</button>
    </div>
    {% endfor %}
  </div>
  <button type="button" data-add-location>Add location</button>
  <span class="dim small">{{ hint }}</span>
  {{ err(errors, name) }}
</div>
{% endmacro %}

{% macro checkbox(values, name, label) %}
<label class="check"><input type="checkbox" name="{{ name }}" {% if values.get(name) %}checked{% endif %}> {{ label }}</label>
{% endmacro %}
```

Prefs section:

```jinja
<section class="settings-section">
  <h2>Search preferences</h2>
  <p class="dim small">Just for {{ active.display_name }}. One item per line in the text boxes.</p>
  {{ err(prefs_errors, "_form") }}
  <form method="post" action="/p/{{ active.slug }}/settings/prefs/form" class="settings-form">
    <fieldset>
      <legend>What</legend>
      {{ lines_field(prefs_values, prefs_errors, "titles", "Job titles", "Matched as part of the job title.") }}
      {{ lines_field(prefs_values, prefs_errors, "seniority", "Seniority words", "Leave empty to skip the seniority check.") }}
      {{ lines_field(prefs_values, prefs_errors, "exclude_keywords", "Exclude jobs mentioning") }}
      <label class="field"><span>Minimum salary (USD, 0 for none)</span>
        <input name="comp_floor_usd" inputmode="numeric" value="{{ prefs_values.get('comp_floor_usd', 0) }}">
        {{ err(prefs_errors, "comp_floor_usd") }}</label>
    </fieldset>
    <fieldset>
      <legend>Where</legend>
      {{ location_field(prefs_values, prefs_errors, "search_locations", "Search in", "Where the job sites are searched. Pick a suggestion, or Remote.") }}
      {{ checkbox(prefs_values, "remote_ok", "Remote jobs are OK") }}
      {{ location_field(prefs_values, prefs_errors, "locations", "Keep jobs located in", "Matched as part of a job's location, so GA or a town name both work.") }}
    </fieldset>
    <fieldset>
      <legend>Sources</legend>
      {{ lines_field(prefs_values, prefs_errors, "indeed_queries", "Indeed searches") }}
      {{ lines_field(prefs_values, prefs_errors, "linkedin_queries", "LinkedIn searches") }}
      {{ lines_field(prefs_values, prefs_errors, "glassdoor_queries", "Glassdoor searches") }}
      {{ lines_field(prefs_values, prefs_errors, "wellfound_queries", "Wellfound searches") }}
      {{ lines_field(prefs_values, prefs_errors, "otta_queries", "Otta searches") }}
      {{ lines_field(prefs_values, prefs_errors, "greenhouse_companies", "Greenhouse companies") }}
      {{ lines_field(prefs_values, prefs_errors, "lever_companies", "Lever companies") }}
      {{ lines_field(prefs_values, prefs_errors, "ashby_companies", "Ashby companies") }}
      {{ lines_field(prefs_values, prefs_errors, "workable_companies", "Workable companies") }}
      {{ lines_field(prefs_values, prefs_errors, "smartrecruiters_companies", "SmartRecruiters companies") }}
      {{ lines_field(prefs_values, prefs_errors, "rss_urls", "RSS feed URLs") }}
      {{ checkbox(prefs_values, "hn_enabled", "HN Who's Hiring") }}
      {{ checkbox(prefs_values, "remoteok_enabled", "RemoteOK") }}
      {{ checkbox(prefs_values, "remotive_enabled", "Remotive") }}
    </fieldset>
    <div><button type="submit">Save preferences</button></div>
  </form>
</section>
```

- [ ] **Step 9: `static/settings.js`**

```javascript
// Location inputs on the settings page: add/remove rows, and fill the shared
// #place-options datalist with suggestions as you type.
let placeTimer;

document.addEventListener("input", (e) => {
  if (!e.target.matches('input[list="place-options"]')) return;
  clearTimeout(placeTimer);
  placeTimer = setTimeout(async () => {
    const r = await fetch("/places?q=" + encodeURIComponent(e.target.value));
    document.getElementById("place-options").innerHTML = await r.text();
  }, 200);
});

document.addEventListener("click", (e) => {
  const add = e.target.closest("[data-add-location]");
  if (add) {
    const list = add.previousElementSibling;
    const row = list.querySelector(".location-row").cloneNode(true);
    row.querySelector("input").value = "";
    list.append(row);
    row.querySelector("input").focus();
    return;
  }
  const remove = e.target.closest("[data-remove-location]");
  if (remove) {
    const row = remove.closest(".location-row");
    // Keep one row so there is always somewhere to type.
    if (row.parentElement.children.length > 1) row.remove();
    else row.querySelector("input").value = "";
  }
});
```

- [ ] **Step 10: CSS** (append to `style.css`)

```css
.settings-form fieldset { border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: var(--gap); }
.settings-form .field { display: flex; flex-direction: column; gap: 0.25rem; margin-bottom: 0.75rem; max-width: 40rem; }
.settings-form .field textarea, .settings-form .field input { width: 100%; }
.settings-form .check { display: block; margin-bottom: 0.5rem; }
.location-row { display: flex; gap: 0.5rem; margin-bottom: 0.25rem; }
.location-row input { flex: 1; }
```

- [ ] **Step 11: Run new and existing settings tests, expect PASS. Run ruff, mypy.**

- [ ] **Step 12: Commit** - `feat: edit search preferences through a form`

---

### Task 6: Config form

**Files:**
- Modify: `shortlist_web/settings_forms.py`, `shortlist_web/routes/settings.py`, `shortlist_web/templates/settings.html`
- Test: append to `tests/unit/test_settings_forms.py` and `tests/integration/test_web_settings_forms.py`

**Interfaces:**
- Produces: `CONFIG_FIELDS: Mapping[str, tuple[str, str]]` (form name to section/key), `CONFIG_ERROR_NAMES`, `CONFIG_HEADER`, `config_data(form: FormData, current: dict[str, Any]) -> dict[str, Any]`, `config_values(current: dict[str, Any]) -> dict[str, object]`, `current_config(text: str | None) -> dict[str, Any]`.

- [ ] **Step 1: Unit test**

```python
def test_config_data_updates_only_form_fields() -> None:
    current = {
        "anthropic": {"key_source": "env", "key_env_var": "OLD"},
        "budget": {"daily_usd": 5.0, "monthly_usd": 60.0},
        "sources": {"rss": {"enabled": True}},
    }
    data = sf.config_data(_form(key_env_var="NEW", daily_usd="6", pdf_template=""), current)
    assert data["anthropic"] == {"key_source": "env", "key_env_var": "NEW"}
    assert data["budget"]["daily_usd"] == "6"
    assert data["sources"] == {"rss": {"enabled": True}}
    assert data["paths"]["pdf_template"] is None
    assert current["anthropic"]["key_env_var"] == "OLD"  # input not mutated
```

- [ ] **Step 2: Integration tests** (add `import yaml` and `from shortlist import paths`, `from shortlist.config import DEFAULT_CONFIG_YAML`)

```python
CONFIG_FORM = {
    "key_env_var": "ANTHROPIC_API_KEY",
    "daily_usd": "6",
    "monthly_usd": "60",
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "rerank_model": "claude-haiku-4-5-20251001",
    "top_k_for_llm_rerank": "30",
    "tailor_model": "claude-sonnet-4-6",
    "cover_paragraphs": "3",
    "pdf_template": "",
}


def _write_default_config() -> None:
    paths.config_path().parent.mkdir(parents=True, exist_ok=True)
    paths.config_path().write_text(DEFAULT_CONFIG_YAML)


def test_config_form_keeps_fields_it_does_not_show(client: TestClient) -> None:
    _write_default_config()
    r = client.post("/p/kat/settings/config/form", data=CONFIG_FORM)
    assert r.status_code == 200
    saved = yaml.safe_load(paths.config_path().read_text())
    before = yaml.safe_load(DEFAULT_CONFIG_YAML)
    assert saved["sources"] == before["sources"]
    assert saved["anthropic"]["key_source"] == "env"
    assert saved["budget"]["daily_usd"] == 6.0
    assert "pdf_template" not in saved.get("paths", {})


def test_config_form_bad_number_writes_nothing(client: TestClient) -> None:
    _write_default_config()
    r = client.post("/p/kat/settings/config/form", data=CONFIG_FORM | {"daily_usd": "-1"})
    assert r.status_code == 400
    assert 'value="-1"' in r.text
    assert paths.config_path().read_text() == DEFAULT_CONFIG_YAML


def test_config_form_creates_missing_file(client: TestClient) -> None:
    assert not paths.config_path().exists()
    assert client.post("/p/kat/settings/config/form", data=CONFIG_FORM).status_code == 200
    assert paths.config_path().exists()
```

- [ ] **Step 3: Run, expect FAIL.**

- [ ] **Step 4: Implement in `settings_forms.py`**

```python
import copy
from typing import Any

from shortlist.config import DEFAULT_CONFIG_YAML

CONFIG_HEADER = "# Shortlist configuration. Saved from the settings form.\n"

# Form field name -> (section, key) in config.yaml. Anything not listed here
# (anthropic.key_source, sources, legacy paths) is never shown and is kept.
CONFIG_FIELDS: Mapping[str, tuple[str, str]] = {
    "key_env_var": ("anthropic", "key_env_var"),
    "daily_usd": ("budget", "daily_usd"),
    "monthly_usd": ("budget", "monthly_usd"),
    "embedding_model": ("ranker", "embedding_model"),
    "rerank_model": ("ranker", "rerank_model"),
    "top_k_for_llm_rerank": ("ranker", "top_k_for_llm_rerank"),
    "tailor_model": ("tailor", "model"),
    "cover_paragraphs": ("tailor", "cover_paragraphs"),
    "pdf_template": ("paths", "pdf_template"),
}
CONFIG_ERROR_NAMES: Mapping[tuple[str, ...], str] = {
    path: name for name, path in CONFIG_FIELDS.items()
}


def config_data(form: FormData, current: dict[str, Any]) -> dict[str, Any]:
    """`current` config with the form's fields replaced; `current` is not changed."""
    data = copy.deepcopy(current)
    for name, (section, key) in CONFIG_FIELDS.items():
        value: str | None = str(form.get(name, "")).strip()
        if name == "pdf_template" and not value:
            value = None  # optional path: empty means unset
        data.setdefault(section, {})[key] = value
    return data


def config_values(current: dict[str, Any]) -> dict[str, object]:
    """Form values read out of a config dict."""
    return {
        name: (current.get(section) or {}).get(key)
        for name, (section, key) in CONFIG_FIELDS.items()
    }


def current_config(text: str | None) -> dict[str, Any]:
    """The config file's data, or the built-in default when there is no file."""
    data = yaml.safe_load(text if text is not None else DEFAULT_CONFIG_YAML)
    return data if isinstance(data, dict) else {}
```

`to_yaml` with `exclude_none=True` drops `pdf_template: None`, matching the integration test.

- [ ] **Step 5: Route**

```python
@router.post("/settings/config/form", response_class=HTMLResponse)
async def save_config_form(
    request: Request, profile: Profile = Depends(profile_dep)
) -> HTMLResponse:
    path = paths.config_path()
    try:
        current = settings_forms.current_config(path.read_text() if path.exists() else None)
    except yaml.YAMLError as exc:
        message = f"config.yaml is not valid YAML ({exc}); fix it under Advanced."
        return _render_settings(request, profile, config_errors={"_form": message}, code=400)
    data = settings_forms.config_data(await request.form(), current)
    try:
        config = Config.model_validate(data)
    except ValidationError as exc:
        errors = settings_forms.field_errors(exc, settings_forms.CONFIG_ERROR_NAMES)
        submitted = settings_forms.config_values(data)
        return _render_settings(
            request, profile, config_values=submitted, config_errors=errors, code=400
        )
    _write_with_backup(path, settings_forms.to_yaml(settings_forms.CONFIG_HEADER, config))
    return _render_settings(request, profile, note="Saved.")
```

`_render_settings` gains `config_values` and `config_errors` keyword arguments; when `config_values` is None it reads them from disk through `current_config`, catching `yaml.YAMLError` into a `"_form"` error the same way prefs does.

- [ ] **Step 6: Template** - config section after the prefs section:

```jinja
{% macro text_field(values, errors, name, label) %}
<label class="field"><span>{{ label }}</span>
  <input name="{{ name }}" value="{{ values.get(name) if values.get(name) is not none else '' }}">
  {{ err(errors, name) }}</label>
{% endmacro %}

<section class="settings-section">
  <h2>Shared configuration</h2>
  <p class="dim small">Used by every profile. The API key itself is never stored here, only the name of the environment variable that holds it.</p>
  {{ err(config_errors, "_form") }}
  <form method="post" action="/p/{{ active.slug }}/settings/config/form" class="settings-form">
    <fieldset>
      <legend>Anthropic and budget</legend>
      {{ text_field(config_values, config_errors, "key_env_var", "API key environment variable") }}
      {{ text_field(config_values, config_errors, "daily_usd", "Daily budget (USD)") }}
      {{ text_field(config_values, config_errors, "monthly_usd", "Monthly budget (USD)") }}
    </fieldset>
    <fieldset>
      <legend>Models</legend>
      {{ text_field(config_values, config_errors, "embedding_model", "Embedding model") }}
      {{ text_field(config_values, config_errors, "rerank_model", "Rerank model") }}
      {{ text_field(config_values, config_errors, "top_k_for_llm_rerank", "Jobs sent to the rerank model") }}
      {{ text_field(config_values, config_errors, "tailor_model", "Tailoring model") }}
      {{ text_field(config_values, config_errors, "cover_paragraphs", "Cover letter paragraphs") }}
    </fieldset>
    <fieldset>
      <legend>Files</legend>
      {{ text_field(config_values, config_errors, "pdf_template", "PDF template path (optional)") }}
    </fieldset>
    <div><button type="submit">Save configuration</button></div>
  </form>
</section>
```

- [ ] **Step 7: Run all tests, ruff, mypy, expect PASS.**

- [ ] **Step 8: Commit** - `feat: edit shared configuration through a form`

---

### Task 7: Finish

- [ ] Full suite, `ruff check`, `ruff format --check`, `mypy`.
- [ ] Add `search_locations: ["Brunswick, GA", "Remote"]` to Katherine's prefs (local data, not committed); verify it loads.
- [ ] Restart the dev server with the API key scoped to its process; check `/p/katherine/settings` renders and `/places?q=brun` answers.
- [ ] Update the spec status line to "implemented"; commit.
