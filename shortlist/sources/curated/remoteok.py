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
