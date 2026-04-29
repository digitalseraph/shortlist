# Shortlist — Plan 6 of 6 (Curated Boards + RSS + Release)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the final source classes — curated boards (HN "Who is hiring?", Wellfound, Otta, RemoteOK) + generic RSS feeds — and prepare a 0.1.0 release. After Plan 6 the project is feature-complete per the design spec; subsequent work is bug-fixes, model bumps, and source maintenance.

**Architecture:** Two new packages plus a release pipeline:

- `shortlist/sources/curated/` — HN (Algolia API, JSON), RemoteOK (public REST). No browser needed.
- `shortlist/sources/scraped/` extended — Wellfound, Otta. Use existing `_browser.py` from Plan 5.
- `shortlist/sources/feeds/rss.py` — generic RSS reader via `feedparser`.
- `.github/workflows/release.yml` — tag-driven GitHub Release workflow. PyPI publish deferred (separate decision).
- Version bump 0.0.1 → 0.1.0 + `CHANGELOG.md`.

**Tech Stack additions:** `feedparser>=6.0` (RSS). HN + RemoteOK use existing `httpx`. Wellfound + Otta reuse `playwright` from Plan 5.

**Decisions on Plan-5 open questions:**
- **HN "Who's Hiring":** auto-discover the latest monthly thread via the Algolia HN search API — no manual thread-ID pinning.
- **Wellfound:** anonymous public listings only (auth too brittle, multiplies ToS risk).
- **RSS:** ship empty by default; users add URLs to `prefs.yaml`. Power users can plug in company career-page RSS feeds, We Work Remotely, etc.
- **Release:** GitHub Releases only at v0.1.0. PyPI publishing left as a one-line addition for whoever wants it. Version pinned in `pyproject.toml`; release workflow triggers on `v*` tag.

**Plan-6 file map:**

```
shortlist/
├── pyproject.toml                                  (modify — feedparser dep, version 0.1.0)
├── CHANGELOG.md                                    (new)
├── shortlist/
│   ├── cli.py                                      (modify — _DEFAULT_PREFS + _build_sources)
│   ├── config.py                                   (modify — curated/feeds Prefs fields)
│   └── sources/
│       ├── _browser.py                             (move from scraped/)
│       ├── curated/
│       │   ├── __init__.py                         (new)
│       │   ├── hn_who_hiring.py                    (new)
│       │   └── remoteok.py                         (new)
│       ├── scraped/
│       │   ├── wellfound.py                        (new)
│       │   └── otta.py                             (new)
│       └── feeds/
│           ├── __init__.py                         (new)
│           └── rss.py                              (new)
├── shortlist_tui/
│   └── workers.py                                  (modify — extend _build_sources)
├── .github/workflows/
│   └── release.yml                                 (new — tag-driven release)
└── tests/
    ├── fixtures/
    │   ├── curated/
    │   │   ├── hn_algolia_search.json              (new)
    │   │   ├── hn_thread_comments.json             (new)
    │   │   └── remoteok_api.json                   (new)
    │   ├── scraped/
    │   │   ├── wellfound_search.html               (new)
    │   │   └── otta_search.html                    (new)
    │   └── feeds/
    │       └── sample.rss                          (new)
    └── unit/
        ├── test_hn_parser.py                       (new)
        ├── test_remoteok.py                        (new)
        ├── test_wellfound_parser.py                (new)
        ├── test_otta_parser.py                     (new)
        └── test_rss.py                             (new)
```

**Plan location:** `<monorepo>/docs/superpowers/plans/2026-04-29-shortlist-plan-6-curated-release.md`. Task 10 migrates it.

---

## Task 1: Relocate `_browser.py` + new source dirs + deps

**Files:**
- Move: `shortlist/sources/scraped/_browser.py` → `shortlist/sources/_browser.py`
- Modify: `shortlist/sources/scraped/{indeed,linkedin,glassdoor}.py` (update import path)
- Create: `shortlist/sources/curated/__init__.py` (empty)
- Create: `shortlist/sources/feeds/__init__.py` (empty)
- Modify: `pyproject.toml` (add `feedparser>=6.0`)

This refactor pulls `_browser.py` to a neutral location so curated/scraped/feeds can all import it without weird cross-package coupling.

- [ ] **Step 1: Move file**

```bash
cd ~/dev/repos/shortlist
git mv shortlist/sources/scraped/_browser.py shortlist/sources/_browser.py
mkdir -p shortlist/sources/curated shortlist/sources/feeds
touch shortlist/sources/curated/__init__.py shortlist/sources/feeds/__init__.py
```

- [ ] **Step 2: Update imports in scraped sources**

In `shortlist/sources/scraped/indeed.py`, `linkedin.py`, `glassdoor.py`, change:

```python
from shortlist.sources.scraped._browser import headless_context
```

to:

```python
from shortlist.sources._browser import headless_context
```

- [ ] **Step 3: Update test imports**

In `tests/integration/test_scraped_browser.py`:

```python
from shortlist.sources._browser import headless_context
```

- [ ] **Step 4: Add feedparser dep to `pyproject.toml`**

In `[project] dependencies`, append:

```toml
    "feedparser>=6.0",
```

- [ ] **Step 5: Reinstall + run gates**

```bash
source .venv/bin/activate
pip install -e ".[dev]"
.venv/bin/pytest -m "not browser and not live" -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add -A
git commit -m "refactor(sources): relocate _browser.py to sources/ + feedparser dep"
```

Expected: 147 pass + 1 skip + 5 deselected (no test changes; relocation invisible).

---

## Task 2: HN "Who's Hiring" source

**Files:**
- Create: `tests/fixtures/curated/hn_algolia_search.json`
- Create: `tests/fixtures/curated/hn_thread_comments.json`
- Create: `shortlist/sources/curated/hn_who_hiring.py`
- Create: `tests/unit/test_hn_parser.py`

