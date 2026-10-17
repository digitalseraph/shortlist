"""AppliTrack (Frontline) school district job postings.

Public, unauthenticated. Many US school districts post every opening here:
  GET https://www.applitrack.com/{district}/onlineapp/jobpostings/Output.asp?all=1

The response is a script of `document.write('...')` calls that build the
postings list, so the HTML is unwrapped from those calls before parsing.
"""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl

from shortlist.models import RawJob
from shortlist.sources.base import Source

logger = logging.getLogger(__name__)

_BASE = "https://www.applitrack.com"
_WRITE_RE = re.compile(r"document\.write\('((?:[^'\\]|\\.)*)'\)")
_ESCAPE_RE = re.compile(r"\\(.)")
# The "Email To A Friend" text on each posting names the district.
_DISTRICT_RE = re.compile(r"opportunity I found at (.+?)\. The position")


def postings_url(district: str) -> str:
    return f"{_BASE}/{district}/onlineapp/jobpostings/Output.asp?all=1"


def posting_url(district: str, job_id: str) -> str:
    return (
        f"{_BASE}/{district}/onlineapp/default.aspx"
        f"?AppliTrackJobId={job_id}&AppliTrackLayoutMode=detail&AppliTrackViewPosting=1"
    )


def unwrap(script: str) -> str:
    """The HTML written by the script's `document.write` calls."""
    return "".join(_ESCAPE_RE.sub(r"\1", s) for s in _WRITE_RE.findall(script))


def _fields(posting: Tag) -> dict[str, str]:
    """Label -> value for the "Position Type:", "Date Posted:", ... items."""
    out: dict[str, str] = {}
    for li in posting.find_all("li", recursive=False):
        label = li.find("span", class_="label")
        if label is None:
            continue
        values = [s.get_text(strip=True) for s in li.find_all("span", class_="normal")]
        out[label.get_text(strip=True).rstrip(":")] = "".join(values)
    return out


def _posted(text: str) -> datetime:
    try:
        return datetime.strptime(text, "%m/%d/%Y").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def parse_postings(script: str, *, district: str) -> list[RawJob]:
    html = unwrap(script)
    m = _DISTRICT_RE.search(html)
    district_name = m.group(1) if m else district
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawJob] = []
    for posting in soup.select("ul.postingsList"):
        title_el = posting.select_one("td#wrapword")
        id_match = re.fullmatch(r"p(\d+)_", str(posting.get("id") or ""))
        if title_el is None or id_match is None:
            continue
        job_id = id_match.group(1)
        # The list items sit inside a wrapper div, not directly in the ul.
        wrapper = posting.find("div", recursive=False)
        fields = _fields(wrapper) if isinstance(wrapper, Tag) else {}
        school = fields.get("Location", "")
        position_type = fields.get("Position Type", "")
        out.append(
            RawJob(
                source="applitrack",
                external_id=f"{district}:{job_id}",
                company=district_name,
                title=title_el.get_text(strip=True),
                url=HttpUrl(posting_url(district, job_id)),
                posted_at=_posted(fields.get("Date Posted", "")),
                # Schools are named, not placed, so the district name goes in
                # the location: prefs can then keep e.g. "Glynn County".
                location=f"{school}, {district_name}" if school else district_name,
                remote=False,
                description_md=f"Position type: {position_type}" if position_type else None,
            )
        )
    return out


class AppliTrackSource(Source):
    """Pulls postings from a configured set of AppliTrack districts.

    `districts` are the URL codes, e.g. "glynnco" in
    https://www.applitrack.com/glynnco/onlineapp/.
    """

    name: ClassVar[str] = "applitrack"

    def __init__(self, *, districts: list[str], timeout: float = 30.0):
        self._districts = districts
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 shortlist/0.1"},
        )

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()

    def fetch(self, since: datetime | None) -> Iterator[RawJob]:  # noqa: ARG002
        for district in self._districts:
            try:
                resp = self._client.get(postings_url(district))
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("applitrack: fetch failed for %s: %s", district, e)
                continue
            yield from parse_postings(resp.text, district=district)
