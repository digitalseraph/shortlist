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
    if len(parts) < 2:  # noqa: PLR2004
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