**Strategy:**

1. Query Algolia HN search for `"Ask HN: Who is hiring?"` newest result → thread `objectID`.
2. Fetch thread descendants via `https://hn.algolia.com/api/v1/items/<id>` → tree of comments.
3. Each top-level comment is one job post. Parse the comment body for company, location, title, URL, remote indicator.

The body is freeform Markdown-ish. We use heuristics: first line is usually `Company | Location | Comp | (Remote)`; subsequent paragraphs are description. URL is the first http(s) link.

- [ ] **Step 1: Synthetic fixture `tests/fixtures/curated/hn_algolia_search.json`**

```json
{
  "hits": [
    {
      "objectID": "44000001",
      "title": "Ask HN: Who is hiring? (April 2026)",
      "author": "whoishiring",
      "created_at_i": 1746662400,
      "num_comments": 380
    },
    {
      "objectID": "43000001",
      "title": "Ask HN: Who is hiring? (March 2026)",
      "author": "whoishiring",
      "created_at_i": 1740960000,
      "num_comments": 412
    }
  ],
  "nbHits": 2
}
```

- [ ] **Step 2: Synthetic fixture `tests/fixtures/curated/hn_thread_comments.json`**

```json
{
  "id": 44000001,
  "type": "story",
  "title": "Ask HN: Who is hiring? (April 2026)",
  "children": [
    {
      "id": 44000100,
      "type": "comment",
      "author": "acme_recruiter",
      "created_at_i": 1746669600,
      "text": "<p>Acme Inc | Senior Backend Engineer | Remote (US) | $200-240k<p>We build distributed services in Python. Postgres at scale, Kubernetes everywhere.<p>Apply: <a href=\"https://acme.example/jobs/be\">https://acme.example/jobs/be</a>",
      "children": []
    },
    {
      "id": 44000101,
      "type": "comment",
      "author": "globex_eng",
      "created_at_i": 1746673200,
      "text": "<p>Globex | Staff Site Reliability Engineer | Atlanta, GA<p>Multi-region Kubernetes. <a href=\"https://globex.example/sre\">apply here</a>",
      "children": []
    },
    {
      "id": 44000102,
      "type": "comment",
      "author": "lurker",
      "created_at_i": 1746676800,
      "text": "<p>Just a regular comment, not a job post.",
      "children": []
    }
  ]
}
```

- [ ] **Step 3: Implement `shortlist/sources/curated/hn_who_hiring.py`**

```python
"""Hacker News 'Ask HN: Who is hiring?' source.

Algolia HN endpoints (public, no auth):
  - https://hn.algolia.com/api/v1/search?query=...&tags=ask_hn
  - https://hn.algolia.com/api/v1/items/<id>
"""
from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from pydantic import HttpUrl

from shortlist.models import RawJob
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
_ITEM_URL = "https://hn.algolia.com/api/v1/items"
_TAG_RE = re.compile(r"<[^>]+>")
_LINK_RE = re.compile(r'https?://[^\s<>"]+')


def _strip_html(s: str) -> str:
    return _TAG_RE.sub(" ", html.unescape(s)).strip()


def find_latest_thread_id(client: httpx.Client) -> int | None:
    resp = client.get(
        _SEARCH_URL,
        params={
            "query": "Ask HN: Who is hiring?",
            "tags": "story,author_whoishiring",
            "hitsPerPage": "5",
        },
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    hits.sort(key=lambda h: int(h.get("created_at_i") or 0), reverse=True)
    return int(hits[0]["objectID"]) if hits else None


def parse_comment(comment: dict[str, Any]) -> RawJob | None:
    text_html = comment.get("text") or ""
    if not text_html:
        return None
    text = _strip_html(text_html)
    first_line = text.split("\n", 1)[0].strip()
    parts = [p.strip() for p in first_line.split("|") if p.strip()]
    if len(parts) < 2:
        return None
    company = parts[0]
    title = parts[1] if len(parts) > 1 else "Unknown"
    location = parts[2] if len(parts) > 2 else ""
    is_remote = any("remote" in p.lower() for p in parts)
    link_m = _LINK_RE.search(text_html)
    url = link_m.group(0) if link_m else f"https://news.ycombinator.com/item?id={comment['id']}"
    posted_at = datetime.fromtimestamp(int(comment.get("created_at_i") or 0), tz=UTC)
    return RawJob(
        source="hn_who_hiring",
        external_id=str(comment["id"]),
        company=company[:100],
        title=title[:200],
        url=HttpUrl(url),
        posted_at=posted_at,
        location=location or None,
        remote=is_remote,
        description_md=text[:2000],
    )


def parse_thread(payload: dict[str, Any]) -> list[RawJob]:
    out: list[RawJob] = []
    for c in payload.get("children", []):
        if c.get("type") != "comment":
            continue
        rj = parse_comment(c)
        if rj is not None:
            out.append(rj)
    return out


class HNWhoHiringSource(Source):
    name: ClassVar[str] = "hn_who_hiring"

    def __init__(self, *, timeout: float = 30.0, thread_id: int | None = None):
        self._client = httpx.Client(timeout=timeout)
        self._thread_id = thread_id

    def __del__(self) -> None:
        with suppress(Exception):
            self._client.close()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        thread_id = self._thread_id or find_latest_thread_id(self._client)
        if thread_id is None:
            logger.warning("hn_who_hiring: no thread found")
            return iter([])
        resp = self._client.get(f"{_ITEM_URL}/{thread_id}")
        resp.raise_for_status()
        return iter(parse_thread(resp.json()))
```

- [ ] **Step 4: Failing tests**

