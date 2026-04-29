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
    return (
        now
        - {
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=n * 30),
        }[unit]
    )


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
    return [
        rj
        for card in soup.select('li[data-testid="job-card"]')
        if (rj := _parse_card(card)) is not None
    ]


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
                    await page.wait_for_selector('li[data-testid="job-card"]', timeout=15_000)
                except Exception as e:  # noqa: BLE001
                    logger.warning("otta: load failed: %s", e)
                    continue
                html = await page.content()
                out.extend(parse_search_html(html))
                await asyncio.sleep(self._rate)
        return out
