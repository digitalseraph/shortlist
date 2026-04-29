# Shortlist — Plan 5 of 6 (Scraped Aggregators)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **⚠️ HIGH-RISK PLAN.** Indeed/LinkedIn/Glassdoor actively detect and block scraping. Implementations are **brittle by nature** — selectors will break, IPs will get banned, captchas will appear. Plan-1 spec §9 acknowledges this; this plan ships scrapers **disabled by default**, with stealth + rate limiting + 24h auto-cooldown. Treat as a best-effort dragnet, not a primary source. ATS APIs from Plans 1+2 remain the recommended path.

**Goal:** Add three scraped aggregator sources (Indeed, LinkedIn public job search, Glassdoor) using Playwright with browser-fingerprint stealth, per-source rate limits, and automatic 24h cooldown on ban detection. Each source ships **disabled** in `_DEFAULT_CONFIG` — users opt in explicitly.

**Architecture:** New `shortlist/sources/scraped/` package paralleling `shortlist/sources/ats/`. Each source has the same shape (`*Client`, `_normalize`, `*Source`) but the client uses Playwright + a small homegrown stealth module instead of httpx. A new `_browser.py` provides a context-managed `headless_context()` with anti-detection patches. Cooldown state lives in the existing `sources.cooldown_until` column (already from Plan 1 — no new migration). The fetch CLI/TUI worker checks `cooldown_until` before invoking each scraped source.

**Tech Stack additions:** `playwright>=1.45`. Stealth via homegrown navigator overrides — `playwright-stealth` python library is unmaintained as of 2026-01, so we ship ~30 lines of init scripts ourselves. **System dep:** `playwright install chromium` must run once after pip install.

**Decisions on Plan-4 open questions:**
- **Browser context:** ephemeral per-fetch. Cleaner, prevents cookie poisoning across runs.
- **Auth:** anonymous-only. Storing user credentials multiplies ToS risk and credential-leak risk; users can hit sites directly in their browser for richer data.
- **Captcha policy:** skip + cooldown 24h. Unattended-friendly. CLI/TUI workflow can't pause for manual solve. The user can re-enable the source after rotating IP.

**Plan-5 file map:**

```
shortlist/
├── pyproject.toml                                  (modify — playwright dep)
├── shortlist/
│   ├── store/
│   │   └── db.py                                   (modify — cooldown helpers)
│   ├── config.py                                   (modify — scraped queries fields)
│   ├── cli.py                                      (modify — _DEFAULT_PREFS + _build_sources)
│   └── sources/
│       └── scraped/
│           ├── __init__.py                         (new)
│           ├── _browser.py                         (new — Playwright + stealth)
│           ├── indeed.py                           (new)
│           ├── linkedin.py                         (new)
│           └── glassdoor.py                        (new)
├── shortlist_tui/
│   └── workers.py                                  (modify — extend _build_sources)
└── tests/
    ├── fixtures/scraped/
    │   ├── indeed_search.html                      (new — saved HTML sample)
    │   ├── linkedin_search.html                    (new)
    │   └── glassdoor_search.html                   (new)
    ├── unit/
    │   ├── test_indeed_parser.py                   (new — pure HTML parsing)
    │   ├── test_linkedin_parser.py                 (new)
    │   ├── test_glassdoor_parser.py                (new)
    │   └── test_cooldown.py                        (new — store cooldown helpers)
    └── integration/
        ├── test_scraped_browser.py                 (new — @browser, validates stealth)
        └── test_scraped_live.py                    (new — gated by RUN_LIVE=1, @browser, @live)
```

**Plan location:** `<monorepo>/docs/superpowers/plans/2026-04-29-shortlist-plan-5-scraped.md`. Task 10 migrates it.

---

## Task 1: Deps + cooldown helpers + config fields

**Files:**
- Modify: `pyproject.toml`
- Modify: `shortlist/store/db.py` (add `mark_source_cooldown`, `is_source_in_cooldown`, `clear_source_cooldown`)
- Modify: `shortlist/config.py` (add `indeed_queries`, `linkedin_queries`, `glassdoor_queries` to `Prefs`)
- Create: `tests/unit/test_cooldown.py`

- [ ] **Step 1: Update `pyproject.toml`**

In `[project] dependencies`, append:

```toml
    "playwright>=1.45",
    "beautifulsoup4>=4.12",
```

(`bs4` is needed for HTML parsing in T3-T5; pin explicitly even if pulled transitively.)

- [ ] **Step 2: Reinstall + install Chromium**

```bash
cd ~/dev/repos/shortlist
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

(`playwright install chromium` downloads a ~150MB browser to `~/.cache/ms-playwright/`. One-time.)

- [ ] **Step 3: Add cooldown helpers to `shortlist/store/db.py`**

Append:

```python
def mark_source_cooldown(path: Path, name: str, *, until: datetime) -> None:
    """Set the cooldown_until timestamp for a source."""
    with connect(path) as conn:
        conn.execute(
            """
            INSERT INTO sources (name, cooldown_until) VALUES (?, ?)
            ON CONFLICT (name) DO UPDATE SET cooldown_until = excluded.cooldown_until
            """,
            (name, _utc_iso(until)),
        )


def is_source_in_cooldown(path: Path, name: str, *, now: datetime | None = None) -> bool:
    """Return True if the source is currently cooled down."""
    now = now or datetime.now(UTC)
    with connect(path) as conn:
        row = conn.execute(
            "SELECT cooldown_until FROM sources WHERE name = ?", (name,)
        ).fetchone()
    if row is None or row[0] is None:
        return False
    until = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
    return now < until


def clear_source_cooldown(path: Path, name: str) -> None:
    """Reset cooldown_until for a source."""
    with connect(path) as conn:
        conn.execute(
            "UPDATE sources SET cooldown_until = NULL WHERE name = ?", (name,)
        )