```python
# tests/unit/test_hn_parser.py
import json
from pathlib import Path
from unittest.mock import MagicMock

from shortlist.sources.curated.hn_who_hiring import (
    find_latest_thread_id,
    parse_comment,
    parse_thread,
)

FIXTURES = Path(__file__).parent.parent / "fixtures/curated"


def test_find_latest_thread_id_returns_newest():
    payload = json.loads((FIXTURES / "hn_algolia_search.json").read_text())
    fake_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    fake_client.get.return_value = resp
    assert find_latest_thread_id(fake_client) == 44000001


def test_parse_thread_extracts_jobs():
    payload = json.loads((FIXTURES / "hn_thread_comments.json").read_text())
    jobs = parse_thread(payload)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "hn_who_hiring"
    assert j0.external_id == "44000100"
    assert j0.company == "Acme Inc"
    assert j0.remote is True
    assert "acme.example" in str(j0.url)


def test_parse_comment_returns_none_for_non_job_post():
    comment = {
        "id": 999,
        "type": "comment",
        "text": "<p>Just a regular comment, not a job post.",
        "created_at_i": 1746676800,
    }
    assert parse_comment(comment) is None
```

- [ ] **Step 5: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_hn_parser.py -v
.venv/bin/pytest -m "not browser and not live" -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/sources/curated/__init__.py shortlist/sources/curated/hn_who_hiring.py tests/unit/test_hn_parser.py tests/fixtures/curated/
git commit -m "feat(curated/hn): HN Who is hiring? source via Algolia API"
```

Expected: 3 new pass + 147 prior + 1 skip + 5 deselected = 150 pass + 1 skip + 5 deselected.

---

## Task 3: RemoteOK source

**Files:**
- Create: `tests/fixtures/curated/remoteok_api.json`
- Create: `shortlist/sources/curated/remoteok.py`
- Create: `tests/unit/test_remoteok.py`

RemoteOK exposes a JSON API at `https://remoteok.com/api`. First element of the array is a license/legal blob; the rest are jobs.

- [ ] **Step 1: Synthetic fixture `tests/fixtures/curated/remoteok_api.json`**

```json
[
  {"legal": "Copyright RemoteOK"},
  {
    "id": "rok_1001",
    "slug": "acme-senior-backend-engineer",
    "company": "Acme",
    "position": "Senior Backend Engineer",
    "tags": ["python", "postgres", "remote"],
    "description": "Build distributed services.",
    "location": "Worldwide",
    "salary_min": 200000,
    "salary_max": 240000,
    "url": "https://remoteok.com/remote-jobs/rok_1001",
    "apply_url": "https://acme.example/apply",
    "date": "2026-04-25T09:00:00+00:00"
  },
  {
    "id": "rok_1002",
    "company": "Globex",
    "position": "Staff Site Reliability Engineer",
    "tags": ["sre", "kubernetes"],
    "description": "Multi-region SRE.",
    "location": "USA",
    "salary_min": null,
    "salary_max": null,
    "url": "https://remoteok.com/remote-jobs/rok_1002",
    "date": "2026-04-26T10:30:00+00:00"
  }
]
```

- [ ] **Step 2: Implement `shortlist/sources/curated/remoteok.py`**

```python
"""RemoteOK public JSON API source."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import suppress
from datetime import datetime
from typing import Any, ClassVar

import httpx
from pydantic import HttpUrl

from shortlist.models import RawJob
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_API = "https://remoteok.com/api"


def parse_job(item: dict[str, Any]) -> RawJob | None:
    if "id" not in item or "company" not in item or "position" not in item:
        return None
    location = item.get("location") or ""
    return RawJob(
        source="remoteok",
        external_id=str(item["id"]),
        company=str(item["company"]),
        title=str(item["position"]),
        url=HttpUrl(str(item.get("url") or item.get("apply_url") or "https://remoteok.com")),
        posted_at=datetime.fromisoformat(str(item["date"]).replace("Z", "+00:00")),
        location=location or None,
        remote=True,
        comp_min=item.get("salary_min"),
        comp_max=item.get("salary_max"),
        description_md=str(item.get("description") or "")[:2000] or None,
    )


def parse_payload(items: list[dict[str, Any]]) -> list[RawJob]:
    return [rj for it in items if (rj := parse_job(it)) is not None]


class RemoteOKSource(Source):
    name: ClassVar[str] = "remoteok"

    def __init__(self, *, timeout: float = 30.0):
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 shortlist/0.1"},
        )

    def __del__(self) -> None:
        with suppress(Exception):
            self._client.close()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        try:
            resp = self._client.get(_API)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("remoteok: fetch failed: %s", e)
            return iter([])
        return iter(parse_payload(resp.json()))
```

- [ ] **Step 3: Failing tests `tests/unit/test_remoteok.py`**

```python
import json
from pathlib import Path

from shortlist.sources.curated.remoteok import parse_payload

FIXTURES = Path(__file__).parent.parent / "fixtures/curated"


def test_parse_remoteok_payload():
    items = json.loads((FIXTURES / "remoteok_api.json").read_text())
    jobs = parse_payload(items)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "remoteok"
    assert j0.external_id == "rok_1001"
    assert j0.company == "Acme"
    assert j0.title == "Senior Backend Engineer"
    assert j0.remote is True
    assert j0.comp_min == 200000


def test_parse_skips_legal_blob():
    items = [{"legal": "Copyright RemoteOK"}]
    jobs = parse_payload(items)
    assert jobs == []
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_remoteok.py -v
.venv/bin/pytest -m "not browser and not live" -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/sources/curated/remoteok.py tests/unit/test_remoteok.py tests/fixtures/curated/remoteok_api.json
git commit -m "feat(curated/remoteok): RemoteOK public JSON API source"
```

Expected: 2 new pass + 150 prior = 152 pass + 1 skip + 5 deselected.

---

## Task 4: Wellfound source

**Files:**
- Create: `tests/fixtures/scraped/wellfound_search.html`
- Create: `shortlist/sources/scraped/wellfound.py`
- Create: `tests/unit/test_wellfound_parser.py`

