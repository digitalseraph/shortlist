"""Generic RSS feed source."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import urlparse

import feedparser  # type: ignore[import-untyped]
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
    time_tuple = entry.get("published_parsed") or entry.get("updated_parsed")
    if time_tuple:
        yr, mo, dy, hr, mn, sc = time_tuple[:6]
        posted_at = datetime(yr, mo, dy, hr, mn, sc, tzinfo=UTC)

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
        rj
        for e in parsed.entries
        if (rj := _entry_to_rawjob(e, channel_title=channel_title, feed_url=feed_url)) is not None
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
