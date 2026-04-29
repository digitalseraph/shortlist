"""Workable public widget client.

Endpoint:
  GET https://apply.workable.com/api/v1/widget/accounts/{subdomain}?details=true
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

_BASE = "https://apply.workable.com/api/v1/widget/accounts"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG_RE.sub("", html.unescape(s)).strip()


def _is_remote(loc: str) -> bool:
    return "remote" in loc.lower()


def _normalize(job: dict[str, Any], *, company: str) -> RawJob:
    loc_obj = job.get("location") or {}
    location = loc_obj.get("location_str") or ""
    desc = _strip_html(job.get("description") or "")
    reqs = _strip_html(job.get("requirements") or "")
    description_md = "\n\n".join(p for p in (desc, reqs) if p) or None
    return RawJob(
        source="workable",
        external_id=str(job["shortcode"]),
        company=company,
        title=job["title"],
        url=job["application_url"],
        posted_at=datetime.fromisoformat(job["posted_date"]).replace(tzinfo=UTC),
        location=location or None,
        remote=_is_remote(location),
        description_md=description_md,
    )


class WorkableClient:
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

    def fetch_company(self, subdomain: str) -> Iterator[dict[str, Any]]:
        try:
            resp = self._get(f"{_BASE}/{subdomain}", {"details": "true"})
        except httpx.HTTPStatusError as e:
            logger.warning("workable fetch failed for %s: %s", subdomain, e)
            return
        if resp.status_code == 404:
            return
        resp.raise_for_status()
        yield from resp.json().get("jobs", [])


class WorkableSource(Source):
    name: ClassVar[str] = "workable"

    def __init__(self, *, companies: dict[str, str], client: WorkableClient | None = None):
        self._companies = companies
        self._client = client or WorkableClient()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        for sub, display in self._companies.items():
            for raw in self._client.fetch_company(sub):
                normalized = _normalize(raw, company=display)
                yield normalized.model_copy(
                    update={"external_id": f"{sub}:{normalized.external_id}"}
                )