Wellfound (formerly AngelList Talent) public listings: `https://wellfound.com/jobs?q=<query>`. Heavy JS render — Playwright required.

- [ ] **Step 1: Synthetic fixture `tests/fixtures/scraped/wellfound_search.html`**

```html
<!DOCTYPE html>
<html><body>
<div data-test="JobSearchResults">
  <div data-test="JobSearchCard">
    <a class="job-listing-link" href="/jobs/wf-9001-senior-backend-engineer-acme">
      <h2 class="job-title">Senior Backend Engineer</h2>
    </a>
    <div class="company-name">Acme Inc</div>
    <div class="job-location">Remote</div>
    <div class="job-snippet">Build distributed services in Python.</div>
    <span class="posted-at" data-posted-at="2026-04-25T00:00:00Z">3 days ago</span>
  </div>
  <div data-test="JobSearchCard">
    <a class="job-listing-link" href="/jobs/wf-9002-staff-platform-engineer-globex">
      <h2 class="job-title">Staff Platform Engineer</h2>
    </a>
    <div class="company-name">Globex</div>
    <div class="job-location">San Francisco</div>
    <div class="job-snippet">Lead the platform team.</div>
    <span class="posted-at" data-posted-at="2026-04-26T00:00:00Z">1 day ago</span>
  </div>
</div>
</body></html>
```

- [ ] **Step 2: Implement `shortlist/sources/scraped/wellfound.py`**

```python
"""Wellfound (formerly AngelList Talent) public job listings."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime
from typing import ClassVar
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl

from shortlist.models import RawJob
from shortlist.sources._browser import headless_context
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://wellfound.com/jobs"
_BAN_MARKERS = ("captcha", "Access Denied", "Cloudflare")


class WellfoundBanDetectedError(RuntimeError):
    pass


def _parse_card(card: Tag) -> RawJob | None:
    a = card.select_one("a.job-listing-link")
    title_el = card.select_one(".job-title")
    company_el = card.select_one(".company-name")
    location_el = card.select_one(".job-location")
    snippet_el = card.select_one(".job-snippet")
    date_el = card.select_one(".posted-at")

    if a is None or title_el is None:
        return None
    href = str(a.get("href") or "")
    if href.startswith("/"):
        href = f"https://wellfound.com{href}"
    m = re.search(r"/jobs/([^/]+)", href)
    if m is None:
        return None
    external_id = m.group(1)

    location = location_el.get_text(strip=True) if location_el else ""
    posted_iso = (
        date_el["data-posted-at"]
        if date_el is not None and date_el.get("data-posted-at") else None
    )
    posted_at = (
        datetime.fromisoformat(str(posted_iso).replace("Z", "+00:00"))
        if posted_iso else datetime.now(UTC)
    )

    return RawJob(
        source="wellfound",
        external_id=external_id,
        company=company_el.get_text(strip=True) if company_el else "Unknown",
        title=title_el.get_text(strip=True),
        url=HttpUrl(href),
        posted_at=posted_at,
        location=location or None,
        remote="remote" in location.lower(),
        description_md=snippet_el.get_text(strip=True) if snippet_el else None,
    )


def parse_search_html(html: str) -> list[RawJob]:
    if any(m.lower() in html.lower() for m in _BAN_MARKERS):
        raise WellfoundBanDetectedError("ban marker in page")
    soup = BeautifulSoup(html, "html.parser")
    return [rj for card in soup.select('div[data-test="JobSearchCard"]')
            if (rj := _parse_card(card)) is not None]


class WellfoundSource(Source):
    name: ClassVar[str] = "wellfound"

    def __init__(self, *, queries: list[str], rate_limit_seconds: float = 8.0):
        self._queries = queries
        self._rate = rate_limit_seconds

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        return iter(asyncio.run(self._fetch_all()))

    async def _fetch_all(self) -> list[RawJob]:
        out: list[RawJob] = []
        async with headless_context() as ctx:
            page = await ctx.new_page()
            for q in self._queries:
                url = f"{_BASE}?{urlencode({'q': q})}"
                logger.info("wellfound: fetching %s", url)
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_selector(
                        'div[data-test="JobSearchCard"]', timeout=15_000
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("wellfound: load failed: %s", e)
                    continue
                html = await page.content()
                out.extend(parse_search_html(html))
                await asyncio.sleep(self._rate)
        return out
```

- [ ] **Step 3: Failing tests `tests/unit/test_wellfound_parser.py`**

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortlist.sources.scraped.wellfound import (
    WellfoundBanDetectedError,
    parse_search_html,
)

FIXTURES = Path(__file__).parent.parent / "fixtures/scraped"


def test_parse_synthetic_wellfound():
    html = (FIXTURES / "wellfound_search.html").read_text()
    jobs = parse_search_html(html)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "wellfound"
    assert j0.external_id.startswith("wf-9001")
    assert j0.company == "Acme Inc"
    assert j0.remote is True
    assert j0.posted_at == datetime(2026, 4, 25, 0, 0, tzinfo=UTC)


def test_parse_detects_cloudflare():
    html = "<html><body>Cloudflare protection — captcha required.</body></html>"
    with pytest.raises(WellfoundBanDetectedError):
        parse_search_html(html)
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_wellfound_parser.py -v
.venv/bin/pytest -m "not browser and not live" -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/sources/scraped/wellfound.py tests/unit/test_wellfound_parser.py tests/fixtures/scraped/wellfound_search.html
git commit -m "feat(scraped/wellfound): Wellfound parser + Source"
```

Expected: 2 new pass + 152 prior = 154 pass + 1 skip + 5 deselected.

---

## Task 5: Otta source

**Files:**
- Create: `tests/fixtures/scraped/otta_search.html`
- Create: `shortlist/sources/scraped/otta.py`
- Create: `tests/unit/test_otta_parser.py`

Otta (now Welcome to the Jungle) public listings: `https://otta.com/jobs?keywords=<query>`. JS-rendered → Playwright.

