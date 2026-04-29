"""Greenhouse Job Boards API client.

Public, unauthenticated. Endpoint:
  GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

`content=true` returns the URL-encoded HTML description with the job, avoiding
a per-job follow-up call.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

_BASE = "https://boards-api.greenhouse.io/v1/boards"


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
