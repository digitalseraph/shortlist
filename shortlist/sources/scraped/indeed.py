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
from pydantic import HttpUrl

from shortlist.models import RawJob
from shortlist.sources._browser import headless_context
from shortlist.sources.base import Source

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
    jk_match = re.search(r"jk=([a-zA-Z0-9]+)", href) or re.search(
        r"job_([a-zA-Z0-9]+)", str(title_a.get("id") or "")
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
        url=HttpUrl(href),
        posted_at=posted_at,
        location=location or None,
        remote="remote" in location.lower(),
        description_md=snippet_el.get_text(strip=True) if snippet_el else None,
    )


def parse_search_html(html: str, *, query: str) -> list[RawJob]:  # noqa: ARG001
    if any(m.lower() in html.lower() for m in _BAN_MARKERS):
        raise IndeedBanDetectedError("ban / captcha marker found in HTML")
    soup = BeautifulSoup(html, "html.parser")
    return [rj for card in soup.select("li.result") if (rj := _normalize_card(card)) is not None]


class IndeedSource(Source):
    name: ClassVar[str] = "indeed"

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

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        return iter(asyncio.run(self._fetch_all()))

    async def _fetch_all(self) -> list[RawJob]:
        out: list[RawJob] = []
        async with headless_context() as ctx:
            page = await ctx.new_page()
            for q, url in self.search_urls():
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