```

- [ ] **Step 4: Extend `Prefs` in `shortlist/config.py`**

Append fields after `smartrecruiters_companies`:

```python
    indeed_queries: list[str] = Field(default_factory=list)
    linkedin_queries: list[str] = Field(default_factory=list)
    glassdoor_queries: list[str] = Field(default_factory=list)
```

Extend the `_strip` validator's argument list:

```python
    @field_validator(
        "titles", "locations", "exclude_keywords", "seniority",
        "greenhouse_companies", "lever_companies", "ashby_companies",
        "workable_companies", "smartrecruiters_companies",
        "indeed_queries", "linkedin_queries", "glassdoor_queries",
    )
```

- [ ] **Step 5: Failing tests `tests/unit/test_cooldown.py`**

```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortlist.store.db import (
    clear_source_cooldown,
    is_source_in_cooldown,
    mark_source_cooldown,
    migrate,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "db.sqlite"


def test_no_cooldown_by_default(db_path):
    migrate(db_path)
    assert is_source_in_cooldown(db_path, "indeed") is False


def test_mark_then_check_cooldown(db_path):
    migrate(db_path)
    until = datetime.now(UTC) + timedelta(hours=24)
    mark_source_cooldown(db_path, "indeed", until=until)
    assert is_source_in_cooldown(db_path, "indeed") is True


def test_expired_cooldown_returns_false(db_path):
    migrate(db_path)
    past = datetime.now(UTC) - timedelta(hours=1)
    mark_source_cooldown(db_path, "indeed", until=past)
    assert is_source_in_cooldown(db_path, "indeed") is False


def test_clear_cooldown(db_path):
    migrate(db_path)
    until = datetime.now(UTC) + timedelta(hours=24)
    mark_source_cooldown(db_path, "indeed", until=until)
    clear_source_cooldown(db_path, "indeed")
    assert is_source_in_cooldown(db_path, "indeed") is False
```

Append a test for the new Prefs fields in `tests/unit/test_config.py`:

```python
def test_prefs_includes_scraped_queries():
    p = Prefs.model_validate({
        "titles": ["Eng"], "locations": ["Remote"], "remote_ok": True,
        "comp_floor_usd": 100000, "exclude_keywords": [], "seniority": [],
        "greenhouse_companies": [],
    })
    assert p.indeed_queries == []
    assert p.linkedin_queries == []
    assert p.glassdoor_queries == []
```

- [ ] **Step 6: Run + commit**

```bash
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add pyproject.toml shortlist/store/db.py shortlist/config.py tests/unit/test_cooldown.py tests/unit/test_config.py
git commit -m "feat(store): cooldown helpers + scraped query prefs fields"
```

Expected: 5 new pass + 133 prior + 1 skip = 138 pass + 1 skip.

---

## Task 2: Browser helper with stealth

**Files:**
- Create: `shortlist/sources/scraped/__init__.py`
- Create: `shortlist/sources/scraped/_browser.py`
- Create: `tests/integration/test_scraped_browser.py` (gated by `@pytest.mark.browser`)

`_browser.py` ships ~30 lines of navigator-override init scripts run before page nav. Targets the most common automation tells: `navigator.webdriver`, `navigator.languages`, `navigator.plugins`, `chrome` object, missing-permissions API.

- [ ] **Step 1: Implement `shortlist/sources/scraped/_browser.py`**

```python
"""Playwright browser context with anti-detection patches.

Async API. Use as:

    async with headless_context() as ctx:
        page = await ctx.new_page()
        await page.goto("https://...")

The init script runs in every page created from the context, before any
site code, and patches navigator.webdriver, navigator.languages, etc.
This is best-effort — modern bot-detection (Cloudflare, Datadome,
PerimeterX) layers behavioral fingerprinting on top of these basics.
Sites WILL still detect us; the cooldown layer (T6) handles that.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from playwright.async_api import BrowserContext, async_playwright

logger = logging.getLogger(__name__)

# User agent close to default Chrome on Linux x86_64. Update yearly.
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# Init script: patch known automation tells. Runs before any site JS on
# every page. Keep small and well-tested.
_STEALTH_INIT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {
    get: () => [{name: 'Chrome PDF Viewer'}, {name: 'Native Client'}]
});
window.chrome = window.chrome || {runtime: {}};
const origQuery = window.navigator.permissions && window.navigator.permissions.query;
if (origQuery) {
    window.navigator.permissions.query = (p) => (
        p.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : origQuery(p)
    );
}
"""


@asynccontextmanager
async def headless_context(
    *, user_agent: str = _UA, timeout_ms: int = 30_000,
) -> AsyncIterator[BrowserContext]:
    """Launch a stealth-patched Chromium context. Always headless."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
        )
        await context.add_init_script(_STEALTH_INIT)
        context.set_default_timeout(timeout_ms)
        try:
            yield context
        finally:
            await context.close()
            await browser.close()
```

- [ ] **Step 2: Create `shortlist/sources/scraped/__init__.py` (empty)**

- [ ] **Step 3: Failing live smoke test**

```python
# tests/integration/test_scraped_browser.py
import pytest

from shortlist.sources.scraped._browser import headless_context


@pytest.mark.browser
@pytest.mark.asyncio
async def test_headless_context_loads_about_blank():
    async with headless_context() as ctx:
        page = await ctx.new_page()
        await page.goto("about:blank")
        title = await page.title()
        assert title == ""


@pytest.mark.browser
@pytest.mark.asyncio
async def test_navigator_webdriver_is_undefined():
    async with headless_context() as ctx:
        page = await ctx.new_page()
        await page.goto("about:blank")
        is_webdriver = await page.evaluate("navigator.webdriver")
        assert is_webdriver is None  # patched away
```

- [ ] **Step 4: Run + commit**

These tests use `@pytest.mark.browser` so default `pytest -q` skips them. Run explicitly:

```bash
.venv/bin/pytest tests/integration/test_scraped_browser.py -v -m browser
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/sources/scraped/__init__.py shortlist/sources/scraped/_browser.py tests/integration/test_scraped_browser.py
git commit -m "feat(scraped): Playwright headless context with stealth init script"
```

Expected: 138 default pass + 1 skip + 2 new browser tests pass when run with `-m browser`.

## Important nuances

- The `async_playwright()` block is required outside the `async with browser`/`context` because `async_playwright` itself is the entry point.
- `context.add_init_script` runs before every page navigation in the context — including iframes.
- `--no-sandbox` is needed for headless Chromium in many container/CI environments. Safe on a personal laptop.
- The user agent string MUST be updated yearly — Chrome version drift means a 2024 UA looks suspicious in 2027.

---

## Task 3: Indeed source

**Files:**
- Create: `shortlist/sources/scraped/indeed.py`
- Create: `tests/fixtures/scraped/indeed_search.html`
- Create: `tests/unit/test_indeed_parser.py`

The Indeed source navigates to a search URL, waits for the results list, parses anchor cards, and yields `RawJob` per posting. Selectors target the public job search page; **expect them to break quarterly**.

- [ ] **Step 1: Synthetic fixture `tests/fixtures/scraped/indeed_search.html`**

```html
<!DOCTYPE html>
<html><body>
<div id="mosaic-provider-jobcards">
  <ul class="jobsearch-ResultsList">
    <li class="result">
      <h2 class="jobTitle"><a href="/viewjob?jk=abc123" id="job_abc123">Senior Backend Engineer</a></h2>
      <span data-testid="company-name">Acme Inc</span>
      <div data-testid="text-location">Remote</div>
      <div class="job-snippet">Build distributed services in Python.</div>
      <span class="date">Posted 3 days ago</span>
    </li>
    <li class="result">
      <h2 class="jobTitle"><a href="/viewjob?jk=def456" id="job_def456">Staff SRE</a></h2>
      <span data-testid="company-name">Globex</span>
      <div data-testid="text-location">Atlanta, GA</div>
      <div class="job-snippet">Run multi-region Kubernetes at scale.</div>
      <span class="date">Posted 1 day ago</span>
    </li>
  </ul>
</div>
</body></html>
```

- [ ] **Step 2: Implement `shortlist/sources/scraped/indeed.py`**

```python
"""Indeed scraped source."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from shortlist.models import RawJob
from shortlist.sources.base import Source
from shortlist.sources.scraped._browser import headless_context

logger = logging.getLogger(__name__)

_BASE = "https://www.indeed.com/jobs"
_BAN_MARKERS = ("Verify you are human", "challenge-platform", "blocked")


class IndeedBanDetectedError(RuntimeError):
    pass


def _parse_relative_date(text: str, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    s = text.lower()
    if "just posted" in s or "today" in s:
        return now
    m = re.search(r"(\d+)\s*(hour|day|week|month)s?\s*ago", s)
    if not m:
        return now
    n = int(m.group(1))
    unit = m.group(2)
    if unit == "hour":
        return now - timedelta(hours=n)
    if unit == "day":
        return now - timedelta(days=n)
    if unit == "week":
        return now - timedelta(weeks=n)
    return now - timedelta(days=n * 30)


def _normalize_card(card: Tag) -> RawJob | None:
    title_a = card.select_one("h2.jobTitle a")
    if title_a is None:
        return None
    title = title_a.get_text(strip=True)
    href = str(title_a.get("href") or "")
    if href.startswith("/"):
        href = f"https://www.indeed.com{href}"
    jk_match = (
        re.search(r"jk=([a-zA-Z0-9]+)", href)
        or re.search(r"job_([a-zA-Z0-9]+)", str(title_a.get("id") or ""))
    )
    if jk_match is None:
        return None
    external_id = jk_match.group(1)

    company_el = card.select_one('[data-testid="company-name"]')
    location_el = card.select_one('[data-testid="text-location"]')
    snippet_el = card.select_one(".job-snippet")
    date_el = card.select_one(".date")

    location = location_el.get_text(strip=True) if location_el else ""
    posted_at = _parse_relative_date(date_el.get_text(strip=True) if date_el else "")

    return RawJob(
        source="indeed",
        external_id=external_id,
        company=(company_el.get_text(strip=True) if company_el else "Unknown"),
        title=title,
        url=href,
        posted_at=posted_at,
        location=location or None,
        remote="remote" in location.lower(),
        description_md=snippet_el.get_text(strip=True) if snippet_el else None,
    )


def parse_search_html(html: str, *, query: str) -> list[RawJob]:  # noqa: ARG001
    if any(m.lower() in html.lower() for m in _BAN_MARKERS):
        raise IndeedBanDetectedError("ban / captcha marker found in HTML")
    soup = BeautifulSoup(html, "html.parser")
    return [rj for card in soup.select("li.result")
            if (rj := _normalize_card(card)) is not None]


class IndeedSource(Source):
    name: ClassVar[str] = "indeed"

    def __init__(self, *, queries: list[str], location: str = "Remote",
                 rate_limit_seconds: float = 8.0):
        self._queries = queries
        self._location = location
        self._rate = rate_limit_seconds

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        return iter(asyncio.run(self._fetch_all()))

    async def _fetch_all(self) -> list[RawJob]:
        out: list[RawJob] = []
        async with headless_context() as ctx:
            page = await ctx.new_page()
            for q in self._queries:
                url = f"{_BASE}?{urlencode({'q': q, 'l': self._location})}"
                logger.info("indeed: fetching %s", url)
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_selector("li.result", timeout=15_000)
                except Exception as e:  # noqa: BLE001
                    logger.warning("indeed: page load failed for %r: %s", q, e)
                    continue
                html = await page.content()
                out.extend(parse_search_html(html, query=q))
                await asyncio.sleep(self._rate)
        return out
```

- [ ] **Step 3: Failing parser tests**

```python
# tests/unit/test_indeed_parser.py
from pathlib import Path

import pytest

from shortlist.models import RawJob
from shortlist.sources.scraped.indeed import IndeedBanDetectedError, parse_search_html

FIXTURES = Path(__file__).parent.parent / "fixtures/scraped"


def test_parse_synthetic_indeed_search():
    html = (FIXTURES / "indeed_search.html").read_text()
    jobs = parse_search_html(html, query="senior backend")
    assert len(jobs) == 2
    j0 = jobs[0]
    assert isinstance(j0, RawJob)
    assert j0.source == "indeed"
    assert j0.external_id == "abc123"
    assert j0.title == "Senior Backend Engineer"
    assert j0.company == "Acme Inc"
    assert j0.remote is True
    assert "Build distributed" in (j0.description_md or "")


def test_parse_detects_ban_marker():
    html = "<html><body>Verify you are human before continuing</body></html>"
    with pytest.raises(IndeedBanDetectedError):
        parse_search_html(html, query="x")


def test_parse_handles_missing_optional_fields():
    html = """
    <ul class="jobsearch-ResultsList">
      <li class="result">
        <h2 class="jobTitle"><a href="/viewjob?jk=zzz" id="job_zzz">Some Title</a></h2>
      </li>
    </ul>
    """
    jobs = parse_search_html(html, query="x")
    assert len(jobs) == 1
    assert jobs[0].title == "Some Title"
    assert jobs[0].company == "Unknown"
    assert jobs[0].location is None
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_indeed_parser.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/sources/scraped/indeed.py tests/unit/test_indeed_parser.py tests/fixtures/scraped/indeed_search.html
git commit -m "feat(scraped/indeed): Indeed parser + Source with ban detection"
```

Expected: 3 new pass + 138 prior + 1 skip = 141 pass + 1 skip.

## Important nuances

- `IndeedSource.fetch()` is sync (matches `Source` ABC) but wraps async `_fetch_all` via `asyncio.run`. This means scraped sources can't be called from inside an existing event loop — TUI must dispatch them in a thread (already the case via `@work(thread=True)` workers from Plan 4).
- `wait_for_selector("li.result", timeout=15_000)` waits up to 15s for results to render. If Indeed returns a ban page, the selector won't appear; we catch the timeout and skip.

---

## Task 4: LinkedIn source

**Files:**
- Create: `shortlist/sources/scraped/linkedin.py`
- Create: `tests/fixtures/scraped/linkedin_search.html`
- Create: `tests/unit/test_linkedin_parser.py`

LinkedIn's public guest job search is at `https://www.linkedin.com/jobs/search?keywords=<q>&location=<l>`. Public guest results are limited (paginated, often paywalled after page 2) but parseable.

- [ ] **Step 1: Synthetic fixture `tests/fixtures/scraped/linkedin_search.html`**

```html
<!DOCTYPE html>
<html><body>
<ul class="jobs-search__results-list">
  <li>
    <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/3987654321/">
      <span class="sr-only">Senior Backend Engineer</span>
    </a>
    <h3 class="base-search-card__title">Senior Backend Engineer</h3>
    <h4 class="base-search-card__subtitle">Acme Inc</h4>
    <span class="job-search-card__location">Remote</span>
    <time class="job-search-card__listdate" datetime="2026-04-25">3 days ago</time>
  </li>
  <li>
    <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/3987654322/">
      <span class="sr-only">Staff Engineer</span>
    </a>
    <h3 class="base-search-card__title">Staff Engineer</h3>
    <h4 class="base-search-card__subtitle">Globex</h4>
    <span class="job-search-card__location">Atlanta, GA</span>
    <time class="job-search-card__listdate" datetime="2026-04-26">1 day ago</time>
  </li>
</ul>
</body></html>
```

- [ ] **Step 2: Implement `shortlist/sources/scraped/linkedin.py`**

```python
"""LinkedIn public guest jobs search."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from shortlist.models import RawJob
from shortlist.sources.base import Source
from shortlist.sources.scraped._browser import headless_context

logger = logging.getLogger(__name__)

_BASE = "https://www.linkedin.com/jobs/search"
_BAN_MARKERS = (
    "authwall", "request a verification", "/checkpoint/challenge",
    "rate limit", "Sign in to continue",
)


class LinkedInBanDetectedError(RuntimeError):
    pass


def _parse_card(card: Tag) -> RawJob | None:
    a = card.select_one("a.base-card__full-link")
    title_el = card.select_one(".base-search-card__title")
    company_el = card.select_one(".base-search-card__subtitle")
    location_el = card.select_one(".job-search-card__location")
    date_el = card.select_one("time.job-search-card__listdate")

    if a is None or title_el is None:
        return None
    href = str(a.get("href") or "")
    m = re.search(r"/jobs/view/(\d+)", href)
    if m is None:
        return None
    external_id = m.group(1)

    location = location_el.get_text(strip=True) if location_el else ""
    posted_at = (
        datetime.fromisoformat(str(date_el["datetime"])).replace(tzinfo=UTC)
        if date_el is not None and date_el.get("datetime") else datetime.now(UTC)
    )
    return RawJob(
        source="linkedin",
        external_id=external_id,
        company=company_el.get_text(strip=True) if company_el else "Unknown",
        title=title_el.get_text(strip=True),
        url=href,
        posted_at=posted_at,
        location=location or None,
        remote="remote" in location.lower(),
    )


def parse_search_html(html: str) -> list[RawJob]:
    if any(m.lower() in html.lower() for m in _BAN_MARKERS):
        raise LinkedInBanDetectedError("ban / authwall marker found")
    soup = BeautifulSoup(html, "html.parser")
    return [rj for card in soup.select("ul.jobs-search__results-list > li")
            if (rj := _parse_card(card)) is not None]


class LinkedInSource(Source):
    name: ClassVar[str] = "linkedin"

    def __init__(self, *, queries: list[str], location: str = "United States",
                 rate_limit_seconds: float = 15.0, max_pages: int = 2):
        self._queries = queries
        self._location = location
        self._rate = rate_limit_seconds
        self._max_pages = max_pages

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        return iter(asyncio.run(self._fetch_all()))

    async def _fetch_all(self) -> list[RawJob]:
        out: list[RawJob] = []
        async with headless_context() as ctx:
            page = await ctx.new_page()
            for q in self._queries:
                for p in range(self._max_pages):
                    params = {"keywords": q, "location": self._location, "start": p * 25}
                    url = f"{_BASE}?{urlencode(params)}"
                    logger.info("linkedin: fetching %s", url)
                    try:
                        await page.goto(url, wait_until="domcontentloaded")
                        await page.wait_for_selector(
                            "ul.jobs-search__results-list", timeout=15_000
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.warning("linkedin: load failed: %s", e)
                        break
                    html = await page.content()
                    out.extend(parse_search_html(html))
                    await asyncio.sleep(self._rate)
        return out
```

- [ ] **Step 3: Failing parser tests**

```python
# tests/unit/test_linkedin_parser.py
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.sources.scraped.linkedin import (
    LinkedInBanDetectedError,
    parse_search_html,
)

FIXTURES = Path(__file__).parent.parent / "fixtures/scraped"


def test_parse_synthetic_linkedin_search():
    html = (FIXTURES / "linkedin_search.html").read_text()
    jobs = parse_search_html(html)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "linkedin"
    assert j0.external_id == "3987654321"
    assert j0.title == "Senior Backend Engineer"
    assert j0.company == "Acme Inc"
    assert j0.remote is True
    assert j0.posted_at == datetime(2026, 4, 25, 0, 0, tzinfo=UTC)


def test_parse_detects_authwall():
    html = "<html><body>authwall: Sign in to continue browsing.</body></html>"
    with pytest.raises(LinkedInBanDetectedError):
        parse_search_html(html)
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_linkedin_parser.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/sources/scraped/linkedin.py tests/unit/test_linkedin_parser.py tests/fixtures/scraped/linkedin_search.html
git commit -m "feat(scraped/linkedin): LinkedIn guest search parser + Source"
```

Expected: 2 new pass + 141 prior + 1 skip = 143 pass + 1 skip.

---

## Task 5: Glassdoor source

**Files:**
- Create: `shortlist/sources/scraped/glassdoor.py`
- Create: `tests/fixtures/scraped/glassdoor_search.html`
- Create: `tests/unit/test_glassdoor_parser.py`

Glassdoor's structure changes more often than the others; this is the most fragile of the three. URL: `https://www.glassdoor.com/Job/jobs.htm?sc.keyword=<q>&locKeyword=<l>`.

- [ ] **Step 1: Synthetic fixture `tests/fixtures/scraped/glassdoor_search.html`**

```html
<!DOCTYPE html>
<html><body>
<ul aria-label="Jobs List" class="JobsList_jobsList">
  <li data-test="jobListing">
    <a data-test="job-title" href="/job-listing/senior-backend-acme-JV_KO0,22.htm?jl=1234567890" data-id="1234567890">Senior Backend Engineer</a>
    <div data-test="employer-name">Acme Inc</div>
    <div data-test="emp-location">Remote</div>
    <div class="JobCard_jobDescriptionSnippet">Build distributed services in Python.</div>
    <div data-test="job-age">3d</div>
  </li>
  <li data-test="jobListing">
    <a data-test="job-title" href="/job-listing/staff-engineer-globex-JV_KO0,15.htm?jl=1234567891" data-id="1234567891">Staff Engineer</a>
    <div data-test="employer-name">Globex</div>
    <div data-test="emp-location">Atlanta, GA</div>
    <div class="JobCard_jobDescriptionSnippet">Architecture leadership.</div>
    <div data-test="job-age">1d</div>
  </li>
</ul>
</body></html>
```

- [ ] **Step 2: Implement `shortlist/sources/scraped/glassdoor.py`**

```python
"""Glassdoor public job search."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from shortlist.models import RawJob
from shortlist.sources.base import Source
from shortlist.sources.scraped._browser import headless_context

logger = logging.getLogger(__name__)

_BASE = "https://www.glassdoor.com/Job/jobs.htm"
_BAN_MARKERS = ("captcha", "Access Denied", "blocked")


class GlassdoorBanDetectedError(RuntimeError):
    pass


def _parse_age(s: str, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    m = re.match(r"^(\d+)\s*([hdmw])", s.strip().lower())
    if not m:
        return now
    n = int(m.group(1))
    unit = m.group(2)
    if unit == "h":
        return now - timedelta(hours=n)
    if unit == "d":
        return now - timedelta(days=n)
    if unit == "w":
        return now - timedelta(weeks=n)
    if unit == "m":
        return now - timedelta(days=n * 30)
    return now


def _parse_card(card: Tag) -> RawJob | None:
    a = card.select_one('a[data-test="job-title"]')
    company_el = card.select_one('[data-test="employer-name"]')
    location_el = card.select_one('[data-test="emp-location"]')
    snippet_el = card.select_one(".JobCard_jobDescriptionSnippet")
    age_el = card.select_one('[data-test="job-age"]')

    if a is None:
        return None
    title = a.get_text(strip=True)
    href = str(a.get("href") or "")
    if href.startswith("/"):
        href = f"https://www.glassdoor.com{href}"
    external_id = str(a.get("data-id") or "")
    if not external_id:
        m = re.search(r"jl=(\d+)", href)
        if m is None:
            return None
        external_id = m.group(1)

    location = location_el.get_text(strip=True) if location_el else ""
    return RawJob(
        source="glassdoor",
        external_id=external_id,
        company=company_el.get_text(strip=True) if company_el else "Unknown",
        title=title,
        url=href,
        posted_at=_parse_age(age_el.get_text(strip=True) if age_el else ""),
        location=location or None,
        remote="remote" in location.lower(),
        description_md=snippet_el.get_text(strip=True) if snippet_el else None,
    )


def parse_search_html(html: str) -> list[RawJob]:
    if any(m.lower() in html.lower() for m in _BAN_MARKERS):
        raise GlassdoorBanDetectedError("ban marker found")
    soup = BeautifulSoup(html, "html.parser")
    return [rj for card in soup.select('li[data-test="jobListing"]')
            if (rj := _parse_card(card)) is not None]


class GlassdoorSource(Source):
    name: ClassVar[str] = "glassdoor"

    def __init__(self, *, queries: list[str], location: str = "Remote",
                 rate_limit_seconds: float = 10.0):
        self._queries = queries
        self._location = location
        self._rate = rate_limit_seconds

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        return iter(asyncio.run(self._fetch_all()))

    async def _fetch_all(self) -> list[RawJob]:
        out: list[RawJob] = []
        async with headless_context() as ctx:
            page = await ctx.new_page()
            for q in self._queries:
                params = {"sc.keyword": q, "locKeyword": self._location}
                url = f"{_BASE}?{urlencode(params)}"
                logger.info("glassdoor: fetching %s", url)
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_selector(
                        'li[data-test="jobListing"]', timeout=15_000
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("glassdoor: load failed: %s", e)
                    continue
                html = await page.content()
                out.extend(parse_search_html(html))
                await asyncio.sleep(self._rate)
        return out
```

- [ ] **Step 3: Failing tests**

```python
# tests/unit/test_glassdoor_parser.py
from pathlib import Path

import pytest

from shortlist.sources.scraped.glassdoor import (
    GlassdoorBanDetectedError,
    parse_search_html,
)

FIXTURES = Path(__file__).parent.parent / "fixtures/scraped"


def test_parse_synthetic_glassdoor():
    html = (FIXTURES / "glassdoor_search.html").read_text()
    jobs = parse_search_html(html)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "glassdoor"
    assert j0.external_id == "1234567890"
    assert j0.company == "Acme Inc"
    assert j0.remote is True


def test_parse_detects_captcha():
    html = "<html><body>captcha: please verify</body></html>"
    with pytest.raises(GlassdoorBanDetectedError):
        parse_search_html(html)
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_glassdoor_parser.py -v
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/sources/scraped/glassdoor.py tests/unit/test_glassdoor_parser.py tests/fixtures/scraped/glassdoor_search.html
git commit -m "feat(scraped/glassdoor): Glassdoor parser + Source"
```

Expected: 2 new pass + 143 prior + 1 skip = 145 pass + 1 skip.

---

## Task 6: Wire scraped sources into fetch + cooldown

**Files:**
- Modify: `shortlist/cli.py` (`_DEFAULT_PREFS`, `_DEFAULT_CONFIG`, `_build_sources`, `fetch`)
- Modify: `shortlist_tui/workers.py` (`_build_sources`, `fetch_all`)
- Modify: `tests/integration/test_cli.py` (cooldown skip test)

- [ ] **Step 1: Update `_DEFAULT_PREFS` in `shortlist/cli.py`**

Append to the `_DEFAULT_PREFS` YAML string after `smartrecruiters_companies: []`:

```yaml
indeed_queries: []
linkedin_queries: []
glassdoor_queries: []
```

In `_DEFAULT_CONFIG`'s `sources:` block, append (each disabled by default):

```yaml
  indeed:
    enabled: false
    rate_limit_rpm: 6
  linkedin:
    enabled: false
    rate_limit_rpm: 4
  glassdoor:
    enabled: false
    rate_limit_rpm: 6
```

- [ ] **Step 2: Update `_build_sources` in `shortlist/cli.py`**

Append after the existing 5 ATS clauses:

```python
from shortlist.sources.scraped.glassdoor import GlassdoorSource
from shortlist.sources.scraped.indeed import IndeedSource
from shortlist.sources.scraped.linkedin import LinkedInSource


def _build_sources(prefs: Prefs) -> list[Source]:
    sources: list[Source] = []  # existing 5 ATS clauses preserved
    # ... existing greenhouse/lever/ashby/workable/smartrecruiters ...
    if prefs.indeed_queries:
        sources.append(IndeedSource(queries=prefs.indeed_queries))
    if prefs.linkedin_queries:
        sources.append(LinkedInSource(queries=prefs.linkedin_queries))
    if prefs.glassdoor_queries:
        sources.append(GlassdoorSource(queries=prefs.glassdoor_queries))
    return sources
```

- [ ] **Step 3: Update `fetch` in `shortlist/cli.py` to honor cooldown + ban detection**

Add imports:

```python
from datetime import timedelta

from shortlist.sources.scraped.glassdoor import GlassdoorBanDetectedError
from shortlist.sources.scraped.indeed import IndeedBanDetectedError
from shortlist.sources.scraped.linkedin import LinkedInBanDetectedError
```

In the `fetch()` source-loop, before invoking `src.fetch`:

```python
for src in _build_sources(prefs):
    if store_db.is_source_in_cooldown(db, src.name):
        console.print(f"[dim]{src.name} in cooldown, skipping[/dim]")
        continue
    try:
        for raw in src.fetch(since=store_db.source_last_fetched(db, src.name)):
            store_db.upsert_job(db, raw)
            total += 1
        store_db.mark_source_fetched(db, src.name, datetime.now(timezone.utc))
    except (IndeedBanDetectedError, LinkedInBanDetectedError, GlassdoorBanDetectedError):
        until = datetime.now(timezone.utc) + timedelta(hours=24)
        store_db.mark_source_cooldown(db, src.name, until=until)
        console.print(f"[red]{src.name} banned — cooled down until {until.isoformat()}[/red]")
    except Exception as e:  # noqa: BLE001
        console.print(f"[yellow]{src.name} error:[/yellow] {e}")
```

- [ ] **Step 4: Mirror `_build_sources` updates in `shortlist_tui/workers.py`**

Same diff as Step 2. Update `fetch_all`:

```python
def fetch_all(db_path: Path, prefs: Prefs) -> str:
    total = 0
    errors: list[str] = []
    cooled: list[str] = []
    for src in _build_sources(prefs):
        if store_db.is_source_in_cooldown(db_path, src.name):
            cooled.append(src.name)
            continue
        try:
            for raw in src.fetch(since=store_db.source_last_fetched(db_path, src.name)):
                store_db.upsert_job(db_path, raw)
                total += 1
            store_db.mark_source_fetched(db_path, src.name, datetime.now(UTC))
        except (IndeedBanDetectedError, LinkedInBanDetectedError, GlassdoorBanDetectedError):
            from datetime import timedelta
            store_db.mark_source_cooldown(
                db_path, src.name,
                until=datetime.now(UTC) + timedelta(hours=24),
            )
            errors.append(f"{src.name}: banned, cooled 24h")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{src.name}: {e}")
    parts = [f"fetched {total} jobs"]
    if cooled:
        parts.append(f"({len(cooled)} cooled)")
    if errors:
        parts.append(f"({len(errors)} errors)")
    return " ".join(parts)
```

- [ ] **Step 5: Append failing test**

```python
def test_fetch_skips_source_in_cooldown(env, monkeypatch):
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    (cfg / "prefs.yaml").write_text(
        (cfg / "prefs.yaml").read_text().replace(
            "indeed_queries: []",
            "indeed_queries:\n  - python backend",
        )
    )
    runner.invoke(app, ["db", "init"])
    from datetime import UTC, datetime, timedelta

    from shortlist.store.db import mark_source_cooldown
    mark_source_cooldown(
        data / "db.sqlite", "indeed",
        until=datetime.now(UTC) + timedelta(hours=24),
    )

    result = runner.invoke(app, ["fetch"])
    assert result.exit_code == 0, result.output
    assert ("cooldown" in result.output.lower()
            or "cooled" in result.output.lower()
            or "skipping" in result.output.lower())
```

- [ ] **Step 6: Run + commit**

```bash
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/cli.py shortlist_tui/workers.py tests/integration/test_cli.py
git commit -m "feat(scraped): wire Indeed/LinkedIn/Glassdoor + cooldown enforcement"
```

Expected: 1 new pass + 145 prior + 1 skip = 146 pass + 1 skip.

## Important nuances

- Scraped sources are **disabled by default** in `_DEFAULT_CONFIG` AND require non-empty `*_queries` in `prefs.yaml`. Two-key requirement is intentional friction.
- The cooldown is 24 hours from ban detection. Users can manually clear via `shortlist sources clear-cooldown <name>` (T9).
- Bans propagate as exceptions from the source's `fetch()` iterator. The CLI/worker catches and converts to a cooldown row in `sources` table.

---

## Task 7: Live smoke (gated)

**Files:**
- Create: `tests/integration/test_scraped_live.py`

These tests hit real Indeed/LinkedIn/Glassdoor. They:

- Use `@pytest.mark.browser` AND `@pytest.mark.live` (need both opt-ins)
- Skip unless `RUN_LIVE=1`
- Tolerate failures (real sites may ban us during the test run)

- [ ] **Step 1: Write live tests**

```python
# tests/integration/test_scraped_live.py
import os

import pytest

from shortlist.sources.scraped.indeed import IndeedBanDetectedError, IndeedSource

LIVE = os.environ.get("RUN_LIVE") == "1"
pytestmark = [
    pytest.mark.browser,
    pytest.mark.live,
    pytest.mark.skipif(not LIVE, reason="RUN_LIVE=1 required"),
]


def test_indeed_live_returns_some_results_or_bans():
    """Either a few jobs or a ban — both acceptable outcomes."""
    src = IndeedSource(queries=["senior backend engineer"], location="Remote",
                       rate_limit_seconds=2.0)
    try:
        jobs = list(src.fetch(since=None))
    except IndeedBanDetectedError:
        pytest.skip("Indeed banned us — expected sometimes")
        return
    if jobs:
        assert all(j.source == "indeed" for j in jobs)
        assert all(j.title for j in jobs)
```

(Mirror tests for LinkedIn + Glassdoor — same shape.)

- [ ] **Step 2: Run + commit (do not run live)**

```bash
.venv/bin/pytest -q  # will skip these
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add tests/integration/test_scraped_live.py
git commit -m "test(scraped): live smoke tests gated by RUN_LIVE=1"
```

Expected: tests skip; suite stays at 146 pass + skips include new live skips.

---

## Task 8: README + warnings

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Replace "Plan 4 of 6" status block with:

```markdown
This is **Plan 5 of 6** (scraped aggregators). Cumulative status:

- ✅ Plan 1 (foundation): Greenhouse + SQLite + hard filter + CLI
- ✅ Plan 2: Lever, Ashby, Workable, SmartRecruiters; embeddings via `sentence-transformers`; Haiku 4.5 rerank with budget guard
- ✅ Plan 3: Sonnet 4.6 per-job tailoring; pandoc → PDF; status state machine; contacts CRUD
- ✅ Plan 4: Textual TUI — JobList, JobDetail, ApplicationsBoard, Settings; vim-style key bindings; live search
- ✅ Plan 5 (this): Scraped aggregators — Indeed, LinkedIn, Glassdoor via Playwright + stealth; 24h auto-cooldown on ban; **disabled by default**
- ⏳ Plan 6: curated boards (HN/Wellfound/Otta/RemoteOK) + RSS + release polish
```

Add a "Scraped sources" warning section after "TUI key bindings":

```markdown
## Scraped sources (Indeed, LinkedIn, Glassdoor)

These sources ship **disabled by default** and require explicit opt-in:

1. Set `enabled: true` in the relevant `sources:` block in `~/.config/shortlist/config.yaml`.
2. Add at least one query string to `*_queries` in `~/.config/shortlist/prefs.yaml`:
   ```yaml
   indeed_queries:
     - "senior backend engineer"
   linkedin_queries:
     - "platform engineer"
   ```
3. Run `playwright install chromium` once.

**Expect breakage.** The three sites detect headless browsers and ban
aggressively. When detected, the source enters a 24-hour cooldown
recorded in `sources.cooldown_until`. Fetches will skip cooled sources
silently. Manually clear via `shortlist sources clear-cooldown indeed`
(or wait it out, or rotate IP).

ATS APIs from Plans 1+2 (Greenhouse/Lever/Ashby/Workable/SmartRecruiters)
remain the recommended primary path. Scrapers are a best-effort dragnet.
```

In "Testing" section append:

```markdown
- `RUN_LIVE=1 .venv/bin/pytest -m "browser and live"` — opt-in live scrape smoke (real Indeed/LinkedIn/Glassdoor; expect occasional bans)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README — Plan 5 features + scraped source warnings"
```

---

## Task 9: `sources` CLI subgroup

**Files:**
- Modify: `shortlist/cli.py` (add `sources` subgroup with `clear-cooldown`, `status`)
- Modify: `tests/integration/test_cli.py`

- [ ] **Step 1: Add `sources` subgroup**

```python
sources_app = typer.Typer(help="Manage source cooldown state.")
app.add_typer(sources_app, name="sources")


@sources_app.command("clear-cooldown")
def sources_clear_cooldown(name: str = typer.Argument(...)) -> None:
    """Clear the cooldown timestamp for a source."""
    store_db.clear_source_cooldown(paths.db_path(), name)
    console.print(f"[green]cleared[/green] cooldown for {name}")


@sources_app.command("status")
def sources_status() -> None:
    """Print fetch + cooldown state for every source."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Source")
    table.add_column("Last fetched")
    table.add_column("Cooldown until")
    table.add_column("Last error")
    with store_db.connect(paths.db_path()) as conn:
        rows = conn.execute(
            "SELECT name, last_fetched_at, cooldown_until, last_error FROM sources "
            "ORDER BY name"
        ).fetchall()
    for r in rows:
        table.add_row(r[0], r[1] or "—", r[2] or "—", r[3] or "—")
    console.print(table)
```

- [ ] **Step 2: Failing test**

```python
def test_sources_clear_cooldown_cli(env):
    cfg, data = env
    runner.invoke(app, ["db", "init"])
    from datetime import UTC, datetime, timedelta

    from shortlist.store.db import is_source_in_cooldown, mark_source_cooldown
    mark_source_cooldown(data / "db.sqlite", "indeed",
                          until=datetime.now(UTC) + timedelta(hours=24))
    assert is_source_in_cooldown(data / "db.sqlite", "indeed") is True

    result = runner.invoke(app, ["sources", "clear-cooldown", "indeed"])
    assert result.exit_code == 0
    assert is_source_in_cooldown(data / "db.sqlite", "indeed") is False
```

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/cli.py tests/integration/test_cli.py
git commit -m "feat(cli): sources subgroup (clear-cooldown, status)"
```

Expected: 1 new pass + 146 prior + 1 skip = 147 pass + 1 skip.

---

## Task 10: Migrate plan + final CI + push

**Files:**
- Create: `docs/plans/2026-04-29-shortlist-plan-5-scraped.md`

- [ ] **Step 1: Copy**

```bash
cp /run/media/seraph/Win1Tb/dev/repos/digitalseraph/docs/superpowers/plans/2026-04-29-shortlist-plan-5-scraped.md ~/dev/repos/shortlist/docs/plans/
```

- [ ] **Step 2: Final CI**

```bash
cd ~/dev/repos/shortlist
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy shortlist shortlist_tui
.venv/bin/pytest --cov=shortlist --cov=shortlist_tui --cov-report=term-missing --cov-fail-under=80
```

Expected: green; coverage ≥ 80%.

- [ ] **Step 3: Commit + push**

```bash
git add docs/plans/2026-04-29-shortlist-plan-5-scraped.md
git commit -m "docs: import Plan 5 (scraped) from monorepo"
git push
```

---

## Done definition (Plan 5)

- `IndeedSource`, `LinkedInSource`, `GlassdoorSource` parse synthetic fixtures correctly.
- `_browser.py` provides a working stealth Playwright context (verified by browser-marked tests).
- Cooldown table is read+written by both CLI and TUI workers; banned sources skip silently for 24h.
- `shortlist sources clear-cooldown <name>` and `shortlist sources status` work.
- All tests pass (~14 new); coverage ≥ 80%.
- Live tests skip without `RUN_LIVE=1`.
- Plan 5 file in `<shortlist-repo>/docs/plans/`.

## Next plan trigger

Plan 6 begins on user request. Plan 6 scope: curated boards (HN Who's Hiring, Wellfound, Otta, RemoteOK) + RSS feeds + release polish (PyPI publish prep, GitHub Actions release workflow, version 0.1.0 tag).

## Open questions for Plan 6 brainstorm

- HN "Who's Hiring": parse the monthly Ask HN thread (id rolling) — find latest thread automatically, or pin per release?
- Wellfound (formerly AngelList): public listings or auth-only? Public is paginated heavily.
- RSS sources: shipping a curated default list, or empty by default?
- Release: PyPI publish or GitHub Releases only? Version pin in `pyproject.toml` or auto-bump from git tag?
