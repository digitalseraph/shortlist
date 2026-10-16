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
from pydantic import HttpUrl

from shortlist.models import RawJob
from shortlist.sources._browser import headless_context
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://www.linkedin.com/jobs/search"
_BAN_MARKERS = (
    "authwall",
    "request a verification",
    "/checkpoint/challenge",
    "rate limit",
    "Sign in to continue",
)


_DEFAULT_LOCATION = "United States"
_REMOTE_WORK_TYPE = "2"  # LinkedIn's f_WT value for remote jobs


class LinkedInBanDetectedError(RuntimeError):
    pass


def _search_params(query: str, location: str) -> dict[str, str]:
    # LinkedIn has no "Remote" place; remote is a filter on a country search.
    if location == "Remote":
        return {"keywords": query, "location": _DEFAULT_LOCATION, "f_WT": _REMOTE_WORK_TYPE}
    return {"keywords": query, "location": location}


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
        if date_el is not None and date_el.get("datetime")
        else datetime.now(UTC)
    )
    return RawJob(
        source="linkedin",
        external_id=external_id,
        company=company_el.get_text(strip=True) if company_el else "Unknown",
        title=title_el.get_text(strip=True),
        url=HttpUrl(href),
        posted_at=posted_at,
        location=location or None,
        remote="remote" in location.lower(),
    )


def parse_search_html(html: str) -> list[RawJob]:
    if any(m.lower() in html.lower() for m in _BAN_MARKERS):
        raise LinkedInBanDetectedError("ban / authwall marker found")
    soup = BeautifulSoup(html, "html.parser")
    return [
        rj
        for card in soup.select("ul.jobs-search__results-list > li")
        if (rj := _parse_card(card)) is not None
    ]


class LinkedInSource(Source):
    name: ClassVar[str] = "linkedin"

    def __init__(
        self,
        *,
        queries: list[str],
        locations: list[str] | None = None,
        rate_limit_seconds: float = 15.0,
        max_pages: int = 2,
    ):
        self._queries = queries
        self._locations = locations or [_DEFAULT_LOCATION]
        self._rate = rate_limit_seconds
        self._max_pages = max_pages

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

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        return iter(asyncio.run(self._fetch_all()))

    async def _fetch_all(self) -> list[RawJob]:
        out: list[RawJob] = []
        async with headless_context() as ctx:
            page = await ctx.new_page()
            for pages in self.search_urls():
                for url in pages:
                    logger.info("linkedin: fetching %s", url)
                    try:
                        await page.goto(url, wait_until="domcontentloaded")
                        await page.wait_for_selector("ul.jobs-search__results-list", timeout=15_000)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("linkedin: load failed: %s", e)
                        break
                    html = await page.content()
                    out.extend(parse_search_html(html))
                    await asyncio.sleep(self._rate)
        return out