- [ ] **Step 1: Synthetic fixture `tests/fixtures/scraped/otta_search.html`**

```html
<!DOCTYPE html>
<html><body>
<ul data-testid="job-feed">
  <li data-testid="job-card">
    <a data-testid="job-card-link" href="/jobs/ot-501/senior-backend-engineer">
      <h3 class="job-card-title">Senior Backend Engineer</h3>
    </a>
    <div class="job-card-company">Acme Inc</div>
    <div class="job-card-location">Remote · UK/EU</div>
    <div class="job-card-summary">Distributed Python services.</div>
    <span class="job-card-age">2 days ago</span>
  </li>
  <li data-testid="job-card">
    <a data-testid="job-card-link" href="/jobs/ot-502/staff-platform-engineer">
      <h3 class="job-card-title">Staff Platform Engineer</h3>
    </a>
    <div class="job-card-company">Globex</div>
    <div class="job-card-location">London</div>
    <div class="job-card-summary">Platform leadership.</div>
    <span class="job-card-age">5 days ago</span>
  </li>
</ul>
</body></html>
```

- [ ] **Step 2: Implement `shortlist/sources/scraped/otta.py`**

```python
"""Otta (Welcome to the Jungle) public job listings."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl

from shortlist.models import RawJob
from shortlist.sources._browser import headless_context
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://otta.com/jobs"
_BAN_MARKERS = ("captcha", "Access Denied")


class OttaBanDetectedError(RuntimeError):
    pass


def _parse_age(s: str, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    m = re.match(r"^(\d+)\s*(hour|day|week|month)s?\s*ago", s.strip().lower())
    if not m:
        return now
    n = int(m.group(1))
    unit = m.group(2)
    return now - {
        "hour": timedelta(hours=n),
        "day": timedelta(days=n),
        "week": timedelta(weeks=n),
        "month": timedelta(days=n * 30),
    }[unit]


def _parse_card(card: Tag) -> RawJob | None:
    a = card.select_one('a[data-testid="job-card-link"]')
    title_el = card.select_one(".job-card-title")
    company_el = card.select_one(".job-card-company")
    location_el = card.select_one(".job-card-location")
    summary_el = card.select_one(".job-card-summary")
    age_el = card.select_one(".job-card-age")

    if a is None or title_el is None:
        return None
    href = str(a.get("href") or "")
    if href.startswith("/"):
        href = f"https://otta.com{href}"
    m = re.search(r"/jobs/([^/]+)", href)
    if m is None:
        return None
    external_id = m.group(1)

    location = location_el.get_text(strip=True) if location_el else ""
    return RawJob(
        source="otta",
        external_id=external_id,
        company=company_el.get_text(strip=True) if company_el else "Unknown",
        title=title_el.get_text(strip=True),
        url=HttpUrl(href),
        posted_at=_parse_age(age_el.get_text(strip=True) if age_el else ""),
        location=location or None,
        remote="remote" in location.lower(),
        description_md=summary_el.get_text(strip=True) if summary_el else None,
    )


def parse_search_html(html: str) -> list[RawJob]:
    if any(m.lower() in html.lower() for m in _BAN_MARKERS):
        raise OttaBanDetectedError("ban marker in page")
    soup = BeautifulSoup(html, "html.parser")
    return [rj for card in soup.select('li[data-testid="job-card"]')
            if (rj := _parse_card(card)) is not None]


class OttaSource(Source):
    name: ClassVar[str] = "otta"

    def __init__(self, *, queries: list[str], rate_limit_seconds: float = 8.0):
        self._queries = queries
        self._rate = rate_limit_seconds

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        return iter(asyncio.run(self._fetch_all()))

    async def _fetch_all(self) -> list[RawJob]:
        out: list[RawJob] = []
        async with headless_context() as ctx:
            page = await ctx.new_page()
            for q in self._queries:
                url = f"{_BASE}?{urlencode({'keywords': q})}"
                logger.info("otta: fetching %s", url)
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_selector(
                        'li[data-testid="job-card"]', timeout=15_000
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("otta: load failed: %s", e)
                    continue
                html = await page.content()
                out.extend(parse_search_html(html))
                await asyncio.sleep(self._rate)
        return out
```

- [ ] **Step 3: Failing tests `tests/unit/test_otta_parser.py`**

```python
from pathlib import Path

import pytest

from shortlist.sources.scraped.otta import OttaBanDetectedError, parse_search_html

FIXTURES = Path(__file__).parent.parent / "fixtures/scraped"


def test_parse_synthetic_otta():
    html = (FIXTURES / "otta_search.html").read_text()
    jobs = parse_search_html(html)
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "otta"
    assert j0.external_id == "ot-501"
    assert j0.company == "Acme Inc"
    assert j0.remote is True


def test_parse_detects_captcha():
    html = "<html><body>captcha required.</body></html>"
    with pytest.raises(OttaBanDetectedError):
        parse_search_html(html)
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_otta_parser.py -v
.venv/bin/pytest -m "not browser and not live" -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/sources/scraped/otta.py tests/unit/test_otta_parser.py tests/fixtures/scraped/otta_search.html
git commit -m "feat(scraped/otta): Otta parser + Source"
```

Expected: 2 new pass + 154 prior = 156 pass + 1 skip + 5 deselected.

---

## Task 6: Generic RSS source

**Files:**
- Create: `tests/fixtures/feeds/sample.rss`
- Create: `shortlist/sources/feeds/rss.py`
- Create: `tests/unit/test_rss.py`

Generic feed reader. Each entry becomes a `RawJob`. The user supplies a list of feed URLs in `prefs.yaml` under `rss_urls`.

