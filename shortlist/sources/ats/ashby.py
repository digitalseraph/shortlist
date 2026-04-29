"""Ashby public job-board API client.

Endpoint:
  GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterator
from contextlib import suppress
from datetime import datetime
from typing import Any, ClassVar

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from shortlist.models import RawJob
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://api.ashbyhq.com/posting-api/job-board"
_TAG_RE = re.compile(r"<[^>]+>")
_COMP_RE = re.compile(r"\$([\d.]+)\s*([km])?\s*[–-]\s*\$?([\d.]+)\s*([km])?", re.IGNORECASE)


def _strip_html(s: str) -> str:
    return _TAG_RE.sub("", html.unescape(s)).strip()


def _is_remote(loc: str) -> bool:
    return "remote" in loc.lower()


def _parse_money(num: str, unit: str | None) -> int:
    v = float(num)
    if unit and unit.lower() == "k":
        v *= 1000
    elif unit and unit.lower() == "m":
        v *= 1_000_000
    return int(v)


def _parse_comp(summary: str | None) -> tuple[int | None, int | None]:
    if not summary:
        return None, None
    m = _COMP_RE.search(summary)
    if not m:
        return None, None
    return _parse_money(m.group(1), m.group(2)), _parse_money(m.group(3), m.group(4))


def _normalize(job: dict[str, Any], *, company: str) -> RawJob:
    location = job.get("location") or ""
    comp_min, comp_max = _parse_comp(job.get("compensationTierSummary"))
    return RawJob(
        source="ashby",
        external_id=str(job["id"]),
        company=company,
        title=job["title"],
        url=job["jobUrl"],
        posted_at=datetime.fromisoformat(job["publishedAt"].replace("Z", "+00:00")),
        location=location or None,
        remote=_is_remote(location),
        comp_min=comp_min,
        comp_max=comp_max,
        description_md=_strip_html(job.get("descriptionHtml") or "") or None,
    )


class AshbyClient:
    def __init__(self, *, timeout: float = 30.0):
        self._client = httpx.Client(timeout=timeout)

    def __del__(self) -> None:
        with suppress(Exception):
            self._client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, params: dict[str, str]) -> httpx.Response:
        resp = self._client.get(url, params=params)
        if resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_company(self, board: str) -> Iterator[dict[str, Any]]:
        try:
            resp = self._get(f"{_BASE}/{board}", {"includeCompensation": "true"})
        except httpx.HTTPStatusError as e:
            logger.warning("ashby fetch failed for %s: %s", board, e)
            return
        if resp.status_code == 404:
            return
        resp.raise_for_status()
        yield from resp.json().get("jobs", [])


class AshbySource(Source):
    name: ClassVar[str] = "ashby"

    def __init__(self, *, companies: dict[str, str], client: AshbyClient | None = None):
        self._companies = companies
        self._client = client or AshbyClient()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        for board, display in self._companies.items():
            for raw in self._client.fetch_company(board):
                normalized = _normalize(raw, company=display)
                yield normalized.model_copy(
                    update={"external_id": f"{board}:{normalized.external_id}"}
                )
