"""Greenhouse Job Boards API client.

Public, unauthenticated. Endpoint:
  GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

`content=true` returns the URL-encoded HTML description with the job, avoiding
a per-job follow-up call.
"""

from __future__ import annotations

import contextlib
import html
import logging
import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any, ClassVar
from urllib.parse import unquote

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

_BASE = "https://boards-api.greenhouse.io/v1/boards"
_TAG_RE = re.compile(r"<[^>]+>")


class GreenhouseClient:
    def __init__(self, *, timeout: float = 30.0):
        self._client = httpx.Client(timeout=timeout)

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
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

    def fetch_company(self, board_token: str) -> Iterator[dict[str, Any]]:
        """Yield raw job dicts for a Greenhouse board.

        Greenhouse returns the full list in one response (no pagination on
        the boards endpoint), but we treat it as an iterator so the calling
        Source can stream-persist."""
        url = f"{_BASE}/{board_token}/jobs"
        try:
            resp = self._get(url, {"content": "true"})
        except httpx.HTTPStatusError as e:
            logger.warning("greenhouse fetch failed for %s: %s", board_token, e)
            return
        if resp.status_code == 404:
            logger.info("greenhouse board not found: %s", board_token)
            return
        resp.raise_for_status()
        payload = resp.json()
        yield from payload.get("jobs", [])


def _strip_html(s: str) -> str:
    return _TAG_RE.sub("", html.unescape(unquote(s))).strip()


def _is_remote(loc: str) -> bool:
    return "remote" in loc.lower()


def _normalize(job: dict[str, Any], *, company: str) -> RawJob:
    location = (job.get("location") or {}).get("name") or ""
    description = _strip_html(job.get("content") or "") or None
    comp_min, comp_max = parse_comp_from_text(description) if description else (None, None)
    return RawJob(
        source="greenhouse",
        external_id=str(job["id"]),
        company=company,
        title=job["title"],
        url=job["absolute_url"],
        posted_at=datetime.fromisoformat(job["updated_at"]),
        location=location or None,
        remote=_is_remote(location),
        comp_min=comp_min,
        comp_max=comp_max,
        description_md=description,
    )


class GreenhouseSource(Source):
    """Pulls jobs from a configured set of Greenhouse boards.

    `companies` maps `board_token -> display_name`. The board token is the
    URL slug (e.g. "acme" in https://boards.greenhouse.io/acme).
    """

    name: ClassVar[str] = "greenhouse"

    def __init__(
        self,
        *,
        companies: dict[str, str],
        client: GreenhouseClient | None = None,
    ):
        self._companies = companies
        self._client = client or GreenhouseClient()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        for token, display in self._companies.items():
            for raw in self._client.fetch_company(token):
                normalized = _normalize(raw, company=display)
                # Make external_id unique across boards: prefix with token.
                yield normalized.model_copy(
                    update={"external_id": f"{token}:{normalized.external_id}"}
                )
