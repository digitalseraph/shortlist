"""Lever public postings client.

Endpoint:
  GET https://api.lever.co/v0/postings/{site}?mode=json

Response is a flat JSON array of posting dicts.
"""

from __future__ import annotations

import logging
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
from shortlist.sources._comp import parse_comp_from_text
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://api.lever.co/v0/postings"


def _is_remote(loc: str) -> bool:
    return "remote" in loc.lower()


def _extract_lever_comp(posting: dict[str, Any]) -> tuple[int | None, int | None]:
    """Lever has an optional structured `salaryRange: {min, max, currency}`."""
    sr = posting.get("salaryRange") or {}
    raw_min = sr.get("min")
    raw_max = sr.get("max")
    if isinstance(raw_min, int | float) and isinstance(raw_max, int | float):
        return int(raw_min), int(raw_max)
    if isinstance(raw_min, int | float):
        return int(raw_min), None
    if isinstance(raw_max, int | float):
        return None, int(raw_max)
    return None, None


def _normalize(posting: dict[str, Any], *, company: str) -> RawJob:
    cats = posting.get("categories") or {}
    location = cats.get("location") or ""
    description = (posting.get("descriptionPlain") or "").strip() or None
    comp_min, comp_max = _extract_lever_comp(posting)
    if comp_min is None and comp_max is None and description:
        comp_min, comp_max = parse_comp_from_text(description)
    return RawJob(
        source="lever",
        external_id=str(posting["id"]),
        company=company,
        title=posting["text"],
        url=posting["hostedUrl"],
        posted_at=datetime.fromtimestamp(int(posting["createdAt"]) / 1000, tz=UTC),
        location=location or None,
        remote=_is_remote(location),
        comp_min=comp_min,
        comp_max=comp_max,
        description_md=description,
    )


class LeverClient:
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

    def fetch_company(self, site: str) -> Iterator[dict[str, Any]]:
        try:
            resp = self._get(f"{_BASE}/{site}", {"mode": "json"})
        except httpx.HTTPStatusError as e:
            logger.warning("lever fetch failed for %s: %s", site, e)
            return
        if resp.status_code == 404:
            return
        resp.raise_for_status()
        yield from resp.json()


class LeverSource(Source):
    name: ClassVar[str] = "lever"

    def __init__(self, *, companies: dict[str, str], client: LeverClient | None = None):
        self._companies = companies
        self._client = client or LeverClient()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        for site, display in self._companies.items():
            for raw in self._client.fetch_company(site):
                normalized = _normalize(raw, company=display)
                yield normalized.model_copy(
                    update={"external_id": f"{site}:{normalized.external_id}"}
                )