- [ ] **Step 1: Synthetic fixture `tests/fixtures/feeds/sample.rss`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Acme Careers</title>
    <link>https://acme.example/careers</link>
    <description>Open roles at Acme</description>
    <item>
      <title>Senior Backend Engineer</title>
      <link>https://acme.example/careers/be-senior</link>
      <description>Build distributed services in Python. Remote.</description>
      <pubDate>Sat, 25 Apr 2026 09:00:00 GMT</pubDate>
      <guid isPermaLink="false">acme-be-senior-001</guid>
    </item>
    <item>
      <title>Staff SRE</title>
      <link>https://acme.example/careers/sre-staff</link>
      <description>Multi-region Kubernetes. Atlanta.</description>
      <pubDate>Sun, 26 Apr 2026 10:30:00 GMT</pubDate>
      <guid isPermaLink="false">acme-sre-staff-002</guid>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: Implement `shortlist/sources/feeds/rss.py`**

```python
"""Generic RSS feed source."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import urlparse

import feedparser
from pydantic import HttpUrl

from shortlist.models import RawJob
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)


def _entry_to_rawjob(entry: Any, *, channel_title: str, feed_url: str) -> RawJob | None:
    title = str(entry.get("title") or "").strip()
    link = str(entry.get("link") or "").strip()
    if not title or not link:
        return None
    guid = str(entry.get("id") or entry.get("guid") or link)
    summary = str(entry.get("summary") or entry.get("description") or "")[:2000]

    posted_at = datetime.now(UTC)
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        posted_at = datetime(*parsed[:6], tzinfo=UTC)

    location_marker = ""
    if "remote" in summary.lower():
        location_marker = "Remote"

    feed_host = urlparse(feed_url).netloc or "rss"
    return RawJob(
        source="rss",
        external_id=f"{feed_host}:{guid}",
        company=channel_title or feed_host,
        title=title,
        url=HttpUrl(link),
        posted_at=posted_at,
        location=location_marker or None,
        remote=bool(location_marker),
        description_md=summary or None,
    )


def parse_feed(content: str | bytes, *, feed_url: str) -> list[RawJob]:
    parsed = feedparser.parse(content)
    channel_title = str(parsed.feed.get("title") or "")
    return [
        rj for e in parsed.entries
        if (rj := _entry_to_rawjob(e, channel_title=channel_title, feed_url=feed_url))
        is not None
    ]


class RSSSource(Source):
    name: ClassVar[str] = "rss"

    def __init__(self, *, urls: list[str]):
        self._urls = urls

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        out: list[RawJob] = []
        for url in self._urls:
            try:
                parsed = feedparser.parse(url)
                channel_title = str(parsed.feed.get("title") or "")
                for e in parsed.entries:
                    rj = _entry_to_rawjob(e, channel_title=channel_title, feed_url=url)
                    if rj is not None:
                        out.append(rj)
            except Exception as e:  # noqa: BLE001
                logger.warning("rss: %s failed: %s", url, e)
        return iter(out)
```

- [ ] **Step 3: Failing tests `tests/unit/test_rss.py`**

```python
from pathlib import Path

from shortlist.sources.feeds.rss import parse_feed

FIXTURES = Path(__file__).parent.parent / "fixtures/feeds"


def test_parse_sample_rss():
    content = (FIXTURES / "sample.rss").read_text()
    jobs = parse_feed(content, feed_url="https://acme.example/feed.rss")
    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source == "rss"
    assert j0.title == "Senior Backend Engineer"
    assert j0.company == "Acme Careers"
    assert j0.remote is True
    assert "acme.example" in j0.external_id


def test_parse_empty_feed():
    jobs = parse_feed("<rss><channel></channel></rss>", feed_url="x")
    assert jobs == []
```

- [ ] **Step 4: Run + commit**

```bash
.venv/bin/pytest tests/unit/test_rss.py -v
.venv/bin/pytest -m "not browser and not live" -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/sources/feeds/__init__.py shortlist/sources/feeds/rss.py tests/unit/test_rss.py tests/fixtures/feeds/
git commit -m "feat(feeds/rss): generic RSS source via feedparser"
```

Expected: 2 new pass + 156 prior = 158 pass + 1 skip + 5 deselected.

---

## Task 7: Wire all 5 new sources into CLI/TUI fetch + Prefs

**Files:**
- Modify: `shortlist/config.py` (Prefs additions)
- Modify: `shortlist/cli.py` (`_DEFAULT_PREFS`, `_DEFAULT_CONFIG`, `_build_sources`, `fetch` ban handling)
- Modify: `shortlist_tui/workers.py` (mirror updates)
- Modify: `tests/integration/test_cli.py`

- [ ] **Step 1: Update `Prefs` in `shortlist/config.py`**

Append after `glassdoor_queries`:

```python
    hn_enabled: bool = False
    remoteok_enabled: bool = False
    wellfound_queries: list[str] = Field(default_factory=list)
    otta_queries: list[str] = Field(default_factory=list)
    rss_urls: list[str] = Field(default_factory=list)
```

Extend the `_strip` validator's argument list to include `wellfound_queries`, `otta_queries`, `rss_urls`.

- [ ] **Step 2: Update `_DEFAULT_PREFS` in `shortlist/cli.py`**

Append after `glassdoor_queries: []`:

```yaml
hn_enabled: false
remoteok_enabled: false
wellfound_queries: []
otta_queries: []
rss_urls: []
```

In `_DEFAULT_CONFIG`'s `sources:` block, append:

```yaml
  hn_who_hiring:
    enabled: true
  remoteok:
    enabled: true
  wellfound:
    enabled: false
    rate_limit_rpm: 6
  otta:
    enabled: false
    rate_limit_rpm: 6
  rss:
    enabled: true
```

(HN, RemoteOK, RSS default-enabled — API-based, no ban risk. Wellfound/Otta default-disabled like Plan-5 scraped sources.)

