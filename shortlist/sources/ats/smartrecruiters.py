"""SmartRecruiters public postings client.

Endpoint:
  GET https://api.smartrecruiters.com/v1/companies/{identifier}/postings
        ?limit={page_size}&offset={n}

Returns {offset, limit, totalFound, content: [posting...]}. Paginate by
offset until len(content) < limit.
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
from shortlist.sources._comp import parse_comp_from_text
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://api.smartrecruiters.com/v1/companies"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG_RE.sub("", html.unescape(s)).strip()


def _normalize(job: dict[str, Any], *, company: str) -> RawJob:
    loc = job.get("location") or {}
    location = loc.get("fullLocation") or loc.get("city") or ""
    sections = (job.get("jobAd") or {}).get("sections") or {}
    parts = []
    for key in ("jobDescription", "qualifications", "additionalInformation"):
        text = ((sections.get(key) or {}).get("text") or "").strip()
        if text:
            parts.append(_strip_html(text))
    description_md = "\n\n".join(parts) or None
    comp_min, comp_max = parse_comp_from_text(description_md) if description_md else (None, None)
    return RawJob(
        source="smartrecruiters",
        external_id=str(job["id"]),
        company=company,
        title=job["name"],
        url=job["applyUrl"],
        posted_at=datetime.fromisoformat(job["releasedDate"].replace("Z", "+00:00")),
        location=location or None,
        remote=bool(loc.get("remote")),
        comp_min=comp_min,
        comp_max=comp_max,
        description_md=description_md,
    )


class SmartRecruitersClient:
    def __init__(self, *, timeout: float = 30.0, page_size: int = 100):
        self._client = httpx.Client(timeout=timeout)
        self._page_size = page_size

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

    def fetch_company(self, identifier: str) -> Iterator[dict[str, Any]]:
        offset = 0
        while True:
            try:
                resp = self._get(
                    f"{_BASE}/{identifier}/postings",
                    {"limit": str(self._page_size), "offset": str(offset)},
                )
            except httpx.HTTPStatusError as e:
                logger.warning("smartrecruiters fetch failed for %s: %s", identifier, e)
                return
            if resp.status_code == 404:
                return
            resp.raise_for_status()
            payload = resp.json()
            content = payload.get("content", [])
            if not content:
                return
            yield from content
            total_found = payload.get("totalFound", 0)
            offset += len(content)
            if len(content) < self._page_size or offset >= total_found:
                return


class SmartRecruitersSource(Source):
    name: ClassVar[str] = "smartrecruiters"

    def __init__(
        self,
        *,
        companies: dict[str, str],
        client: SmartRecruitersClient | None = None,
    ):
        self._companies = companies
        self._client = client or SmartRecruitersClient()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        for ident, display in self._companies.items():
            for raw in self._client.fetch_company(ident):
                normalized = _normalize(raw, company=display)
                yield normalized.model_copy(
                    update={"external_id": f"{ident}:{normalized.external_id}"}
                )
