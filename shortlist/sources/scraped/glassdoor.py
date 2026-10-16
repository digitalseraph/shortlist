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
from pydantic import HttpUrl

from shortlist.models import RawJob
from shortlist.sources._browser import headless_context, on_bot_check
from shortlist.sources.base import Source

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
        url=HttpUrl(href),
        posted_at=_parse_age(age_el.get_text(strip=True) if age_el else ""),
        location=location or None,
        remote="remote" in location.lower(),
        description_md=snippet_el.get_text(strip=True) if snippet_el else None,
    )


def parse_search_html(html: str) -> list[RawJob]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('li[data-test="jobListing"]')
    # Normal results pages also load reCAPTCHA and carry "blocked" JSON flags,
    # so a marker only means a ban when the page has no listings at all.
    if not cards and any(m.lower() in html.lower() for m in _BAN_MARKERS):
        raise GlassdoorBanDetectedError("ban marker found")
    return [rj for card in cards if (rj := _parse_card(card)) is not None]


class GlassdoorSource(Source):
    name: ClassVar[str] = "glassdoor"

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

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        return iter(asyncio.run(self._fetch_all()))

    async def _fetch_all(self) -> list[RawJob]:
        out: list[RawJob] = []
        async with headless_context() as ctx:
            page = await ctx.new_page()
            for url in self.search_urls():
                logger.info("glassdoor: fetching %s", url)
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_selector('li[data-test="jobListing"]', timeout=15_000)
                except Exception as e:  # noqa: BLE001
                    if await on_bot_check(page):
                        logger.warning("glassdoor: bot check shown; skipping remaining searches")
                        break
                    logger.warning("glassdoor: load failed: %s", e)
                    continue
                html = await page.content()
                out.extend(parse_search_html(html))
                await asyncio.sleep(self._rate)
        return out