- [ ] **Step 3: Update `_build_sources` in `shortlist/cli.py`**

Add imports:

```python
from shortlist.sources.curated.hn_who_hiring import HNWhoHiringSource
from shortlist.sources.curated.remoteok import RemoteOKSource
from shortlist.sources.feeds.rss import RSSSource
from shortlist.sources.scraped.otta import OttaBanDetectedError, OttaSource
from shortlist.sources.scraped.wellfound import WellfoundBanDetectedError, WellfoundSource
```

Extend `_build_sources(prefs)`:

```python
if prefs.hn_enabled:
    sources.append(HNWhoHiringSource())
if prefs.remoteok_enabled:
    sources.append(RemoteOKSource())
if prefs.wellfound_queries:
    sources.append(WellfoundSource(queries=prefs.wellfound_queries))
if prefs.otta_queries:
    sources.append(OttaSource(queries=prefs.otta_queries))
if prefs.rss_urls:
    sources.append(RSSSource(urls=prefs.rss_urls))
```

In `fetch()`, extend the ban-detection except clause:

```python
except (
    IndeedBanDetectedError, LinkedInBanDetectedError, GlassdoorBanDetectedError,
    WellfoundBanDetectedError, OttaBanDetectedError,
):
    until = datetime.now(UTC) + timedelta(hours=24)
    store_db.mark_source_cooldown(db, src.name, until=until)
    console.print(f"[red]{src.name} banned — cooled down until {until.isoformat()}[/red]")
```

- [ ] **Step 4: Mirror updates in `shortlist_tui/workers.py`**

Same diff as Step 3.

- [ ] **Step 5: Append failing test**

```python
def test_fetch_with_curated_sources_runs_no_errors(env, monkeypatch):
    """Smoke: enabling HN + RemoteOK + RSS doesn't crash fetch (mocked)."""
    cfg, data = env
    runner.invoke(app, ["config", "init"])
    prefs_yaml = (cfg / "prefs.yaml").read_text() \
        .replace("hn_enabled: false", "hn_enabled: true") \
        .replace("remoteok_enabled: false", "remoteok_enabled: true") \
        .replace("rss_urls: []", "rss_urls:\n  - https://example.invalid/feed.rss")
    (cfg / "prefs.yaml").write_text(prefs_yaml)
    runner.invoke(app, ["db", "init"])

    class _Stub:
        def __init__(self, name):
            self.name = name
        def fetch(self, since=None):
            return iter([])

    import shortlist.cli as cli_mod
    monkeypatch.setattr(cli_mod, "HNWhoHiringSource", lambda: _Stub("hn_who_hiring"))
    monkeypatch.setattr(cli_mod, "RemoteOKSource", lambda: _Stub("remoteok"))
    monkeypatch.setattr(cli_mod, "RSSSource", lambda urls: _Stub("rss"))

    result = runner.invoke(app, ["fetch"])
    assert result.exit_code == 0, result.output
```

- [ ] **Step 6: Run + commit**

```bash
.venv/bin/pytest -m "not browser and not live" -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add shortlist/config.py shortlist/cli.py shortlist_tui/workers.py tests/integration/test_cli.py
git commit -m "feat(sources): wire HN/RemoteOK/Wellfound/Otta/RSS + cooldown extensions"
```

Expected: 1 new pass + 158 prior = 159 pass + 1 skip + 5 deselected.

---

## Task 8: GitHub Actions release workflow

**Files:**
- Create: `.github/workflows/release.yml`

Tag-driven: pushing a `v*` tag (e.g., `v0.1.0`) builds a wheel + sdist, attaches them to a GitHub Release with auto-generated notes.

- [ ] **Step 1: Write `.github/workflows/release.yml`**

```yaml
name: release

on:
  push:
    tags:
      - 'v*'

jobs:
  build-and-release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install build deps
        run: |
          python -m pip install -U pip
          pip install build

      - name: Build wheel + sdist
        run: python -m build

      - name: Generate release notes
        id: notes
        run: |
          TAG="${GITHUB_REF_NAME}"
          PREV=$(git describe --tags --abbrev=0 "${TAG}^" 2>/dev/null || echo "")
          if [ -n "$PREV" ]; then
            git log "${PREV}..${TAG}" --pretty=format:'- %s' --no-merges > notes.md
          else
            git log "${TAG}" --pretty=format:'- %s' --no-merges > notes.md
          fi
          echo "tag=${TAG}" >> $GITHUB_OUTPUT

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.notes.outputs.tag }}
          name: ${{ steps.notes.outputs.tag }}
          body_path: notes.md
          files: |
            dist/*.whl
            dist/*.tar.gz
          draft: false
          prerelease: false
```

