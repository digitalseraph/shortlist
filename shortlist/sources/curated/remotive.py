"""Remotive public JSON API source.

API: https://remotive.com/api/remote-jobs (~3000 active remote jobs).
Optional `category` query trims to a slice (software-dev, devops, etc.).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import suppress
from datetime import datetime
from typing import Any, ClassVar

import httpx
from pydantic import HttpUrl

from shortlist.models import RawJob
from shortlist.sources._comp import parse_comp_from_text
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_API = "https://remotive.com/api/remote-jobs"


def _parse_salary(s: str | None) -> tuple[int | None, int | None]:
    if not s:
        return (None, None)
    return parse_comp_from_text(s)


def parse_job(item: dict[str, Any]) -> RawJob | None:
    try:
        jid = str(item["id"])
        company = str(item["company_name"])
        title = str(item["title"])
        url = str(item["url"])
        published = str(item["publication_date"])
    except KeyError:
        return None
    posted = datetime.fromisoformat(published.replace("Z", "+00:00"))
    comp_min, comp_max = _parse_salary(item.get("salary"))
    return RawJob(
        source="remotive",
        external_id=jid,
        company=company,
        title=title,
        url=HttpUrl(url),
        posted_at=posted,
        location=str(item.get("candidate_required_location") or "") or None,
        remote=True,
        comp_min=comp_min,
        comp_max=comp_max,
        description_md=str(item.get("description") or "")[:2000] or None,
    )


def parse_payload(payload: dict[str, Any]) -> list[RawJob]:
    items = payload.get("jobs") or []
    return [rj for it in items if (rj := parse_job(it)) is not None]


class RemotiveSource(Source):
    name: ClassVar[str] = "remotive"

    def __init__(self, *, category: str | None = None, timeout: float = 30.0):
        self._category = category
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 shortlist/0.1"},
        )

    def __del__(self) -> None:
        with suppress(Exception):
            self._client.close()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        params = {"category": self._category} if self._category else None
        try:
            resp = self._client.get(_API, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("remotive: fetch failed: %s", e)
            return iter([])
        return iter(parse_payload(resp.json()))
