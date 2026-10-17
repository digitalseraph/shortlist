"""USAJOBS Search API source: US federal jobs, including DoDEA teaching posts.

API: https://developer.usajobs.gov/api-reference/get-api-search
Needs a free API key. The key and the email it was issued to are read from
the USAJOBS_API_KEY and USAJOBS_EMAIL environment variables, never prefs.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from pydantic import HttpUrl

from shortlist import places
from shortlist.models import RawJob
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_API = "https://data.usajobs.gov/api/search"
KEY_ENV = "USAJOBS_API_KEY"
EMAIL_ENV = "USAJOBS_EMAIL"
_PAGE_SIZE = 500  # the API's maximum
_PER_YEAR = "PA"  # RateIntervalCode for an annual salary

# USAJOBS spells states out ("Brunswick, Georgia"); prefs and the place list
# use "Brunswick, GA", so locations are rewritten to match.
_STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Puerto Rico": "PR", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}  # fmt: skip


def _abbreviate(location: str) -> str:
    city, _, state = location.rpartition(", ")
    return f"{city}, {_STATES[state]}" if city and state in _STATES else location


def _location(d: dict[str, Any]) -> str | None:
    names = [str(p.get("LocationName") or "") for p in d.get("PositionLocation") or []]
    names = [n for n in names if n] or [str(d.get("PositionLocationDisplay") or "")]
    return "; ".join(_abbreviate(n) for n in names if n) or None


def _salary(d: dict[str, Any]) -> tuple[int | None, int | None]:
    for pay in d.get("PositionRemuneration") or []:
        if pay.get("RateIntervalCode") != _PER_YEAR:
            continue
        with contextlib.suppress(KeyError, TypeError, ValueError):
            return int(float(pay["MinimumRange"])), int(float(pay["MaximumRange"]))
    return (None, None)


def parse_item(item: dict[str, Any], *, remote: bool = False) -> RawJob | None:
    d = item.get("MatchedObjectDescriptor") or {}
    try:
        jid = str(item["MatchedObjectId"])
        title = str(d["PositionTitle"])
        url = str(d["PositionURI"])
        posted = datetime.fromisoformat(str(d["PublicationStartDate"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    if posted.tzinfo is None:  # USAJOBS dates are UTC, often without an offset
        posted = posted.replace(tzinfo=UTC)
    comp_min, comp_max = _salary(d)
    summary = ((d.get("UserArea") or {}).get("Details") or {}).get("JobSummary")
    return RawJob(
        source="usajobs",
        external_id=jid,
        company=str(d.get("OrganizationName") or "US federal government"),
        title=title,
        url=HttpUrl(url),
        posted_at=posted,
        location=_location(d),
        remote=remote,
        comp_min=comp_min,
        comp_max=comp_max,
        description_md=str(summary)[:2000] if summary else None,
    )


def parse_payload(payload: dict[str, Any], *, remote: bool = False) -> list[RawJob]:
    items = (payload.get("SearchResult") or {}).get("SearchResultItems") or []
    return [rj for it in items if (rj := parse_item(it, remote=remote)) is not None]


class USAJobsSource(Source):
    name: ClassVar[str] = "usajobs"

    def __init__(
        self,
        *,
        queries: list[str],
        locations: list[str] | None = None,
        timeout: float = 30.0,
    ):
        self._queries = queries
        # No locations means one nationwide search per query.
        self._locations: list[str | None] = list(locations or []) or [None]
        self._client = httpx.Client(timeout=timeout)

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()

    def search_params(self) -> list[dict[str, str]]:
        """Query parameters for every query in every location."""
        out: list[dict[str, str]] = []
        for q in self._queries:
            for loc in self._locations:
                params = {"Keyword": q, "ResultsPerPage": str(_PAGE_SIZE)}
                if loc == places.REMOTE:
                    params["RemoteIndicator"] = "True"
                elif loc:
                    params["LocationName"] = loc
                out.append(params)
        return out

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        key, email = os.environ.get(KEY_ENV), os.environ.get(EMAIL_ENV)
        if not key or not email:
            raise RuntimeError(f"set {KEY_ENV} and {EMAIL_ENV} to search USAJOBS")
        headers = {"Host": "data.usajobs.gov", "User-Agent": email, "Authorization-Key": key}
        return iter(self._fetch_all(headers))

    def _fetch_all(self, headers: dict[str, str]) -> list[RawJob]:
        out: list[RawJob] = []
        for params in self.search_params():
            try:
                resp = self._client.get(_API, params=params, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("usajobs: search failed for %s: %s", params, e)
                continue
            out.extend(parse_payload(resp.json(), remote="RemoteIndicator" in params))
        return out