- [ ] **Step 2: Test the build locally (don't push tag)**

```bash
cd ~/dev/repos/shortlist
source .venv/bin/activate
pip install build
python -m build
ls dist/
```

Expected: `dist/shortlist-0.0.1-py3-none-any.whl` and `dist/shortlist-0.0.1.tar.gz` (version bump to 0.1.0 happens in T9).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: tag-driven GitHub Release workflow with wheel + sdist artifacts"
```

---

## Task 9: Version 0.1.0 + CHANGELOG

**Files:**
- Modify: `pyproject.toml` (version bump)
- Create: `CHANGELOG.md`

- [ ] **Step 1: Bump version in `pyproject.toml`**

Change `version = "0.0.1"` to `version = "0.1.0"`.

- [ ] **Step 2: Write `CHANGELOG.md`**

```markdown
# Changelog

## [0.1.0] - 2026-04-29

First feature-complete release. Implements the full Shortlist spec across
six task plans:

### Added
- **Plan 1 — Foundation:** Greenhouse public-board ingestion, SQLite store
  with versioned migrations, hard-filter ranking against `prefs.yaml`,
  Typer CLI with `db`, `config`, `fetch`, `rank`, `list` commands.
- **Plan 2 — ATS expansion + LLM rerank:** Lever, Ashby, Workable,
  SmartRecruiters ATS sources. Local embeddings via
  `sentence-transformers` (`bge-small-en-v1.5`) + `sqlite-vec`. Anthropic
  Haiku 4.5 rerank with budget tracking.
- **Plan 3 — Tailoring + Tracker:** Sonnet 4.6 per-job resume + cover
  letter + interview notes generation with no-fabrication system prompt.
  Pandoc → PDF rendering with bundled LaTeX template. Application
  lifecycle state machine. Contacts CRUD.
- **Plan 4 — Textual TUI:** Four screens (JobList, JobDetail,
  ApplicationsBoard, Settings) with vim-style key bindings, live search
  filter, background workers for fetch/rank/tailor.
- **Plan 5 — Scraped aggregators:** Indeed, LinkedIn, Glassdoor via
  Playwright with stealth init script and 24h auto-cooldown on ban
  detection. Disabled by default.
- **Plan 6 — Curated boards + RSS + Release (this):** HN "Who is hiring?"
  via Algolia API, RemoteOK via REST, Wellfound + Otta via Playwright,
  generic RSS feeds via `feedparser`. Tag-driven GitHub Release workflow.

### Notes
- ATS APIs (Plans 1+2) are the recommended primary path. Scraped sources
  (Plan 5, plus Wellfound/Otta from this release) are best-effort and
  ship disabled by default.
- PDF rendering requires `pandoc` + `pdflatex` (TeX Live with LaTeX
  format files) on PATH. MD output works without them.
- Anthropic API key required for `rank` (Haiku) and `tailor` (Sonnet).
  Use `--no-llm` for embedding-only ranking at $0 cost.
```

- [ ] **Step 3: Run gates + commit**

```bash
.venv/bin/pytest -m "not browser and not live" -q
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy shortlist shortlist_tui
git add pyproject.toml CHANGELOG.md
git commit -m "chore: version 0.1.0 + CHANGELOG"
```

---

## Task 10: README + plan migrate + tag + push

**Files:**
- Modify: `README.md`
- Create: `docs/plans/2026-04-29-shortlist-plan-6-curated-release.md`

- [ ] **Step 1: Update README**

Replace "Plan 5 of 6" status block with:

```markdown
**Status: feature-complete (v0.1.0).** All six plans shipped:

- ✅ Plan 1 (foundation): Greenhouse + SQLite + hard filter + CLI
- ✅ Plan 2: Lever, Ashby, Workable, SmartRecruiters; embeddings via `sentence-transformers`; Haiku 4.5 rerank with budget guard
- ✅ Plan 3: Sonnet 4.6 per-job tailoring; pandoc → PDF; status state machine; contacts CRUD
- ✅ Plan 4: Textual TUI — JobList, JobDetail, ApplicationsBoard, Settings; vim-style key bindings; live search
- ✅ Plan 5: Scraped aggregators — Indeed, LinkedIn, Glassdoor via Playwright + stealth; 24h auto-cooldown on ban; **disabled by default**
- ✅ Plan 6: Curated boards (HN Who is hiring?, RemoteOK), Wellfound + Otta (scraped), generic RSS feeds; tag-driven GitHub Release.
```

In "First run" append:

```bash
# Curated sources (recommended — API-based, low risk):
$EDITOR ~/.config/shortlist/prefs.yaml
# set hn_enabled: true
# set remoteok_enabled: true
# add company career RSS feeds to rss_urls

shortlist fetch                   # now includes HN + RemoteOK + your RSS feeds
```

- [ ] **Step 2: Copy plan**

```bash
cp /run/media/seraph/Win1Tb/dev/repos/digitalseraph/docs/superpowers/plans/2026-04-29-shortlist-plan-6-curated-release.md ~/dev/repos/shortlist/docs/plans/
```

- [ ] **Step 3: Final CI**

```bash
cd ~/dev/repos/shortlist
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy shortlist shortlist_tui
.venv/bin/pytest -m "not browser and not live" --cov=shortlist --cov=shortlist_tui --cov-report=term-missing --cov-fail-under=80
```

Expected: green; coverage ≥ 80%.

- [ ] **Step 4: Commit + tag + push**

```bash
git add README.md docs/plans/2026-04-29-shortlist-plan-6-curated-release.md
git commit -m "docs: README + import Plan 6 (curated + release) from monorepo"
git push

# Tag the 0.1.0 release. The release.yml workflow fires on this push.
git tag v0.1.0
git push origin v0.1.0
```

After the tag pushes, watch the GitHub Actions release workflow. It builds wheel + sdist and creates a GitHub Release at `github.com/digitalseraph/shortlist/releases/tag/v0.1.0`.

---

## Done definition (Plan 6 + project)

- HN, RemoteOK, Wellfound, Otta, RSS sources all parse synthetic fixtures correctly.
- `_build_sources` includes all 13 source classes (5 ATS + 3 scraped from Plan 5 + 2 curated + 2 scraped from Plan 6 + 1 RSS).
- All tests pass (~13 new); coverage ≥ 80%.
- `v0.1.0` tag pushed; GitHub Release auto-created with wheel + sdist artifacts.
- Plan 6 file in `<shortlist-repo>/docs/plans/`.
- Project marked feature-complete in README.

## Post-release

- Monitor scraped sources (Indeed, LinkedIn, Glassdoor, Wellfound, Otta) — selectors will break.
- PyPI publish (deferred): add a `publish-pypi` job to `release.yml` using `pypa/gh-action-pypi-publish` and configure trusted publisher in PyPI.
- Schedule a quarterly review of scraped-source selectors and stealth init script.
- Bump Anthropic models as new versions ship (current pins: `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`).
